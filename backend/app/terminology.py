"""Controlled terminology for urban stream assessment.

Design note
-----------
There is no standard code system for freshwater ecological indicators that a
health information system can consume. LOINC and SNOMED CT cover human clinical
observables; environmental indices such as IBMWP live in ecological literature
and national monitoring protocols, with no interoperable representation.

That gap is the reason this project exists, and it is exactly the gap the
OneAquaHealth policy brief names: environmental, water, urban planning and
health sectors run on fragmented data systems with no shared infrastructure.

We therefore define a local CodeSystem under a project URI, and expose it as a
FHIR CodeSystem resource so downstream systems can resolve our codes. Where an
equivalent concept exists in an established system we record the mapping rather
than inventing a parallel code.

A critical distinction is encoded throughout, in the `tier` field:

  OBSERVED   - a citizen can record this directly from the bank of a stream.
  SCREENED   - derived from OBSERVED values; a triage signal, NOT a WFD metric.
  LABORATORY - requires sampling and expert taxonomy. Never produced by an app.

Conflating these tiers is the most common error in citizen-science tooling and
it is scientifically indefensible: IBMWP requires kick-net sampling and
taxonomic identification to family level, and diatom teratology requires
microscopy of a prepared slide. Neither can be inferred from a phone photo.
This project does not claim otherwise. Its purpose is to make citizen
observations *route expert effort*, not to replace it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

CODE_SYSTEM_URI = "https://oneaquahealth.example.org/fhir/CodeSystem/stream-assessment"
PROFILE_BASE_URI = "https://oneaquahealth.example.org/fhir/StructureDefinition"


class Tier(str, Enum):
    """Evidential tier of an indicator. See module docstring."""

    OBSERVED = "observed"
    SCREENED = "screened"
    LABORATORY = "laboratory"


class WFDStatus(str, Enum):
    """Ecological status classes of the EU Water Framework Directive (2000/60/EC).

    The WFD defines five classes. Member states report status as an Ecological
    Quality Ratio (EQR) in [0, 1], which is then banded into these classes.
    Boundaries are type-specific and nationally calibrated; the values used in
    `eqr_to_status` are the equal-interval defaults and are marked as such.
    """

    HIGH = "high"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"
    BAD = "bad"

    @property
    def display(self) -> str:
        return self.value.capitalize()


@dataclass(frozen=True)
class Concept:
    """A single coded concept in the stream-assessment CodeSystem."""

    code: str
    display: str
    tier: Tier
    definition: str
    unit: str | None = None
    equivalent: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Tier 1: what a citizen can actually see from the bank
#
# Field list follows the OneAquaHealth citizen-science protocol: visible water
# quality, surrounding vegetation, wildlife presence, signs of pollution or
# alteration, clarity, flow, odour, land use, litter, erosion, invasive plants.
# --------------------------------------------------------------------------

OBSERVED_CONCEPTS: tuple[Concept, ...] = (
    Concept(
        code="water-clarity",
        display="Water clarity",
        tier=Tier.OBSERVED,
        definition=(
            "Visual transparency of the water column, scored on an ordinal scale "
            "from 0 (opaque) to 4 (bed clearly visible). A proxy for suspended "
            "solids and turbidity, not a measurement of either."
        ),
        unit="{score}",
    ),
    Concept(
        code="flow-condition",
        display="Flow condition",
        tier=Tier.OBSERVED,
        definition=(
            "Observed hydrological state of the reach, from 0 (dry bed) through "
            "2 (normal perennial flow) to 4 (in spate). Context for every other "
            "indicator: low flow concentrates pollutants and is a confounder."
        ),
        unit="{score}",
    ),
    Concept(
        code="odour",
        display="Detectable odour",
        tier=Tier.OBSERVED,
        definition=(
            "Presence and character of smell at the bank. Sewage or sulphide "
            "odour is a strong lay indicator of organic loading and hypoxia, and "
            "is one of the few pollution signals untrained observers report "
            "reliably."
        ),
        unit="{score}",
    ),
    Concept(
        code="litter-load",
        display="Visible litter load",
        tier=Tier.OBSERVED,
        definition=(
            "Density of anthropogenic debris in the channel and on the banks. "
            "Correlates with urban pressure and with public perception of stream "
            "health, which drives stewardship behaviour."
        ),
        unit="{score}",
    ),
    Concept(
        code="bank-erosion",
        display="Bank erosion",
        tier=Tier.OBSERVED,
        definition=(
            "Extent of visible bank instability, undercutting or bare soil. "
            "A hydromorphological pressure indicator under WFD Annex V."
        ),
        unit="{score}",
    ),
    Concept(
        code="riparian-vegetation",
        display="Riparian vegetation condition",
        tier=Tier.OBSERVED,
        definition=(
            "Continuity and naturalness of bankside vegetation. Intact riparian "
            "buffers moderate temperature, intercept diffuse pollution and "
            "provide habitat; their loss is a primary urban stream pressure."
        ),
        unit="{score}",
    ),
    Concept(
        code="invasive-plants",
        display="Invasive plant presence",
        tier=Tier.OBSERVED,
        definition=(
            "Presence of recognisable invasive alien species on the banks. "
            "Citizen reporting is genuinely valuable here because detection is "
            "largely a matter of coverage, not expertise."
        ),
        unit="{score}",
    ),
    Concept(
        code="sewage-indicators",
        display="Visible sewage indicators",
        tier=Tier.OBSERVED,
        definition=(
            "Sewage fungus, grey-white filamentous growth, surface films or "
            "visible discharge points. Direct evidence of untreated input and "
            "the highest-priority citizen observation for public health triage."
        ),
        unit="{score}",
    ),
    Concept(
        code="foam-scum",
        display="Surface foam or scum",
        tier=Tier.OBSERVED,
        definition=(
            "Persistent foam, oily sheen or algal scum on the surface. "
            "Distinguishing natural from surfactant-driven foam is unreliable "
            "for lay observers, so this contributes weakly to screening and "
            "mainly serves to trigger expert follow-up."
        ),
        unit="{score}",
    ),
)


# --------------------------------------------------------------------------
# Tier 2: screening signals derived from citizen observations
#
# These are OUR constructs. They are explicitly not WFD metrics and must never
# be reported as ecological status.
# --------------------------------------------------------------------------

SCREENED_CONCEPTS: tuple[Concept, ...] = (
    Concept(
        code="visual-pressure-index",
        display="Visual Pressure Index (screening)",
        tier=Tier.SCREENED,
        definition=(
            "Weighted composite of citizen-observable pressures, scaled 0-100. "
            "A triage score for prioritising expert sampling. It is NOT an "
            "Ecological Quality Ratio and carries no WFD reporting status."
        ),
        unit="{score}",
    ),
    Concept(
        code="sampling-priority",
        display="Expert sampling priority",
        tier=Tier.SCREENED,
        definition=(
            "Recommended urgency for professional sampling of this reach, "
            "combining the Visual Pressure Index with observation confidence, "
            "time since last expert sample, and downstream population exposed. "
            "The primary output of this system."
        ),
        unit="{score}",
    ),
    Concept(
        code="observation-confidence",
        display="Observation confidence",
        tier=Tier.SCREENED,
        definition=(
            "Estimated reliability of a single citizen submission, from internal "
            "consistency, photo evidence, observer history and agreement with "
            "nearby contemporaneous reports. Low-confidence records are retained "
            "and flagged, never silently discarded."
        ),
        unit="{score}",
    ),
    Concept(
        code="one-health-flag",
        display="One Health escalation flag",
        tier=Tier.SCREENED,
        definition=(
            "Set when observed conditions indicate plausible human exposure risk "
            "(sewage indicators plus public access plus low flow). This is the "
            "resource that crosses the environment/health boundary and is the "
            "reason these data are expressed as FHIR."
        ),
    ),
)


# --------------------------------------------------------------------------
# Tier 3: laboratory metrics. Represented so that expert results can be carried
# in the same record alongside citizen data, closing the loop.
# --------------------------------------------------------------------------

LABORATORY_CONCEPTS: tuple[Concept, ...] = (
    Concept(
        code="ibmwp-score",
        display="IBMWP score",
        tier=Tier.LABORATORY,
        definition=(
            "Iberian Biological Monitoring Working Party score. Sum of "
            "tolerance values for macroinvertebrate families present in a "
            "kick-net sample. Requires field sampling and taxonomic "
            "identification to family level."
        ),
        unit="{score}",
    ),
    Concept(
        code="diatom-teratology-rate",
        display="Diatom teratology rate",
        tier=Tier.LABORATORY,
        definition=(
            "Proportion of diatom valves showing morphological deformity, per "
            "1000 valves counted under microscopy. The OneAquaHealth policy "
            "brief identifies diatom deformities as an early-warning indicator "
            "of contamination that standard WFD assessment protocols miss."
        ),
        unit="/1000",
    ),
    Concept(
        code="ecological-quality-ratio",
        display="Ecological Quality Ratio",
        tier=Tier.LABORATORY,
        definition=(
            "Observed biological value divided by the type-specific reference "
            "value, in [0, 1]. The quantity WFD ecological status is banded "
            "from. Derived from laboratory biological elements only."
        ),
        unit="1",
    ),
    Concept(
        code="wfd-ecological-status",
        display="WFD ecological status class",
        tier=Tier.LABORATORY,
        definition=(
            "One of High, Good, Moderate, Poor or Bad, per Water Framework "
            "Directive 2000/60/EC Annex V. Reportable status; only ever set "
            "from laboratory-tier evidence."
        ),
    ),
)


ALL_CONCEPTS: tuple[Concept, ...] = (
    OBSERVED_CONCEPTS + SCREENED_CONCEPTS + LABORATORY_CONCEPTS
)

_BY_CODE: dict[str, Concept] = {c.code: c for c in ALL_CONCEPTS}


def concept(code: str) -> Concept:
    """Look up a concept, failing loudly on an unknown code."""
    try:
        return _BY_CODE[code]
    except KeyError:
        raise KeyError(
            f"{code!r} is not in the stream-assessment CodeSystem. "
            f"Known codes: {', '.join(sorted(_BY_CODE))}"
        ) from None


def concepts_in_tier(tier: Tier) -> tuple[Concept, ...]:
    return tuple(c for c in ALL_CONCEPTS if c.tier is tier)


# Equal-interval EQR boundaries. Real boundaries are type-specific and set by
# national intercalibration; these are defaults for demonstration and are
# labelled as such wherever they surface in the API.
_EQR_BANDS: tuple[tuple[float, WFDStatus], ...] = (
    (0.80, WFDStatus.HIGH),
    (0.60, WFDStatus.GOOD),
    (0.40, WFDStatus.MODERATE),
    (0.20, WFDStatus.POOR),
)


def eqr_to_status(eqr: float) -> WFDStatus:
    """Band an Ecological Quality Ratio into a WFD status class.

    Uses equal-interval boundaries. Production use requires the type-specific,
    nationally intercalibrated boundaries for the water body in question.
    """
    if not 0.0 <= eqr <= 1.0:
        raise ValueError(f"EQR must lie in [0, 1], got {eqr}")
    for threshold, status in _EQR_BANDS:
        if eqr >= threshold:
            return status
    return WFDStatus.BAD
