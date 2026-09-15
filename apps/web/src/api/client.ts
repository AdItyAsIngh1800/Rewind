import type {
  CaseDetail,
  CaseList,
  CaseReport,
  CreateCaseResponse,
  EvidenceGraph,
  Health,
  Incident,
  IncidentStatus,
  Me,
  Metrics,
  Replay,
  RunList,
  Source,
  Timeline,
} from "./types";

const BASE = "/api/v1";

/** A non-2xx answer, keeping the status so the shell can tell "signed out" from "broken". */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Called on any 401, so the shell can show the login page whatever query hit it. */
export let onUnauthorized: () => void = () => {};
export function setOnUnauthorized(fn: () => void) {
  onUnauthorized = fn;
}

/** Call the API, throwing on non-2xx so TanStack Query sees an error state. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    if (res.status === 401) onUnauthorized();
    // FastAPI puts the reason in `detail`; "case X has no report; reprocess its run"
    // tells an investigator more than "404 Not Found".
    const detail = await res.json().then((b: { detail?: unknown }) => b.detail, () => undefined);
    throw new ApiError(typeof detail === "string" ? detail : `${res.status} ${res.statusText} for ${path}`, res.status);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

function get<T>(path: string, params?: object): Promise<T> {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {}) as [string, string | undefined][]) if (v) query.set(k, v);
  return request<T>(query.size ? `${path}?${query}` : path);
}

export interface CaseFilters {
  severity?: string;
  status?: string;
  limit?: string;
}

const casePath = (id: string, rest = "") => `/cases/${encodeURIComponent(id)}${rest}`;

export const api = {
  listCases: (filters: CaseFilters) => get<CaseList>("/cases", filters),
  getCase: (id: string) => get<CaseDetail>(casePath(id)),
  getTimeline: (id: string) => get<Timeline>(casePath(id, "/timeline")),
  getEvidence: (id: string) => get<EvidenceGraph>(casePath(id, "/evidence")),
  getReport: (id: string) => get<CaseReport>(casePath(id, "/report")),
  getReplay: (id: string) => get<Replay>(casePath(id, "/replay")),
  setCaseStatus: (id: string, status: IncidentStatus) =>
    request<Incident>(casePath(id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  getHealth: () => get<Health>("/health"),
  me: () => get<Me>("/me"),
  login: (name: string, password: string) =>
    request<Me>("/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, password }),
    }),
  logout: () => request<void>("/session", { method: "DELETE" }),
  getMetrics: () => get<Metrics>("/metrics"),
  listRuns: (limit = 50) => get<RunList>("/runs", { limit: String(limit) }),
  listSources: () => get<Source[]>("/sources"),
  createCase: (case_ref: string, dataset_version: string) =>
    request<CreateCaseResponse>("/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_ref, dataset_version }),
    }),
};
