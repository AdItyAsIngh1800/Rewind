"""Operational metrics that stored pipeline output can already answer (spec §N).

The System Health screen reads these through ``GET /metrics``. Everything here is
computed from rows the pipeline has written: event and incident rates, how long a run
takes to issue its report, the two evidence-quality numbers the project is judged on,
and what recent runs cost (ADR-0008). API latency and errors are observed by the API
process itself; a live ID-switch rate needs ground truth and is never computed.

``None`` is the point. A zero event rate or a zero unsupported-claim rate reads as
"idle and healthy", which is a claim; "not measured" is not one.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from packages.database.models import (
    EvidenceNode,
    Hypothesis,
    Incident,
    Observation,
    ProcessingRun,
    Report,
    SemanticEvent,
)
from packages.evaluation.metrics import evidence_coverage, unsupported_claim_rate
from packages.schemas import RunStatus


@dataclass(frozen=True)
class StoredMetrics:
    """The §N metrics computable from the database, ``None`` where nothing is stored yet."""

    event_generation_rate: float | None
    incident_detection_rate: float | None
    report_generation_latency_s: float | None
    evidence_coverage: float | None
    unsupported_claim_rate: float | None
    frames_per_second: float | None
    peak_memory_mb: float | None


#: Throughput and memory describe the system as it runs now, so they come from the most
#: recent runs rather than every run ever stored, which would let a months-old model or
#: machine speak for the current one.
RECENT_RUNS = 20


def stored_metrics(session: Session) -> StoredMetrics:
    """Compute the stored-data metrics across every completed run.

    Rates are per minute of processed footage rather than per run, so runs weigh by how
    much video they covered. A run's footage is its last observation's timestamp: the
    shared timebase starts every run at zero.

    Evidence quality is pooled over every claim of every report, dismissed incidents
    included. The metric asks whether a report cites evidence that exists, not whether
    the incident was real, and a false alert's report has to be grounded too.

    ponytail: loads each report's claims and cited ids into memory; move the unsupported
    check into SQL once reports number in the thousands.
    """
    complete = select(ProcessingRun.run_id).where(ProcessingRun.status == RunStatus.COMPLETE.value)
    per_run = (
        select(func.max(Observation.timestamp_s).label("end_s"))
        .where(Observation.run_id.in_(complete))
        .group_by(Observation.run_id)
        .subquery()
    )
    minutes = (session.scalar(select(func.sum(per_run.c.end_s))) or 0.0) / 60
    events = session.scalar(
        select(func.count()).select_from(SemanticEvent).where(SemanticEvent.run_id.in_(complete))
    )
    incidents = session.scalar(
        select(func.count()).select_from(Incident).where(Incident.run_id.in_(complete))
    )

    latencies = [
        (issued - started).total_seconds()
        for issued, started in session.execute(
            select(Report.created_at, ProcessingRun.started_at)
            .join(ProcessingRun, ProcessingRun.run_id == Report.run_id)
            .where(ProcessingRun.started_at.is_not(None))
        )
    ]

    claims_total = 0
    covered = 0.0
    unsupported = 0.0
    for report in session.scalars(select(Report)):
        known = set(
            session.scalars(
                select(EvidenceNode.node_id).where(EvidenceNode.incident_id == report.incident_id)
            )
        )
        known |= set(
            session.scalars(
                select(SemanticEvent.event_id).where(SemanticEvent.run_id == report.run_id)
            )
        )
        known |= set(
            session.scalars(
                select(Hypothesis.hypothesis_id).where(Hypothesis.incident_id == report.incident_id)
            )
        )
        claims = list(report.claims)
        claims_total += len(claims)
        covered += evidence_coverage(claims) * len(claims)
        unsupported += unsupported_claim_rate(claims, known) * len(claims)

    recent = session.execute(
        select(ProcessingRun.frames_processed, ProcessingRun.stages_s, ProcessingRun.peak_memory_mb)
        .where(
            ProcessingRun.status == RunStatus.COMPLETE.value,
            ProcessingRun.frames_processed.is_not(None),
        )
        .order_by(ProcessingRun.finished_at.desc())
        .limit(RECENT_RUNS)
    ).all()
    frames = sum(row.frames_processed or 0 for row in recent)
    perception_s = sum(
        seconds
        for row in recent
        for stage, seconds in (row.stages_s or {}).items()
        if stage.startswith("perception:")
    )
    memory = [row.peak_memory_mb for row in recent if row.peak_memory_mb is not None]

    return StoredMetrics(
        event_generation_rate=(events or 0) / minutes if minutes else None,
        incident_detection_rate=(incidents or 0) / minutes if minutes else None,
        report_generation_latency_s=sum(latencies) / len(latencies) if latencies else None,
        evidence_coverage=covered / claims_total if claims_total else None,
        unsupported_claim_rate=unsupported / claims_total if claims_total else None,
        frames_per_second=frames / perception_s if perception_s else None,
        peak_memory_mb=max(memory) if memory else None,
    )
