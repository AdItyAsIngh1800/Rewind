import type { CaseList } from "./types";

const BASE = "/api/v1";

/** Fetch JSON from the API, throwing on non-2xx so TanStack Query sees an error state. */
async function get<T>(path: string, params?: object): Promise<T> {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {}) as [string, string | undefined][]) if (v) query.set(k, v);
  const suffix = query.size ? `?${query}` : "";
  const res = await fetch(`${BASE}${path}${suffix}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return (await res.json()) as T;
}

export interface CaseFilters {
  severity?: string;
  status?: string;
}

export const api = {
  listCases: (filters: CaseFilters) => get<CaseList>("/cases", filters),
};
