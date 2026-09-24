"""Conformance with the official OneAquaHealth HL7 FHIR Implementation Guide.

The IG
------
HL7 Europe maintains a OneAquaHealth FHIR Implementation Guide
(`hl7.eu.fhir.oah`, canonical `http://hl7.eu/fhir/ig/oah`, FHIR R4/R4B). It
profiles `Location`, `Observation`, `Specimen`, `Group` and `Library` for this
exact domain, and publishes a temporary CodeSystem of 185 environmental and
health indicator concepts.

Two things follow from that, and this module implements both.

**First, conform.** Laboratory results here are emitted against
`ObservationIndicatorsOah` and reaches against `LocationOah`, tagged in
`meta.profile`, with the IG's own indicator codes alongside our local ones.
An independent local vocabulary that nobody else resolves is worth little;
the point of this project is interoperability, so it uses the community's
artifacts where they exist.

One decision is worth recording: we chose `Observation.subject ->  Location`
before discovering the IG, on the grounds that the subject of a stream
assessment is a place rather than a patient. `ObservationIndicatorsOah`
constrains exactly that:

    * subject only Reference(LocationOah)

Arriving independently at the constraint the IG mandates is reassurance that
the modelling is sound, not a coincidence worth hiding.

**Second, report the gap.** `ObservationIndicatorsOah` fixes the status:

    * status = #final

`final` in FHIR means verified. The IG therefore has no way to represent an
*unverified* observation — which is precisely what citizen-science evidence
is. Every indicator it can express is already authoritative.

That is a real limitation for a project whose own citizen-science app invites
the public to submit observations, and this module documents it rather than
working around it silently. Citizen submissions here are deliberately **not**
claimed as `ObservationIndicatorsOah`: they use the same shape, the same
codes and the same Location subject, but carry `status = preliminary` and omit
the profile assertion. Claiming conformance we do not have would be worse than
not conforming, because a downstream system trusting the profile would treat
unverified reports as laboratory-grade.

`PROPOSED_IG_CHANGE` below states the change that would close the gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .terminology import CODE_SYSTEM_URI

# --------------------------------------------------------------------------
# Canonical URLs from the IG (sushi-config.yaml: canonical http://hl7.eu/fhir/ig/oah)
# --------------------------------------------------------------------------

OAH_CANONICAL = "http://hl7.eu/fhir/ig/oah"
OAH_CODE_SYSTEM = f"{OAH_CANONICAL}/CodeSystem/temporarySystem-oah-eu"

PROFILE_LOCATION = f"{OAH_CANONICAL}/StructureDefinition/location-oah"
PROFILE_OBSERVATION = f"{OAH_CANONICAL}/StructureDefinition/observation-indicators-oah"
PROFILE_OBSERVATION_COMP = (
    f"{OAH_CANONICAL}/StructureDefinition/observation-with-component-oah"
)
PROFILE_SPECIMEN = f"{OAH_CANONICAL}/StructureDefinition/specimen-oah"

# The IG's examples identify locations under this system.
OAH_LOCATION_ID_SYSTEM = "https://oneaquahealth.eu/location-id"

SNOMED = "http://snomed.info/sct"
# Used by the IG's own Location examples for urban monitoring sites.
SCT_CITY_ENVIRONMENT = ("288520005", "City environment")


class Equivalence(str, Enum):
    """ConceptMap equivalence, per FHIR R4 `ConceptMapEquivalence`.

    Using the real value set rather than a home-made confidence label is the
    point: a consuming terminology server can act on these.
    """

    EQUIVALENT = "equivalent"
    WIDER = "wider"  # the target concept is broader than ours
    NARROWER = "narrower"  # the target concept is more specific than ours
    RELATEDTO = "relatedto"  # related, but neither contains the other
    UNMATCHED = "unmatched"  # no target concept exists


@dataclass(frozen=True)
class Mapping:
    """One local concept mapped onto the IG's vocabulary."""

    source: str
    target: str | None
    target_display: str | None
    equivalence: Equivalence
    comment: str


# --------------------------------------------------------------------------
# The mapping.
#
# Honesty matters more than coverage here. Forcing a match where none exists
# would corrupt any downstream analysis that trusted it, so several concepts
# are deliberately left UNMATCHED and say why. That is useful output in its
# own right: the unmatched list is evidence of what a citizen-science
# vocabulary needs that the IG does not yet carry.
# --------------------------------------------------------------------------

MAPPINGS: tuple[Mapping, ...] = (
    Mapping(
        source="diatom-teratology-rate",
        target="diatomTratology",
        target_display="Diatom teratology (deformities)",
        equivalence=Equivalence.EQUIVALENT,
        comment=(
            "Exact match. The IG carries the same early-warning indicator the "
            "OneAquaHealth policy brief highlights."
        ),
    ),
    Mapping(
        source="riparian-vegetation",
        target="riparianVegetation",
        target_display="Riparian vegetation",
        equivalence=Equivalence.EQUIVALENT,
        comment="Exact match.",
    ),
    Mapping(
        source="ibmwp-score",
        target="macroinvertebreates",
        target_display="Benthic Macroinvertebrates count",
        equivalence=Equivalence.NARROWER,
        comment=(
            "IBMWP is a specific scoring system computed from benthic "
            "macroinvertebrate families, so it is narrower than the IG's "
            "general count concept. A receiver should not read an IBMWP score "
            "as an abundance count; the units differ."
        ),
    ),
    Mapping(
        source="flow-condition",
        target="hydrology",
        target_display="Hydrology of the stream",
        equivalence=Equivalence.NARROWER,
        comment=(
            "The IG concept spans flow type, diversity, longitudinal "
            "connectivity and runoff. Ours is an ordinal judgement of flow "
            "state alone."
        ),
    ),
    Mapping(
        source="invasive-plants",
        target="invasiveOrganisms",
        target_display="Invasive invertebrate, plants and fish",
        equivalence=Equivalence.NARROWER,
        comment=(
            "The IG concept covers invertebrates, plants and fish. A citizen "
            "observer can reliably report only conspicuous bankside plants."
        ),
    ),
    Mapping(
        source="bank-erosion",
        target="morophology",
        target_display="Morphology of the streams",
        equivalence=Equivalence.NARROWER,
        comment=(
            "The IG concept covers habitat, channel and valley shape and "
            "substrate. Bank erosion is one visible facet of it."
        ),
    ),
    Mapping(
        source="odour",
        target="foam",
        target_display="Foam/colour/smell",
        equivalence=Equivalence.NARROWER,
        comment=(
            "The IG bundles foam, colour and smell into one concept. We "
            "separate odour from surface foam because they differ sharply in "
            "how reliably untrained observers report them — odour is one of "
            "the most dependable lay signals, surface foam one of the least. "
            "Both therefore map to the same coarser target, which loses that "
            "distinction."
        ),
    ),
    Mapping(
        source="foam-scum",
        target="foam",
        target_display="Foam/colour/smell",
        equivalence=Equivalence.NARROWER,
        comment=(
            "See `odour`. Two distinct local concepts collapse onto this one "
            "IG concept, so the mapping is lossy in that direction."
        ),
    ),
    Mapping(
        source="water-clarity",
        target="tss",
        target_display="Total suspended solids (TSS)",
        equivalence=Equivalence.RELATEDTO,
        comment=(
            "Related, not equivalent, and deliberately not marked narrower. "
            "Visual clarity is a lay proxy for suspended solids, but a "
            "peat-stained stream is naturally dark at low TSS and clear water "
            "can carry dissolved contaminants. Treating an ordinal clarity "
            "score as a TSS measurement would be wrong."
        ),
    ),
    Mapping(
        source="sewage-indicators",
        target=None,
        target_display=None,
        equivalence=Equivalence.UNMATCHED,
        comment=(
            "No IG concept covers visible evidence of untreated discharge — "
            "sewage fungus, grey filamentous growth, an active outfall. "
            "`coliforms` is a laboratory measurement of a different thing and "
            "mapping to it would misrepresent a visual observation as a "
            "microbiological result. This is the single most decision-relevant "
            "citizen observation and the IG has no home for it."
        ),
    ),
    Mapping(
        source="litter-load",
        target=None,
        target_display=None,
        equivalence=Equivalence.UNMATCHED,
        comment=(
            "No IG concept for anthropogenic debris. Weak evidence of "
            "ecological condition, but a strong driver of public perception "
            "and stewardship, which is why a citizen-facing vocabulary needs "
            "it even though a laboratory vocabulary does not."
        ),
    ),
    Mapping(
        source="ecological-quality-ratio",
        target=None,
        target_display=None,
        equivalence=Equivalence.UNMATCHED,
        comment=(
            "No IG concept for the Water Framework Directive EQR or its "
            "status classes, despite the WFD being the reporting framework "
            "these indicators ultimately feed."
        ),
    ),
    Mapping(
        source="wfd-ecological-status",
        target=None,
        target_display=None,
        equivalence=Equivalence.UNMATCHED,
        comment="See `ecological-quality-ratio`.",
    ),
)

_BY_SOURCE: dict[str, Mapping] = {m.source: m for m in MAPPINGS}


def oah_code_for(local_code: str) -> tuple[str, str] | None:
    """The IG code and display for a local concept, when one genuinely exists.

    Returns None for unmatched concepts and for concepts we never mapped,
    such as the screening-tier composites, which are ours by construction.
    """
    mapping = _BY_SOURCE.get(local_code)
    if mapping is None or mapping.target is None:
        return None
    return mapping.target, mapping.target_display or mapping.target


def unmatched_concepts() -> tuple[Mapping, ...]:
    """Local concepts with no IG equivalent. See `PROPOSED_IG_CHANGE`."""
    return tuple(
        m for m in MAPPINGS if m.equivalence is Equivalence.UNMATCHED
    )


PROPOSED_IG_CHANGE = """\
Proposal to the OneAquaHealth FHIR Implementation Guide
=======================================================

1. Relax `ObservationIndicatorsOah.status`
------------------------------------------
The profile currently fixes `status = #final`. In FHIR, `final` asserts that a
result is complete and verified. The profile therefore cannot represent an
unverified observation.

The OneAquaHealth project runs a citizen-science app that invites the public to
submit structured stream observations. Those observations are, by construction,
not verified: that is what distinguishes them from laboratory results, and it
is the reason they are cheap and plentiful. Under the current profile they
either cannot be expressed at all, or must be misrepresented as verified.

Proposed: bind `status` to {preliminary | final | amended | corrected |
entered-in-error} rather than fixing it, so that `preliminary` carries citizen
evidence. FHIR's existing semantics then do the work, and any conformant client
can separate verified from unverified evidence with `?status=final` — with no
extension and no project-specific knowledge.

2. Add concepts for citizen-observable conditions
--------------------------------------------------
The temporary CodeSystem is oriented toward laboratory and survey measurement.
Several conditions a member of the public can reliably report have no
representation:

  * visible evidence of untreated discharge (sewage fungus, grey filamentous
    growth, an active outfall). `coliforms` is a laboratory measurement of a
    different thing and is not a substitute.
  * anthropogenic litter load.
  * Water Framework Directive Ecological Quality Ratio and status class.

3. Separate odour from surface foam
------------------------------------
`foam` bundles "Foam/colour/smell". These differ sharply in observer
reliability: sewage odour is among the most dependable untrained observations,
while natural and surfactant-driven foam are not reliably distinguishable by
eye. Collapsing them discards information that any confidence weighting needs.
"""


def build_concept_map() -> dict:
    """A FHIR ConceptMap from our CodeSystem to the IG's.

    Hand-built rather than produced through fhir.resources: ConceptMap's
    nested group/element/target structure gains nothing from the model layer
    here, and the flat dict is easier to read beside the mapping table above.
    """
    elements = []
    for mapping in MAPPINGS:
        element: dict = {"code": mapping.source}
        if mapping.target is None:
            # An unmatched element carries a target with no code, which is how
            # ConceptMap records "considered, and deliberately not mapped".
            element["target"] = [
                {
                    "equivalence": Equivalence.UNMATCHED.value,
                    "comment": mapping.comment,
                }
            ]
        else:
            element["target"] = [
                {
                    "code": mapping.target,
                    "display": mapping.target_display,
                    "equivalence": mapping.equivalence.value,
                    "comment": mapping.comment,
                }
            ]
        elements.append(element)

    return {
        "resourceType": "ConceptMap",
        "id": "tributary-to-oah",
        "url": (
            "https://oneaquahealth.example.org/fhir/ConceptMap/tributary-to-oah"
        ),
        "version": "0.1.0",
        "name": "TributaryToOneAquaHealthIndicators",
        "title": "Tributary stream-assessment indicators to OneAquaHealth IG",
        "status": "draft",
        "experimental": True,
        "date": datetime.now(timezone.utc).isoformat(),
        "publisher": "Tributary - OneAquaHealth IEEE Global Hackathon 2026",
        "description": (
            "Maps Tributary's citizen-observable and laboratory indicators "
            "onto the OneAquaHealth Implementation Guide's temporary code "
            "system. Concepts with no faithful target are recorded as "
            "unmatched with the reason, rather than forced onto an "
            "approximate code: a mapping that overstates its own fidelity is "
            "worse than an absent one, because downstream analysis cannot see "
            "the error."
        ),
        "sourceUri": CODE_SYSTEM_URI,
        "targetUri": OAH_CODE_SYSTEM,
        "group": [
            {
                "source": CODE_SYSTEM_URI,
                "target": OAH_CODE_SYSTEM,
                "element": elements,
            }
        ],
    }
