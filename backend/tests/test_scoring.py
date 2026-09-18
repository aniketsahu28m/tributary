"""Behavioural tests for the screening engine.

These lock in the judgements that make the system defensible, not the exact
numbers. Weights are expected to change once paired citizen/laboratory data
allows calibration; the *orderings* asserted here should survive that.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import AccessLevel, CitizenObservation, StreamReach
from app.scoring import (
    ObserverHistory,
    observation_confidence,
    one_health_assessment,
    sampling_priority,
    screen,
    visual_pressure_index,
)

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)

FULL_DEGRADED = {
    "water-clarity": 1,
    "odour": 3,
    "sewage-indicators": 3,
    "litter-load": 2,
    "bank-erosion": 2,
    "riparian-vegetation": 1,
    "invasive-plants": 1,
    "foam-scum": 1,
    "flow-condition": 1,
}

FULL_HEALTHY = {
    "water-clarity": 4,
    "odour": 0,
    "sewage-indicators": 0,
    "litter-load": 0,
    "bank-erosion": 0,
    "riparian-vegetation": 4,
    "invasive-plants": 0,
    "foam-scum": 0,
    "flow-condition": 2,
}


def make_reach(**kwargs) -> StreamReach:
    base = dict(
        id="r1",
        name="Test reach",
        water_body="Test stream",
        municipality="Coimbra",
        country="PT",
        latitude=40.2,
        longitude=-8.4,
        access=AccessLevel.RECREATIONAL,
        population_within_500m=4200,
    )
    base.update(kwargs)
    return StreamReach(**base)


def make_obs(scores: dict[str, int], **kwargs) -> CitizenObservation:
    base = dict(
        id="o1", reach_id="r1", observer_id="c1", scores=scores, photo_count=3
    )
    base.update(kwargs)
    return CitizenObservation(**base)


class TestInputBoundary:
    """The observed/laboratory boundary is enforced, not merely documented."""

    def test_rejects_laboratory_codes_from_citizens(self):
        with pytest.raises(ValueError, match="not observed-tier"):
            make_obs({"ibmwp-score": 3})

    def test_rejects_screening_codes_from_citizens(self):
        with pytest.raises(ValueError, match="not observed-tier"):
            make_obs({"visual-pressure-index": 2})

    def test_rejects_out_of_range_scores(self):
        with pytest.raises(ValueError, match=r"\[0, 4\]"):
            make_obs({"odour": 9})

    def test_rejects_empty_submission(self):
        with pytest.raises(ValueError, match="at least one"):
            make_obs({})


class TestVisualPressureIndex:
    def test_healthy_stream_scores_near_zero(self):
        assert visual_pressure_index(make_obs(FULL_HEALTHY)) < 5.0

    def test_degraded_stream_scores_high(self):
        assert visual_pressure_index(make_obs(FULL_DEGRADED)) > 45.0

    def test_litter_alone_does_not_dominate(self):
        """A littered reach with clean water is an amenity problem, not an
        ecological emergency, and must not outrank genuine contamination."""
        littered = dict(FULL_HEALTHY, **{"litter-load": 4})
        assert visual_pressure_index(make_obs(littered)) < 25.0

    def test_selective_reporting_does_not_beat_thorough_reporting(self):
        """The bias this guards against: logging only the two worst fields.

        Renormalising over present fields alone would let a two-field report of
        the worst conditions outscore a full survey of the same reach. Flow is
        held equal so this isolates the effect of coverage.
        """
        cherry_picked = make_obs(
            {"odour": 3, "sewage-indicators": 3, "flow-condition": 1}
        )
        thorough = make_obs(FULL_DEGRADED)
        assert visual_pressure_index(cherry_picked) < visual_pressure_index(
            thorough
        )

    def test_omitting_flow_is_not_advantageous(self):
        """Closing a loophole: an observer at a low-flow reach could otherwise
        skip the flow field to dodge the low-flow discount entirely."""
        reported = make_obs(dict(FULL_DEGRADED, **{"flow-condition": 1}))
        omitted = make_obs(
            {k: v for k, v in FULL_DEGRADED.items() if k != "flow-condition"}
        )
        assert visual_pressure_index(omitted) <= visual_pressure_index(reported)

    def test_sparse_benign_report_does_not_certify_health(self):
        """Two good scores are not evidence that a stream is healthy."""
        sparse = make_obs({"odour": 0, "sewage-indicators": 0})
        assert visual_pressure_index(sparse) > visual_pressure_index(
            make_obs(FULL_HEALTHY)
        )

    def test_low_flow_discounts_apparent_pressure(self):
        """Low flow concentrates pollutants, so identical scores mean less."""
        low = make_obs(dict(FULL_DEGRADED, **{"flow-condition": 1}))
        normal = make_obs(dict(FULL_DEGRADED, **{"flow-condition": 2}))
        assert visual_pressure_index(low) < visual_pressure_index(normal)

    def test_spate_amplifies_apparent_pressure(self):
        """Visible pressure despite dilution is more concerning."""
        spate = make_obs(dict(FULL_DEGRADED, **{"flow-condition": 4}))
        normal = make_obs(dict(FULL_DEGRADED, **{"flow-condition": 2}))
        assert visual_pressure_index(spate) > visual_pressure_index(normal)


class TestConfidence:
    def test_photos_and_completeness_raise_confidence(self):
        thin = make_obs({"odour": 2, "sewage-indicators": 2}, photo_count=0)
        rich = make_obs(FULL_DEGRADED, photo_count=3)
        assert observation_confidence(rich) > observation_confidence(thin)

    def test_internal_contradiction_lowers_confidence(self):
        """Strong sewage evidence with no odour at all is incoherent."""
        coherent = make_obs({"sewage-indicators": 3, "odour": 3})
        contradictory = make_obs({"sewage-indicators": 4, "odour": 0})
        assert observation_confidence(contradictory) < observation_confidence(
            coherent
        )

    def test_corroboration_raises_confidence(self):
        obs = make_obs(FULL_DEGRADED)
        assert observation_confidence(
            obs, corroborating_reports=3
        ) > observation_confidence(obs, corroborating_reports=0)

    def test_new_observer_is_treated_as_neutral(self):
        assert ObserverHistory().reliability == pytest.approx(0.5)

    def test_track_record_shrinks_toward_neutral_when_thin(self):
        """One lucky confirmation must not make someone a trusted observer."""
        thin = ObserverHistory(submissions=1, confirmed_by_expert=1)
        established = ObserverHistory(submissions=40, confirmed_by_expert=38)
        assert thin.reliability < established.reliability
        assert thin.reliability < 0.7

    def test_impossible_history_rejected(self):
        with pytest.raises(ValueError):
            ObserverHistory(submissions=2, confirmed_by_expert=5).reliability


class TestOneHealthEscalation:
    """The core One Health claim: exposure pathway, not contamination alone."""

    def test_contamination_with_public_access_escalates(self):
        result = one_health_assessment(make_obs(FULL_DEGRADED), make_reach())
        assert result.escalate

    def test_identical_contamination_without_access_does_not_escalate(self):
        fenced = make_reach(access=AccessLevel.NONE)
        result = one_health_assessment(make_obs(FULL_DEGRADED), fenced)
        assert not result.escalate
        assert "inaccessible" in result.reason

    def test_clean_water_with_access_does_not_escalate(self):
        result = one_health_assessment(make_obs(FULL_HEALTHY), make_reach())
        assert not result.escalate

    def test_exposure_factor_rises_with_access_level(self):
        obs = make_obs(FULL_DEGRADED)
        levels = [
            AccessLevel.NONE,
            AccessLevel.VISUAL,
            AccessLevel.BANKSIDE,
            AccessLevel.RECREATIONAL,
        ]
        factors = [
            one_health_assessment(obs, make_reach(access=a)).exposure_factor
            for a in levels
        ]
        assert factors == sorted(factors)


class TestSamplingPriority:
    def test_degraded_outranks_healthy(self):
        reach = make_reach()
        high, _ = sampling_priority(
            make_obs(FULL_DEGRADED), reach, confidence=0.8, now=NOW
        )
        low, _ = sampling_priority(
            make_obs(FULL_HEALTHY), reach, confidence=0.8, now=NOW
        )
        assert high > low

    def test_low_confidence_severe_report_outranks_confident_healthy_one(self):
        """Confidence gates but must not dominate: an unreliable report of
        sewage still deserves a look before a trusted report of a clean
        stream."""
        reach = make_reach()
        unreliable_severe, _ = sampling_priority(
            make_obs(FULL_DEGRADED), reach, confidence=0.1, now=NOW
        )
        confident_healthy, _ = sampling_priority(
            make_obs(FULL_HEALTHY), reach, confidence=1.0, now=NOW
        )
        assert unreliable_severe > confident_healthy

    def test_staleness_raises_priority(self):
        reach = make_reach()
        obs = make_obs(FULL_DEGRADED)
        fresh, _ = sampling_priority(
            obs, reach, confidence=0.8, last_expert_sample=NOW, now=NOW
        )
        stale, _ = sampling_priority(
            obs,
            reach,
            confidence=0.8,
            last_expert_sample=NOW - timedelta(days=400),
            now=NOW,
        )
        assert stale > fresh

    def test_never_sampled_is_maximally_stale(self):
        reach = make_reach()
        obs = make_obs(FULL_HEALTHY)
        never, terms_never = sampling_priority(
            obs, reach, confidence=0.8, last_expert_sample=None, now=NOW
        )
        old, terms_old = sampling_priority(
            obs,
            reach,
            confidence=0.8,
            last_expert_sample=NOW - timedelta(days=400),
            now=NOW,
        )
        assert terms_never["sampling_staleness"] == terms_old["sampling_staleness"]

    def test_population_has_diminishing_returns(self):
        """Dense central reaches must not crowd out every peripheral one."""
        obs = make_obs(FULL_DEGRADED)
        _, small = sampling_priority(
            obs, make_reach(population_within_500m=1_000), confidence=0.8, now=NOW
        )
        _, large = sampling_priority(
            obs, make_reach(population_within_500m=10_000), confidence=0.8, now=NOW
        )
        _, huge = sampling_priority(
            obs, make_reach(population_within_500m=50_000), confidence=0.8, now=NOW
        )
        assert small["population_exposed"] < large["population_exposed"]
        assert huge["population_exposed"] == large["population_exposed"]

    def test_terms_sum_to_total(self):
        """The breakdown shown to a monitoring officer must actually explain
        the score."""
        total, terms = sampling_priority(
            make_obs(FULL_DEGRADED), make_reach(), confidence=0.7, now=NOW
        )
        assert sum(terms.values()) == pytest.approx(total, abs=0.05)

    def test_priority_stays_in_range(self):
        worst = make_obs(FULL_DEGRADED)
        total, _ = sampling_priority(
            worst,
            make_reach(population_within_500m=500_000),
            confidence=1.0,
            last_expert_sample=None,
            now=NOW,
        )
        assert 0.0 <= total <= 100.0


class TestScreenPipeline:
    def test_screen_is_consistent_with_its_parts(self):
        obs, reach = make_obs(FULL_DEGRADED), make_reach()
        result = screen(obs, reach, now=NOW)
        assert result.visual_pressure_index == visual_pressure_index(obs)
        assert result.one_health.escalate is True
        assert sum(result.priority_terms.values()) == pytest.approx(
            result.priority, abs=0.05
        )
