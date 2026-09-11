"""Write and read the semantic event stream.

Events are stored merged across cameras, one row per physical event, because that is
what every consumer reads: the timeline endpoint, the incident triggers (E6) and the
evidence graph (E7). The per-camera provenance is not lost by merging; it lives in
``evidence_refs`` and ``payload["merged_from_cameras"]``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import SemanticEvent as EventRow
from packages.schemas import SemanticEvent

log = logging.getLogger(__name__)


def write_events(session: Session, events: Sequence[SemanticEvent]) -> int:
    """Bulk-insert events, skipping any already present; returns rows inserted."""
    if not events:
        return 0
    statement = (
        insert(EventRow)
        .values(
            [
                {
                    "event_id": e.event_id,
                    "run_id": e.run_id,
                    "event_type": e.event_type.value,
                    "timestamp_s": e.timestamp_s,
                    "camera_id": e.camera_id,
                    "entity_ids": list(e.entity_ids),
                    "zone_id": e.zone_id,
                    "confidence": e.confidence,
                    "evidence_refs": list(e.evidence_refs),
                    "payload": dict(e.payload),
                }
                for e in events
            ]
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(EventRow.event_id)
    )
    inserted = len(session.execute(statement).all())
    session.flush()
    log.info("wrote %d of %d events", inserted, len(events))
    return inserted


def events_for_run(
    session: Session,
    run_id: str,
    *,
    start_s: float | None = None,
    end_s: float | None = None,
) -> list[EventRow]:
    """Events of one run in time order, optionally clipped to ``[start_s, end_s]``.

    Served by the ``(run_id, timestamp_s)`` index, so a rewind window over a long
    run costs the same as a short one.
    """
    query = select(EventRow).where(EventRow.run_id == run_id)
    if start_s is not None:
        query = query.where(EventRow.timestamp_s >= start_s)
    if end_s is not None:
        query = query.where(EventRow.timestamp_s <= end_s)
    return list(session.scalars(query.order_by(EventRow.timestamp_s, EventRow.event_id)))


def to_contract(row: EventRow) -> SemanticEvent:
    """Rehydrate a row as the frozen contract, so the API returns validated shapes."""
    return SemanticEvent(
        event_id=row.event_id,
        run_id=row.run_id,
        event_type=row.event_type,  # type: ignore[arg-type]
        timestamp_s=row.timestamp_s,
        camera_id=row.camera_id,
        entity_ids=list(row.entity_ids),
        zone_id=row.zone_id,
        confidence=row.confidence,
        evidence_refs=list(row.evidence_refs),
        payload=dict(row.payload),
    )
