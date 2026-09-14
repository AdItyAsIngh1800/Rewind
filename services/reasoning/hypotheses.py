"""Hypothesis generation and ranking (E7.2): candidate causes, never one asserted cause.

Candidates are read from graph patterns around the trigger, one hypothesis per entity:

- **E-stop.** A person, forklift or pallet that entered the robot's lane or the
  intersection, or came close to the robot, in the look-back window before the stop.
- **Blocked zone.** An entity that was in the blocked zone around the moment the object
  came to rest there: arriving before it, leaving after it, or both.

Each is scored on four named components so the ranking can be argued with:
temporal precedence, spatial relevance, evidence strength and convergence (towards the
robot, or arrive-and-leave for an obstruction). The score sets the order. The evidence
level is capped separately by what argues against it: a hypothesis whose critical
interval a coverage gap hides is at most POSSIBLE however well it scores, because the
decisive moment was not seen (scene spec §6.2). An inference is never CONFIRMED; that
level belongs to observations.

When no candidate exists the result is a single UNKNOWN hypothesis. Saying nothing
would be read as "no cause", which is a claim the evidence does not make either.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import shapely

from packages.schemas import (
    SCHEMA_VERSION,
    EventType,
    EvidenceEdge,
    EvidenceLevel,
    EvidenceNode,
    Hypothesis,
    Incident,
    IncidentClass,
    NodeType,
    Provenance,
    Relation,
    SemanticEvent,
)
from services.events import EventConfig, Zone
from services.evidence.graph import EvidenceGraph, id_base


@dataclass(frozen=True)
class RankingConfig:
    """Every weight and window that shapes the ranking, recorded on each hypothesis."""

    #: Time constant of temporal precedence: an event 5 s before the trigger keeps
    #: e^-1 of the credit of one at the trigger.
    tau_s: float = 5.0
    #: Events may be stamped up to this late and still count as preceding (the Gate 2
    #: timing floor): a crossing timed 0.2 s after a stop may have happened before it.
    timing_tolerance_s: float = 0.5
    lookback_s: float = 10.0
    #: Spatial relevance of a zone entry to a robot stop: its own lane counts fully,
    #: the intersection it crosses counts less.
    path_zones: tuple[tuple[str, float], ...] = (("Z1", 1.0), ("Z2", 0.6))
    keep_clear_zones: tuple[str, ...] = ("Z2",)
    w_temporal: float = 0.35
    w_spatial: float = 0.30
    w_strength: float = 0.20
    w_convergence: float = 0.15
    strong: float = 0.7
    min_score: float = 0.25

    @property
    def version(self) -> str:
        """Identifier recorded in each hypothesis edge's provenance."""
        return (
            f"hypotheses:tau{self.tau_s:g}:look{self.lookback_s:g}"
            f":w{self.w_temporal:g}/{self.w_spatial:g}/{self.w_strength:g}/{self.w_convergence:g}"
            f":strong{self.strong:g}"
        )


@dataclass
class _Candidate:
    entity: EvidenceNode
    anchor: EvidenceNode
    anchor_event: SemanticEvent
    components: dict[str, float]
    support: list[str]
    description: str
    score: float = 0.0


class _Index:
    """The graph and its events, indexed the ways the patterns need to ask."""

    def __init__(self, graph: EvidenceGraph, events: Sequence[SemanticEvent]) -> None:
        self.nodes = {n.node_id: n for n in graph.nodes}
        self.events = {e.event_id: e for e in events}
        self.event_node = {
            n.source_ref: n for n in graph.of_type(NodeType.EVENT) if n.source_ref is not None
        }
        self.observed: dict[str, list[EvidenceNode]] = defaultdict(list)
        self.near: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
        self.against: dict[str, list[EvidenceNode]] = defaultdict(list)
        self.same_as: dict[str, str] = {}
        for edge in graph.edges:
            source, target = self.nodes[edge.from_node], self.nodes[edge.to_node]
            if edge.relation is Relation.OBSERVED_AS:
                self.observed[source.node_id].append(target)
            elif edge.relation is Relation.NEAR:
                via = edge.provenance.derived_from[0] if edge.provenance.derived_from else ""
                self.near[source.node_id].append((target.node_id, edge.weight, via))
                self.near[target.node_id].append((source.node_id, edge.weight, via))
            elif edge.relation in (
                Relation.OCCLUDES,
                Relation.CONTRADICTS,
            ) and source.node_type in (
                NodeType.GAP,
                NodeType.CONFLICT,
            ):
                self.against[target.node_id].append(source)
            elif edge.relation is Relation.SAME_ENTITY_AS:
                self.same_as[source.node_id] = target.node_id

    def event_of(self, node: EvidenceNode) -> SemanticEvent | None:
        return self.events.get(node.source_ref or "")

    def entity_class(self, entity_id: str) -> str:
        """Return an entity's class, the first word of its node label.

        Not the ``entity_class`` of its events: a proximity event carries the class of
        the entity it was emitted for, so a robot observed in one would read as a person.
        """
        return self.nodes[entity_id].label.split(" ", 1)[0].lower()

    def entities_of(self, event_node: EvidenceNode) -> list[str]:
        return [entity for entity, observed in self.observed.items() if event_node in observed]


def _cameras(event: SemanticEvent) -> int:
    merged = event.payload.get("merged_from_cameras")
    return len(merged) if isinstance(merged, list) else 1


def _strength(node: EvidenceNode, event: SemanticEvent) -> float:
    """Node confidence, discounted when only one camera saw it."""
    return node.confidence * (0.5 + 0.5 * min(1.0, _cameras(event) / 2))


def _bounded(event: SemanticEvent) -> bool:
    return bool(event.payload.get("at_first_sight") or event.payload.get("during_gap"))


def _happened_between(event: SemanticEvent, window_start: float) -> tuple[float, float]:
    """Return when an event happened: its stamp, or the interval a bounded event fell in.

    The extractor stamps a crossing that happened while the track was unseen at the
    reappearance and records the gap in ``during_gap``. Judged by its stamp, a person
    who entered the lane unseen and reappeared after the stop looks like they entered
    after it, and the case the project is named for produces no hypothesis (EXP-0010,
    F5). Judged by the interval, the entry may precede the stop, and is *possible*.

    A track that reappears after a gap longer than the tracker bridges comes back as a
    *new* track, first seen already inside the zone (``at_first_sight``), with no
    earlier sighting of its own to bound the crossing by. Nothing before the incident
    window is in evidence, so the crossing is bounded by the window's start: the same
    honesty as ``during_gap``, with a wider interval. Without this the product path,
    which always runs the tracker, never produced the hypothesis F5 was for (E9.4,
    golden e2e).
    """
    gap = event.payload.get("during_gap")
    if isinstance(gap, list) and len(gap) == 2:
        return float(gap[0]), float(gap[1])
    if event.payload.get("at_first_sight"):
        return min(window_start, event.timestamp_s), event.timestamp_s
    return event.timestamp_s, event.timestamp_s


def _overlaps(node: EvidenceNode, lo: float, hi: float) -> bool:
    if node.interval_s is None:
        return False
    return node.interval_s[0] < hi and lo < node.interval_s[1]


def rank_hypotheses(
    incident: Incident,
    graph: EvidenceGraph,
    events: Sequence[SemanticEvent],
    zones: Sequence[Zone],
    created_at: datetime,
    config: RankingConfig | None = None,
) -> list[Hypothesis]:
    """Rank the candidate causes of one incident, most plausible first.

    Adds a ``CANDIDATE_CAUSE_OF`` edge from each hypothesis's anchor event to the
    trigger, and a ``CONTRADICTS`` edge from each gap or conflict held against it, to
    ``graph`` in place, so the graph view shows why a cause was ranked where it was.
    """
    cfg = config or RankingConfig()
    index = _Index(graph, events)
    trigger_node = index.event_node[incident.trigger_event_id]
    trigger = index.events[incident.trigger_event_id]

    if incident.incident_class is IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION:
        candidates = _estop_candidates(index, trigger_node, trigger, cfg, incident.window_start_s)
    else:
        candidates = _blocked_candidates(index, trigger_node, trigger, zones, cfg)

    base = id_base(incident.incident_id)
    scored: list[tuple[_Candidate, list[EvidenceNode], EvidenceLevel]] = []
    for c in candidates:
        c.score = round(
            cfg.w_temporal * c.components["temporal_precedence"]
            + cfg.w_spatial * c.components["spatial"]
            + cfg.w_strength * c.components["evidence_strength"]
            + cfg.w_convergence * c.components["convergence"],
            4,
        )
        if c.score < cfg.min_score:
            continue
        # The critical interval runs between the anchor and the trigger, in whichever
        # order they fall: an obstruction's anchor can be the departure after it.
        t_anchor, t_trigger = c.anchor_event.timestamp_s, trigger.timestamp_s
        critical_lo = min(t_anchor, t_trigger) - cfg.timing_tolerance_s
        critical_hi = max(t_anchor, t_trigger) + cfg.timing_tolerance_s
        against = [
            n
            for n in index.against.get(c.entity.node_id, [])
            if _overlaps(n, critical_lo, critical_hi)
        ]
        scored.append((c, against, _level(c, against, cfg)))

    scored.sort(key=lambda item: (-item[0].score, item[0].anchor.node_id))
    hypotheses: list[Hypothesis] = []
    for n, (c, against, level) in enumerate(scored, start=1):
        hypothesis_id = f"{base}/H{n:02d}"
        hypotheses.append(
            Hypothesis(
                schema_version=SCHEMA_VERSION,
                hypothesis_id=hypothesis_id,
                run_id=incident.run_id,
                incident_id=incident.incident_id,
                description=c.description,
                evidence_level=level,
                score=c.score,
                support_refs=list(dict.fromkeys(c.support)),
                contradiction_refs=[a.node_id for a in against],
                components={k: round(v, 4) for k, v in c.components.items()},
            )
        )
        _edge(
            graph,
            base,
            incident,
            c.anchor.node_id,
            trigger_node.node_id,
            Relation.CANDIDATE_CAUSE_OF,
            c.score,
            [hypothesis_id],
            cfg,
            created_at,
        )
        for a in against:
            _edge(
                graph,
                base,
                incident,
                a.node_id,
                c.anchor.node_id,
                Relation.CONTRADICTS,
                0.5,
                [hypothesis_id],
                cfg,
                created_at,
            )

    if not hypotheses:
        hidden = [
            n.node_id
            for n in [*graph.of_type(NodeType.GAP), *graph.of_type(NodeType.CONFLICT)]
            if _overlaps(
                n,
                trigger.timestamp_s - cfg.lookback_s,
                trigger.timestamp_s + cfg.timing_tolerance_s,
            )
        ]
        hypotheses.append(
            Hypothesis(
                schema_version=SCHEMA_VERSION,
                hypothesis_id=f"{base}/H01",
                run_id=incident.run_id,
                incident_id=incident.incident_id,
                description="No entity in the evidence accounts for the trigger",
                evidence_level=EvidenceLevel.UNKNOWN,
                score=0.0,
                contradiction_refs=hidden,
            )
        )
    return hypotheses


def _level(c: _Candidate, against: Sequence[EvidenceNode], cfg: RankingConfig) -> EvidenceLevel:
    """Cap the level by what argues against the hypothesis, whatever its score."""
    if any(a.node_type is NodeType.CONFLICT for a in against) and c.score >= cfg.strong:
        return EvidenceLevel.CONFLICTING
    if against or _bounded(c.anchor_event) or c.score < cfg.strong:
        return EvidenceLevel.POSSIBLE
    return EvidenceLevel.STRONGLY_INFERRED


def _edge(
    graph: EvidenceGraph,
    base: str,
    incident: Incident,
    from_node: str,
    to_node: str,
    relation: Relation,
    weight: float,
    derived_from: list[str],
    cfg: RankingConfig,
    created_at: datetime,
) -> None:
    graph.edges.append(
        EvidenceEdge(
            schema_version=SCHEMA_VERSION,
            edge_id=f"{base}/K{sum(1 for e in graph.edges if '/K' in e.edge_id) + 1:04d}",
            run_id=incident.run_id,
            incident_id=incident.incident_id,
            from_node=from_node,
            to_node=to_node,
            relation=relation,
            weight=max(0.0, min(1.0, weight)),
            provenance=Provenance(
                producer_service="reasoning",
                producer_version=cfg.version,
                run_id=incident.run_id,
                derived_from=derived_from,
                created_at=created_at,
            ),
        )
    )


def _estop_candidates(
    index: _Index,
    trigger_node: EvidenceNode,
    trigger: SemanticEvent,
    cfg: RankingConfig,
    window_start: float,
) -> list[_Candidate]:
    t_stop = trigger.timestamp_s
    zone_weight = dict(cfg.path_zones)
    robots = {e for e in index.observed if index.entity_class(e) == "robot"}
    robots |= {index.same_as[r] for r in list(robots) if r in index.same_as}
    limit = EventConfig().proximity_distance
    out: list[_Candidate] = []

    for entity_id, observed in index.observed.items():
        if entity_id in robots:
            continue
        best: _Candidate | None = None
        support: list[str] = [entity_id]
        for node in observed:
            event = index.event_of(node)
            if event is None:
                continue
            earliest, latest = _happened_between(event, window_start)
            if latest < t_stop - cfg.lookback_s or earliest > t_stop + cfg.timing_tolerance_s:
                continue
            # The moment it most plausibly happened: its stamp, or for a bounded event
            # the middle of the part of its gap that precedes the stop.
            when = (earliest + min(latest, t_stop + cfg.timing_tolerance_s)) / 2
            if event.event_type is EventType.ZONE_ENTRY and event.zone_id in zone_weight:
                spatial = zone_weight[event.zone_id]
                zone_node = _zone_node(index, node)
                zone_label = index.nodes[zone_node].label if zone_node else event.zone_id
                what = f"entered {zone_label}"
            elif (
                event.event_type is EventType.PROXIMITY
                and event.payload.get("other_class") == "robot"
            ):
                distance = event.payload.get("distance_m")
                d = float(distance) if isinstance(distance, int | float) else limit
                spatial = 1.0 - 0.5 * min(1.0, d / limit)
                what = f"came within {d:g} m of the robot"
            else:
                continue
            support.append(node.node_id)
            components = {
                "temporal_precedence": math.exp(-max(0.0, t_stop - when) / cfg.tau_s),
                "spatial": spatial,
                "evidence_strength": _strength(node, event),
                "convergence": max(
                    (
                        w
                        for other, w, via in index.near.get(entity_id, [])
                        if other in robots
                        and via in index.events
                        and t_stop - cfg.lookback_s
                        <= index.events[via].timestamp_s
                        <= t_stop + cfg.timing_tolerance_s
                    ),
                    default=0.0,
                ),
            }
            partial = sum(
                components[k] for k in ("temporal_precedence", "spatial", "evidence_strength")
            )
            if best is None or partial > sum(
                best.components[k] for k in ("temporal_precedence", "spatial", "evidence_strength")
            ):
                if earliest == latest:
                    timing = (
                        f"at {event.timestamp_s:g} s, {t_stop - event.timestamp_s:.1f} s before "
                        "the robot's emergency stop"
                    )
                else:
                    timing = (
                        f"at some moment between {earliest:g} and {latest:g} s while no camera "
                        "saw it, around the robot's emergency stop"
                    )
                best = _Candidate(
                    entity=index.nodes[entity_id],
                    anchor=node,
                    anchor_event=event,
                    components=components,
                    support=[],
                    description=f"{index.nodes[entity_id].label} {what} {timing}",
                )
        if best is not None:
            best.support = [*support, trigger_node.node_id]
            out.append(best)
    return out


def _zone_node(index: _Index, event_node: EvidenceNode) -> str | None:
    event = index.event_of(event_node)
    if event is None or event.zone_id is None:
        return None
    return next(
        (
            n.node_id
            for n in index.nodes.values()
            if n.node_type is NodeType.LOCATION and n.source_ref == event.zone_id
        ),
        None,
    )


def _blocked_candidates(
    index: _Index,
    trigger_node: EvidenceNode,
    trigger: SemanticEvent,
    zones: Sequence[Zone],
    cfg: RankingConfig,
) -> list[_Candidate]:
    t_rest = trigger.timestamp_s
    x, y = trigger.payload.get("x"), trigger.payload.get("y")
    zone_id = next(
        (
            z.zone_id
            for z in zones
            if z.zone_id in cfg.keep_clear_zones
            and isinstance(x, int | float)
            and isinstance(y, int | float)
            and z.polygon.covers(shapely.Point(x, y))
        ),
        None,
    )
    object_class = str(trigger.payload.get("entity_class", "object"))
    out: list[_Candidate] = []
    if zone_id is None:
        return out
    # The object is every track of its class resting in the zone while the trigger's
    # does, the rule `detect_incidents` uses to call per-camera stops one obstruction.
    # Identity may have refused to join those tracks, and a contact seen by one camera
    # must still count against the object another camera's stop triggered on.
    zone_poly = next(z.polygon for z in zones if z.zone_id == zone_id)
    t_end = trigger.payload.get("end_s")
    trigger_end = float(t_end) if isinstance(t_end, int | float) else t_rest
    objects = set(index.entities_of(trigger_node))
    for entity_id, observed in index.observed.items():
        for node in observed:
            event = index.event_of(node)
            if event is None or event.event_type is not EventType.STOP:
                continue
            if event.payload.get("entity_class") != object_class:
                continue
            ex, ey, e_end = (event.payload.get(k) for k in ("x", "y", "end_s"))
            if not (
                isinstance(ex, int | float)
                and isinstance(ey, int | float)
                and isinstance(e_end, int | float)
            ):
                continue
            if zone_poly.covers(shapely.Point(ex, ey)) and (
                event.timestamp_s <= trigger_end and t_rest <= e_end
            ):
                objects.add(entity_id)
    # Every moment the object came to rest in the window, not only the last: an object
    # set down, nudged and set down again has a contributor at each rest (EXP-0010, F7).
    rests = sorted(
        {t_rest}
        | {
            e.timestamp_s
            for o in objects
            for n in index.observed[o]
            if (e := index.event_of(n)) is not None
            and e.event_type is EventType.STOP
            and e.timestamp_s < t_rest
        }
    )

    def nearest_rest(t: float) -> float:
        return min(rests, key=lambda r: abs(r - t))

    for entity_id, observed in index.observed.items():
        if entity_id in objects:
            continue
        arrivals: list[tuple[EvidenceNode, SemanticEvent]] = []
        departures: list[tuple[EvidenceNode, SemanticEvent]] = []
        contacts: list[tuple[EvidenceNode, SemanticEvent]] = []
        for node in observed:
            event = index.event_of(node)
            if event is None:
                continue
            rest = nearest_rest(event.timestamp_s)
            if (
                event.event_type is EventType.PROXIMITY
                and event.payload.get("other_class") == object_class
                and objects & set(index.entities_of(node))
            ):
                # Contact overlapping the look-back before a rest: whoever was with the
                # object as it came to rest, including a vehicle still withdrawing its
                # forks after setting it down. Needs no zone crossing, so one that only
                # nosed up to the edge still counts.
                end = event.payload.get("end_s")
                left = float(end) if isinstance(end, int | float) else event.timestamp_s
                if (
                    event.timestamp_s <= rest + cfg.timing_tolerance_s
                    and left >= rest - cfg.lookback_s
                ):
                    contacts.append((node, event))
                continue
            if event.zone_id != zone_id or abs(event.timestamp_s - rest) > cfg.lookback_s:
                continue
            if (
                event.event_type is EventType.ZONE_ENTRY
                and event.timestamp_s <= rest + cfg.timing_tolerance_s
            ):
                arrivals.append((node, event))
            elif (
                event.event_type is EventType.ZONE_EXIT
                and event.timestamp_s >= rest - cfg.timing_tolerance_s
            ):
                departures.append((node, event))
        if not arrivals and not departures and not contacts:
            continue
        # The event closest to a rest anchors the hypothesis. Arriving before and
        # leaving after, or being in contact as it came to rest, is what "left it"
        # looks like.
        anchor_node, anchor = min(
            [*arrivals, *departures, *contacts],
            key=lambda ne: abs(ne[1].timestamp_s - nearest_rest(ne[1].timestamp_s)),
        )
        t_anchor_rest = nearest_rest(anchor.timestamp_s)
        convergence = 1.0 if (arrivals and departures) or contacts else 0.5
        parts = []
        if arrivals:
            parts.append(f"entered {zone_id} at {min(e.timestamp_s for _, e in arrivals):g} s")
        if departures:
            parts.append(f"left at {min(e.timestamp_s for _, e in departures):g} s")
        if contacts:
            _, first = min(contacts, key=lambda ne: ne[1].timestamp_s)
            d = first.payload.get("distance_m")
            near = f"within {float(d):g} m of" if isinstance(d, int | float) else "beside"
            parts.append(f"was {near} the {object_class} from {first.timestamp_s:g} s")
        out.append(
            _Candidate(
                entity=index.nodes[entity_id],
                anchor=anchor_node,
                anchor_event=anchor,
                components={
                    "temporal_precedence": math.exp(
                        -abs(anchor.timestamp_s - t_anchor_rest) / cfg.tau_s
                    ),
                    "spatial": 1.0,
                    "evidence_strength": _strength(anchor_node, anchor),
                    "convergence": convergence,
                },
                support=[
                    entity_id,
                    *(n.node_id for n, _ in [*arrivals, *departures, *contacts]),
                    trigger_node.node_id,
                ],
                description=(
                    f"{index.nodes[entity_id].label} {' and '.join(parts)}, around when the "
                    f"{object_class} came to rest there at {t_anchor_rest:g} s"
                ),
            )
        )
    return out
