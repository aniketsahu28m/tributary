"""In-memory repository and demonstration dataset.

Storage is deliberately in-memory. A hackathon demonstration that depends on
migrations and a database file is a demonstration that fails on someone else's
laptop, and nothing here needs durability to make its point. The repository
interface is narrow enough that swapping in SQLModel later touches this module
only.

ALL OBSERVATION DATA BELOW IS SYNTHETIC. It is constructed to exercise the
screening logic across contrasting cases, not to describe the real condition of
any watercourse. Reach names are illustrative. No claim is made about any
actual stream, and none of it should be read as a finding about Coimbra or
anywhere else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import AccessLevel, CitizenObservation, ExpertSample, StreamReach
from .scoring import ObserverHistory, ScreeningResult, screen


class Store:
    """Narrow repository over reaches, observations, samples and observers."""

    def __init__(self) -> None:
        self.reaches: dict[str, StreamReach] = {}
        self.observations: dict[str, CitizenObservation] = {}
        self.samples: dict[str, ExpertSample] = {}
        self.observers: dict[str, ObserverHistory] = {}

    # -- writes ----------------------------------------------------------
    def add_reach(self, reach: StreamReach) -> StreamReach:
        self.reaches[reach.id] = reach
        return reach

    def add_observation(self, obs: CitizenObservation) -> CitizenObservation:
        if obs.reach_id not in self.reaches:
            raise KeyError(f"unknown reach {obs.reach_id!r}")
        self.observations[obs.id] = obs
        return obs

    def add_sample(self, sample: ExpertSample) -> ExpertSample:
        if sample.reach_id not in self.reaches:
            raise KeyError(f"unknown reach {sample.reach_id!r}")
        self.samples[sample.id] = sample
        return sample

    # -- reads -----------------------------------------------------------
    def observations_for(self, reach_id: str) -> list[CitizenObservation]:
        return sorted(
            (o for o in self.observations.values() if o.reach_id == reach_id),
            key=lambda o: o.recorded_at,
            reverse=True,
        )

    def samples_for(self, reach_id: str) -> list[ExpertSample]:
        return sorted(
            (s for s in self.samples.values() if s.reach_id == reach_id),
            key=lambda s: s.sampled_at,
            reverse=True,
        )

    def last_sample_date(self, reach_id: str) -> datetime | None:
        samples = self.samples_for(reach_id)
        return samples[0].sampled_at if samples else None

    def corroborating_count(
        self, obs: CitizenObservation, *, window_hours: int = 72
    ) -> int:
        """Independent reports of the same reach within a time window.

        Counts distinct *observers*, not submissions: one enthusiastic person
        filing four reports is not corroboration, and treating it as such would
        let a single voice manufacture confidence.
        """
        window = timedelta(hours=window_hours)
        others = {
            o.observer_id
            for o in self.observations.values()
            if o.reach_id == obs.reach_id
            and o.id != obs.id
            and o.observer_id != obs.observer_id
            and abs(o.recorded_at - obs.recorded_at) <= window
        }
        return len(others)

    # -- derived ---------------------------------------------------------
    def screen_observation(
        self, obs: CitizenObservation, *, now: datetime | None = None
    ) -> ScreeningResult:
        return screen(
            obs,
            self.reaches[obs.reach_id],
            history=self.observers.get(obs.observer_id),
            corroborating_reports=self.corroborating_count(obs),
            last_expert_sample=self.last_sample_date(obs.reach_id),
            now=now,
        )

    def priority_queue(
        self, *, now: datetime | None = None
    ) -> list[tuple[StreamReach, CitizenObservation, ScreeningResult]]:
        """Reaches ranked by sampling priority, using their latest observation.

        One row per reach rather than per observation: a monitoring officer
        allocates visits to places, and showing the same reach five times
        because five people reported it would bury everywhere else.
        """
        rows = []
        for reach in self.reaches.values():
            latest = self.observations_for(reach.id)
            if not latest:
                continue
            obs = latest[0]
            rows.append((reach, obs, self.screen_observation(obs, now=now)))
        return sorted(rows, key=lambda r: r[2].priority, reverse=True)


# ---------------------------------------------------------------------------
# Demonstration dataset — synthetic. See module docstring.
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def _reach(rid, name, water, lat, lon, access, pop) -> StreamReach:
    return StreamReach(
        id=rid,
        name=name,
        water_body=water,
        municipality="Coimbra",
        country="PT",
        latitude=lat,
        longitude=lon,
        access=access,
        population_within_500m=pop,
    )


def seed(store: Store) -> Store:
    """Populate a store with contrasting synthetic cases.

    The cases are chosen so that the priority queue demonstrates a real
    judgement rather than simply sorting by how dirty each stream looks:
    a heavily degraded but fenced culvert should rank *below* a moderately
    degraded reach where children play.
    """
    reaches = [
        _reach("coselhas-03", "Coselhas, reach 3 (footbridge to weir)",
               "Ribeira de Coselhas", 40.2216, -8.4194,
               AccessLevel.RECREATIONAL, 4200),
        _reach("coselhas-07", "Coselhas, reach 7 (culverted section)",
               "Ribeira de Coselhas", 40.2301, -8.4102,
               AccessLevel.NONE, 900),
        _reach("ceira-01", "Ceira, reach 1 (municipal park)",
               "Rio Ceira", 40.1846, -8.3892,
               AccessLevel.RECREATIONAL, 11800),
        _reach("ceira-04", "Ceira, reach 4 (industrial margin)",
               "Rio Ceira", 40.1702, -8.3615,
               AccessLevel.VISUAL, 300),
        _reach("mondego-12", "Mondego, reach 12 (riverside path)",
               "Rio Mondego", 40.2071, -8.4290,
               AccessLevel.BANKSIDE, 7600),
    ]
    for r in reaches:
        store.add_reach(r)

    store.observers.update({
        "cit-anabela": ObserverHistory(submissions=34, confirmed_by_expert=29),
        "cit-rui": ObserverHistory(submissions=11, confirmed_by_expert=7),
        "cit-marta": ObserverHistory(submissions=3, confirmed_by_expert=2),
        "cit-novo": ObserverHistory(),
    })

    observations = [
        # Degraded and publicly accessible: should top the queue.
        CitizenObservation(
            id="obs-001", reach_id="coselhas-03", observer_id="cit-anabela",
            recorded_at=_T0,
            scores={"water-clarity": 1, "odour": 3, "sewage-indicators": 3,
                    "litter-load": 3, "bank-erosion": 2,
                    "riparian-vegetation": 1, "invasive-plants": 2,
                    "foam-scum": 2, "flow-condition": 1},
            photo_count=5,
            note="Grey filamentous growth below the outfall; strong smell.",
        ),
        # Independent corroboration of the above, from a different observer.
        CitizenObservation(
            id="obs-002", reach_id="coselhas-03", observer_id="cit-rui",
            recorded_at=_T0 + timedelta(hours=6),
            scores={"water-clarity": 1, "odour": 2, "sewage-indicators": 3,
                    "litter-load": 3, "flow-condition": 1},
            photo_count=2, note="Same white growth, confirmed downstream.",
        ),
        # Equally degraded but inaccessible: high pressure, no escalation.
        CitizenObservation(
            id="obs-003", reach_id="coselhas-07", observer_id="cit-anabela",
            recorded_at=_T0 + timedelta(days=1),
            scores={"water-clarity": 0, "odour": 4, "sewage-indicators": 4,
                    "litter-load": 2, "bank-erosion": 1,
                    "riparian-vegetation": 0, "invasive-plants": 0,
                    "foam-scum": 3, "flow-condition": 1},
            photo_count=3, note="Visible through the grating only.",
        ),
        # Healthy, busy park reach.
        CitizenObservation(
            id="obs-004", reach_id="ceira-01", observer_id="cit-marta",
            recorded_at=_T0 + timedelta(days=1, hours=3),
            scores={"water-clarity": 4, "odour": 0, "sewage-indicators": 0,
                    "litter-load": 1, "bank-erosion": 0,
                    "riparian-vegetation": 4, "invasive-plants": 0,
                    "foam-scum": 0, "flow-condition": 2},
            photo_count=4, note="Clear water, fish visible, alder intact.",
        ),
        # Sparse low-confidence report from a brand-new observer.
        CitizenObservation(
            id="obs-005", reach_id="ceira-04", observer_id="cit-novo",
            recorded_at=_T0 + timedelta(days=2),
            scores={"odour": 2, "foam-scum": 3, "flow-condition": 2},
            photo_count=0, note="Foam near the pipe. Not sure if it matters.",
        ),
        # Moderate pressure, bankside access, dense population.
        CitizenObservation(
            id="obs-006", reach_id="mondego-12", observer_id="cit-rui",
            recorded_at=_T0 + timedelta(days=2, hours=5),
            scores={"water-clarity": 2, "odour": 1, "sewage-indicators": 1,
                    "litter-load": 4, "bank-erosion": 3,
                    "riparian-vegetation": 2, "invasive-plants": 3,
                    "foam-scum": 0, "flow-condition": 2},
            photo_count=3, note="Heavy litter after the weekend; banks eroding.",
        ),
    ]
    for o in observations:
        store.add_observation(o)

    # Expert results, present for some reaches and absent for others so the
    # staleness term in sampling priority has something to bite on.
    store.add_sample(ExpertSample(
        id="lab-001", reach_id="coselhas-03",
        sampled_at=_T0 - timedelta(days=240), laboratory="MARE-UC",
        ibmwp_score=41, diatom_teratology_rate=12.4,
        ecological_quality_ratio=0.38,
    ))
    store.add_sample(ExpertSample(
        id="lab-002", reach_id="ceira-01",
        sampled_at=_T0 - timedelta(days=45), laboratory="MARE-UC",
        ibmwp_score=118, diatom_teratology_rate=1.1,
        ecological_quality_ratio=0.82,
    ))
    # mondego-12, coselhas-07 and ceira-04 have never been sampled.

    return store


def seeded_store() -> Store:
    return seed(Store())
