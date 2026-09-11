// Mirrors packages/schemas (SCHEMA_VERSION 1.0.0). Field names and enum values are
// the frozen contract; changing one here without changing the Pydantic model is a
// bug that the fixture round-trip in E8.6 will surface.

export type Severity = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "new" | "investigating" | "resolved" | "dismissed";
export type IncidentClass = "robot_estop_human_incursion" | "zone_blocked_unattended_object";

export interface Incident {
  schema_version: string;
  incident_id: string;
  run_id: string;
  incident_class: IncidentClass;
  trigger_event_id: string;
  detected_at_s: number;
  window_start_s: number;
  window_end_s: number;
  severity: Severity;
  status: IncidentStatus;
}

export interface CaseList {
  cases: Incident[];
  total: number;
}

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
export const STATUSES: IncidentStatus[] = ["new", "investigating", "resolved", "dismissed"];

/** Investigator-facing wording for each incident class, from the charter. */
export const INCIDENT_CLASS_LABEL: Record<IncidentClass, string> = {
  robot_estop_human_incursion: "Robot e-stop after human incursion",
  zone_blocked_unattended_object: "Zone blocked by unattended object",
};
