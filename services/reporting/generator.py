"""The deterministic report generator (E7.4): an incident written up with no LLM.

Structure follows the roadmap: what was observed, what is inferred from it, the ranked
hypotheses, and what cannot be determined. Every sentence is a ``Claim``, and the
wording of each is fixed by its evidence level (``ALLOWED_LANGUAGE``), never chosen.

Two properties are structural rather than checked afterwards:

- A claim at any level but UNKNOWN cannot be built without a reference: the ``Claim``
  contract refuses it.
- A reference that does not resolve to a graph node, a window event or a hypothesis
  makes the generator raise. A report citing something that does not exist is not
  issued at all. That is what holds the unsupported-claim rate at zero (Gate 5).

The generator writes only from the stored graph, the ranked hypotheses and the events
behind them. It adds no knowledge of its own, so the report cannot say more than the
evidence graph does.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from packages.schemas import (
    ALLOWED_LANGUAGE,
    SCHEMA_VERSION,
    Claim,
    EvidenceLevel,
    EvidenceNode,
    Hypothesis,
    Incident,
    IncidentClass,
    NodeType,
    Relation,
    Report,
    SemanticEvent,
)
from services.evidence.graph import EvidenceGraph, id_base

GENERATOR_VERSION = "deterministic-0.1.0"

#: A standing limitation true of every report this system writes, whatever the case.
STANDING_LIMITATION = (
    "Reconstructed from three fixed cameras and robot telemetry. Positions come from "
    "single-camera back-projection and can be off by up to a metre for large or partly "
    "hidden objects. Physical contact is never inferred from video, and ranked causes "
    "are inferences, not findings."
)


class ReportError(ValueError):
    """Raised when a report would cite evidence that does not exist."""


def _bounded(event: SemanticEvent) -> tuple[float, float] | None:
    during = event.payload.get("during_gap")
    if isinstance(during, list) and len(during) == 2:
        return float(during[0]), float(during[1])
    return None


def generate_report(
    incident: Incident,
    graph: EvidenceGraph,
    hypotheses: Sequence[Hypothesis],
    events: Sequence[SemanticEvent],
    created_at: datetime,
) -> Report:
    """Write the report for one incident from its graph, hypotheses and events.

    Raises:
        ReportError: if any claim would cite an id that is not a node of ``graph``, an
            event in ``events`` or one of ``hypotheses``.

    """
    nodes = {n.node_id: n for n in graph.nodes}
    event_by_id = {e.event_id: e for e in events}
    trigger_node = graph.node_for_source(incident.trigger_event_id)
    trigger = event_by_id.get(incident.trigger_event_id)
    if trigger_node is None or trigger is None:
        raise ReportError(f"incident {incident.incident_id} has no stored trigger event")

    claims: list[Claim] = []

    def claim(level: EvidenceLevel, body: str, refs: Sequence[str]) -> None:
        claims.append(
            Claim(
                schema_version=SCHEMA_VERSION,
                claim_id=f"CLM-{len(claims) + 1:03d}",
                text=f"{ALLOWED_LANGUAGE[level]}: {body}",
                evidence_level=level,
                evidence_refs=list(dict.fromkeys(refs)),
            )
        )

    # 1. What was observed: the trigger, then the events the hypotheses stand on.
    claim(
        EvidenceLevel.CONFIRMED,
        _trigger_sentence(incident, trigger_node, trigger),
        [trigger.event_id, trigger_node.node_id],
    )
    cited: set[str] = {trigger_node.node_id}
    for h in hypotheses:
        for ref in h.support_refs:
            node = nodes.get(ref)
            if node is None or node.node_type is not NodeType.EVENT or ref in cited:
                continue
            cited.add(ref)
            event = event_by_id.get(node.source_ref or "")
            if event is None:
                raise ReportError(f"node {ref} stands for an event that was not supplied")
            bound = _bounded(event)
            if bound is None and not event.payload.get("at_first_sight"):
                claim(EvidenceLevel.CONFIRMED, node.label, [event.event_id, ref])
            else:
                when = f" (time bounded between {bound[0]:g} and {bound[1]:g} s)" if bound else ""
                claim(EvidenceLevel.POSSIBLE, f"{node.label}{when}", [event.event_id, ref])

    # 2 and 3. The inferences, in ranked order, each worded by its own level.
    for h in hypotheses:
        if h.evidence_level is EvidenceLevel.UNKNOWN:
            claim(
                EvidenceLevel.UNKNOWN,
                f"a contributing cause. {h.description}",
                [h.hypothesis_id, *h.contradiction_refs],
            )
        else:
            claim(
                h.evidence_level,
                f"{h.description} (score {h.score:.2f})",
                [h.hypothesis_id, *h.support_refs],
            )

    # 4. What cannot be determined: gaps on the entities the causes name, gaps held
    # against a cause, and identity questions left open around the trigger.
    named = {
        ref
        for h in hypotheses
        for ref in h.support_refs
        if ref in nodes and nodes[ref].node_type is NodeType.ENTITY
    }
    against = {ref for h in hypotheses for ref in h.contradiction_refs}
    hides = {
        e.from_node for e in graph.edges if e.relation is Relation.OCCLUDES and e.to_node in named
    }
    gap_nodes = [n for n in graph.of_type(NodeType.GAP) if n.node_id in hides | against]
    for gap in gap_nodes:
        claim(EvidenceLevel.UNKNOWN, _gap_sentence(gap), [gap.node_id])
    for conflict in graph.of_type(NodeType.CONFLICT):
        if conflict.node_id in against or _near_trigger(conflict, trigger.timestamp_s):
            claim(
                EvidenceLevel.UNKNOWN,
                _lower_first(conflict.label.removeprefix("Cannot determine ")),
                [conflict.node_id],
            )

    known = set(nodes) | set(event_by_id) | {h.hypothesis_id for h in hypotheses}
    for c in claims:
        missing = [r for r in c.evidence_refs if r not in known]
        if missing:
            raise ReportError(f"{c.claim_id} cites {missing}, which the evidence does not contain")

    all_gaps = graph.of_type(NodeType.GAP)
    top = hypotheses[0] if hypotheses else None
    return Report(
        schema_version=SCHEMA_VERSION,
        report_id=f"REP-{id_base(incident.incident_id)}",
        run_id=incident.run_id,
        incident_id=incident.incident_id,
        generator_version=GENERATOR_VERSION,
        created_at=created_at,
        summary=_summary(incident, trigger_node, trigger, top),
        claims=claims,
        ranked_hypotheses=[h.hypothesis_id for h in hypotheses],
        gaps=[g.node_id for g in all_gaps],
        limitations=_limitations(all_gaps, graph.of_type(NodeType.CONFLICT)),
    )


def _trigger_sentence(incident: Incident, node: EvidenceNode, trigger: SemanticEvent) -> str:
    if incident.incident_class is IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION:
        robot = trigger.entity_ids[0] if trigger.entity_ids else "the robot"
        return f"robot {robot} reported an emergency stop at {trigger.timestamp_s:g} s"
    return (
        f"{node.label.split(' at ', 1)[0].lower()} at {trigger.timestamp_s:g} s and was still "
        f"there when the dwell limit was crossed at {incident.detected_at_s:g} s"
    )


def _gap_sentence(gap: EvidenceNode) -> str:
    detail = gap.label.removeprefix("No camera saw ")
    return f"what happened to {detail}; no camera saw it"


def _near_trigger(node: EvidenceNode, t: float, margin_s: float = 10.0) -> bool:
    return (
        node.interval_s is not None
        and node.interval_s[0] <= t + 0.5
        and t - margin_s <= node.interval_s[1]
    )


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _summary(
    incident: Incident, node: EvidenceNode, trigger: SemanticEvent, top: Hypothesis | None
) -> str:
    opened = _trigger_sentence(incident, node, trigger)
    lead = opened[:1].upper() + opened[1:] + "."
    if top is None or top.evidence_level is EvidenceLevel.UNKNOWN:
        return f"{lead} No contributing cause could be determined from the evidence."
    return f"{lead} {ALLOWED_LANGUAGE[top.evidence_level]}: {top.description}."


def _limitations(gaps: Sequence[EvidenceNode], conflicts: Sequence[EvidenceNode]) -> str:
    parts = []
    if gaps:
        parts.append(
            f"{len(gaps)} interval(s) in which a tracked entity was out of every camera's view."
        )
    if conflicts:
        parts.append(f"{len(conflicts)} cross-camera identity question(s) left undecided.")
    parts.append(STANDING_LIMITATION)
    return " ".join(parts)
