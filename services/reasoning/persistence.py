"""Write and read ranked hypotheses."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import Hypothesis as HypothesisRow
from packages.schemas import EvidenceLevel, Hypothesis

log = logging.getLogger(__name__)


def write_hypotheses(session: Session, hypotheses: Sequence[Hypothesis]) -> int:
    """Insert hypotheses, skipping any already present; returns rows inserted."""
    if not hypotheses:
        return 0
    statement = (
        insert(HypothesisRow)
        .values(
            [
                {
                    "hypothesis_id": h.hypothesis_id,
                    "run_id": h.run_id,
                    "incident_id": h.incident_id,
                    "description": h.description,
                    "evidence_level": h.evidence_level.value,
                    "score": h.score,
                    "support_refs": list(h.support_refs),
                    "contradiction_refs": list(h.contradiction_refs),
                    "components": dict(h.components),
                }
                for h in hypotheses
            ]
        )
        .on_conflict_do_nothing(index_elements=["hypothesis_id"])
        .returning(HypothesisRow.hypothesis_id)
    )
    inserted = len(session.execute(statement).all())
    session.flush()
    log.info("wrote %d of %d hypotheses", inserted, len(hypotheses))
    return inserted


def hypotheses_for_incident(session: Session, incident_id: str) -> list[Hypothesis]:
    """Return an incident's hypotheses as frozen contracts, highest score first.

    The id breaks ties, so two equal scores always come back in the order they were
    ranked in, and a report citing "the first hypothesis" means the same one on reload.
    """
    rows = session.scalars(
        select(HypothesisRow)
        .where(HypothesisRow.incident_id == incident_id)
        .order_by(HypothesisRow.score.desc(), HypothesisRow.hypothesis_id)
    )
    return [
        Hypothesis(
            hypothesis_id=r.hypothesis_id,
            run_id=r.run_id,
            incident_id=r.incident_id,
            description=r.description,
            evidence_level=EvidenceLevel(r.evidence_level),
            score=r.score,
            support_refs=list(r.support_refs),
            contradiction_refs=list(r.contradiction_refs),
            components=dict(r.components),
        )
        for r in rows
    ]
