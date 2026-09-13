"""Write and read incidents, the rows the case inbox and every case view start from."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import Incident as IncidentRow
from packages.schemas import Incident, IncidentClass, IncidentStatus, Severity

log = logging.getLogger(__name__)

#: Triage order for the inbox. Severity is stored as text, and text order would put
#: `critical` after `high`.
SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}


def write_incidents(session: Session, incidents: Sequence[Incident]) -> int:
    """Bulk-insert incidents, skipping any already present; returns rows inserted.

    Runs in the caller's transaction with the events that triggered them, so a run
    never ends with an incident whose trigger event was not stored, or the reverse.
    """
    if not incidents:
        return 0
    statement = (
        insert(IncidentRow)
        .values(
            [
                {
                    "incident_id": i.incident_id,
                    "run_id": i.run_id,
                    "incident_class": i.incident_class.value,
                    "trigger_event_id": i.trigger_event_id,
                    "detected_at_s": i.detected_at_s,
                    "window_start_s": i.window_start_s,
                    "window_end_s": i.window_end_s,
                    "severity": i.severity.value,
                    "status": i.status.value,
                }
                for i in incidents
            ]
        )
        .on_conflict_do_nothing(index_elements=["incident_id"])
        .returning(IncidentRow.incident_id)
    )
    inserted = len(session.execute(statement).all())
    session.flush()
    log.info("wrote %d of %d incidents", inserted, len(incidents))
    return inserted


def list_incidents(
    session: Session,
    *,
    severity: Severity | None = None,
    status: IncidentStatus | None = None,
    limit: int = 50,
) -> tuple[list[IncidentRow], int]:
    """Incidents for the inbox, most severe first, and the total before the limit.

    ponytail: sorts in Python after filtering; move the rank into SQL once the inbox
    holds more incidents than one query can comfortably return.
    """
    query = select(IncidentRow)
    if severity is not None:
        query = query.where(IncidentRow.severity == severity.value)
    if status is not None:
        query = query.where(IncidentRow.status == status.value)
    rows = sorted(
        session.scalars(query),
        key=lambda r: (SEVERITY_RANK[Severity(r.severity)], r.run_id, r.detected_at_s),
    )
    return rows[:limit], len(rows)


def incident_to_contract(row: IncidentRow) -> Incident:
    """Rehydrate a row as the frozen contract, so the API returns validated shapes."""
    return Incident(
        incident_id=row.incident_id,
        run_id=row.run_id,
        incident_class=IncidentClass(row.incident_class),
        trigger_event_id=row.trigger_event_id,
        detected_at_s=row.detected_at_s,
        window_start_s=row.window_start_s,
        window_end_s=row.window_end_s,
        severity=Severity(row.severity),
        status=IncidentStatus(row.status),
    )
