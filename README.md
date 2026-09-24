# Tributary

**Citizen stream observations, triaged into expert sampling priority, and
published as FHIR so that ecosystem evidence can reach health systems.**

OneAquaHealth IEEE Global Hackathon 2026 — **Track 7 (Digital Health
Standards)**, with **Track 3 (AI-Supported Assessment)**.

---

## The problem

Professional stream monitoring is expensive and therefore sparse. A municipal
laboratory might sample a given urban reach once or twice a year. Citizen
observers are numerous and frequent, but they cannot produce Water Framework
Directive metrics: IBMWP needs kick-net sampling and taxonomic identification
to family level, and diatom teratology needs microscopy of a prepared slide.
No phone observation can produce either.

So the useful question is not *can citizens replace experts* — they cannot —
but **can citizen observation tell experts where to spend the next sampling
visit**.

That is what Tributary answers. Its headline output is a sampling priority
queue, not an ecological score.

The second problem is what happens to the answer. The OneAquaHealth policy
brief's central governance finding is that environmental, water management,
urban planning and health sectors run on fragmented data systems, and it
recommends unified data infrastructure across them. Three of those four
sectors have no shared standard. The fourth — health — has one deployed at
national scale across Europe: **HL7 FHIR**.

Rather than invent a fifth format, Tributary expresses stream observations in
the health sector's own standard, so a stream's condition can arrive in a
public health system the same way a laboratory result does. That is what makes
"One Health" computable rather than rhetorical.

---

## The core idea, in one comparison

Two reaches of the same stream, from the demonstration dataset:

| | Coselhas reach 3 | Coselhas reach 7 |
|---|---|---|
| Visual pressure index | 55.7 | **67.0** (worse) |
| Public access | Recreational | None — fenced culvert |
| One Health escalation | **Yes** | No |
| **Sampling priority** | **63.2** | 47.3 |

Reach 7 is the more polluted stretch. Reach 3 is the higher priority, because
people swim there.

Contamination alone is an environmental matter. It becomes a **One Health**
matter when there is a pathway to people — and that is a property of the
place, not the pollutant. A degraded culverted reach behind a fence and an
identically degraded reach where children paddle warrant different responses,
and only the second belongs in a health system's inbox.

---

## Three evidential tiers, enforced rather than documented

Every indicator declares what kind of evidence it is:

| Tier | Meaning | Examples |
|---|---|---|
| `OBSERVED` | A person with a phone can judge it from the bank | water clarity, odour, sewage indicators, litter, bank erosion |
| `SCREENED` | Derived from observed values. A triage signal, **not** a WFD metric | visual pressure index, observation confidence, sampling priority |
| `LABORATORY` | Requires sampling and expert taxonomy. Never produced by an app | IBMWP, diatom teratology rate, EQR, WFD status |

The boundary is enforced in code, not merely written down. A citizen
submission carrying an IBMWP score or an EQR is **rejected at validation**:

```python
>>> CitizenObservation(id="x", reach_id="r1", observer_id="c1",
...                    scores={"ibmwp-score": 41})
ValidationError: 1 validation error for CitizenObservation
scores
  Value error, not observed-tier concept codes: ['ibmwp-score'].
  Screening and laboratory indicators are derived or measured,
  never submitted by an observer.
```

Over HTTP the same submission returns `422`.

Conflating these tiers is the most common error in citizen-science tooling and
it is scientifically indefensible. This project does not claim otherwise; its
purpose is to make citizen observations **route expert effort**, not replace
it.

---

## Design invariant: withholding information must never improve a score

Two selective-reporting loopholes were found by the test suite and closed.
Both are real failure modes in citizen science, and both are usually innocent —
people report what stands out.

**Cherry-picking beat thoroughness.** Renormalising over only the fields
present meant that logging just the two worst things outscored a full
eight-field survey, because the good news never entered the denominator. The
index is now shrunk toward a neutral prior in proportion to how little of the
available evidence weight a submission covers.

**Omitting a field was rewarded.** An observer at a low-flow reach could skip
the flow question to dodge the low-flow discount, scoring 64.4 instead of 54.8
for saying less. Unknown flow now takes the least favourable plausible value.

Both are pinned by tests (`test_selective_reporting_does_not_beat_thorough_reporting`,
`test_omitting_flow_is_not_advantageous`).

---

## FHIR modelling decisions

Targets **FHIR R4B**, because R4 is what is actually deployed across Europe.

**1. `Observation.subject` references a `Location`, not a `Patient`.**
R4 permits `Reference(Patient | Group | Device | Location)`. The subject of a
stream assessment is a place, and saying so honestly is better than minting a
synthetic Patient to stand in for a river.

**2. Evidential tier rides on `Observation.status`.**
Citizen submissions are `preliminary`; laboratory results are `final`. FHIR
already means by those words exactly what we need — a preliminary result is
usable but not yet verified. Reusing them means any FHIR client understands the
distinction with no knowledge of this project:

```
GET /fhir/Observation?status=final       → only laboratory-grade evidence
GET /fhir/Observation?status=preliminary → only citizen evidence
```

**3. Terminology is published as a resolvable `CodeSystem`.**
There is no standard code system for freshwater ecological indicators that a
health information system can consume. LOINC and SNOMED CT cover human clinical
observables. Ours is defined under a project URI and served at
`/fhir/CodeSystem/stream-assessment`, with each concept carrying its tier as a
property, so a consumer cannot mistake a screening score for a WFD status
determination.

**4. Confidence is an extension**, because FHIR has no element for it —
defined under our own URI rather than overloading an existing field.

---

## Conformance with the official OneAquaHealth IG

HL7 Europe maintains a [OneAquaHealth FHIR Implementation
Guide](https://github.com/hl7-eu/oah) (`hl7.eu.fhir.oah`, canonical
`http://hl7.eu/fhir/ig/oah`) that profiles exactly this domain.

**We conform where we can.** Reaches are emitted as `LocationOah`, laboratory
results as `ObservationIndicatorsOah`, both asserted in `meta.profile` and
checked by tests.

One thing is worth recording. We chose `Observation.subject → Location` on our
own reasoning — the subject of a stream assessment is a place, not a patient —
before finding the IG. The IG constrains precisely that:

```
* subject only Reference(LocationOah)
```

**We report where we cannot, rather than overclaiming.**
`ObservationIndicatorsOah` fixes the status:

```
* status = #final
```

In FHIR, `final` asserts a verified result. The profile therefore cannot
represent an *unverified* observation — which is exactly what citizen-science
evidence is. Citizen submissions here use the same shape, codes and Location
subject, carry `status = preliminary`, and **deliberately do not assert the
profile**. Claiming conformance we don't have would let a downstream system
treat a stranger's phone report as laboratory-grade. There is a test for the
negative case.

The gap, and the change that would close it, are stated in
`GET /api/ig-conformance` and in `app/oah_ig.py`.

**Terminology is mapped, not replaced.** `GET
/fhir/ConceptMap/tributary-to-oah` maps our 13 relevant concepts onto the IG's
code system using real FHIR equivalence codes:

| Equivalence | Count | Example |
|---|---|---|
| `equivalent` | 2 | `diatom-teratology-rate` → `diatomTratology` |
| `narrower` | 6 | `ibmwp-score` → `macroinvertebreates` |
| `relatedto` | 1 | `water-clarity` → `tss` |
| `unmatched` | 4 | `sewage-indicators`, `litter-load`, EQR, WFD status |

Unmatched concepts are recorded as unmatched, with the reason, rather than
forced onto an approximate code. A mapping that overstates its fidelity is
worse than an absent one, because downstream analysis cannot see the error.

The unmatched list is itself a finding: the IG has no concept for visible
evidence of untreated discharge — the single most decision-relevant thing a
citizen can report — and `coliforms` is a laboratory measurement of a
different thing.

---

## Scoring: stated judgements, not fitted parameters

Every weight is an inspectable judgement with a written rationale, isolated in
`backend/app/scoring.py`. Sewage indicators carry weight 3.0 because a visible
discharge is the strongest single lay observation; surface foam carries 0.5
because lay observers cannot reliably separate natural from surfactant-driven
foam, and that ambiguity belongs in the weight rather than hidden in a
threshold.

There is no labelled dataset linking citizen scores to laboratory outcomes, so
fitting a model would produce false precision. Transparent weights an ecologist
can disagree with explicitly are the honest design. The weights sit in one
module so that calibration, once paired data exists, is a single-file change.

The sampling priority breakdown is returned term by term and always shown in
the UI, because a monitoring officer deciding where to send a van is entitled
to know why one reach outranked another.

---

## Running it

Requires **Python 3.11** (3.14 has no `pydantic-core` wheel and the Rust build
caps at 3.13) and Node 20+.

```bash
# Backend — http://localhost:8077
cd backend
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/uvicorn app.api:app --port 8077
```

```bash
# Frontend — http://localhost:5173
cd frontend
npm install
npm run dev
```

```bash
# Tests — runs from the repository root or from backend/
./backend/.venv/bin/python -m pytest backend
```

Interactive API docs at <http://localhost:8077/docs>.

---

## Endpoints

Two surfaces, deliberately separate. The dashboard shape may change freely;
the FHIR shape is a contract with external systems. Collapsing them is how
interoperability projects end up with FHIR-shaped resources that nothing else
can consume.

| Dashboard | |
|---|---|
| `GET /api/priority-queue` | Reaches ranked by where the next visit buys most |
| `GET /api/escalations` | The One Health handover queue |
| `GET /api/reaches/{id}` | Observations, screening and laboratory record |
| `GET /api/indicators` | Indicator catalogue by tier, with weights and rationales |
| `GET /api/ig-conformance` | What we conform to in the official IG, and what we cannot |
| `POST /api/observations` | Submit a citizen observation |

| FHIR R4B | |
|---|---|
| `GET /fhir/metadata` | CapabilityStatement |
| `GET /fhir/CodeSystem/stream-assessment` | The terminology, resolvable |
| `GET /fhir/ConceptMap/tributary-to-oah` | Our codes mapped onto the official IG |
| `GET /fhir/Location/{id}` | A stream reach |
| `GET /fhir/Observation/{id}` | One observation |
| `GET /fhir/Observation?subject=&status=` | Searchset Bundle |

---

## Accessibility

Colour was computed rather than chosen. Validating the Water Framework
Directive's five official status colours as a categorical palette **fails**:
Poor and Bad separate by only ΔE 7.1 for normal vision against a floor of 15,
and darkening Bad merely exposes Moderate against Poor at 13.7. A five-class
warm rainbow cannot be rescued by re-stepping.

Rather than silently substitute hues that European water professionals would
not recognise, WFD colours are confined to badge accents that **always carry
the class name as text**, and never encode anything by colour alone. Charts use
a validated four-slot categorical palette with direct labels.

Dark mode is separately stepped for the dark surface, not an automatic flip.

---

## Repository layout

```
backend/
  app/
    terminology.py    Code system; the three evidential tiers
    models.py         Domain model and input validation
    scoring.py        Screening engine; weights and rationales
    fhir_mapping.py   Projection onto FHIR R4B
    store.py          Repository and synthetic demonstration data
    api.py            HTTP surfaces
  tests/              54 tests
frontend/
  src/
    api.ts            Typed client
    components.tsx    Presentation components
    App.tsx           Monitoring officer's view
    theme.css         Design tokens, with colour decisions recorded
```

---

## Data

**All observation data in this repository is synthetic.** It is constructed to
exercise the screening logic across contrasting cases, not to describe the real
condition of any watercourse. Reach names are illustrative. No claim is made
about Coimbra or anywhere else.

The indicators, indices and the diatom-deformity early-warning finding are
drawn from the OneAquaHealth project's published outputs and from the
freshwater biomonitoring literature; the measurements attached to them here are
invented.

---

## Licence

MIT.
