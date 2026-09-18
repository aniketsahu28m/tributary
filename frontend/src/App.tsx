/** Tributary — monitoring officer's view.
 *
 * The screen answers one question: where should the next expert sampling visit
 * go, and why. Everything else is subordinate to that, which is why the
 * priority queue owns the left rail and the score breakdown is always visible
 * rather than hidden behind a click. A ranking nobody can interrogate is a
 * ranking nobody will act on.
 */

import { useEffect, useState } from "react";
import "./theme.css";
import "./App.css";
import {
  ACCESS_LABEL,
  api,
  type QueueRow,
  type ReachDetail,
} from "./api";
import {
  Disclosure,
  EscalationFlag,
  ExpertSampleTable,
  Meter,
  PriorityBreakdown,
  QueueItem,
} from "./components";

export default function App() {
  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReachDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .priorityQueue()
      .then((rows) => {
        setQueue(rows);
        setSelectedId((current) => current ?? rows[0]?.reach.id ?? null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    // Responses can land out of order when the user clicks quickly. Dropping a
    // stale one matters more than usual here: the panel would otherwise show
    // one reach's laboratory record under another reach's name.
    let current = true;
    setDetail(null);
    api
      .reach(selectedId)
      .then((d) => {
        if (current) setDetail(d);
      })
      .catch((e) => {
        if (current) setError(String(e));
      });
    return () => {
      current = false;
    };
  }, [selectedId]);

  if (error) {
    return (
      <main className="shell">
        <div className="panel error-panel">
          <h2>Cannot reach the API</h2>
          <p>{error}</p>
          <p className="muted">
            Expected at <code>{api.base}</code>. Start it with{" "}
            <code>uvicorn app.api:app --port 8077</code> from{" "}
            <code>backend/</code>.
          </p>
        </div>
      </main>
    );
  }

  const escalations = queue?.filter((r) => r.screening.oneHealth.escalate) ?? [];
  const selected = queue?.find((r) => r.reach.id === selectedId) ?? null;

  // `selected` comes from the already-loaded queue and so updates on the very
  // first render after a click, while `detail` arrives a round trip later.
  // Gating on identity rather than nullability keeps the two from ever
  // disagreeing on screen, even for a single frame.
  const loadedDetail = detail?.reach.id === selectedId ? detail : null;

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1>Tributary</h1>
          <p className="tagline">
            Citizen stream observations, triaged into expert sampling priority
            and published as FHIR.
          </p>
        </div>
        <dl className="masthead-stats">
          <div>
            <dt>Reaches monitored</dt>
            <dd>{queue?.length ?? "—"}</dd>
          </div>
          <div>
            <dt>One Health escalations</dt>
            <dd className={escalations.length ? "is-critical" : ""}>
              {queue ? escalations.length : "—"}
            </dd>
          </div>
        </dl>
      </header>

      <div className="columns">
        <section className="panel queue-panel" aria-labelledby="queue-heading">
          <h2 id="queue-heading">Sampling priority</h2>
          <p className="panel-note">
            Where the next laboratory visit buys the most. Ranked by exposure
            and evidence, not by how polluted a stream looks.
          </p>
          {queue === null ? (
            <p className="empty">Loading…</p>
          ) : (
            <ol className="queue">
              {queue.map((row, i) => (
                <QueueItem
                  key={row.reach.id}
                  rank={i + 1}
                  reach={row.reach}
                  screening={row.screening}
                  selected={row.reach.id === selectedId}
                  onSelect={() => setSelectedId(row.reach.id)}
                />
              ))}
            </ol>
          )}
        </section>

        <section className="panel detail-panel" aria-live="polite">
          {selected === null ? (
            <p className="empty">Select a reach.</p>
          ) : (
            <>
              <div className="detail-head">
                <div>
                  <h2>{selected.reach.name}</h2>
                  <p className="muted">
                    {selected.reach.waterBody} · {selected.reach.municipality} ·{" "}
                    {ACCESS_LABEL[selected.reach.access]} ·{" "}
                    {selected.reach.populationWithin500m.toLocaleString()}{" "}
                    residents within 500 m
                  </p>
                </div>
                <EscalationFlag
                  escalate={selected.screening.oneHealth.escalate}
                />
              </div>

              <p className="reason">{selected.screening.oneHealth.reason}</p>

              <div className="figure">
                <div className="figure-head">
                  <h3>Why this rank</h3>
                  <span className="hero">{selected.screening.priority}</span>
                </div>
                <PriorityBreakdown
                  terms={selected.screening.priorityTerms}
                  total={selected.screening.priority}
                />
              </div>

              <div className="meters">
                <Meter
                  label="Visual pressure index"
                  value={selected.screening.visualPressureIndex}
                />
                <Meter
                  label="Observation confidence"
                  value={Math.round(selected.screening.confidence * 100)}
                  suffix="%"
                />
              </div>

              <Disclosure summary="What these numbers are, and are not">
                <p>
                  The visual pressure index is a screening composite of what a
                  person can see from the bank. It is <strong>not</strong> an
                  Ecological Quality Ratio and carries no Water Framework
                  Directive reporting status. IBMWP and diatom teratology
                  require kick-net sampling and microscopy; no phone
                  observation can produce them, and this system does not
                  pretend otherwise.
                </p>
                <p>
                  Weights are stated judgements rather than fitted parameters.
                  With no paired citizen and laboratory data to calibrate
                  against, a fitted model would be false precision.
                </p>
              </Disclosure>

              <section aria-labelledby="lab-heading">
                <h3 id="lab-heading">Laboratory record</h3>
                {/* "Never sampled" is a claim about the world, not a way to
                    render an empty array. While the request is in flight we do
                    not yet know, so we must not assert it. */}
                {loadedDetail === null ? (
                  <p className="empty">Loading…</p>
                ) : (
                  <ExpertSampleTable samples={loadedDetail.expertSamples} />
                )}
              </section>

              <section aria-labelledby="obs-heading">
                <h3 id="obs-heading">
                  Citizen reports
                  {loadedDetail ? ` (${loadedDetail.observations.length})` : ""}
                </h3>
                <ul className="obs-list">
                  {(loadedDetail?.observations ?? []).map((o) => (
                    <li key={o.id}>
                      <div className="obs-head">
                        <span className="obs-when">
                          {new Date(o.recordedAt).toLocaleString()}
                        </span>
                        <span className="obs-conf">
                          confidence{" "}
                          {Math.round(o.screening.confidence * 100)}%
                        </span>
                      </div>
                      {o.note && <p className="obs-note">“{o.note}”</p>}
                      <div className="obs-scores">
                        {Object.entries(o.scores).map(([code, value]) => (
                          <span key={code} className="chip">
                            {code.replace(/-/g, " ")}{" "}
                            <strong>{value}</strong>
                          </span>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <p className="fhir-link">
                Interoperability:{" "}
                <a
                  href={`${api.base}/fhir/Observation?subject=Location/${selected.reach.id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  FHIR Bundle for this reach
                </a>{" "}
                ·{" "}
                <a
                  href={`${api.base}/fhir/CodeSystem/stream-assessment`}
                  target="_blank"
                  rel="noreferrer"
                >
                  CodeSystem
                </a>
              </p>
            </>
          )}
        </section>
      </div>

      <footer className="footnote">
        All observation data shown is synthetic, constructed to exercise the
        screening logic. It makes no claim about the condition of any real
        watercourse.
      </footer>
    </div>
  );
}
