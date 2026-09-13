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

export type EvidenceLevel = "confirmed" | "strongly_inferred" | "possible" | "conflicting" | "unknown";
export type EntityClass = "person" | "robot" | "forklift" | "pallet";
export type EventType =
  | "zone_entry"
  | "zone_exit"
  | "stop"
  | "direction_change"
  | "proximity"
  | "occlusion_start"
  | "occlusion_end"
  | "state_change";
export type NodeType = "entity" | "observation" | "event" | "location" | "interval" | "gap" | "conflict";
export type Relation =
  | "observed_as"
  | "precedes"
  | "co_occurs"
  | "near"
  | "same_entity_as"
  | "occludes"
  | "candidate_cause_of"
  | "contradicts";

/** The only words each evidence level may use: `ALLOWED_LANGUAGE` in the contract. */
export const EVIDENCE_LABEL: Record<EvidenceLevel, string> = {
  confirmed: "Observed",
  strongly_inferred: "Likely contributed",
  possible: "Possible",
  conflicting: "Conflicting evidence",
  unknown: "Cannot determine",
};

export interface Provenance {
  producer_service: string;
  producer_version: string;
  run_id: string;
  created_at: string;
  derived_from: string[];
}

export interface Camera {
  camera_id: string;
  name: string;
  source_uri: string;
  timezone: string;
  clock_offset_s: number;
  width: number;
  height: number;
  fps: number;
  calibration_ref: string | null;
}

export interface ProcessingRun {
  run_id: string;
  input_hash: string;
  dataset_version: string;
  model_versions: Record<string, string>;
  config_version: string;
  status: string;
  device: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface CaseDetail {
  incident: Incident;
  run: ProcessingRun;
  cameras: Camera[];
}

export interface SemanticEvent {
  event_id: string;
  run_id: string;
  event_type: EventType;
  timestamp_s: number;
  camera_id: string | null;
  entity_ids: string[];
  zone_id: string | null;
  confidence: number;
  evidence_refs: string[];
  payload: Record<string, unknown>;
}

export interface TrackSegment {
  segment_id: string;
  run_id: string;
  camera_id: string;
  local_track_id: string;
  entity_class: EntityClass;
  start_time_s: number;
  end_time_s: number;
  observation_ids: string[];
  mean_confidence: number;
}

export interface IdentityLink {
  link_id: string;
  run_id: string;
  segment_a: string;
  segment_b: string;
  decision: "linked" | "unknown";
  score: number;
  threshold: number;
  components: Record<string, number>;
  evidence_refs: string[];
}

export interface Timeline {
  run_id: string;
  start_s: number | null;
  end_s: number | null;
  events: SemanticEvent[];
  segments: TrackSegment[];
  identity_links: IdentityLink[];
}

export interface EvidenceNode {
  node_id: string;
  incident_id: string;
  node_type: NodeType;
  label: string;
  timestamp_s: number | null;
  interval_s: [number, number] | null;
  source_ref: string | null;
  confidence: number;
  provenance: Provenance;
}

export interface EvidenceEdge {
  edge_id: string;
  incident_id: string;
  from_node: string;
  to_node: string;
  relation: Relation;
  weight: number;
  provenance: Provenance;
}

export interface EvidenceGraph {
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
}

export interface Hypothesis {
  hypothesis_id: string;
  incident_id: string;
  description: string;
  evidence_level: EvidenceLevel;
  score: number;
  support_refs: string[];
  contradiction_refs: string[];
  components: Record<string, number>;
}

export interface Claim {
  claim_id: string;
  text: string;
  evidence_level: EvidenceLevel;
  evidence_refs: string[];
}

export interface Report {
  report_id: string;
  run_id: string;
  incident_id: string;
  generator_version: string;
  created_at: string;
  summary: string;
  claims: Claim[];
  ranked_hypotheses: string[];
  gaps: string[];
  limitations: string;
}

export interface CaseReport {
  report: Report;
  hypotheses: Hypothesis[];
}

export interface Health {
  status: string;
  api_version: string;
  schema_version: string;
  checked_at: string;
  mock?: boolean;
}

/** The spec §N metric set. `null` means not measured, never zero: see services/observability/metrics.py. */
export interface Metrics {
  queue_depth: number | null;
  queue_oldest_age_s: number | null;
  worker_last_seen_s: number | null;
  frames_per_second: number | null;
  tracking_id_switch_rate: number | null;
  event_generation_rate: number | null;
  incident_detection_rate: number | null;
  report_generation_latency_s: number | null;
  api_error_rate: number | null;
  worker_retries: number | null;
  dead_letter_jobs: number | null;
  evidence_coverage: number | null;
  unsupported_claim_rate: number | null;
}

export interface RunList {
  runs: ProcessingRun[];
  total: number;
}

/** A dismissal is how a false alert is recorded, so the label says so. */
export const STATUS_LABEL: Record<IncidentStatus, string> = {
  new: "New",
  investigating: "Investigating",
  resolved: "Resolved",
  dismissed: "Dismissed (false alert)",
};
