"""HTTP API for Tributary.

Two surfaces, deliberately separated:

  /api/*   a plain JSON interface shaped for the dashboard.
  /fhir/*  standards-conformant FHIR R4B resources for interoperability.

They are not the same endpoints with a format switch, because they answer to
different masters. The dashboard needs whatever shape makes the UI simple and
may change freely; the FHIR surface is a contract with external systems and
should change only with a version bump. Collapsing them would drag UI
convenience into the standards layer, which is how interoperability projects
end up with FHIR-shaped resources that no other system can actually consume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .fhir_mapping import (
    build_code_system,
    citizen_observation_to_fhir,
    expert_sample_to_fhir,
    reach_to_location,
)
from .models import CitizenObservation, ExpertSample, StreamReach
from .scoring import PRESSURE_WEIGHTS, ScreeningResult
from .store import Store, seeded_store
from .terminology import ALL_CONCEPTS, Tier

app = FastAPI(
    title="Tributary",
    version="0.1.0",
    description=(
        "Citizen stream observations to expert sampling priority, expressed "
        "in FHIR so that ecosystem evidence can reach health systems. "
        "OneAquaHealth IEEE Global Hackathon 2026, Tracks 7 and 3."
    ),
)

# The dashboard is served from a separate origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

store: Store = seeded_store()


def _screening_json(result: ScreeningResult) -> dict[str, Any]:
    return {
        "visualPressureIndex": result.visual_pressure_index,
        "confidence": result.confidence,
        "priority": result.priority,
        "priorityTerms": result.priority_terms,
        "oneHealth": {
            "escalate": result.one_health.escalate,
            "exposureFactor": result.one_health.exposure_factor,
            "reason": result.one_health.reason,
        },
    }


def _reach_json(reach: StreamReach) -> dict[str, Any]:
    return {
        "id": reach.id,
        "name": reach.name,
        "waterBody": reach.water_body,
        "municipality": reach.municipality,
        "country": reach.country,
        "latitude": reach.latitude,
        "longitude": reach.longitude,
        "access": reach.access.value,
        "populationWithin500m": reach.population_within_500m,
    }


def _observation_json(obs: CitizenObservation) -> dict[str, Any]:
    return {
        "id": obs.id,
        "reachId": obs.reach_id,
        "observerId": obs.observer_id,
        "recordedAt": obs.recorded_at.isoformat(),
        "scores": obs.scores,
        "photoCount": obs.photo_count,
        "note": obs.note,
    }


def _sample_json(sample: ExpertSample) -> dict[str, Any]:
    status = sample.wfd_status
    return {
        "id": sample.id,
        "reachId": sample.reach_id,
        "sampledAt": sample.sampled_at.isoformat(),
        "laboratory": sample.laboratory,
        "ibmwpScore": sample.ibmwp_score,
        "diatomTeratologyRate": sample.diatom_teratology_rate,
        "ecologicalQualityRatio": sample.ecological_quality_ratio,
        "wfdStatus": status.value if status else None,
        "wfdStatusDisplay": status.display if status else None,
    }


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "tributary"}


@app.get("/api/indicators")
def indicators() -> dict[str, Any]:
    """The indicator catalogue, grouped by evidential tier.

    The UI renders this rather than hard-coding field lists, so that the
    observed/laboratory boundary cannot drift apart between the form and the
    validation rules.
    """
    return {
        "tiers": {
            tier.value: [
                {
                    "code": c.code,
                    "display": c.display,
                    "definition": c.definition,
                    "unit": c.unit,
                    "pressureWeight": (
                        PRESSURE_WEIGHTS[c.code].weight
                        if c.code in PRESSURE_WEIGHTS
                        else None
                    ),
                    "inverted": (
                        PRESSURE_WEIGHTS[c.code].inverted
                        if c.code in PRESSURE_WEIGHTS
                        else None
                    ),
                    "rationale": (
                        PRESSURE_WEIGHTS[c.code].rationale
                        if c.code in PRESSURE_WEIGHTS
                        else None
                    ),
                }
                for c in ALL_CONCEPTS
                if c.tier is tier
            ]
            for tier in Tier
        }
    }


@app.get("/api/reaches")
def list_reaches() -> list[dict[str, Any]]:
    return [_reach_json(r) for r in store.reaches.values()]


@app.get("/api/reaches/{reach_id}")
def get_reach(reach_id: str) -> dict[str, Any]:
    reach = store.reaches.get(reach_id)
    if reach is None:
        raise HTTPException(404, f"no reach {reach_id!r}")

    observations = store.observations_for(reach_id)
    return {
        "reach": _reach_json(reach),
        "observations": [
            {
                **_observation_json(o),
                "screening": _screening_json(store.screen_observation(o)),
            }
            for o in observations
        ],
        "expertSamples": [_sample_json(s) for s in store.samples_for(reach_id)],
        "lastExpertSample": (
            store.last_sample_date(reach_id).isoformat()
            if store.last_sample_date(reach_id)
            else None
        ),
    }


@app.get("/api/priority-queue")
def priority_queue() -> list[dict[str, Any]]:
    """Reaches ranked by where the next expert sampling visit should go.

    The headline output. Each row carries the term-by-term breakdown of its
    score, because a ranking a monitoring officer cannot interrogate is a
    ranking they will not act on.
    """
    return [
        {
            "reach": _reach_json(reach),
            "latestObservation": _observation_json(obs),
            "screening": _screening_json(result),
            "lastExpertSample": (
                store.last_sample_date(reach.id).isoformat()
                if store.last_sample_date(reach.id)
                else None
            ),
        }
        for reach, obs, result in store.priority_queue()
    ]


@app.post("/api/observations")
def submit_observation(obs: CitizenObservation) -> dict[str, Any]:
    """Accept a citizen submission and return what the screening made of it.

    Validation rejects any attempt to submit screening- or laboratory-tier
    codes; see `terminology` for why that boundary is enforced here rather
    than left to the client.
    """
    try:
        store.add_observation(obs)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    return {
        **_observation_json(obs),
        "screening": _screening_json(store.screen_observation(obs)),
    }


@app.get("/api/escalations")
def escalations() -> list[dict[str, Any]]:
    """Observations that crossed into human health territory.

    This is the One Health handover queue: the subset a public health team
    should see, as opposed to everything an environmental team should see.
    """
    rows = []
    for reach, obs, result in store.priority_queue():
        if result.one_health.escalate:
            rows.append(
                {
                    "reach": _reach_json(reach),
                    "observation": _observation_json(obs),
                    "screening": _screening_json(result),
                    "fhir": f"/fhir/Observation/{obs.id}",
                }
            )
    return rows


# ---------------------------------------------------------------------------
# FHIR R4B surface
# ---------------------------------------------------------------------------


@app.get("/fhir/metadata")
def capability_statement() -> dict[str, Any]:
    """A minimal CapabilityStatement.

    Abbreviated rather than absent: FHIR clients look here first to discover
    what a server supports, and a server that cannot answer /metadata is not
    really a FHIR server.
    """
    return {
        "resourceType": "CapabilityStatement",
        "status": "draft",
        "date": datetime.now(timezone.utc).isoformat(),
        "publisher": "Tributary - OneAquaHealth IEEE Global Hackathon 2026",
        "kind": "instance",
        "fhirVersion": "4.3.0",
        "format": ["application/fhir+json"],
        "rest": [
            {
                "mode": "server",
                "documentation": (
                    "Read-only. Environmental observations are expressed with "
                    "Observation.subject referencing a Location rather than a "
                    "Patient, and evidential tier is carried by "
                    "Observation.status: citizen reports are preliminary, "
                    "laboratory results are final."
                ),
                "resource": [
                    {
                        "type": "Location",
                        "interaction": [{"code": "read"}, {"code": "search-type"}],
                    },
                    {
                        "type": "Observation",
                        "interaction": [{"code": "read"}, {"code": "search-type"}],
                        "searchParam": [
                            {"name": "subject", "type": "reference"},
                            {"name": "status", "type": "token"},
                        ],
                    },
                    {"type": "CodeSystem", "interaction": [{"code": "read"}]},
                ],
            }
        ],
    }


@app.get("/fhir/CodeSystem/stream-assessment")
def code_system() -> dict[str, Any]:
    """The stream-assessment terminology as a resolvable FHIR CodeSystem."""
    return build_code_system().dict()


@app.get("/fhir/Location/{reach_id}")
def fhir_location(reach_id: str) -> dict[str, Any]:
    reach = store.reaches.get(reach_id)
    if reach is None:
        raise HTTPException(404, f"no reach {reach_id!r}")
    return reach_to_location(reach).dict()


@app.get("/fhir/Observation/{observation_id}")
def fhir_observation(observation_id: str) -> dict[str, Any]:
    obs = store.observations.get(observation_id)
    if obs is not None:
        result = store.screen_observation(obs)
        return citizen_observation_to_fhir(
            obs, confidence=result.confidence
        ).dict()

    # Laboratory observations carry a suffix identifying which metric they
    # hold, since one sample yields several Observations.
    for sample in store.samples.values():
        for resource in expert_sample_to_fhir(sample):
            if resource.id == observation_id:
                return resource.dict()

    raise HTTPException(404, f"no observation {observation_id!r}")


@app.get("/fhir/Observation")
def fhir_observation_search(
    subject: str | None = None, status: str | None = None
) -> dict[str, Any]:
    """Search Observations, returned as a FHIR searchset Bundle.

    `subject` accepts either a bare reach id or a `Location/{id}` reference,
    because both forms appear in the wild and rejecting one is a pointless
    source of integration friction.
    """
    reach_id = subject.split("/")[-1] if subject else None
    if reach_id is not None and reach_id not in store.reaches:
        raise HTTPException(404, f"no reach {reach_id!r}")

    resources = []
    for obs in store.observations.values():
        if reach_id and obs.reach_id != reach_id:
            continue
        result = store.screen_observation(obs)
        resources.append(
            citizen_observation_to_fhir(obs, confidence=result.confidence)
        )
    for sample in store.samples.values():
        if reach_id and sample.reach_id != reach_id:
            continue
        resources.extend(expert_sample_to_fhir(sample))

    if status:
        resources = [r for r in resources if r.status == status]

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resources),
        "entry": [
            {
                "fullUrl": f"/fhir/Observation/{r.id}",
                "resource": r.dict(),
            }
            for r in resources
        ],
    }
