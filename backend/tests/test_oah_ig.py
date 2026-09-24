"""Conformance with the official OneAquaHealth HL7 FHIR Implementation Guide.

These tests guard claims made to reviewers. Asserting conformance we do not
have would be worse than not conforming, so the negative cases here matter as
much as the positive ones.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import api
from app.fhir_mapping import (
    citizen_observation_to_fhir,
    expert_sample_to_fhir,
    reach_to_location,
)
from app.models import AccessLevel, CitizenObservation, ExpertSample, StreamReach
from app.oah_ig import (
    MAPPINGS,
    OAH_CODE_SYSTEM,
    PROFILE_LOCATION,
    PROFILE_OBSERVATION,
    Equivalence,
    build_concept_map,
    oah_code_for,
    unmatched_concepts,
)
from app.store import seeded_store
from app.terminology import ALL_CONCEPTS, CODE_SYSTEM_URI


@pytest.fixture
def client() -> TestClient:
    api.store = seeded_store()
    return TestClient(api.app)


def make_reach() -> StreamReach:
    return StreamReach(
        id="coselhas-03",
        name="Coselhas reach 3",
        water_body="Ribeira de Coselhas",
        municipality="Coimbra",
        country="PT",
        latitude=40.2216,
        longitude=-8.4194,
        access=AccessLevel.RECREATIONAL,
        population_within_500m=4200,
    )


def make_sample() -> ExpertSample:
    return ExpertSample(
        id="lab-001",
        reach_id="coselhas-03",
        sampled_at=datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc),
        laboratory="MARE-UC",
        ibmwp_score=41,
        diatom_teratology_rate=12.4,
        ecological_quality_ratio=0.38,
    )


class TestLocationOahConformance:
    """LocationOah requires identifier 1.., name 1.., mode = #instance."""

    def test_asserts_the_profile(self):
        assert reach_to_location(make_reach()).meta.profile == [PROFILE_LOCATION]

    def test_identifier_is_present(self):
        location = reach_to_location(make_reach())
        assert location.identifier
        assert location.identifier[0].value

    def test_mode_is_instance(self):
        assert reach_to_location(make_reach()).mode == "instance"

    def test_position_carries_both_coordinates(self):
        """The profile makes latitude and longitude 1..1 when position exists."""
        position = reach_to_location(make_reach()).position
        assert position.latitude is not None
        assert position.longitude is not None


class TestObservationIndicatorsOahConformance:
    def test_laboratory_results_assert_the_profile(self):
        for observation in expert_sample_to_fhir(make_sample()):
            assert observation.meta.profile == [PROFILE_OBSERVATION]

    def test_laboratory_results_are_final(self):
        """The profile fixes status = #final."""
        for observation in expert_sample_to_fhir(make_sample()):
            assert observation.status == "final"

    def test_subject_is_a_location(self):
        """`subject only Reference(LocationOah)` — the constraint we reached
        independently before finding the IG."""
        for observation in expert_sample_to_fhir(make_sample()):
            assert observation.subject.reference.startswith("Location/")

    def test_performer_is_present(self):
        """`performer 1..`"""
        for observation in expert_sample_to_fhir(make_sample()):
            assert observation.performer

    def test_citizen_observations_do_not_claim_the_profile(self):
        """The important negative case.

        Citizen evidence is unverified, and the profile fixes status=final.
        Asserting conformance anyway would let a downstream system treat a
        stranger's phone report as a laboratory result.
        """
        observation = citizen_observation_to_fhir(
            CitizenObservation(
                id="obs-1",
                reach_id="coselhas-03",
                observer_id="cit-1",
                scores={"odour": 3, "sewage-indicators": 2},
            ),
            confidence=0.7,
        )
        assert observation.status == "preliminary"
        profiles = observation.meta.profile if observation.meta else []
        assert PROFILE_OBSERVATION not in (profiles or [])


class TestTerminologyMapping:
    def test_mapped_concepts_carry_both_codings(self):
        """A CodeableConcept is several codings for the same concept, so the
        IG's code travels beside ours rather than replacing it."""
        teratology = [
            o
            for o in expert_sample_to_fhir(make_sample())
            if o.id.endswith("teratology")
        ][0]
        systems = {c.system for c in teratology.code.coding}
        assert CODE_SYSTEM_URI in systems
        assert OAH_CODE_SYSTEM in systems

    def test_unmatched_concepts_emit_only_our_coding(self):
        """EQR has no IG equivalent, so no OAH coding may be invented for it."""
        eqr = [
            o for o in expert_sample_to_fhir(make_sample()) if o.id.endswith("eqr")
        ][0]
        assert {c.system for c in eqr.code.coding} == {CODE_SYSTEM_URI}

    def test_exact_matches_are_marked_equivalent(self):
        by_source = {m.source: m for m in MAPPINGS}
        assert by_source["diatom-teratology-rate"].equivalence is (
            Equivalence.EQUIVALENT
        )
        assert by_source["riparian-vegetation"].equivalence is (
            Equivalence.EQUIVALENT
        )

    def test_clarity_is_related_not_narrower(self):
        """Visual clarity is a proxy for suspended solids, not a measurement of
        them. Marking it `narrower` would license treating an ordinal score as
        a TSS value."""
        by_source = {m.source: m for m in MAPPINGS}
        assert by_source["water-clarity"].equivalence is Equivalence.RELATEDTO

    def test_unmatched_mappings_have_no_target(self):
        for mapping in unmatched_concepts():
            assert mapping.target is None
            assert mapping.comment.strip()

    def test_oah_code_for_returns_nothing_when_unmatched(self):
        assert oah_code_for("sewage-indicators") is None
        assert oah_code_for("litter-load") is None

    def test_every_mapping_names_a_real_local_concept(self):
        known = {c.code for c in ALL_CONCEPTS}
        for mapping in MAPPINGS:
            assert mapping.source in known, f"{mapping.source} is not our concept"

    def test_every_mapping_carries_a_reason(self):
        for mapping in MAPPINGS:
            assert mapping.comment.strip(), f"{mapping.source} has no comment"


class TestConceptMapResource:
    def test_is_a_well_formed_concept_map(self):
        cm = build_concept_map()
        assert cm["resourceType"] == "ConceptMap"
        assert cm["sourceUri"] == CODE_SYSTEM_URI
        assert cm["targetUri"] == OAH_CODE_SYSTEM

    def test_covers_every_mapping(self):
        cm = build_concept_map()
        codes = {e["code"] for e in cm["group"][0]["element"]}
        assert codes == {m.source for m in MAPPINGS}

    def test_uses_real_fhir_equivalence_codes(self):
        """Not a home-made confidence label: a terminology server can act on
        these."""
        legal = {e.value for e in Equivalence}
        for element in build_concept_map()["group"][0]["element"]:
            for target in element["target"]:
                assert target["equivalence"] in legal

    def test_unmatched_elements_have_no_target_code(self):
        cm = build_concept_map()
        for element in cm["group"][0]["element"]:
            for target in element["target"]:
                if target["equivalence"] == "unmatched":
                    assert "code" not in target


class TestConformanceEndpoints:
    def test_concept_map_is_served(self, client):
        body = client.get("/fhir/ConceptMap/tributary-to-oah").json()
        assert body["resourceType"] == "ConceptMap"

    def test_conformance_statement_lists_both_sides(self, client):
        body = client.get("/api/ig-conformance").json()
        assert body["conforms"]
        assert body["cannotConform"], (
            "the citizen-evidence gap must be stated, not quietly omitted"
        )
        assert body["unmatchedConcepts"]
        assert "status" in body["proposedIgChange"]

    def test_served_location_asserts_the_profile(self, client):
        body = client.get("/fhir/Location/coselhas-03").json()
        assert PROFILE_LOCATION in body["meta"]["profile"]

    def test_served_laboratory_observation_asserts_the_profile(self, client):
        body = client.get("/fhir/Observation/lab-001-ibmwp").json()
        assert PROFILE_OBSERVATION in body["meta"]["profile"]

    def test_served_citizen_observation_does_not(self, client):
        body = client.get("/fhir/Observation/obs-001").json()
        profiles = body.get("meta", {}).get("profile", [])
        assert PROFILE_OBSERVATION not in profiles
