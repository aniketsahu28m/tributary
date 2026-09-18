/** Typed client for the Tributary dashboard API.
 *
 * Only the /api surface is consumed here. The /fhir surface exists for other
 * systems, and the dashboard deliberately does not read it: if the UI depended
 * on FHIR shapes, every UI convenience would start leaking into a contract that
 * external consumers rely on.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8077";

export type AccessLevel = "none" | "visual" | "bankside" | "recreational";

export interface Reach {
  id: string;
  name: string;
  waterBody: string;
  municipality: string;
  country: string;
  latitude: number;
  longitude: number;
  access: AccessLevel;
  populationWithin500m: number;
}

export interface Observation {
  id: string;
  reachId: string;
  observerId: string;
  recordedAt: string;
  scores: Record<string, number>;
  photoCount: number;
  note: string | null;
}

export interface PriorityTerms {
  visual_pressure: number;
  one_health_escalation: number;
  sampling_staleness: number;
  population_exposed: number;
}

export interface Screening {
  visualPressureIndex: number;
  confidence: number;
  priority: number;
  priorityTerms: PriorityTerms;
  oneHealth: {
    escalate: boolean;
    exposureFactor: number;
    reason: string;
  };
}

export interface QueueRow {
  reach: Reach;
  latestObservation: Observation;
  screening: Screening;
  lastExpertSample: string | null;
}

export interface ExpertSample {
  id: string;
  reachId: string;
  sampledAt: string;
  laboratory: string;
  ibmwpScore: number | null;
  diatomTeratologyRate: number | null;
  ecologicalQualityRatio: number | null;
  wfdStatus: string | null;
  wfdStatusDisplay: string | null;
}

export interface ReachDetail {
  reach: Reach;
  observations: (Observation & { screening: Screening })[];
  expertSamples: ExpertSample[];
  lastExpertSample: string | null;
}

export interface Indicator {
  code: string;
  display: string;
  definition: string;
  unit: string | null;
  pressureWeight: number | null;
  inverted: boolean | null;
  rationale: string | null;
}

export interface IndicatorCatalogue {
  tiers: {
    observed: Indicator[];
    screened: Indicator[];
    laboratory: Indicator[];
  };
}

export interface Escalation {
  reach: Reach;
  observation: Observation;
  screening: Screening;
  fhir: string;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  base: BASE,
  priorityQueue: () => get<QueueRow[]>("/api/priority-queue"),
  escalations: () => get<Escalation[]>("/api/escalations"),
  reach: (id: string) => get<ReachDetail>(`/api/reaches/${id}`),
  indicators: () => get<IndicatorCatalogue>("/api/indicators"),

  async submitObservation(body: {
    id: string;
    reach_id: string;
    observer_id: string;
    scores: Record<string, number>;
    photo_count: number;
    note?: string;
  }): Promise<Observation & { screening: Screening }> {
    const response = await fetch(`${BASE}/api/observations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      // 422 carries the validation message that explains *why* a code was
      // refused, which is the most useful thing to show a submitter.
      const detail = await response.json().catch(() => null);
      throw new Error(
        detail?.detail?.[0]?.msg ?? detail?.detail ?? `HTTP ${response.status}`,
      );
    }
    return response.json();
  },
};

export const ACCESS_LABEL: Record<AccessLevel, string> = {
  none: "No public access",
  visual: "Visible only",
  bankside: "Bankside access",
  recreational: "Recreational use",
};

export const TERM_LABEL: Record<keyof PriorityTerms, string> = {
  visual_pressure: "Visual pressure",
  one_health_escalation: "One Health escalation",
  sampling_staleness: "Sampling overdue",
  population_exposed: "Population exposed",
};

export const TERM_COLOR: Record<keyof PriorityTerms, string> = {
  visual_pressure: "var(--series-1)",
  one_health_escalation: "var(--series-2)",
  sampling_staleness: "var(--series-3)",
  population_exposed: "var(--series-4)",
};

export const TERM_ORDER: (keyof PriorityTerms)[] = [
  "visual_pressure",
  "one_health_escalation",
  "sampling_staleness",
  "population_exposed",
];
