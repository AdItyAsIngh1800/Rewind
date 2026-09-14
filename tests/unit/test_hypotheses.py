"""Hypotheses rank candidate causes, cap their level by what hides them, and never stay silent."""

from __future__ import annotations

from packages.schemas import (
    SCHEMA_VERSION,
    EventType,
    EvidenceLevel,
    Incident,
    IncidentClass,
    Relation,
    SemanticEvent,
    Severity,
)
from services.evidence import EvidenceGraph, build_graph
from services.reasoning.hypotheses import rank_hypotheses
from services.tracking import segments_from_observations
from tests.unit.test_evidence_graph import NOW, ZONES, _scene, _track


def _graph(scene: dict[str, object]) -> tuple[Incident, EvidenceGraph, list[SemanticEvent]]:
    """Build the graph for a scene and return what the ranker needs."""
    incident = scene.pop("incident")
    assert isinstance(incident, Incident)
    events = scene["events"]
    assert isinstance(events, list)
    graph = build_graph(incident, zones=ZONES, created_at=NOW, **scene)  # type: ignore[arg-type]
    return incident, graph, events


def test_person_entering_the_lane_before_the_stop_ranks_first() -> None:
    """The flagship pattern: lane entry 0.6 s before the e-stop, seen and uncontradicted."""
    incident, graph, events = _graph(_scene())
    [top, *_] = rank_hypotheses(incident, graph, events, ZONES, NOW)
    assert top.description.startswith("Person (CAM_A-T001, CAM_B-T001) entered Z1")
    assert top.evidence_level is EvidenceLevel.STRONGLY_INFERRED
    assert set(top.components) == {
        "temporal_precedence",
        "spatial",
        "evidence_strength",
        "convergence",
    }
    trigger = graph.node_for_source(incident.trigger_event_id)
    assert trigger is not None and trigger.node_id in top.support_refs
    [cause] = [e for e in graph.edges if e.relation is Relation.CANDIDATE_CAUSE_OF]
    assert cause.to_node == trigger.node_id and cause.weight == top.score


def test_a_gap_over_the_approach_caps_the_hypothesis_at_possible() -> None:
    """Scene spec §6.2: consistent with the evidence, but the decisive moment was unseen."""
    scene = _scene()
    observations = scene["observations"]
    assert isinstance(observations, list)
    scene["observations"] = [
        o for o in observations if not (o.track_id == "CAM_A-T001" and 10.0 <= o.timestamp_s < 14.0)
    ]
    scene["segments"] = segments_from_observations("r", scene["observations"])  # type: ignore[arg-type]
    incident, graph, events = _graph(scene)
    [top, *_] = rank_hypotheses(incident, graph, events, ZONES, NOW)
    assert top.evidence_level is EvidenceLevel.POSSIBLE
    assert top.contradiction_refs, "the hiding gap must be named against it"
    assert any(
        e.relation is Relation.CONTRADICTS and e.from_node in top.contradiction_refs
        for e in graph.edges
    )


def test_no_candidate_is_an_explicit_unknown_not_silence() -> None:
    """With only the trigger, the ranker says it cannot determine a cause."""
    scene = _scene()
    events = scene["events"]
    assert isinstance(events, list)
    scene["events"] = [e for e in events if e.event_type is EventType.STATE_CHANGE]
    incident, graph, remaining = _graph(scene)
    [only] = rank_hypotheses(incident, graph, remaining, ZONES, NOW)
    assert only.evidence_level is EvidenceLevel.UNKNOWN and not only.support_refs


def _zone_event(
    n: int, kind: EventType, t: float, track: str, cls: str, zone: str | None, **payload: object
) -> SemanticEvent:
    """Build one merged event naming a zone."""
    return SemanticEvent(
        schema_version=SCHEMA_VERSION,
        event_id=f"EVT-b-{n:04d}",
        run_id="b",
        event_type=kind,
        timestamp_s=t,
        entity_ids=[track],
        zone_id=zone,
        confidence=0.8,
        evidence_refs=[f"b-{track}-00140"],
        payload={"entity_class": cls, **payload},
    )


def test_forklift_that_arrived_and_left_ranks_first_for_a_blocked_zone() -> None:
    """Scene spec §6.4: the forklift carried the pallet in, and left without it."""
    observations = (
        _track("b", "CAM_A-T001", "pallet", [(11.0, 40.0)])
        + _track("b", "CAM_A-T002", "forklift", [(5.0, 25.0)])
        + _track("b", "CAM_A-T003", "person", [(0.0, 40.0)])
    )
    trigger = _zone_event(
        3, EventType.STOP, 14.0, "CAM_A-T001", "pallet", None, duration_s=30.0, x=12.0, y=8.0
    )
    events = [
        _zone_event(1, EventType.ZONE_ENTRY, 11.5, "CAM_A-T002", "forklift", "Z2"),
        _zone_event(2, EventType.ZONE_ENTRY, 11.5, "CAM_A-T001", "pallet", "Z2"),
        trigger,
        _zone_event(4, EventType.ZONE_EXIT, 16.1, "CAM_A-T002", "forklift", "Z2"),
        _zone_event(5, EventType.ZONE_ENTRY, 12.0, "CAM_A-T003", "person", "Z3"),
    ]
    segments = segments_from_observations("b", observations)
    incident = Incident(
        incident_id="INC-b-01",
        run_id="b",
        incident_class=IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT,
        trigger_event_id=trigger.event_id,
        detected_at_s=34.0,
        window_start_s=4.0,
        window_end_s=44.0,
        severity=Severity.MEDIUM,
    )
    graph = build_graph(
        incident,
        events=events,
        observations=observations,
        segments=segments,
        links=[],
        groups={s.local_track_id: s.local_track_id for s in segments},
        zones=ZONES,
        created_at=NOW,
    )
    ranked = rank_hypotheses(incident, graph, events, ZONES, NOW)
    assert ranked[0].description.startswith(
        "Forklift (CAM_A-T002) entered Z2 at 11.5 s and left at 16.1 s"
    )
    assert ranked[0].evidence_level is EvidenceLevel.STRONGLY_INFERRED
    assert not any("Person" in h.description or "Pallet" in h.description for h in ranked)


def test_hypotheses_come_back_ranked_with_unique_edge_ids() -> None:
    """Scores descend, ids follow the ranking, and added edges do not collide."""
    incident, graph, events = _graph(_scene())
    ranked = rank_hypotheses(incident, graph, events, ZONES, NOW)
    assert [h.score for h in ranked] == sorted((h.score for h in ranked), reverse=True)
    assert [h.hypothesis_id for h in ranked] == [
        f"INC-r-01/H{n:02d}" for n in range(1, len(ranked) + 1)
    ]
    assert len({e.edge_id for e in graph.edges}) == len(graph.edges)


def test_an_entry_seen_only_after_the_stop_but_bounded_before_it_is_possible() -> None:
    """The project's namesake: the entry happened unseen and the track reappears after the stop.

    The extractor stamps such an entry at the reappearance with the gap it fell in.
    Judged by its stamp it is after the stop and no cause is ranked (EXP-0010, F5);
    judged by the gap it may precede the stop, and is *possible*, never more.
    """
    scene = _scene()
    events = scene["events"]
    observations = scene["observations"]
    assert isinstance(events, list) and isinstance(observations, list)
    # Nobody saw CAM_A-T001 from 10 to 14.5 s; it reappears inside Z1 after the 13.4 s stop.
    scene["observations"] = [
        o for o in observations if not (o.track_id == "CAM_A-T001" and 10.0 <= o.timestamp_s < 14.5)
    ]
    scene["segments"] = segments_from_observations("r", scene["observations"])  # type: ignore[arg-type]
    bounded_entry = events[0].model_copy(
        update={
            "timestamp_s": 14.5,
            "payload": {"entity_class": "person", "during_gap": [10.0, 14.5]},
        }
    )
    scene["events"] = [bounded_entry, *events[2:]]
    incident, graph, remaining = _graph(scene)
    [top, *_] = rank_hypotheses(incident, graph, remaining, ZONES, NOW)
    assert top.description.startswith("Person (CAM_A-T001, CAM_B-T001) entered Z1")
    assert "between 10 and 14.5 s while no camera saw it" in top.description
    assert top.evidence_level is EvidenceLevel.POSSIBLE
    assert 0 < top.components["temporal_precedence"] < 1


def test_both_forklifts_that_handled_the_pallet_are_ranked() -> None:
    """Scene spec §6.6: one set it down at the edge, another nudged it in; both surface with scores.

    Neither crossed into the zone by more than a wobble, so neither has a zone entry
    (EXP-0011, F3); each was in contact with the pallet as it came to rest.
    """
    observations = (
        _track("b", "CAM_A-T001", "pallet", [(4.0, 45.0)])
        + _track("b", "CAM_A-T002", "forklift", [(4.0, 20.0)])
        + _track("b", "CAM_A-T003", "forklift", [(15.0, 30.0)])
    )
    first_rest = _zone_event(
        2,
        EventType.STOP,
        10.3,
        "CAM_A-T001",
        "pallet",
        None,
        duration_s=11.7,
        end_s=22.0,
        x=11.0,
        y=6.2,
    )
    trigger = _zone_event(
        5,
        EventType.STOP,
        24.1,
        "CAM_A-T001",
        "pallet",
        None,
        duration_s=20.8,
        end_s=44.9,
        x=12.0,
        y=7.5,
    )
    events = [
        _zone_event(
            1,
            EventType.PROXIMITY,
            10.2,
            "CAM_A-T002",
            "forklift",
            None,
            other_class="pallet",
            distance_m=0.1,
            end_s=11.5,
        ).model_copy(update={"entity_ids": ["CAM_A-T002", "CAM_A-T001"]}),
        first_rest,
        _zone_event(
            3,
            EventType.PROXIMITY,
            17.7,
            "CAM_A-T003",
            "forklift",
            None,
            other_class="pallet",
            distance_m=1.5,
            end_s=22.8,
        ).model_copy(update={"entity_ids": ["CAM_A-T003", "CAM_A-T001"]}),
        trigger,
    ]
    segments = segments_from_observations("b", observations)
    incident = Incident(
        incident_id="INC-b-02",
        run_id="b",
        incident_class=IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT,
        trigger_event_id=trigger.event_id,
        detected_at_s=44.1,
        window_start_s=0.3,
        window_end_s=44.9,
        severity=Severity.MEDIUM,
    )
    graph = build_graph(
        incident,
        events=events,
        observations=observations,
        segments=segments,
        links=[],
        groups={s.local_track_id: s.local_track_id for s in segments},
        zones=ZONES,
        created_at=NOW,
    )
    ranked = rank_hypotheses(incident, graph, events, ZONES, NOW)
    who = {h.description.split(" ")[1].strip("(),") for h in ranked}
    assert who == {"CAM_A-T002", "CAM_A-T003"}, "both handlers, neither hidden"
    assert all(h.score > 0 for h in ranked)
    nudger = next(h for h in ranked if "CAM_A-T003" in h.description)
    assert "came to rest there at 24.1 s" in nudger.description
    placer = next(h for h in ranked if "CAM_A-T002" in h.description)
    assert "came to rest there at 10.3 s" in placer.description
