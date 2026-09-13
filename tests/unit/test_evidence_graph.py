"""The evidence graph names what was seen, what was not, and where identity is uncertain."""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime

import pytest

from packages.schemas import (
    SCHEMA_VERSION,
    BBox,
    EventType,
    IdentityLink,
    Incident,
    IncidentClass,
    LinkDecision,
    NodeType,
    Observation,
    Relation,
    SemanticEvent,
    Severity,
)
from services.events import load_zones
from services.evidence import EvidenceGraph, build_graph
from services.reasoning import coverage_gaps
from services.tracking import segments_from_observations

ZONES = load_zones(json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text()))
NOW = datetime(2026, 9, 13, tzinfo=UTC)


def _track(run: str, track: str, cls: str, spans: list[tuple[float, float]]) -> list[Observation]:
    """Observations of one track at 10 FPS over each span."""
    rows = []
    for lo, hi in spans:
        for frame in range(round(lo * 10), round(hi * 10) + 1):
            rows.append(
                Observation(
                    schema_version=SCHEMA_VERSION,
                    observation_id=f"{run}-{track}-{frame:05d}",
                    run_id=run,
                    camera_id=track.split("-")[0],
                    frame_index=frame,
                    timestamp_s=frame / 10,
                    entity_class=cls,
                    bbox=BBox(x1=0, y1=0, x2=10, y2=20),
                    confidence=0.9,
                    track_id=track,
                )
            )
    return rows


def _event(
    run: str, n: int, kind: EventType, t: float, ids: list[str], **payload: object
) -> SemanticEvent:
    """Build one merged event."""
    return SemanticEvent(
        schema_version=SCHEMA_VERSION,
        event_id=f"EVT-{run}-{n:04d}",
        run_id=run,
        event_type=kind,
        timestamp_s=t,
        entity_ids=ids,
        zone_id="Z1" if kind is EventType.ZONE_ENTRY else None,
        confidence=0.8,
        evidence_refs=[f"{run}-{ids[0]}-00128"]
        if not payload.get("source")
        else [f"telemetry:{ids[0]}:{t:g}"],
        payload=payload,
    )


def _scene(run: str = "r", robots: int = 1) -> dict[str, object]:
    """Build an e-stop case: a person on two linked cameras, a third unlinked sighting, robots."""
    observations = (
        _track(run, "CAM_A-T001", "person", [(4.0, 8.0), (12.0, 20.0)])
        + _track(run, "CAM_B-T001", "person", [(6.0, 9.0)])
        + _track(run, "CAM_C-T001", "person", [(14.0, 18.0)])
    )
    for i in range(robots):
        observations += _track(run, f"CAM_A-T00{2 + i}", "robot", [(0.0, 30.0)])
    segments = segments_from_observations(run, observations)
    seg = {s.local_track_id: s.segment_id for s in segments}
    links = [
        IdentityLink(
            link_id=f"LNK-{run}-0001",
            run_id=run,
            segment_a=seg["CAM_A-T001"],
            segment_b=seg["CAM_C-T001"],
            decision=LinkDecision.UNKNOWN,
            score=0.6,
            threshold=0.75,
            evidence_refs=[seg["CAM_A-T001"]],
        )
    ]
    groups = {s.local_track_id: s.local_track_id for s in segments} | {"CAM_B-T001": "CAM_A-T001"}
    trigger = _event(
        run,
        3,
        EventType.STATE_CHANGE,
        13.4,
        ["R12"],
        entity_class="robot",
        source="telemetry",
        to="estop",
    )
    events = [
        _event(
            run, 1, EventType.ZONE_ENTRY, 12.8, ["CAM_A-T001", "CAM_B-T001"], entity_class="person"
        ),
        _event(
            run,
            2,
            EventType.PROXIMITY,
            13.0,
            ["CAM_A-T001", "CAM_A-T002"],
            entity_class="person",
            distance_m=1.2,
            other_class="robot",
        ),
        trigger,
        _event(run, 4, EventType.ZONE_ENTRY, 30.0, ["CAM_A-T001"], entity_class="person"),
    ]
    incident = Incident(
        incident_id=f"INC-{run}-01",
        run_id=run,
        incident_class=IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION,
        trigger_event_id=trigger.event_id,
        detected_at_s=13.4,
        window_start_s=3.4,
        window_end_s=23.4,
        severity=Severity.HIGH,
    )
    return {
        "incident": incident,
        "events": events,
        "observations": observations,
        "segments": segments,
        "links": links,
        "groups": groups,
    }


def _build(**scene: object) -> EvidenceGraph:
    """Build the graph for a scene from ``_scene``."""
    incident = scene.pop("incident")
    return build_graph(incident, zones=ZONES, created_at=NOW, **scene)  # type: ignore[arg-type]


def test_coverage_gaps_are_holes_across_all_cameras_including_window_edges() -> None:
    """Two linked cameras cover each other; only time neither saw counts."""
    s = _scene()
    gaps = coverage_gaps(s["observations"], s["groups"], 3.4, 23.4, entities={"CAM_A-T001"})  # type: ignore[arg-type]
    assert [(g.start_s, g.end_s) for g in gaps] == [(3.4, 4.0), (9.0, 12.0), (20.0, 23.4)]
    assert gaps[1].bounded_by == ("r-CAM_B-T001-00090", "r-CAM_A-T001-00120")


def test_graph_holds_window_events_entities_zones_gaps_and_conflicts() -> None:
    """Every node kind the uncertainty engine and reconstruction need is present."""
    graph = _build(**_scene())
    kinds = {n.node_type for n in graph.nodes}
    assert kinds == {
        NodeType.INTERVAL,
        NodeType.EVENT,
        NodeType.ENTITY,
        NodeType.LOCATION,
        NodeType.GAP,
        NodeType.CONFLICT,
    }
    assert [n.timestamp_s for n in graph.of_type(NodeType.EVENT)] == [12.8, 13.0, 13.4]
    assert graph.node_for_source("EVT-r-0004") is None, "events outside the window stay out"
    [conflict] = graph.of_type(NodeType.CONFLICT)
    assert conflict.source_ref == "LNK-r-0001" and conflict.confidence == 0.6
    assert any(g.interval_s == (9.0, 12.0) for g in graph.of_type(NodeType.GAP))


def test_every_node_and_edge_carries_provenance_and_edges_resolve() -> None:
    """No assertion without a source, and no edge to a node that does not exist."""
    graph = _build(**_scene())
    ids = {n.node_id for n in graph.nodes}
    for item in [*graph.nodes, *graph.edges]:
        assert item.provenance.run_id == "r"
        assert item.provenance.derived_from, f"{item} cites nothing"
    assert all(e.from_node in ids and e.to_node in ids for e in graph.edges)
    relations = {e.relation for e in graph.edges}
    assert {
        Relation.OBSERVED_AS,
        Relation.PRECEDES,
        Relation.CO_OCCURS,
        Relation.NEAR,
        Relation.OCCLUDES,
        Relation.CONTRADICTS,
    } <= relations


def test_telemetry_robot_joins_the_only_tracked_robot() -> None:
    """One tracked robot: the robot that reported the stop is that one."""
    graph = _build(**_scene())
    [same] = [e for e in graph.edges if e.relation is Relation.SAME_ENTITY_AS]
    assert "telemetry" in graph.node(same.from_node).label
    assert graph.node(same.to_node).label.startswith("Robot (CAM_A-T002")


def test_two_tracked_robots_make_the_join_a_conflict() -> None:
    """With two robots in view, which one stopped is recorded as undetermined."""
    graph = _build(**_scene(robots=2))
    assert not [e for e in graph.edges if e.relation is Relation.SAME_ENTITY_AS]
    assert any("which of 2 tracked robots" in n.label for n in graph.of_type(NodeType.CONFLICT))


def test_ids_fit_their_columns_for_a_long_run_id() -> None:
    """Run ids are hashes; node and edge ids must still fit 64 characters."""
    graph = _build(**_scene(run="r" * 60))
    assert (
        max(len(i) for i in [*(n.node_id for n in graph.nodes), *(e.edge_id for e in graph.edges)])
        <= 64
    )


@pytest.mark.parametrize("missing", ["CAM_A-T001"])
def test_entity_never_seen_in_window_is_all_gap(missing: str) -> None:
    """An entity asked about but unseen throughout is one gap spanning the window."""
    gaps = coverage_gaps([], {}, 3.4, 23.4, entities={missing})
    assert [(g.start_s, g.end_s, g.bounded_by) for g in gaps] == [(3.4, 23.4, ())]


def test_conflict_names_both_tracks_even_when_other_links_joined_them() -> None:
    """A refusal inside one identity group must not read as "X and X"."""
    apart = [n.label for n in _build(**_scene()).of_type(NodeType.CONFLICT)]
    assert apart == ["Cannot determine whether CAM_A-T001 and CAM_C-T001 are the same person"]

    scene = _scene()
    groups = scene["groups"]
    assert isinstance(groups, dict)
    scene["groups"] = groups | {"CAM_C-T001": "CAM_A-T001"}
    [joined] = [n.label for n in _build(**scene).of_type(NodeType.CONFLICT)]
    assert joined.endswith(
        "CAM_A-T001 and CAM_C-T001 are the same person (joined through other cameras)"
    )
