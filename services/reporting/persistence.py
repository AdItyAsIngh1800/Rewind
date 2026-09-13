"""Write and read reports.

Claims go in as JSON and come back out through the ``Claim`` contract, so a stored
claim that could not be validated fails on read rather than reaching an investigator.
Reports are immutable once issued: a second write of the same report is skipped, never
merged, so a cited report still reads as issued when it is audited.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.database.models import Report as ReportRow
from packages.schemas import Claim, Report

log = logging.getLogger(__name__)


def write_report(session: Session, report: Report) -> bool:
    """Store a report unless one with its id exists; returns whether it was written."""
    statement = (
        insert(ReportRow)
        .values(
            report_id=report.report_id,
            run_id=report.run_id,
            incident_id=report.incident_id,
            generator_version=report.generator_version,
            created_at=report.created_at,
            summary=report.summary,
            claims=[c.model_dump(mode="json") for c in report.claims],
            ranked_hypotheses=list(report.ranked_hypotheses),
            gaps=list(report.gaps),
            limitations=report.limitations,
        )
        .on_conflict_do_nothing(index_elements=["report_id"])
        .returning(ReportRow.report_id)
    )
    written = bool(session.execute(statement).all())
    session.flush()
    log.info(
        "incident %s: report %s %s",
        report.incident_id,
        report.report_id,
        "written" if written else "exists",
    )
    return written


def report_for_incident(session: Session, incident_id: str) -> Report | None:
    """Return the incident's report, validated as the frozen contract, if one exists."""
    row = session.scalars(
        select(ReportRow)
        .where(ReportRow.incident_id == incident_id)
        .order_by(ReportRow.created_at.desc())
    ).first()
    if row is None:
        return None
    return Report(
        report_id=row.report_id,
        run_id=row.run_id,
        incident_id=row.incident_id,
        generator_version=row.generator_version,
        created_at=row.created_at,
        summary=row.summary,
        claims=[Claim.model_validate(c) for c in row.claims],
        ranked_hypotheses=list(row.ranked_hypotheses),
        gaps=list(row.gaps),
        limitations=row.limitations,
    )
