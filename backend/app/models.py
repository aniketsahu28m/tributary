"""Internal domain model for citizen stream assessments.

These are the shapes the API accepts and stores. They are deliberately kept
separate from the FHIR representation: FHIR is an *interoperability* format,
not a convenient working model, and conflating the two makes both worse.
`fhir_mapping` projects these onto FHIR resources at the boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .terminology import OBSERVED_CONCEPTS, WFDStatus

OBSERVED_CODES: frozenset[str] = frozenset(c.code for c in OBSERVED_CONCEPTS)

# Ordinal scale used by every citizen-observable field.
SCORE_MIN, SCORE_MAX = 0, 4


class AccessLevel(str, Enum):
    """How readily the public can make physical contact with the water.

    Drives the One Health escalation flag: contamination only becomes a human
    health question where people actually touch the water.
    """

    NONE = "none"           # fenced, culverted or otherwise inaccessible
    VISUAL = "visual"       # visible from a path, no bank access
    BANKSIDE = "bankside"   # reachable on foot, incidental contact plausible
    RECREATIONAL = "recreational"  # paddling, swimming, dog-walking, angling


class StreamReach(BaseModel):
    """A monitored segment of urban watercourse.

    A 'reach' rather than a point: citizen observers cannot reliably return to
    a GPS coordinate, but they can reliably return to a named stretch between
    two landmarks. Aggregating to the reach is what makes repeat observation
    comparable over time.
    """

    id: str
    name: str = Field(min_length=1)
    water_body: str = Field(description="Parent water body or catchment name.")
    municipality: str
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2.")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    access: AccessLevel = AccessLevel.BANKSIDE
    population_within_500m: int = Field(
        default=0,
        ge=0,
        description=(
            "Residents within 500 m. Used to weight sampling priority: a "
            "polluted reach beside a housing estate matters more, per unit of "
            "monitoring effort, than one in an industrial margin."
        ),
    )

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class CitizenObservation(BaseModel):
    """A single submission from the bank of a stream.

    Every field is something a person with a phone can actually judge. Nothing
    here requires equipment, sampling or taxonomy — see `terminology` on why
    that boundary is enforced rather than blurred.
    """

    id: str
    reach_id: str
    observer_id: str
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    scores: dict[str, int] = Field(
        description=(
            "Ordinal 0-4 scores keyed by observed-tier concept code. Partial "
            "submissions are valid: an observer who cannot smell the water "
            "should omit `odour`, not guess."
        )
    )
    photo_count: int = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("scores")
    @classmethod
    def _known_codes_in_range(cls, v: dict[str, int]) -> dict[str, int]:
        if not v:
            raise ValueError("at least one observed score is required")
        unknown = set(v) - OBSERVED_CODES
        if unknown:
            raise ValueError(
                f"not observed-tier concept codes: {sorted(unknown)}. "
                f"Screening and laboratory indicators are derived or measured, "
                f"never submitted by an observer."
            )
        bad = {k: s for k, s in v.items() if not SCORE_MIN <= s <= SCORE_MAX}
        if bad:
            raise ValueError(
                f"scores must lie in [{SCORE_MIN}, {SCORE_MAX}], got {bad}"
            )
        return v


class ExpertSample(BaseModel):
    """A laboratory result for a reach, closing the loop on citizen triage.

    Carried in the same record so that a health system consuming these data
    sees citizen screening and expert confirmation side by side, with their
    evidential tiers intact.
    """

    id: str
    reach_id: str
    sampled_at: datetime
    laboratory: str
    ibmwp_score: int | None = Field(default=None, ge=0)
    diatom_teratology_rate: float | None = Field(
        default=None, ge=0, description="Deformed valves per 1000 counted."
    )
    ecological_quality_ratio: float | None = Field(default=None, ge=0, le=1)

    @property
    def wfd_status(self) -> WFDStatus | None:
        """Banded ecological status, or None when no EQR was determined."""
        from .terminology import eqr_to_status

        if self.ecological_quality_ratio is None:
            return None
        return eqr_to_status(self.ecological_quality_ratio)
