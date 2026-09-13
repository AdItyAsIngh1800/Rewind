"""Score the reconstruction: cause ranking, named gaps and report grounding (E7.5).

The Gate 4 and Gate 5 numbers. For each tune case with an incident, in two modes
(perfect tracks and the real pipeline, as for events), this builds the evidence graph,
ranks hypotheses and writes the report exactly as a processing run does, then scores:

- **Cause top-1 / top-3.** Whether the entity behind the annotated cause
  (`cause_gt.json`) is the entity of the first, or one of the first three, hypotheses.
  A hypothesis names its entity as a graph node whose provenance lists the track
  segments behind it; those segments are matched to true entities as in EXP-0004.
- **Gap recall and precision**, in seconds, against `gaps_gt.json` clipped to the
  investigation window, per entity. Recall asks how much truly unseen time the graph
  names; precision how much of what it names was truly unseen.
- **Evidence coverage** and the **unsupported-claim rate** of the report, with the
  benchmark's own metric functions.

    uv run python scripts/evaluation/reasoning_on_detections.py
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime

from packages.common.camera import CameraModel
from packages.evaluation.metrics import evidence_coverage, unsupported_claim_rate
from packages.schemas import IdentityLink, NodeType, Observation, Relation, TrackSegment
from scripts.evaluation.events_on_detections import run_perception
from scripts.evaluation.events_on_truth import REPORTS, SAMPLES, SCENE, perfect_tracks
from scripts.evaluation.incidents_on_detections import CASES_CONFIG, TRUTH
from scripts.evaluation.tracking_on_detections import assign_identities
from services.events import (
    EventConfig,
    class_heights,
    extract_events,
    load_zones,
    localise_all,
    merge_across_cameras,
)
from services.evidence import EvidenceGraph, build_graph
from services.identity import associate, build_segment_tracks, entity_groups
from services.incidents import IncidentConfig, detect_incidents, load_case_script, state_changes
from services.observability.logging import configure_logging
from services.reasoning.hypotheses import rank_hypotheses
from services.reporting import generate_report
from services.tracking import segments_from_observations

log = logging.getLogger(__name__)

#: The entity behind each annotated cause (`cause_gt.json`), for the cases with one.
CAUSE_ENTITY = {"case_01": "P01", "case_03": "P01", "case_04": "F01"}


def _interval_overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _union(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping intervals.

    One true entity split into two tracked fragments gets a gap node per fragment, and
    those overlap; scoring them separately counts the same unseen second twice.
    """
    merged: list[tuple[float, float]] = []
    for lo, hi in sorted(spans):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _entity_of_node(
    graph: EvidenceGraph, node_id: str, truth_of_segment: dict[str, str]
) -> str | None:
    """Majority true entity of the segments an entity node was built from."""
    node = graph.node(node_id)
    votes = Counter(
        truth_of_segment[s] for s in node.provenance.derived_from if s in truth_of_segment
    )
    return votes.most_common(1)[0][0] if votes else None


def score_case(
    case_id: str,
    label: str,
    observations: list[Observation],
    segments: list[TrackSegment],
    links: list[IdentityLink],
    groups: dict[str, str],
    truth_of_segment: dict[str, str],
) -> dict[str, object]:
    """Reconstruct one case as a run would and score the reconstruction."""
    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    zones = load_zones(scene)
    config = EventConfig()
    events = merge_across_cameras(
        extract_events("eval", observations, zones, cameras, class_heights(scene), config),
        config.merge_tolerance_s,
        groups,
    )
    events = [*events, *state_changes("eval", load_case_script(CASES_CONFIG, case_id))]
    run_end_s = max(o.timestamp_s for o in observations)
    truth = TRUTH[case_id]
    incidents = [
        i
        for i in detect_incidents("eval", events, zones, run_end_s, IncidentConfig())
        if truth is not None and i.incident_class is truth[0]
    ]
    if not incidents:
        return {"case_id": case_id, "mode": label, "incident": None}
    incident = incidents[0]
    built_at = datetime.now(UTC)
    graph = build_graph(
        incident,
        events=events,
        observations=observations,
        segments=segments,
        links=links,
        groups=groups,
        zones=zones,
        created_at=built_at,
        event_version=config.version,
    )
    hypotheses = rank_hypotheses(incident, graph, events, zones, built_at)
    report = generate_report(incident, graph, hypotheses, events, built_at)

    # Cause ranking: the first entity node each hypothesis cites is the one it is about.
    ranked_entities = []
    for h in hypotheses:
        entity_node = next(
            (r for r in h.support_refs if graph.node(r).node_type is NodeType.ENTITY), None
        )
        ranked_entities.append(
            _entity_of_node(graph, entity_node, truth_of_segment) if entity_node else None
        )
    cause = CAUSE_ENTITY.get(case_id)

    # Gaps, per true entity, clipped to the window.
    window = (incident.window_start_s, incident.window_end_s)
    true_gaps: dict[str, list[tuple[float, float]]] = {
        entity: [
            (max(lo, window[0]), min(hi, window[1]))
            for lo, hi in spans
            if min(hi, window[1]) > max(lo, window[0])
        ]
        for entity, spans in json.loads((SAMPLES / case_id / "gaps_gt.json").read_text()).items()
    }
    predicted: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for edge in graph.edges:
        if edge.relation is not Relation.OCCLUDES:
            continue
        gap = graph.node(edge.from_node)
        entity = _entity_of_node(graph, edge.to_node, truth_of_segment)
        if gap.interval_s is not None and entity is not None:
            predicted[entity].append(gap.interval_s)
    predicted = {entity: _union(spans) for entity, spans in predicted.items()}
    truth_s = sum(hi - lo for spans in true_gaps.values() for lo, hi in spans)
    named_s = sum(hi - lo for spans in predicted.values() for lo, hi in spans)
    hit_s = sum(
        _interval_overlap(p, t)
        for entity, spans in predicted.items()
        for p in spans
        for t in true_gaps.get(entity, [])
    )

    claims = [c.model_dump(mode="json") for c in report.claims]
    known = (
        {n.node_id for n in graph.nodes}
        | {e.event_id for e in events}
        | {h.hypothesis_id for h in hypotheses}
    )
    return {
        "case_id": case_id,
        "mode": label,
        "incident": incident.incident_class.value,
        "window": list(window),
        "cause_entity": cause,
        "ranked_entities": ranked_entities,
        "top_levels": [h.evidence_level.value for h in hypotheses[:3]],
        "cause_top1": cause is not None and ranked_entities[:1] == [cause],
        "cause_top3": cause is not None and cause in ranked_entities[:3],
        "gap_truth_s": round(truth_s, 2),
        "gap_named_s": round(named_s, 2),
        "gap_recall": round(hit_s / truth_s, 3) if truth_s else None,
        "gap_precision": round(hit_s / named_s, 3) if named_s else None,
        "gap_named_s_by_entity": {
            entity: round(sum(hi - lo for lo, hi in spans), 2)
            for entity, spans in predicted.items()
        },
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "claims": len(claims),
        "claims_by_level": dict(Counter(c.evidence_level.value for c in report.claims)),
        "evidence_coverage": evidence_coverage(claims),
        "unsupported_claim_rate": unsupported_claim_rate(claims, known),
        "summary": report.summary,
    }


def main() -> int:
    """Score both modes on every tune case with an incident and write a JSON report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=list(CAUSE_ENTITY))
    args = parser.parse_args()

    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    speeds = {
        k: float(v["max_speed_mps"]) for k, v in scene["entities"].items() if not k.startswith("_")
    }
    results = []
    for case_id in args.cases:
        perfect = perfect_tracks(SAMPLES / case_id, projected=False)
        segments = segments_from_observations("eval", perfect)
        results.append(
            score_case(
                case_id,
                "perfect",
                perfect,
                segments,
                [],
                {str(o.track_id): str(o.entity_id) for o in perfect},
                {s.segment_id: s.local_track_id.split("-", 1)[1] for s in segments},
            )
        )
        log_result(results[-1])

        observations, segments, descriptors = run_perception(case_id)
        links = associate(
            "eval",
            build_segment_tracks(
                segments,
                observations,
                localise_all(observations, cameras, class_heights(scene)),
                descriptors,
            ),
            speeds,
        )
        truth_rows = [
            Observation.model_validate(r)
            for r in json.loads((SAMPLES / case_id / "observations_gt.json").read_text())
        ]
        votes: dict[str, Counter[str]] = defaultdict(Counter)
        for camera_id in sorted({o.camera_id for o in observations}):
            relabelled, _ = assign_identities(
                [o for o in observations if o.camera_id == camera_id],
                [t for t in truth_rows if t.camera_id == camera_id],
            )
            for o in relabelled:
                if o.track_id and o.entity_id:
                    votes[f"SEG-eval-{o.track_id}"][o.entity_id] += 1
        results.append(
            score_case(
                case_id,
                "detections",
                observations,
                segments,
                links,
                entity_groups(links, segments),
                {seg: c.most_common(1)[0][0] for seg, c in votes.items()},
            )
        )
        log_result(results[-1])

    out = REPORTS / f"reasoning-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"results": results}, indent=2))
    log.info("written to %s", out)
    return 0


def log_result(r: dict[str, object]) -> None:
    """One line per case and mode, then the summary the report opens with."""
    if r.get("incident") is None:
        log.info("%-10s %s  no incident opened", r["mode"], r["case_id"])
        return
    log.info(
        "%-10s %s  top1 %s top3 %s  ranked %s %s"
        "  gaps recall %s precision %s (truth %ss, named %ss)"
        "  claims %s %s  coverage %.2f  unsupported %.2f  graph %s/%s",
        r["mode"],
        r["case_id"],
        r["cause_top1"],
        r["cause_top3"],
        r["ranked_entities"],
        r["top_levels"],
        r["gap_recall"],
        r["gap_precision"],
        r["gap_truth_s"],
        r["gap_named_s"],
        r["claims"],
        r["claims_by_level"],
        r["evidence_coverage"],
        r["unsupported_claim_rate"],
        r["nodes"],
        r["edges"],
    )
    log.info("           %s", r["summary"])


if __name__ == "__main__":
    raise SystemExit(main())
