"""Write and read evidence graphs.

Nodes are written before edges in one flush, because every edge's endpoints are
foreign keys: an edge pointing at a node that was never stored fails here, at write
time, rather than as a broken link in the UI.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import EvidenceEdge as EdgeRow
from packages.database.models import EvidenceNode as NodeRow
from packages.schemas import EvidenceEdge, EvidenceNode, NodeType, Provenance, Relation
from services.evidence.graph import EvidenceGraph

log = logging.getLogger(__name__)


def write_graph(session: Session, graph: EvidenceGraph) -> tuple[int, int]:
    """Insert a graph's nodes then edges, skipping rows already present."""
    nodes = edges = 0
    if graph.nodes:
        statement = (
            insert(NodeRow)
            .values(
                [
                    {
                        "node_id": n.node_id,
                        "run_id": n.run_id,
                        "incident_id": n.incident_id,
                        "node_type": n.node_type.value,
                        "label": n.label,
                        "timestamp_s": n.timestamp_s,
                        "interval_start_s": n.interval_s[0] if n.interval_s else None,
                        "interval_end_s": n.interval_s[1] if n.interval_s else None,
                        "source_ref": n.source_ref,
                        "confidence": n.confidence,
                        "provenance": n.provenance.model_dump(mode="json"),
                    }
                    for n in graph.nodes
                ]
            )
            .on_conflict_do_nothing(index_elements=["node_id"])
            .returning(NodeRow.node_id)
        )
        nodes = len(session.execute(statement).all())
    if graph.edges:
        statement = (
            insert(EdgeRow)
            .values(
                [
                    {
                        "edge_id": e.edge_id,
                        "run_id": e.run_id,
                        "incident_id": e.incident_id,
                        "from_node": e.from_node,
                        "to_node": e.to_node,
                        "relation": e.relation.value,
                        "weight": e.weight,
                        "provenance": e.provenance.model_dump(mode="json"),
                    }
                    for e in graph.edges
                ]
            )
            .on_conflict_do_nothing(index_elements=["edge_id"])
            .returning(EdgeRow.edge_id)
        )
        edges = len(session.execute(statement).all())
    session.flush()
    log.info("incident %s: wrote %d nodes, %d edges", graph.incident_id, nodes, edges)
    return nodes, edges


def graph_for_incident(session: Session, incident_id: str) -> EvidenceGraph:
    """Load one incident's graph back as frozen contracts, ordered by id."""
    node_rows = session.scalars(
        select(NodeRow).where(NodeRow.incident_id == incident_id).order_by(NodeRow.node_id)
    )
    edge_rows = session.scalars(
        select(EdgeRow).where(EdgeRow.incident_id == incident_id).order_by(EdgeRow.edge_id)
    )
    return EvidenceGraph(
        incident_id=incident_id,
        nodes=[
            EvidenceNode(
                node_id=r.node_id,
                run_id=r.run_id,
                incident_id=r.incident_id,
                node_type=NodeType(r.node_type),
                label=r.label,
                timestamp_s=r.timestamp_s,
                interval_s=(
                    (r.interval_start_s, r.interval_end_s)
                    if r.interval_start_s is not None and r.interval_end_s is not None
                    else None
                ),
                source_ref=r.source_ref,
                confidence=r.confidence,
                provenance=Provenance.model_validate(r.provenance),
            )
            for r in node_rows
        ],
        edges=[
            EvidenceEdge(
                edge_id=r.edge_id,
                run_id=r.run_id,
                incident_id=r.incident_id,
                from_node=r.from_node,
                to_node=r.to_node,
                relation=Relation(r.relation),
                weight=r.weight,
                provenance=Provenance.model_validate(r.provenance),
            )
            for r in edge_rows
        ],
    )
