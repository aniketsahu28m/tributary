"""Screening engine: from citizen observations to expert sampling priority.

The problem this solves
-----------------------
Professional stream monitoring is expensive and therefore sparse. A municipal
laboratory might sample a given urban reach once or twice a year. Citizen
observers are numerous and frequent but cannot produce Water Framework
Directive metrics.

The useful question is therefore not "can citizens replace experts" (they
cannot) but "can citizen observation tell experts where to spend their next
sampling visit". That is the question this module answers, and it is why
`sampling-priority` rather than any ecological score is the system's headline
output.

Every weight below is a stated, inspectable judgement rather than a fitted
parameter. With no labelled training data linking citizen scores to laboratory
outcomes, fitting a model would produce false precision; the honest design is
transparent weights that a freshwater ecologist can disagree with explicitly.
Once enough paired citizen/laboratory records exist, `calibrate.py` can replace
these with fitted values — the interface is built for that, and the weights are
deliberately isolated here to make the swap a one-file change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import SCORE_MAX, AccessLevel, CitizenObservation, StreamReach

# --------------------------------------------------------------------------
# Visual Pressure Index
#
# Weights express how strongly a citizen-observable condition indicates real
# ecological pressure. They encode three ideas:
#
#   * Direct evidence of untreated input outranks everything else. Sewage
#     fungus and sewage odour are the two signals lay observers report most
#     reliably and that most directly imply a discharge.
#   * Aesthetic pressure is real but weaker evidence. Litter tracks urban
#     pressure and drives public perception, but a clean-looking stream can be
#     chemically degraded and a littered one can be ecologically functional.
#   * Signals a lay observer cannot reliably discriminate get low weight.
#     Natural foam from dissolved organic carbon looks much like surfactant
#     foam; that ambiguity belongs in the weight, not hidden in a threshold.
#
# `inverted` marks fields where a HIGH score means a HEALTHIER stream, so the
# pressure contribution is (SCORE_MAX - score) instead of score.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PressureWeight:
    weight: float
    inverted: bool = False
    rationale: str = ""


PRESSURE_WEIGHTS: dict[str, PressureWeight] = {
    "sewage-indicators": PressureWeight(
        weight=3.0,
        rationale=(
            "Sewage fungus or a visible discharge is direct evidence of "
            "untreated input and the strongest single lay observation."
        ),
    ),
    "odour": PressureWeight(
        weight=2.5,
        rationale=(
            "Sulphide or sewage odour indicates organic loading and hypoxia. "
            "Reported reliably because it needs no training to notice."
        ),
    ),
    "water-clarity": PressureWeight(
        weight=2.0,
        inverted=True,
        rationale=(
            "Turbidity proxy. Inverted: clear water scores high, low pressure. "
            "Weaker than it appears, since clear water can carry dissolved "
            "contaminants and some streams are naturally peat-stained."
        ),
    ),
    "riparian-vegetation": PressureWeight(
        weight=1.5,
        inverted=True,
        rationale=(
            "Intact bankside vegetation moderates temperature and intercepts "
            "diffuse pollution. Its loss is a primary urban stream pressure "
            "under WFD Annex V hydromorphology."
        ),
    ),
    "bank-erosion": PressureWeight(
        weight=1.5,
        rationale="Hydromorphological degradation; visible and fairly objective.",
    ),
    "litter-load": PressureWeight(
        weight=1.0,
        rationale=(
            "Tracks urban pressure and strongly shapes public perception, but "
            "is weak evidence of ecological condition on its own."
        ),
    ),
    "invasive-plants": PressureWeight(
        weight=1.0,
        rationale=(
            "Genuine ecological pressure, and citizen detection is largely a "
            "matter of coverage rather than expertise."
        ),
    ),
    "foam-scum": PressureWeight(
        weight=0.5,
        rationale=(
            "Deliberately low: lay observers cannot reliably separate natural "
            "from surfactant-driven foam. Serves mainly to trigger follow-up."
        ),
    ),
}

# `flow-condition` is intentionally absent above. It is not a pressure — it is
# a confounder. See `_flow_modifier`.

VPI_SCALE_MAX = 100.0


def _flow_modifier(scores: dict[str, int]) -> float:
    """Multiplier accounting for flow state as a confounder, not a pressure.

    Low flow concentrates any pollutant present and makes visual pressure look
    worse than the underlying condition warrants, so observations at low flow
    carry a mild discount. High flow dilutes and hides, so a stream that looks
    bad *in spate* is more concerning than the raw scores suggest.

    A dry bed is a special case: pressure scores are close to meaningless, and
    the reach should be assessed on return of flow.

    When flow is not reported, the low-flow discount is applied rather than a
    neutral one. This enforces a design invariant the whole system depends on:
    **withholding an observation must never improve the resulting score.** A
    neutral default would be strictly better than honestly reporting low flow,
    which hands observers a reason to leave the field blank. Taking the least
    favourable plausible value instead removes that incentive, and is
    substantively reasonable — an observer who did not record flow may well
    have been standing at a reach where pressure was concentrated by it.
    """
    flow = scores.get("flow-condition")
    if flow is None:
        return 0.85
    return {
        0: 0.50,  # dry bed - visual assessment barely meaningful
        1: 0.85,  # low flow - pollution concentrated, discount slightly
        2: 1.00,  # normal perennial flow - the reference condition
        3: 1.10,  # elevated
        4: 1.20,  # in spate - dilution means visible pressure understates
    }.get(flow, 1.0)


# Typical pressure for an urban stream reach, on the VPI scale. Used as the
# prior that sparse submissions are shrunk toward. Urban streams are degraded
# more often than not, so the neutral value sits above the midpoint.
VPI_NEUTRAL_PRIOR = 35.0

# Fraction of total available evidence weight below which shrinkage bites.
# At full coverage there is no shrinkage at all.
COVERAGE_FOR_FULL_TRUST = 0.75

# Flow contributes no pressure of its own, but a submission that omits it is
# less complete evidence — and without this term, omitting flow would be
# strictly advantageous to an observer whose stream is in low flow, since the
# low-flow discount would simply not apply. Coverage accounting therefore
# includes flow even though the index does not.
_FLOW_COVERAGE_WEIGHT = 1.5

_TOTAL_COVERAGE_WEIGHT = (
    sum(w.weight for w in PRESSURE_WEIGHTS.values()) + _FLOW_COVERAGE_WEIGHT
)


def visual_pressure_index(obs: CitizenObservation) -> float:
    """Composite pressure signal in [0, 100]. A triage score, NOT an EQR.

    Partial submissions are renormalised over the weights actually present, so
    that an observer who could not assess every field is not penalised for the
    fields they left out.

    Renormalisation alone, however, creates a selective-reporting bias: an
    observer who records only the two worst things they can see produces a
    higher index than one who patiently scores all eight, because the good news
    never enters the denominator. That is a real failure mode in citizen
    science, and it is usually innocent — people report what stands out.

    The index is therefore shrunk toward a neutral prior in proportion to how
    little of the available evidence weight the submission covers. A sparse
    report moves the number a little; a thorough one moves it a lot. This is
    the same shrinkage principle used for observer reliability, applied to
    evidence coverage rather than track record.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for code, score in obs.scores.items():
        spec = PRESSURE_WEIGHTS.get(code)
        if spec is None:  # flow-condition, handled as a modifier
            continue
        raw = (SCORE_MAX - score) if spec.inverted else score
        weighted_sum += spec.weight * raw
        total_weight += spec.weight

    if total_weight == 0.0:
        return 0.0

    normalised = weighted_sum / (total_weight * SCORE_MAX)
    raw_index = normalised * VPI_SCALE_MAX * _flow_modifier(obs.scores)

    covered = total_weight + (
        _FLOW_COVERAGE_WEIGHT if "flow-condition" in obs.scores else 0.0
    )
    coverage = covered / _TOTAL_COVERAGE_WEIGHT
    trust = min(coverage / COVERAGE_FOR_FULL_TRUST, 1.0)

    shrunk = trust * raw_index + (1.0 - trust) * VPI_NEUTRAL_PRIOR
    return round(min(shrunk, VPI_SCALE_MAX), 1)


# --------------------------------------------------------------------------
# Observation confidence
# --------------------------------------------------------------------------

# Pairs that should move together. A submission asserting one strongly while
# denying the other is internally inconsistent, which usually means a
# misunderstood question rather than a dishonest observer — so such records are
# flagged for review, never discarded.
_COHERENT_PAIRS: tuple[tuple[str, str], ...] = (
    ("sewage-indicators", "odour"),
    ("water-clarity", "litter-load"),  # inverted pair, handled below
)

_INVERTED_PAIR = {("water-clarity", "litter-load")}


def _coherence(scores: dict[str, int]) -> float:
    """How internally consistent a submission is, in [0, 1]."""
    checked = 0
    penalty = 0.0

    for a, b in _COHERENT_PAIRS:
        if a not in scores or b not in scores:
            continue
        checked += 1
        sa, sb = scores[a], scores[b]
        if (a, b) in _INVERTED_PAIR:
            sb = SCORE_MAX - sb
        divergence = abs(sa - sb) / SCORE_MAX
        # Small divergence is normal; only a strong contradiction is penalised.
        if divergence > 0.5:
            penalty += divergence - 0.5

    if checked == 0:
        return 0.85  # nothing to check against; neither trusted nor doubted
    return max(0.0, 1.0 - penalty / checked)


@dataclass(frozen=True)
class ObserverHistory:
    """Track record of a citizen observer.

    Deliberately thin: agreement rate with subsequent expert sampling is the
    only signal that actually evidences reliability. Submission count alone
    measures enthusiasm, not accuracy, so it only lends weight to the
    agreement rate rather than raising confidence by itself.
    """

    submissions: int = 0
    confirmed_by_expert: int = 0

    @property
    def reliability(self) -> float:
        """Agreement rate, shrunk toward 0.5 when the sample is small.

        With few observations there is not enough evidence to call someone
        reliable or unreliable, so the estimate is pulled toward neutral. The
        prior strength of 5 means roughly five expert confirmations are needed
        before a track record meaningfully moves the number.
        """
        prior_strength = 5.0
        if self.confirmed_by_expert > self.submissions:
            raise ValueError("confirmed_by_expert cannot exceed submissions")
        return (self.confirmed_by_expert + 0.5 * prior_strength) / (
            self.submissions + prior_strength
        )


def observation_confidence(
    obs: CitizenObservation,
    *,
    history: ObserverHistory | None = None,
    corroborating_reports: int = 0,
) -> float:
    """Reliability of a single submission, in [0, 1].

    Low-confidence records are retained and flagged, never silently dropped:
    discarding inconvenient citizen data destroys the trust the whole citizen
    science model depends on, and a cluster of "unreliable" reports from one
    neighbourhood is itself a signal worth seeing.
    """
    completeness = len(obs.scores) / len(PRESSURE_WEIGHTS)
    coherence = _coherence(obs.scores)
    photo_support = min(obs.photo_count, 3) / 3.0
    reliability = history.reliability if history else 0.5
    corroboration = min(corroborating_reports, 3) / 3.0

    score = (
        0.30 * coherence
        + 0.20 * min(completeness, 1.0)
        + 0.20 * photo_support
        + 0.15 * reliability
        + 0.15 * corroboration
    )
    return round(min(max(score, 0.0), 1.0), 3)


# --------------------------------------------------------------------------
# One Health escalation
# --------------------------------------------------------------------------

_EXPOSURE_WEIGHT: dict[AccessLevel, float] = {
    AccessLevel.NONE: 0.0,
    AccessLevel.VISUAL: 0.2,
    AccessLevel.BANKSIDE: 0.6,
    AccessLevel.RECREATIONAL: 1.0,
}

SEWAGE_ESCALATION_THRESHOLD = 2


@dataclass(frozen=True)
class OneHealthAssessment:
    """Whether observed conditions imply a plausible human exposure pathway."""

    escalate: bool
    exposure_factor: float
    reason: str


def one_health_assessment(
    obs: CitizenObservation, reach: StreamReach
) -> OneHealthAssessment:
    """Decide whether this observation crosses into a human health concern.

    Contamination alone is an environmental matter. It becomes a One Health
    matter when there is a pathway to people — which is a property of the
    place, not the pollutant. A degraded culverted reach behind a fence and an
    identically degraded reach where children paddle warrant different
    responses, and only the second belongs in a health system's inbox.
    """
    exposure = _EXPOSURE_WEIGHT[reach.access]
    sewage = obs.scores.get("sewage-indicators", 0)
    odour = obs.scores.get("odour", 0)
    flow = obs.scores.get("flow-condition", 2)

    contamination = sewage >= SEWAGE_ESCALATION_THRESHOLD or (
        odour >= 3 and sewage >= 1
    )

    if not contamination:
        return OneHealthAssessment(
            escalate=False,
            exposure_factor=exposure,
            reason="No sewage or strong-odour evidence reported.",
        )
    if exposure == 0.0:
        return OneHealthAssessment(
            escalate=False,
            exposure_factor=0.0,
            reason=(
                "Contamination indicators present, but the reach is "
                "inaccessible to the public: environmental follow-up only."
            ),
        )

    concentrated = flow <= 1
    return OneHealthAssessment(
        escalate=True,
        exposure_factor=exposure,
        reason=(
            f"Contamination indicators at a reach with {reach.access.value} "
            f"public access"
            + (", during low flow" if concentrated else "")
            + f"; approximately {reach.population_within_500m:,} residents "
            f"within 500 m."
        ),
    )


# --------------------------------------------------------------------------
# Sampling priority: the system's headline output
# --------------------------------------------------------------------------

STALENESS_SATURATION_DAYS = 365


def _staleness(last_expert_sample: datetime | None, *, now: datetime) -> float:
    """How overdue a reach is for expert sampling, in [0, 1]."""
    if last_expert_sample is None:
        return 1.0
    days = (now - last_expert_sample).total_seconds() / 86400.0
    return min(max(days, 0.0) / STALENESS_SATURATION_DAYS, 1.0)


def _population_factor(population: int) -> float:
    """Diminishing-returns weighting of exposed population.

    Linear population weighting would let dense city-centre reaches crowd out
    every peripheral one. A square-root-like curve keeps population relevant
    without making it decisive, saturating around 10,000 residents.
    """
    return min((population / 10_000.0) ** 0.5, 1.0)


def sampling_priority(
    obs: CitizenObservation,
    reach: StreamReach,
    *,
    confidence: float,
    last_expert_sample: datetime | None = None,
    now: datetime | None = None,
) -> tuple[float, dict[str, float]]:
    """Recommended urgency of professional sampling, in [0, 100].

    Returns the score together with the contribution of each term, because a
    monitoring officer deciding where to send a van is entitled to know why
    the system ranked one reach above another. An unexplainable priority queue
    would not survive contact with a real municipal laboratory.
    """
    now = now or datetime.now(timezone.utc)

    vpi = visual_pressure_index(obs)
    one_health = one_health_assessment(obs, reach)
    staleness = _staleness(last_expert_sample, now=now)
    population = _population_factor(reach.population_within_500m)

    # Confidence gates rather than dominates: a low-confidence report of severe
    # pollution should still rank above a high-confidence report of a healthy
    # stream, so its floor is 0.4 rather than 0.
    confidence_gate = 0.4 + 0.6 * confidence

    base = (vpi / VPI_SCALE_MAX) * confidence_gate

    terms = {
        "visual_pressure": round(base * 55.0, 2),
        "one_health_escalation": round(
            25.0 * one_health.exposure_factor if one_health.escalate else 0.0, 2
        ),
        "sampling_staleness": round(staleness * 12.0, 2),
        "population_exposed": round(population * 8.0, 2),
    }
    total = round(min(sum(terms.values()), 100.0), 1)
    return total, terms


@dataclass(frozen=True)
class ScreeningResult:
    """Everything the screening engine derives from one submission."""

    visual_pressure_index: float
    confidence: float
    one_health: OneHealthAssessment
    priority: float
    priority_terms: dict[str, float]


def screen(
    obs: CitizenObservation,
    reach: StreamReach,
    *,
    history: ObserverHistory | None = None,
    corroborating_reports: int = 0,
    last_expert_sample: datetime | None = None,
    now: datetime | None = None,
) -> ScreeningResult:
    """Run the full screening pipeline for a single citizen observation."""
    confidence = observation_confidence(
        obs, history=history, corroborating_reports=corroborating_reports
    )
    priority, terms = sampling_priority(
        obs,
        reach,
        confidence=confidence,
        last_expert_sample=last_expert_sample,
        now=now,
    )
    return ScreeningResult(
        visual_pressure_index=visual_pressure_index(obs),
        confidence=confidence,
        one_health=one_health_assessment(obs, reach),
        priority=priority,
        priority_terms=terms,
    )
