import type { CaseDetail, CaseList, CaseReport, EvidenceGraph, Timeline } from "./types";

const BASE = "/api/v1";

/** Fetch JSON from the API, throwing on non-2xx so TanStack Query sees an error state. */
async function get<T>(path: string, params?: object): Promise<T> {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {}) as [string, string | undefined][]) if (v) query.set(k, v);
  const suffix = query.size ? `?${query}` : "";
  const res = await fetch(`${BASE}${path}${suffix}`);
  if (!res.ok) {
    // FastAPI puts the reason in `detail`; "case X has no report; reprocess its run"
    // tells an investigator more than "404 Not Found".
    const detail = await res.json().then((b: { detail?: unknown }) => b.detail, () => undefined);
    throw new Error(typeof detail === "string" ? detail : `${res.status} ${res.statusText} for ${path}`);
  }
  return (await res.json()) as T;
}

export interface CaseFilters {
  severity?: string;
  status?: string;
}

const casePath = (id: string, rest = "") => `/cases/${encodeURIComponent(id)}${rest}`;

export const api = {
  listCases: (filters: CaseFilters) => get<CaseList>("/cases", filters),
  getCase: (id: string) => get<CaseDetail>(casePath(id)),
  getTimeline: (id: string) => get<Timeline>(casePath(id, "/timeline")),
  getEvidence: (id: string) => get<EvidenceGraph>(casePath(id, "/evidence")),
  getReport: (id: string) => get<CaseReport>(casePath(id, "/report")),
};
