"""Projection of stream assessments onto FHIR R4 resources.

Why FHIR at all
---------------
The OneAquaHealth policy brief's central governance finding is that
environmental, water management, urban planning and health sectors run on
fragmented data systems, and it recommends unified data infrastructure across
them. Three of those four sectors have no shared standard. The fourth — health
— has one that is deployed at national scale across Europe: HL7 FHIR.

So rather than invent a fifth format, this project expresses ecosystem
observations *in the health sector's own standard*, so that a stream's
condition can arrive in a public health system the same way a lab result does.
That is what makes "One Health" computable rather than rhetorical.

Modelling decisions
-------------------
1. `Observation.subject` references a `Location`, not a `Patient`.
   FHIR R4 permits Reference(Patient | Group | Device | Location) here. The
   subject of a stream assessment is a place, and saying so honestly is better
   than minting a synthetic Patient to stand in for a river.

2. Evidential tier is carried by `Observation.status`, not a custom extension.
   Citizen submissions are `preliminary`; laboratory results are `final`. FHIR
   already means by this exactly what we mean: a preliminary result is usable
   but not yet verified. Reusing it means any FHIR client understands the
   distinction with no knowledge of this project.

3. Screening composites are `derived-from` their source observations, using
   `Observation.derivedFrom`. The provenance chain from raw citizen scores to
   a sampling-priority score is therefore machine-traversable, which is what
   makes the output auditable to an environmental regulator.

4. Observation confidence is an extension, because FHIR has no element for it.
   It is defined under our own URI rather than overloading an existing field.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.codesystem import CodeSystem
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.location import Location, LocationPosition
from fhir.resources.R4B.observation import Observation, ObservationComponent
from fhir.resources.R4B.quantity import Quantity
from fhir.resources.R4B.reference import Reference

from .models import CitizenObservation, ExpertSample, StreamReach
from .terminology import (
    ALL_CONCEPTS,
    CODE_SYSTEM_URI,
    PROFILE_BASE_URI,
    Tier,
    concept,
)

CONFIDENCE_EXTENSION_URI = f"{PROFILE_BASE_URI}/observation-confidence"
TIER_EXTENSION_URI = f"{PROFILE_BASE_URI}/evidential-tier"

# FHIR observation-category is an extensible binding, so a local code is legal
# here. "survey" is the closest core code for a structured questionnaire-style
# assessment; we pair it with a local code that says what kind of survey.
_CATEGORY_CORE = "http://terminology.hl7.org/CodeSystem/observation-category"


def _coding(code: str) -> Coding:
    """A Coding for one of our concepts, carrying its display text."""
    c = concept(code)
    return Coding(system=CODE_SYSTEM_URI, code=c.code, display=c.display)


def _concept_cc(code: str) -> CodeableConcept:
    return CodeableConcept(coding=[_coding(code)])


def _category() -> list[CodeableConcept]:
    return [
        CodeableConcept(
            coding=[
                Coding(system=_CATEGORY_CORE, code="survey", display="Survey"),
                Coding(
                    system=CODE_SYSTEM_URI,
                    code="urban-stream-assessment",
                    display="Urban stream assessment",
                ),
            ]
        )
    ]


def _tier_extension(tier: Tier) -> Extension:
    """Make the evidential tier explicit as well as implicit in `status`.

    `status` already encodes preliminary vs final, but a consumer filtering for
    "only laboratory-grade evidence" should not have to infer that from status
    alone once more tiers exist.
    """
    return Extension(url=TIER_EXTENSION_URI, valueCode=tier.value)


def reach_to_location(reach: StreamReach) -> Location:
    """A monitored stream reach as a FHIR Location."""
    return Location(
        id=reach.id,
        status="active",
        name=reach.name,
        description=f"{reach.name}, {reach.water_body} ({reach.municipality})",
        mode="instance",
        physicalType=CodeableConcept(
            coding=[
                Coding(
                    system="http://terminology.hl7.org/CodeSystem/location-physical-type",
                    code="area",
                    display="Area",
                )
            ]
        ),
        position=LocationPosition(
            latitude=reach.latitude, longitude=reach.longitude
        ),
        address={
            "city": reach.municipality,
            "country": reach.country,
        },
    )


def citizen_observation_to_fhir(
    obs: CitizenObservation,
    *,
    confidence: float | None = None,
) -> Observation:
    """A citizen submission as a single FHIR Observation with components.

    The whole submission is one Observation rather than one per score, because
    the scores are a single assessment event at one place and time — splitting
    them would lose that they share flow conditions and an observer.
    """
    components: list[ObservationComponent] = []
    for code, score in sorted(obs.scores.items()):
        c = concept(code)
        components.append(
            ObservationComponent(
                code=_concept_cc(code),
                valueQuantity=Quantity(
                    value=float(score),
                    unit=c.unit or "{score}",
                    system="http://unitsofmeasure.org",
                    code=c.unit or "{score}",
                ),
            )
        )

    extensions = [_tier_extension(Tier.OBSERVED)]
    if confidence is not None:
        extensions.append(
            Extension(url=CONFIDENCE_EXTENSION_URI, valueDecimal=round(confidence, 3))
        )

    return Observation(
        id=obs.id,
        # Citizen evidence is usable but unverified. FHIR already has a word
        # for that, and it is this one.
        status="preliminary",
        category=_category(),
        code=CodeableConcept(
            coding=[
                Coding(
                    system=CODE_SYSTEM_URI,
                    code="citizen-stream-assessment",
                    display="Citizen stream assessment",
                )
            ],
            text="Citizen-reported urban stream condition",
        ),
        subject=Reference(reference=f"Location/{obs.reach_id}"),
        effectiveDateTime=obs.recorded_at,
        issued=datetime.now(timezone.utc),
        performer=[Reference(reference=f"RelatedPerson/{obs.observer_id}")],
        component=components,
        note=[{"text": obs.note}] if obs.note else None,
        extension=extensions,
    )


def expert_sample_to_fhir(sample: ExpertSample) -> list[Observation]:
    """Laboratory results as final-status Observations on the same Location."""
    results: list[Observation] = []

    def _make(suffix: str, code: str, value: float, unit: str) -> Observation:
        return Observation(
            id=f"{sample.id}-{suffix}",
            # Verified by a laboratory. This is the FHIR meaning of final.
            status="final",
            category=_category(),
            code=_concept_cc(code),
            subject=Reference(reference=f"Location/{sample.reach_id}"),
            effectiveDateTime=sample.sampled_at,
            performer=[Reference(display=sample.laboratory)],
            valueQuantity=Quantity(
                value=value,
                unit=unit,
                system="http://unitsofmeasure.org",
                code=unit,
            ),
            extension=[_tier_extension(Tier.LABORATORY)],
        )

    if sample.ibmwp_score is not None:
        results.append(
            _make("ibmwp", "ibmwp-score", float(sample.ibmwp_score), "{score}")
        )
    if sample.diatom_teratology_rate is not None:
        results.append(
            _make(
                "teratology",
                "diatom-teratology-rate",
                sample.diatom_teratology_rate,
                "/1000",
            )
        )
    if sample.ecological_quality_ratio is not None:
        eqr = _make(
            "eqr",
            "ecological-quality-ratio",
            sample.ecological_quality_ratio,
            "1",
        )
        status = sample.wfd_status
        if status is not None:
            # The banded class travels as interpretation of the EQR rather than
            # as a separate Observation: it is the same measurement, expressed
            # on the reporting scale the Directive uses.
            eqr.interpretation = [
                CodeableConcept(
                    coding=[
                        Coding(
                            system=CODE_SYSTEM_URI,
                            code=f"wfd-{status.value}",
                            display=f"{status.display} ecological status",
                        )
                    ],
                    text=(
                        f"WFD ecological status: {status.display}. Banded using "
                        f"equal-interval defaults, not type-specific "
                        f"intercalibrated boundaries."
                    ),
                )
            ]
        results.append(eqr)

    return results


def build_code_system() -> CodeSystem:
    """Our terminology as a publishable FHIR CodeSystem.

    Publishing this is what makes the local codes resolvable by a consuming
    system instead of opaque strings.
    """
    return CodeSystem(
        id="stream-assessment",
        url=CODE_SYSTEM_URI,
        version="0.1.0",
        name="StreamAssessmentIndicators",
        title="Urban Stream Assessment Indicators",
        status="draft",
        experimental=True,
        date=datetime.now(timezone.utc),
        publisher="OneAquaHealth IEEE Global Hackathon entry",
        description=(
            "Indicators for urban freshwater assessment spanning citizen "
            "observation, derived screening signals and laboratory metrics. "
            "Each concept declares its evidential tier so that consuming "
            "systems cannot mistake a citizen screening score for a Water "
            "Framework Directive status determination."
        ),
        caseSensitive=True,
        content="complete",
        count=len(ALL_CONCEPTS),
        property=[
            {
                "code": "tier",
                "description": (
                    "Evidential tier: observed, screened or laboratory."
                ),
                "type": "code",
            }
        ],
        concept=[
            {
                "code": c.code,
                "display": c.display,
                "definition": c.definition,
                "property": [{"code": "tier", "valueCode": c.tier.value}],
            }
            for c in ALL_CONCEPTS
        ],
    )
