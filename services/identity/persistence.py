"""Write and read identity links, refusals included."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import IdentityLink as LinkRow
from packages.schemas import IdentityLink

log = logging.getLogger(__name__)


def write_links(session: Session, links: Sequence[IdentityLink]) -> int:
    """Bulk-insert links, skipping any already present; returns rows inserted."""
    if not links:
        return 0
    statement = (
        insert(LinkRow)
        .values(
            [
                {
                    "link_id": link.link_id,
                    "run_id": link.run_id,
                    "segment_a": link.segment_a,
                    "segment_b": link.segment_b,
                    "decision": link.decision.value,
                    "score": link.score,
                    "threshold": link.threshold,
                    "components": dict(link.components),
                    "evidence_refs": list(link.evidence_refs),
                }
                for link in links
            ]
        )
        .on_conflict_do_nothing(index_elements=["link_id"])
        .returning(LinkRow.link_id)
    )
    inserted = len(session.execute(statement).all())
    session.flush()
    log.info("wrote %d of %d identity links", inserted, len(links))
    return inserted


def links_for_run(session: Session, run_id: str) -> list[LinkRow]:
    """Every comparison a run recorded, links and refusals alike."""
    return list(
        session.scalars(select(LinkRow).where(LinkRow.run_id == run_id).order_by(LinkRow.link_id))
    )


def link_to_contract(row: LinkRow) -> IdentityLink:
    """Rehydrate a row as the frozen contract."""
    return IdentityLink(
        link_id=row.link_id,
        run_id=row.run_id,
        segment_a=row.segment_a,
        segment_b=row.segment_b,
        decision=row.decision,  # type: ignore[arg-type]
        score=row.score,
        threshold=row.threshold,
        components=dict(row.components),
        evidence_refs=list(row.evidence_refs),
    )
