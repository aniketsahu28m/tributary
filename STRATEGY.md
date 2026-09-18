# OneAquaHealth IEEE Global Hackathon — Strategy

**Submission deadline:** Sept 30, 2026 @ 9:00 PM PDT (~12 days)
**Judging:** Oct 1–15 · **Winners announced:** Oct 24 (IEEE iGET Conference)
**Cash:** $1,500 / $1,000 / $500 / 2 × $250 — five cash slots, ~846 registrants
**Eligibility:** individuals OR teams (solo is allowed — rules page confirms)
**Registration:** rules page says closed Aug 31, but the Devpost "Join hackathon"
button is live. Register immediately; do not assume it stays open.

## Judging weights (from the Rules page)

| Criterion | Weight |
|---|---|
| Impact & Alignment with OneAquaHealth mission | **30%** |
| Innovation & Creativity | 20% |
| Technical Implementation | 20% |
| Usability & UX | 15% |
| Feasibility & Scalability | 15% |

Alignment is the single biggest line item. Most entrants will build a generic
water-quality dashboard without ever reading the EU project's actual outputs.
Tight alignment with the real project is the cheapest 30% on the board.

## Reading the judging panel

| Judge | Signal |
|---|---|
| **Gora Datta** — FHL7, SMIEEE, SMACM | HL7 Fellow. Standards/FHIR person. |
| **Maria João Feio, PhD** — OneAquaHealth coordinator | Freshwater ecologist. Will spot fake ecology instantly. |
| **Harm op den Akker, Ângela Freitas** — SHINE 2Europe | eHealth / digital health project partners. |
| **Pradyumna Kodgi** — Oracle PM, IEEE EMBS | Biomedical engineering society. |
| **Alexander Nikolov** (SYNYO), **George Koutalieris** (ENORA) | EU consortium partners. |
| **David E. González** — IEEE Blockchain TC | Blockchain. |

Panel skews heavily toward **One Digital Health, standards, and EU-project
people** — not generic startup judges. Education Session 4 was a hands-on
**HL7 FHIR** sandbox, and Session 3 covered **FAIR principles**. The organizers
are signposting what they want built.

## Track choice: Track 7 (Digital Health Standards), blended with Track 3

Seven tracks are offered. Expect the field to crowd into Tracks 1, 4 and 5
(UX, storytelling, gamification) because they're the easiest to prototype.

**Track 7 will be the emptiest**, because FHIR is intimidating and most student
teams won't touch it — while it is simultaneously the track with an actual HL7
Fellow on the panel. That is the gap.

### The concept

Make "One Health" literally computable: a pipeline that takes citizen-science
stream observations and emits **standards-compliant FHIR resources**, so
ecosystem data can flow into health information systems alongside human health
data. Add a human-in-the-loop AI layer (Track 3) that flags low-confidence
citizen observations before they enter the record.

**Why this scores:**
- *Impact/Alignment (30%)* — directly serves the project's stated interoperability
  goal and the One Health framing.
- *Innovation (20%)* — FHIR has no native resource for a stream macroinvertebrate
  index. Modelling one via FHIR Observation profiles + a CodeSystem is a real,
  defensible technical contribution, not a gimmick.
- *Technical (20%)* — substantial and verifiable.
- *Feasibility (15%)* — standards compliance IS the scalability story.

The weak spot is UX (15%), so the demo needs a clean front end, not raw JSON.

## 12-day plan

| Days | Work |
|---|---|
| 1 | Register on Devpost. Read the OneAquaHealth policy brief + citizen science app docs. Lock the concept. |
| 2–3 | Data model: FHIR profiles for stream observations; CodeSystem for ecological indicators. |
| 4–7 | Build: ingestion, AI validation layer, FHIR export, dashboard. |
| 8–9 | UX pass. Real seed data. Deploy live demo. |
| 10 | README + architecture docs + Devpost write-up. |
| 11 | Demo video (3–5 min, required). |
| 12 | Buffer. Submit early — never on deadline day. |

## Required submission checklist

- [ ] Track alignment stated explicitly
- [ ] Project description: problem, solution, target users, expected impact
- [ ] Demo video, **3–5 minutes** (hard requirement)
- [ ] Public GitHub repo with source + documentation (hard requirement)
- [ ] Working prototype / demo link

## Caveat to keep in view

The Prizes section lists "$1,500 in cash" etc. with no disclaimer, but the Rules
page says "5000$ Cash/InKind Prize TBD" and "All Cash Prizes Subject to IEEE
rules and regulation for any monetary disbursement." IEEE is a real standards
body so the money is credible, but the exact cash/in-kind split is not fully
nailed down. The IEEE credential and conference visibility have independent value.
