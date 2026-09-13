"""Build one incident's evidence graph (E7.1), with provenance on every node and edge.

Nodes are the things a reconstruction talks about: entities, the events inside the
investigation window, the zones they happened in, the window itself, and the gaps and
identity conflicts the uncertainty engine names (E7.3). Edges say how those relate in
time, space and identity. Causal-candidate edges are added by the hypothesis ranker
(E7.2), not here: this module records what the evidence shows, never why.

Observations are not nodes. Every event already cites the observations it was read
from in its provenance, and a node per frame would add thousands of nodes per incident
that repeat what the observations table indexes (ledger, 2026-09-13).

Entities are cross-camera identity groups (E5.3), labelled by the tracks behind them.
The robot that reported the e-stop is known to telemetry by its own id, not by a track;
it is joined to a tracked robot only when exactly one robot was tracked in the window.
With two or more, which of them stopped is an identity conflict, and is recorded as one.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from packages.schemas import (
    SCHEMA_VERSION,
    EventType,
    EvidenceEdge,
    EvidenceNode,
    IdentityLink,
    Incident,
    NodeType,
    Observation,
    Provenance,
    Relation,
    SemanticEvent,
    TrackSegment,
)
from services.events import EventConfig, Zone
from services.reasoning.uncertainty import (
    coverage_gaps,
    identity_conflicts,
    tracked_entities,
)

GRAPH_VERSION = "evidence-0.1.0"
UNCERTAINTY_VERSION = "uncertainty-0.1.0"

#: Node and edge ids live in 64-character columns.
_ID_LIMIT = 64


@dataclass
class EvidenceGraph:
    """One incident's nodes and edges, as built or as loaded back from the database."""

    incident_id: str
    nodes: list[EvidenceNode] = field(default_factory=list)
    edges: list[EvidenceEdge] = field(default_factory=list)

    def node(self, node_id: str) -> EvidenceNode:
        """Look a node up by id; raises KeyError for an id the graph does not hold."""
        return {n.node_id: n for n in self.nodes}[node_id]

    def of_type(self, node_type: NodeType) -> list[EvidenceNode]:
        """Every node of one kind, in build order."""
        return [n for n in self.nodes if n.node_type is node_type]

    def node_for_source(self, source_ref: str) -> EvidenceNode | None:
        """Return the node standing for an event, zone, link or incident, if any."""
        return next((n for n in self.nodes if n.source_ref == source_ref), None)


class _Builder:
    """Assigns ids and fills the provenance every node and edge must carry."""

    def __init__(self, incident: Incident, created_at: datetime) -> None:
        base = incident.incident_id
        if len(base) > _ID_LIMIT - 12:
            base = "INC" + hashlib.sha1(base.encode()).hexdigest()[:16]
        self.base = base
        self.incident = incident
        self.created_at = created_at
        self.graph = EvidenceGraph(incident.incident_id)
        self._seq: dict[str, int] = defaultdict(int)

    def _provenance(self, service: str, version: str, derived_from: Sequence[str]) -> Provenance:
        return Provenance(
            producer_service=service,
            producer_version=version,
            run_id=self.incident.run_id,
            derived_from=list(dict.fromkeys(derived_from)),
            created_at=self.created_at,
        )

    def node(
        self,
        kind: str,
        node_type: NodeType,
        label: str,
        *,
        derived_from: Sequence[str],
        timestamp_s: float | None = None,
        interval_s: tuple[float, float] | None = None,
        source_ref: str | None = None,
        confidence: float = 1.0,
        service: str = "evidence",
        version: str = GRAPH_VERSION,
    ) -> str:
        self._seq[kind] += 1
        node_id = f"{self.base}/{kind}{self._seq[kind]:03d}"
        self.graph.nodes.append(
            EvidenceNode(
                schema_version=SCHEMA_VERSION,
                node_id=node_id,
                run_id=self.incident.run_id,
                incident_id=self.incident.incident_id,
                node_type=node_type,
                label=label,
                timestamp_s=timestamp_s,
                interval_s=interval_s,
                source_ref=source_ref,
                confidence=max(0.0, min(1.0, confidence)),
                provenance=self._provenance(service, version, derived_from),
            )
        )
        return node_id

    def edge(
        self,
        from_node: str,
        to_node: str,
        relation: Relation,
        *,
        derived_from: Sequence[str],
        weight: float = 1.0,
        service: str = "evidence",
        version: str = GRAPH_VERSION,
    ) -> None:
        self._seq["edge"] += 1
        self.graph.edges.append(
            EvidenceEdge(
                schema_version=SCHEMA_VERSION,
                edge_id=f"{self.base}/X{self._seq['edge']:04d}",
                run_id=self.incident.run_id,
                incident_id=self.incident.incident_id,
                from_node=from_node,
                to_node=to_node,
                relation=relation,
                weight=max(0.0, min(1.0, weight)),
                provenance=self._provenance(service, version, derived_from),
            )
        )


def _is_telemetry(event: SemanticEvent) -> bool:
    return event.payload.get("source") == "telemetry"


def build_graph(
    incident: Incident,
    *,
    events: Sequence[SemanticEvent],
    observations: Sequence[Observation],
    segments: Sequence[TrackSegment],
    links: Sequence[IdentityLink],
    groups: Mapping[str, str],
    zones: Sequence[Zone],
    created_at: datetime,
    event_version: str = EventConfig().version,
) -> EvidenceGraph:
    """Build the evidence graph for one incident from everything its run produced.

    Only events inside the investigation window are included, plus the trigger, which
    always belongs to its own incident. Everything else in the run is outside the
    question the incident asks. ``event_version`` is the extractor configuration that
    produced the events, recorded in each event node's provenance.
    """
    b = _Builder(incident, created_at)
    start, end = incident.window_start_s, incident.window_end_s
    zone_names = {z.zone_id: z.name for z in zones}

    window = b.node(
        "I",
        NodeType.INTERVAL,
        f"Investigation window {start:g} to {end:g} s",
        derived_from=[incident.trigger_event_id],
        interval_s=(start, end),
        source_ref=incident.incident_id,
    )

    in_window = sorted(
        (
            e
            for e in events
            if start <= e.timestamp_s <= end or e.event_id == incident.trigger_event_id
        ),
        key=lambda e: (e.timestamp_s, e.event_id),
    )

    # Entities: identity groups with real tracks in the window or named by its events,
    # and every robot that reported through telemetry.
    obs_in_window = [o for o in observations if start <= o.timestamp_s <= end]
    tracked = tracked_entities(observations, groups)
    present = {groups.get(str(o.track_id), str(o.track_id)) for o in obs_in_window if o.track_id}
    classes = {
        groups.get(str(o.track_id), str(o.track_id)): o.entity_class.value
        for o in observations
        if o.track_id
    }
    tracks_of: dict[str, list[str]] = defaultdict(list)
    segments_of: dict[str, list[str]] = defaultdict(list)
    for s in segments:
        group = groups.get(s.local_track_id, s.local_track_id)
        tracks_of[group].append(s.local_track_id)
        segments_of[group].append(s.segment_id)

    entity_node: dict[str, str] = {}

    def entity(key: str, label: str, derived_from: Sequence[str]) -> str:
        if key not in entity_node:
            entity_node[key] = b.node("E", NodeType.ENTITY, label, derived_from=derived_from)
        return entity_node[key]

    for group in sorted(present & tracked):
        tracks = ", ".join(sorted(tracks_of.get(group, [group])))
        entity(
            group,
            f"{classes.get(group, 'entity').capitalize()} ({tracks})",
            segments_of.get(group, []),
        )

    zone_node: dict[str, str] = {}
    last_event_of: dict[str, str] = {}
    for e in in_window:
        telemetry = _is_telemetry(e)
        keys = (
            [f"telemetry:{i}" for i in e.entity_ids]
            if telemetry
            else list(dict.fromkeys(groups.get(i, i) for i in e.entity_ids))
        )
        entity_class = str(e.payload.get("entity_class", "entity"))
        node = b.node(
            "V",
            NodeType.EVENT,
            _event_label(e, entity_class),
            derived_from=e.evidence_refs,
            timestamp_s=e.timestamp_s,
            source_ref=e.event_id,
            confidence=e.confidence,
            service="telemetry" if telemetry else "events",
            version="cases_v1" if telemetry else event_version,
        )
        for key in keys:
            if telemetry:
                label = f"{entity_class.capitalize()} {key.split(':', 1)[1]} (telemetry)"
                source = entity(key, label, e.evidence_refs)
            elif key in tracked:
                source = entity(
                    key, f"{entity_class.capitalize()} ({key})", segments_of.get(key, [])
                )
            else:
                continue
            b.edge(
                source, node, Relation.OBSERVED_AS, derived_from=[e.event_id], weight=e.confidence
            )
            if key in last_event_of:
                b.edge(last_event_of[key], node, Relation.PRECEDES, derived_from=[e.event_id])
            last_event_of[key] = node
        if e.zone_id:
            if e.zone_id not in zone_node:
                zone_node[e.zone_id] = b.node(
                    "L",
                    NodeType.LOCATION,
                    f"{e.zone_id} {zone_names.get(e.zone_id, '')}".strip(),
                    derived_from=[e.zone_id],
                    source_ref=e.zone_id,
                )
            b.edge(node, zone_node[e.zone_id], Relation.CO_OCCURS, derived_from=[e.event_id])
        if (
            e.event_type is EventType.PROXIMITY
            and len(keys) >= 2
            and all(k in entity_node for k in keys[:2])
        ):
            distance = e.payload.get("distance_m")
            # Closer is stronger; at the extractor's proximity limit the edge carries nothing.
            limit = EventConfig().proximity_distance
            weight = 1.0 - float(distance) / limit if isinstance(distance, int | float) else 0.5
            b.edge(
                entity_node[keys[0]],
                entity_node[keys[1]],
                Relation.NEAR,
                derived_from=[e.event_id],
                weight=weight,
            )
        if e.event_id == incident.trigger_event_id:
            b.edge(node, window, Relation.CO_OCCURS, derived_from=[incident.incident_id])

    _join_telemetry(b, entity_node, classes, segments_of, start, end)

    for gap in coverage_gaps(observations, groups, start, end, entities=present & tracked):
        gap_node = b.node(
            "G",
            NodeType.GAP,
            f"No camera saw {gap.entity_class} ({gap.entity})"
            f" between {gap.start_s:g} and {gap.end_s:g} s",
            derived_from=list(gap.bounded_by) or segments_of.get(gap.entity, []),
            interval_s=(gap.start_s, gap.end_s),
            service="reasoning",
            version=UNCERTAINTY_VERSION,
        )
        if gap.entity in entity_node:
            b.edge(
                gap_node,
                entity_node[gap.entity],
                Relation.OCCLUDES,
                derived_from=list(gap.bounded_by),
                service="reasoning",
                version=UNCERTAINTY_VERSION,
            )

    track_group = {s.segment_id: groups.get(s.local_track_id, s.local_track_id) for s in segments}
    for conflict in identity_conflicts(links, segments, start, end):
        a, c = track_group[conflict.segment_a], track_group[conflict.segment_b]
        conflict_node = b.node(
            "C",
            NodeType.CONFLICT,
            f"Cannot determine whether {a} and {c} are the same {conflict.entity_class}",
            derived_from=[conflict.link_id, conflict.segment_a, conflict.segment_b],
            interval_s=(conflict.start_s, conflict.end_s),
            source_ref=conflict.link_id,
            confidence=conflict.score,
            service="reasoning",
            version=UNCERTAINTY_VERSION,
        )
        for key in dict.fromkeys((a, c)):
            if key in entity_node:
                b.edge(
                    conflict_node,
                    entity_node[key],
                    Relation.CONTRADICTS,
                    derived_from=[conflict.link_id],
                    weight=conflict.score,
                    service="reasoning",
                    version=UNCERTAINTY_VERSION,
                )
    return b.graph


def _join_telemetry(
    b: _Builder,
    entity_node: Mapping[str, str],
    classes: Mapping[str, str],
    segments_of: Mapping[str, list[str]],
    start: float,
    end: float,
) -> None:
    """Join each telemetry robot to the one tracked robot, or record that it cannot be."""
    robots = sorted(
        k for k in entity_node if not k.startswith("telemetry:") and classes.get(k) == "robot"
    )
    for key in sorted(k for k in entity_node if k.startswith("telemetry:")):
        if len(robots) == 1:
            b.edge(
                entity_node[key],
                entity_node[robots[0]],
                Relation.SAME_ENTITY_AS,
                derived_from=segments_of.get(robots[0], []),
            )
        elif len(robots) > 1:
            conflict = b.node(
                "C",
                NodeType.CONFLICT,
                f"Cannot determine which of {len(robots)} tracked robots is {key.split(':', 1)[1]}",
                derived_from=[s for r in robots for s in segments_of.get(r, [])],
                interval_s=(start, end),
                service="reasoning",
                version=UNCERTAINTY_VERSION,
            )
            for robot in robots:
                b.edge(
                    conflict,
                    entity_node[robot],
                    Relation.CONTRADICTS,
                    derived_from=segments_of.get(robot, []),
                    weight=0.5,
                    service="reasoning",
                    version=UNCERTAINTY_VERSION,
                )


def _event_label(e: SemanticEvent, entity_class: str) -> str:
    """Label an event node briefly; the report writes its own sentences."""
    what = {
        EventType.ZONE_ENTRY: f"entered {e.zone_id}",
        EventType.ZONE_EXIT: f"left {e.zone_id}",
        EventType.STOP: "stopped",
        EventType.DIRECTION_CHANGE: "changed direction",
        EventType.PROXIMITY: (
            f"within {e.payload.get('distance_m')} m of a {e.payload.get('other_class')}"
        ),
        EventType.OCCLUSION_START: "lost from view",
        EventType.OCCLUSION_END: "back in view",
        EventType.STATE_CHANGE: f"state {e.payload.get('from')} → {e.payload.get('to')}",
    }[e.event_type]
    return f"{entity_class.capitalize()} {what} at {e.timestamp_s:g} s"
