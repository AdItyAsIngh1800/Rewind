import type {
  EvidenceEdge,
  EvidenceGraph,
  EvidenceLevel,
  EvidenceNode,
  Hypothesis,
  IdentityLink,
  SemanticEvent,
  Timeline,
  TrackSegment,
} from "@/api/types";
import { clock } from "./format";

/** Everything a case serves that an evidence id can point into. */
export interface CaseEvidence {
  graph?: EvidenceGraph;
  timeline?: Timeline;
  hypotheses?: Hypothesis[];
}

export type Resolved =
  | { kind: "node"; node: EvidenceNode; edges: EvidenceEdge[] }
  | { kind: "event"; event: SemanticEvent; node?: EvidenceNode }
  | { kind: "hypothesis"; hypothesis: Hypothesis }
  | { kind: "segment"; segment: TrackSegment; links: IdentityLink[] }
  | { kind: "link"; link: IdentityLink }
  | { kind: "missing" };

/**
 * Find what an id names. Reports cite graph nodes, events and hypotheses side by side,
 * and provenance cites segments and links, so one lookup serves every place an id is
 * shown. An id that resolves to nothing is reported as missing, never hidden.
 */
export function resolveRef(id: string, ev: CaseEvidence): Resolved {
  const node = ev.graph?.nodes.find((n) => n.node_id === id);
  if (node && ev.graph) {
    return { kind: "node", node, edges: ev.graph.edges.filter((e) => e.from_node === id || e.to_node === id) };
  }
  const event = ev.timeline?.events.find((e) => e.event_id === id);
  if (event) return { kind: "event", event, node: ev.graph?.nodes.find((n) => n.source_ref === id) };
  const hypothesis = ev.hypotheses?.find((h) => h.hypothesis_id === id);
  if (hypothesis) return { kind: "hypothesis", hypothesis };
  const segment = ev.timeline?.segments.find((s) => s.segment_id === id);
  if (segment && ev.timeline) {
    const links = ev.timeline.identity_links.filter((l) => l.segment_a === id || l.segment_b === id);
    return { kind: "segment", segment, links };
  }
  const link = ev.timeline?.identity_links.find((l) => l.link_id === id);
  if (link) return { kind: "link", link };
  return { kind: "missing" };
}

/**
 * The PS-8 state a graph node is drawn in. Nodes carry no level of their own: a gap is
 * the absence of sight, a conflict is evidence disagreeing with itself, and every other
 * node was read from observations.
 */
export function nodeLevel(node: EvidenceNode): EvidenceLevel {
  if (node.node_type === "gap") return "unknown";
  if (node.node_type === "conflict") return "conflicting";
  return "confirmed";
}

/** When a node happened, as the timeline writes it; empty for timeless nodes. */
export function nodeTime(node: EvidenceNode): string {
  if (node.interval_s) return `${clock(node.interval_s[0])}–${clock(node.interval_s[1])}`;
  if (node.timestamp_s !== null) return clock(node.timestamp_s);
  return "";
}

/** Axis ticks at a round step, about `target` of them across the span. */
export function ticks(start: number, end: number, target = 8): number[] {
  const step = [1, 2, 5, 10, 15, 30, 60].find((s) => (end - start) / s <= target) ?? 120;
  const out: number[] = [];
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) out.push(t);
  return out;
}

/** Snake-case contract values as words: `zone_entry` → `zone entry`. */
export const words = (value: string) => value.replaceAll("_", " ");

/**
 * The shared-timebase moment an id points at, for seeking the replay: an event's time,
 * a node's time or the start of its interval, a track's first sighting. A ranked cause
 * seeks to the first of its supporting ids that has a time, the approach it rests on.
 * `null` for what has no moment, such as an entity or a place.
 */
export function refTime(id: string, ev: CaseEvidence, nested = false): number | null {
  const r = resolveRef(id, ev);
  switch (r.kind) {
    case "event":
      return r.event.timestamp_s;
    case "node":
      return r.node.timestamp_s ?? r.node.interval_s?.[0] ?? null;
    case "segment":
      return r.segment.start_time_s;
    case "hypothesis":
      if (nested) return null;
      for (const support of r.hypothesis.support_refs) {
        const t = refTime(support, ev, true);
        if (t !== null) return t;
      }
      return null;
    default:
      return null;
  }
}
