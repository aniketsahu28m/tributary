/** Presentation components.
 *
 * Two rules hold throughout, both from the visualisation method:
 *   - Colour never carries meaning alone. Every status accent sits beside a
 *     text label, and every chart segment is directly labelled.
 *   - Text wears text tokens, never a series colour. A coloured swatch next to
 *     a label carries the identity; the label itself stays in ink.
 */

import { useState } from "react";
import {
  ACCESS_LABEL,
  TERM_COLOR,
  TERM_LABEL,
  TERM_ORDER,
  type ExpertSample,
  type PriorityTerms,
  type Reach,
  type Screening,
} from "./api";

/* ------------------------------------------------------------------ */
/* Status                                                              */
/* ------------------------------------------------------------------ */

const WFD_COLOR: Record<string, string> = {
  high: "var(--wfd-high)",
  good: "var(--wfd-good)",
  moderate: "var(--wfd-moderate)",
  poor: "var(--wfd-poor)",
  bad: "var(--wfd-bad)",
};

/** A WFD ecological status class.
 *
 * The class name is always rendered as text. See theme.css for why this
 * palette is never allowed to encode data by colour alone.
 */
export function WfdBadge({ status, display }: { status: string; display: string }) {
  return (
    <span className="badge">
      <span
        className="badge-dot"
        style={{ background: WFD_COLOR[status] ?? "var(--text-muted)" }}
        aria-hidden="true"
      />
      {display}
    </span>
  );
}

export function EscalationFlag({ escalate }: { escalate: boolean }) {
  if (!escalate) {
    return (
      <span className="flag flag-calm">
        <span aria-hidden="true">○</span> Environmental follow-up
      </span>
    );
  }
  return (
    <span className="flag flag-critical">
      <span aria-hidden="true">▲</span> One Health escalation
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Meters and bars                                                     */
/* ------------------------------------------------------------------ */

/** A single ratio against a limit. A meter, not a one-bar bar chart. */
export function Meter({
  label,
  value,
  max = 100,
  suffix = "",
}: {
  label: string;
  value: number;
  max?: number;
  suffix?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="meter">
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <span className="meter-value">
          {value}
          {suffix}
        </span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        <div className="meter-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Part-to-whole breakdown of a sampling-priority score.
 *
 * Horizontal stacked bar: four series with long names, which is exactly the
 * case the form guidance sends horizontal. Segments are directly labelled in
 * the legend below rather than inside the bar, because at these widths an
 * in-bar number collides at the first narrow segment.
 */
export function PriorityBreakdown({
  terms,
  total,
}: {
  terms: PriorityTerms;
  total: number;
}) {
  const present = TERM_ORDER.filter((key) => terms[key] > 0);

  return (
    <div className="breakdown">
      <div className="breakdown-bar" role="img"
        aria-label={
          `Sampling priority ${total} of 100, composed of ` +
          present.map((k) => `${TERM_LABEL[k]} ${terms[k]}`).join(", ")
        }
      >
        {present.map((key) => (
          <div
            key={key}
            className="breakdown-seg"
            style={{
              width: `${(terms[key] / 100) * 100}%`,
              background: TERM_COLOR[key],
            }}
          />
        ))}
        <div className="breakdown-remainder" />
      </div>
      <ul className="breakdown-legend">
        {TERM_ORDER.map((key) => (
          <li key={key} className={terms[key] > 0 ? "" : "is-zero"}>
            <span
              className="legend-swatch"
              style={{ background: TERM_COLOR[key] }}
              aria-hidden="true"
            />
            <span className="legend-label">{TERM_LABEL[key]}</span>
            <span className="legend-value">{terms[key].toFixed(1)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Queue                                                               */
/* ------------------------------------------------------------------ */

export function QueueItem({
  rank,
  reach,
  screening,
  selected,
  onSelect,
}: {
  rank: number;
  reach: Reach;
  screening: Screening;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={`queue-item${selected ? " is-selected" : ""}`}
        onClick={onSelect}
        aria-current={selected ? "true" : undefined}
      >
        <span className="queue-rank">{rank}</span>
        <span className="queue-body">
          <span className="queue-name">{reach.name}</span>
          <span className="queue-meta">
            {ACCESS_LABEL[reach.access]} ·{" "}
            {reach.populationWithin500m.toLocaleString()} within 500 m
          </span>
          <span className="queue-track" aria-hidden="true">
            <span
              className="queue-fill"
              style={{ width: `${screening.priority}%` }}
            />
          </span>
        </span>
        <span className="queue-score">
          <span className="queue-score-value">{screening.priority}</span>
          {screening.oneHealth.escalate && (
            <span className="queue-escalate" title="One Health escalation">
              ▲
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

/* ------------------------------------------------------------------ */
/* Expert samples                                                      */
/* ------------------------------------------------------------------ */

export function ExpertSampleTable({ samples }: { samples: ExpertSample[] }) {
  if (samples.length === 0) {
    return (
      <p className="empty">
        Never sampled by a laboratory. Ecological status is therefore unknown —
        citizen screening cannot determine it.
      </p>
    );
  }
  return (
    // A six-column result table cannot fit a phone. Letting the table scroll
    // inside its own box keeps the page itself free of horizontal scroll,
    // which is the thing that actually breaks reading.
    <div className="table-scroll" tabIndex={0} role="group"
      aria-label="Laboratory results, scrollable horizontally">
    <table className="data-table">
      <caption className="sr-only">Laboratory results for this reach</caption>
      <thead>
        <tr>
          <th scope="col">Sampled</th>
          <th scope="col">Laboratory</th>
          <th scope="col">IBMWP</th>
          <th scope="col">Teratology /1000</th>
          <th scope="col">EQR</th>
          <th scope="col">WFD status</th>
        </tr>
      </thead>
      <tbody>
        {samples.map((s) => (
          <tr key={s.id}>
            <td>{new Date(s.sampledAt).toLocaleDateString()}</td>
            <td>{s.laboratory}</td>
            <td className="num">{s.ibmwpScore ?? "—"}</td>
            <td className="num">{s.diatomTeratologyRate ?? "—"}</td>
            <td className="num">{s.ecologicalQualityRatio ?? "—"}</td>
            <td>
              {s.wfdStatus && s.wfdStatusDisplay ? (
                <WfdBadge status={s.wfdStatus} display={s.wfdStatusDisplay} />
              ) : (
                "—"
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Disclosure                                                          */
/* ------------------------------------------------------------------ */

export function Disclosure({
  summary,
  children,
}: {
  summary: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="disclosure">
      <button
        type="button"
        className="disclosure-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span> {summary}
      </button>
      {open && <div className="disclosure-body">{children}</div>}
    </div>
  );
}
