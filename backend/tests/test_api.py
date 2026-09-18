"""API tests, covering both surfaces.

The FHIR tests assert on structure that external systems depend on, which is
the part that must not drift. The dashboard tests assert on behaviour the UI
relies on, which may change more freely.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import api
from app.store import seeded_store


@pytest.fixture
def client() -> TestClient:
    """A client over a freshly seeded store.

    The store is module-level global state, so tests that POST would otherwise
    leak into one another and make failures order-dependent.
    """
    api.store = seeded_store()
    return TestClient(api.app)


class TestPriorityQueue:
    def test_exposure_outranks_raw_pollution(self):
        """The central claim, asserted end to end.

        The culverted reach is the most visibly polluted stretch in the seed
        data. It must still rank below a less polluted reach where the public
        can reach the water, because priority is about where sampling effort
        buys the most, not about which stream looks worst.
        """
        api.store = seeded_store()
        client = TestClient(api.app)
        rows = client.get("/api/priority-queue").json()

        by_id = {r["reach"]["id"]: r for r in rows}
        accessible = by_id["coselhas-03"]
        culverted = by_id["coselhas-07"]

        assert (
            culverted["screening"]["visualPressureIndex"]
            > accessible["screening"]["visualPressureIndex"]
        )
        assert (
            accessible["screening"]["priority"]
            > culverted["screening"]["priority"]
        )

    def test_queue_is_sorted_by_priority(self, client):
        rows = client.get("/api/priority-queue").json()
        priorities = [r["screening"]["priority"] for r in rows]
        assert priorities == sorted(priorities, reverse=True)

    def test_one_row_per_reach(self, client):
        """Two reports of the same reach must not occupy two rows."""
        rows = client.get("/api/priority-queue").json()
        ids = [r["reach"]["id"] for r in rows]
        assert len(ids) == len(set(ids))

    def test_terms_explain_the_score(self, client):
        for row in client.get("/api/priority-queue").json():
            screening = row["screening"]
            assert sum(screening["priorityTerms"].values()) == pytest.approx(
                screening["priority"], abs=0.05
            )


class TestEscalations:
    def test_only_escalated_rows_appear(self, client):
        for row in client.get("/api/escalations").json():
            assert row["screening"]["oneHealth"]["escalate"] is True

    def test_inaccessible_reach_is_not_escalated(self, client):
        ids = {r["reach"]["id"] for r in client.get("/api/escalations").json()}
        assert "coselhas-07" not in ids

    def test_escalation_carries_a_human_readable_reason(self, client):
        rows = client.get("/api/escalations").json()
        assert rows, "seed data should produce at least one escalation"
        for row in rows:
            assert row["screening"]["oneHealth"]["reason"].strip()


class TestSubmission:
    def test_rejects_laboratory_tier_code(self, client):
        response = client.post(
            "/api/observations",
            json={
                "id": "bad-1",
                "reach_id": "ceira-01",
                "observer_id": "cit-x",
                "scores": {"ibmwp-score": 3},
            },
        )
        assert response.status_code == 422

    def test_rejects_out_of_range_score(self, client):
        response = client.post(
            "/api/observations",
            json={
                "id": "bad-2",
                "reach_id": "ceira-01",
                "observer_id": "cit-x",
                "scores": {"odour": 11},
            },
        )
        assert response.status_code == 422

    def test_rejects_unknown_reach(self, client):
        response = client.post(
            "/api/observations",
            json={
                "id": "bad-3",
                "reach_id": "does-not-exist",
                "observer_id": "cit-x",
                "scores": {"odour": 1},
            },
        )
        assert response.status_code == 404

    def test_accepts_and_screens_a_valid_submission(self, client):
        response = client.post(
            "/api/observations",
            json={
                "id": "new-1",
                "reach_id": "ceira-01",
                "observer_id": "cit-x",
                "scores": {
                    "sewage-indicators": 3,
                    "odour": 3,
                    "water-clarity": 1,
                    "flow-condition": 1,
                },
                "photo_count": 2,
            },
        )
        assert response.status_code == 200
        screening = response.json()["screening"]
        assert screening["oneHealth"]["escalate"] is True
        assert screening["priority"] > 0


class TestFhirSurface:
    def test_capability_statement_declares_r4b(self, client):
        body = client.get("/fhir/metadata").json()
        assert body["resourceType"] == "CapabilityStatement"
        assert body["fhirVersion"] == "4.3.0"

    def test_code_system_publishes_every_concept(self, client):
        body = client.get("/fhir/CodeSystem/stream-assessment").json()
        assert body["resourceType"] == "CodeSystem"
        assert body["count"] == len(body["concept"])
        # Every concept must declare its evidential tier, or a consumer cannot
        # tell a citizen screening score from a WFD determination.
        for concept in body["concept"]:
            tiers = [
                p["valueCode"]
                for p in concept["property"]
                if p["code"] == "tier"
            ]
            assert tiers, f"{concept['code']} has no tier property"

    def test_location_has_geographic_position(self, client):
        body = client.get("/fhir/Location/coselhas-03").json()
        assert body["resourceType"] == "Location"
        assert "latitude" in body["position"]
        assert "longitude" in body["position"]

    def test_citizen_observation_is_preliminary_on_a_location(self, client):
        body = client.get("/fhir/Observation/obs-001").json()
        assert body["resourceType"] == "Observation"
        assert body["status"] == "preliminary"
        assert body["subject"]["reference"] == "Location/coselhas-03"

    def test_laboratory_observation_is_final(self, client):
        body = client.get("/fhir/Observation/lab-001-ibmwp").json()
        assert body["status"] == "final"

    def test_status_partitions_citizen_from_laboratory_evidence(self, client):
        """The whole tiering scheme, checked through the FHIR surface."""
        everything = client.get("/fhir/Observation").json()
        preliminary = client.get(
            "/fhir/Observation", params={"status": "preliminary"}
        ).json()
        final = client.get(
            "/fhir/Observation", params={"status": "final"}
        ).json()

        assert preliminary["total"] + final["total"] == everything["total"]
        assert preliminary["total"] > 0 and final["total"] > 0

    def test_search_returns_a_searchset_bundle(self, client):
        body = client.get("/fhir/Observation").json()
        assert body["resourceType"] == "Bundle"
        assert body["type"] == "searchset"
        assert body["total"] == len(body["entry"])

    def test_subject_accepts_bare_id_and_reference_form(self, client):
        """Both forms occur in the wild; rejecting one buys nothing."""
        bare = client.get(
            "/fhir/Observation", params={"subject": "coselhas-03"}
        ).json()
        reference = client.get(
            "/fhir/Observation", params={"subject": "Location/coselhas-03"}
        ).json()
        assert bare["total"] == reference["total"] > 0

    def test_search_rejects_unknown_subject(self, client):
        response = client.get(
            "/fhir/Observation", params={"subject": "Location/nope"}
        )
        assert response.status_code == 404

    def test_confidence_travels_as_an_extension(self, client):
        body = client.get("/fhir/Observation/obs-001").json()
        urls = {e["url"] for e in body["extension"]}
        assert any(u.endswith("observation-confidence") for u in urls)
        assert any(u.endswith("evidential-tier") for u in urls)

    def test_unknown_observation_is_404(self, client):
        assert client.get("/fhir/Observation/nope").status_code == 404


class TestIndicatorCatalogue:
    def test_tiers_are_exposed_for_the_ui(self, client):
        tiers = client.get("/api/indicators").json()["tiers"]
        assert set(tiers) == {"observed", "screened", "laboratory"}
        assert tiers["observed"], "citizens need observable fields to submit"

    def test_pressure_weights_are_published_with_rationales(self, client):
        """The weights are judgements, so they are shown rather than hidden."""
        observed = client.get("/api/indicators").json()["tiers"]["observed"]
        weighted = [c for c in observed if c["pressureWeight"] is not None]
        assert weighted
        for concept in weighted:
            assert concept["rationale"].strip()
