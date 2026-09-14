"""REWIND API — the contract surface.

Every endpoint from specification §F exists here with its real path, response model
and status codes. The ones that need a working pipeline return 501 for now.

This is deliberate. The generated `openapi.json` is a frozen contract from Week 1,
which is what lets the frontend be built against a mock from Week 4 without waiting
for the perception pipeline. An endpoint that 501s but has the right shape is far
more useful than one that does not exist.
"""

from __future__ import annotations

import pathlib
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.queue import enqueue_run, queue_stats
from apps.api.request_stats import requests as request_window
from packages.database.models import Camera, Incident, ProcessingRun
from packages.database.session import get_session
from packages.schemas import (
    SCHEMA_VERSION,
    EvidenceEdge,
    EvidenceNode,
    Hypothesis,
    IdentityLink,
    IncidentStatus,
    Report,
    RunStatus,
    SemanticEvent,
    Severity,
    TrackSegment,
)
from packages.schemas import Camera as CameraContract
from packages.schemas import Incident as IncidentContract
from packages.schemas import ProcessingRun as RunContract
from services.events import events_for_run, to_contract
from services.evidence import graph_for_incident
from services.identity import link_to_contract, links_for_run
from services.incidents import incident_to_contract, list_incidents
from services.ingestion import case_clips, create_run
from services.observability.metrics import stored_metrics
from services.perception.persistence import segment_to_contract, segments_for_run
from services.reasoning.persistence import hypotheses_for_incident
from services.reporting import report_for_incident

#: Where rendered case media lives. A case reference resolves to a directory here
#: rather than to arbitrary caller-supplied paths, so the API cannot be pointed at
#: files outside the dataset.
SAMPLES = pathlib.Path("data/samples")

API_VERSION = "0.1.0"
PREFIX = "/api/v1"


app = FastAPI(
    title="REWIND",
    version=API_VERSION,
    summary="Evidence-backed AI incident reconstruction engine for multi-camera video",
    description=(
        "Endpoints marked **not yet implemented** return 501 with the correct "
        "response shape already defined. The frontend is built against this contract "
        "from Week 4; the pipeline fills it in behind."
    ),
)

CaseId = Annotated[str, Path(description="Case (incident) identifier")]

#: Annotated form rather than a `Depends` default: the default-argument form is the
#: older FastAPI idiom and evaluates a call at import time.
DbSession = Annotated[Session, Depends(get_session)]


@app.middleware("http")
async def observe_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Time every request and note its status, for ``/metrics`` (spec §N).

    A request that raises is recorded as a 500 before the error propagates, so an
    unhandled failure counts against the error rate rather than disappearing from it.
    """
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        request_window.record(status_code, time.perf_counter() - started)


# --------------------------------------------------------------------------
# Operational endpoints — these work now
# --------------------------------------------------------------------------


class Health(BaseModel):
    """Liveness response, including the contract version this API is serving."""

    status: str = "ok"
    api_version: str = API_VERSION
    schema_version: str = SCHEMA_VERSION
    checked_at: datetime


@app.get(f"{PREFIX}/health", response_model=Health, tags=["operations"])
def health() -> Health:
    """Liveness probe. Used by Docker healthchecks and the System Health screen."""
    return Health(checked_at=datetime.now(UTC))


class Metrics(BaseModel):
    """The metric set from specification §N, measured wherever the system can measure it.

    ``None`` means not measured, never zero. A zero queue or a zero unsupported-claim
    rate reads as "idle and healthy", a claim the API could not back. Queue and worker
    values are ``None`` while Redis is unreachable or no worker has reported; throughput
    and memory while no completed run has recorded them (ADR-0008); API latency and
    errors while this process has served nothing in the last five minutes. The
    ID-switch rate is always ``None``: it needs ground truth.
    """

    queue_depth: int | None = None
    queue_oldest_age_s: float | None = None
    worker_last_seen_s: float | None = Field(
        default=None, description="Seconds since the worker's last heartbeat"
    )
    frames_per_second: float | None = Field(
        default=None, description="Frames through perception per second, over recent runs"
    )
    peak_memory_mb: float | None = Field(
        default=None, description="Highest peak memory of recent runs, process plus accelerator"
    )
    tracking_id_switch_rate: float | None = Field(
        default=None,
        description=(
            "Always null: an ID switch is a track changing which true entity it follows, "
            "and live footage has no ground truth. The held-out benchmark measures it offline"
        ),
    )
    event_generation_rate: float | None = Field(
        default=None, description="Events per minute of processed footage"
    )
    incident_detection_rate: float | None = Field(
        default=None, description="Incidents per minute of processed footage"
    )
    report_generation_latency_s: float | None = Field(
        default=None, description="Run start to report issued, mean over reports"
    )
    api_error_rate: float | None = Field(
        default=None, description="Share of requests answered 5xx, last five minutes, this process"
    )
    api_latency_p95_ms: float | None = Field(
        default=None,
        description="95th-percentile request duration, last five minutes, this process",
    )
    worker_retries: int | None = Field(default=None, description="Since the worker started")
    dead_letter_jobs: int | None = Field(
        default=None, description="Jobs that failed every retry, since the worker started"
    )
    evidence_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    unsupported_claim_rate: float | None = Field(default=None, ge=0.0, le=1.0)


@app.get(f"{PREFIX}/metrics", response_model=Metrics, tags=["operations"])
async def metrics(session: DbSession) -> Metrics:
    """Return operational metrics: the queue from Redis, the rest from stored pipeline output."""
    stored = stored_metrics(session)
    queue = await queue_stats()
    return Metrics(
        queue_depth=queue.depth if queue else None,
        queue_oldest_age_s=queue.oldest_age_s if queue else None,
        worker_last_seen_s=queue.worker_last_seen_s if queue else None,
        worker_retries=queue.worker_retries if queue else None,
        dead_letter_jobs=queue.dead_letter_jobs if queue else None,
        event_generation_rate=stored.event_generation_rate,
        incident_detection_rate=stored.incident_detection_rate,
        report_generation_latency_s=stored.report_generation_latency_s,
        evidence_coverage=stored.evidence_coverage,
        unsupported_claim_rate=stored.unsupported_claim_rate,
        frames_per_second=stored.frames_per_second,
        peak_memory_mb=stored.peak_memory_mb,
        api_error_rate=request_window.error_rate(),
        api_latency_p95_ms=request_window.latency_p95_ms(),
    )


class RunList(BaseModel):
    """Processing runs, not yet started first and then most recently started, with the total."""

    runs: list[RunContract]
    total: int


@app.get(f"{PREFIX}/runs", response_model=RunList, tags=["operations"])
def list_runs(session: DbSession, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> RunList:
    """List processing runs for the System Health screen.

    Not in specification §F. The System Health screen in §G shows latency and failures,
    and a run is where a failure and its duration are recorded, so the screen cannot be
    built without this collection.
    """
    rows = session.scalars(
        select(ProcessingRun)
        .order_by(ProcessingRun.started_at.desc().nulls_first(), ProcessingRun.run_id)
        .limit(limit)
    )
    total = session.scalar(select(func.count()).select_from(ProcessingRun)) or 0
    return RunList(runs=[_run_contract(r) for r in rows], total=total)


# --------------------------------------------------------------------------
# Case lifecycle — shapes frozen, implementations pending
# --------------------------------------------------------------------------


class CreateCaseRequest(BaseModel):
    """Body of a request to create a case and queue its processing run."""

    dataset_version: str
    case_ref: str = Field(description="Which rendered case or media set to process")
    config_version: str = "v0.1.0"


class CreateCaseResponse(BaseModel):
    """Acknowledgement of an accepted case, before any processing has happened."""

    run_id: str
    incident_id: str | None = None
    status: str
    #: False when this submission matched an existing run. The caller learns that its
    #: work was already accepted rather than being told, misleadingly, that a second
    #: run was started.
    created: bool = True
    #: False when the run exists but no worker was told about it, because the queue
    #: was unreachable. The run is still QUEUED and can be dispatched later.
    dispatched: bool = False


NOT_IMPLEMENTED = "Pending — see ROADMAP.md for the phase that delivers this."


def _pending(phase: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{NOT_IMPLEMENTED} Delivered by {phase}.",
    )


@app.post(
    f"{PREFIX}/cases",
    response_model=CreateCaseResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["cases"],
)
async def create_case(body: CreateCaseRequest, session: DbSession) -> CreateCaseResponse:
    """Create a processing run for a case, or return the run that already covers it.

    Idempotent by design. Submitting the same case, dataset and config twice returns
    the first run rather than starting a second, which is what makes a redelivered
    message safe to handle.

    After the run is recorded a job is enqueued for the worker. Dispatch is
    best-effort: if the queue is down the run still exists as QUEUED and the response
    says so, rather than the request failing after the run was already written.
    """
    case_dir = SAMPLES / body.case_ref
    if not case_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case media for {body.case_ref!r} under {SAMPLES}.",
        )

    clips = case_clips(case_dir)
    if not clips:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Case {body.case_ref!r} has ground truth but no rendered video. "
                "Run `make render` before creating a processing run."
            ),
        )

    run, created = create_run(
        session,
        input_paths=clips,
        dataset_version=body.dataset_version,
        config_version=body.config_version,
    )
    session.commit()
    dispatched = await enqueue_run(run.run_id, body.case_ref) if created else True
    return CreateCaseResponse(
        run_id=run.run_id, status=run.status, created=created, dispatched=dispatched
    )


class CaseList(BaseModel):
    """One page of the case inbox, and how many incidents matched in total."""

    cases: list[IncidentContract]
    total: int


@app.get(f"{PREFIX}/cases", response_model=CaseList, tags=["cases"])
def list_cases(
    session: DbSession,
    severity: Severity | None = None,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> CaseList:
    """List incidents for the case inbox, most severe first, filtered by severity and status.

    Not present in specification §F, which jumps straight to fetching one case by
    id. The Case Inbox screen in §G filters incidents by severity, time, location
    and status, and cannot be built without a collection endpoint — so §F is
    incomplete rather than this being new scope.
    """
    rows, total = list_incidents(session, severity=severity, status=status_filter, limit=limit)
    return CaseList(cases=[incident_to_contract(r) for r in rows], total=total)


class StatusChange(BaseModel):
    """A change to where an investigation stands."""

    status: IncidentStatus


@app.patch(f"{PREFIX}/cases/{{case_id}}", response_model=IncidentContract, tags=["cases"])
def update_case_status(case_id: CaseId, body: StatusChange, session: DbSession) -> IncidentContract:
    """Move a case through review: investigating, resolved, or dismissed as a false alert.

    Only the status changes. The window, the evidence graph and the report are evidence
    and stay as issued; a dismissal is the investigator's judgement recorded beside them,
    not an edit to them. Unauthenticated, like every endpoint, until E10.3 adds the role
    boundary.
    """
    incident = session.get(Incident, case_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    incident.status = body.status.value
    session.commit()
    return incident_to_contract(incident)


def _run_contract(run: ProcessingRun) -> RunContract:
    """Rehydrate a run row as the frozen contract."""
    return RunContract(
        run_id=run.run_id,
        input_hash=run.input_hash,
        dataset_version=run.dataset_version,
        model_versions=dict(run.model_versions),
        config_version=run.config_version,
        status=RunStatus(run.status),
        device=run.device,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        media_uris=dict(run.media_uris),
        captured_at=run.captured_at,
    )


class CaseDetail(BaseModel):
    """A case: its incident and rewind window, the run behind it, and the cameras."""

    incident: IncidentContract
    run: RunContract
    cameras: list[CameraContract]


@app.get(f"{PREFIX}/cases/{{case_id}}", response_model=CaseDetail, tags=["cases"])
def get_case(case_id: CaseId, session: DbSession) -> CaseDetail:
    """Return one case: the incident with its rewind window, its run, and the cameras.

    Cameras are every registered camera. The frozen ``ProcessingRun`` does not record
    which cameras a run used, and the MVP has exactly three (charter §3); a run over a
    subset would need that field first.
    """
    incident = session.get(Incident, case_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    run = session.get(ProcessingRun, incident.run_id)
    if run is None:  # the foreign key makes this unreachable short of a broken database
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"case {case_id!r} has no run")
    return CaseDetail(
        incident=incident_to_contract(incident),
        run=_run_contract(run),
        cameras=[
            CameraContract(
                camera_id=c.camera_id,
                name=c.name,
                source_uri=c.source_uri,
                timezone=c.timezone,
                clock_offset_s=c.clock_offset_s,
                width=c.width,
                height=c.height,
                fps=c.fps,
                calibration_ref=c.calibration_ref,
            )
            for c in session.scalars(select(Camera).order_by(Camera.camera_id))
        ],
    )


class Timeline(BaseModel):
    """The event stream of one run with the tracks behind it, clipped if asked.

    Segments are included because the timeline view draws an entity lane per track
    and an event lane on top; serving them together saves the UI a second round trip
    for every seek. Identity links carry every cross-camera comparison the run made,
    refusals included, so the UI can show why two lanes are or are not one entity.
    """

    run_id: str
    start_s: float | None
    end_s: float | None
    events: list[SemanticEvent]
    segments: list[TrackSegment]
    identity_links: list[IdentityLink]


def _run_for_case(session: Session, case_id: str) -> tuple[str, Incident | None]:
    """Resolve a case id to the run whose data backs it.

    A case is an incident (E6). Until incidents exist, and for debugging after, a run
    id is accepted in the same position so the timeline of any processed run can be
    read. Unknown ids are a 404, never an empty timeline.
    """
    incident = session.get(Incident, case_id)
    if incident is not None:
        return incident.run_id, incident
    if session.get(ProcessingRun, case_id) is not None:
        return case_id, None
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case or run {case_id!r}")


@app.get(f"{PREFIX}/cases/{{case_id}}/timeline", tags=["cases"])
def get_timeline(
    case_id: CaseId,
    session: DbSession,
    start_s: Annotated[float | None, Query(description="Window start, seconds")] = None,
    end_s: Annotated[float | None, Query(description="Window end, seconds")] = None,
) -> Timeline:
    """Return the cross-camera semantic event timeline of a case's run.

    A case id with no explicit window returns its incident's rewind window, which is
    what opening a case means. An explicit window always wins, so the investigator can
    widen it; a run id has no window of its own and returns everything.
    """
    run_id, incident = _run_for_case(session, case_id)
    if incident is not None and start_s is None and end_s is None:
        start_s, end_s = incident.window_start_s, incident.window_end_s
    events = [to_contract(r) for r in events_for_run(session, run_id, start_s=start_s, end_s=end_s)]
    segments = [
        segment_to_contract(s)
        for s in segments_for_run(session, run_id)
        if (end_s is None or s.start_time_s <= end_s)
        and (start_s is None or s.end_time_s >= start_s)
    ]
    return Timeline(
        run_id=run_id,
        start_s=start_s,
        end_s=end_s,
        events=events,
        segments=segments,
        identity_links=[link_to_contract(r) for r in links_for_run(session, run_id)],
    )


class EvidenceGraphResponse(BaseModel):
    """One incident's evidence graph: every node and edge, each with its provenance."""

    nodes: list[EvidenceNode]
    edges: list[EvidenceEdge]


@app.get(
    f"{PREFIX}/cases/{{case_id}}/evidence", response_model=EvidenceGraphResponse, tags=["cases"]
)
def get_evidence(case_id: CaseId, session: DbSession) -> EvidenceGraphResponse:
    """Return a case's evidence graph, with provenance on every node and edge.

    Built once, when the run that opened the incident finished (E7.1), and served as
    stored: the graph an investigator reads is the one the report was written from.
    """
    if session.get(Incident, case_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    graph = graph_for_incident(session, case_id)
    return EvidenceGraphResponse(nodes=graph.nodes, edges=graph.edges)


class ReplayCamera(BaseModel):
    """One replay pane: where its clip is served and how its clock maps to the shared one."""

    camera_id: str
    name: str
    media_url: str | None = Field(
        description="Where the browser fetches the clip; None when the run recorded none"
    )
    clock_offset_s: float = Field(description="Clip time = shared time + offset")
    fps: float
    width: int
    height: int


class Replay(BaseModel):
    """What the synchronized replay needs: the window, the trigger and a pane per camera."""

    run_id: str
    window_start_s: float
    window_end_s: float
    detected_at_s: float
    cameras: list[ReplayCamera]


@app.get(f"{PREFIX}/cases/{{case_id}}/replay", response_model=Replay, tags=["cases"])
def get_replay(case_id: CaseId, session: DbSession) -> Replay:
    """Return synchronized replay metadata: the window, the trigger and a pane per camera.

    Offsets are carried per camera rather than applied: mapping the shared clock to each
    clip's own time is the player's job while scrubbing, and pre-applying it would let a
    desynchronised player look correct. A camera the run recorded no clip for still gets
    a pane, with no media, so a missing camera is visible rather than silently dropped.

    ponytail: offsets are the registered cameras' current values, not the ones the run
    was processed with; record them beside ``media_uris`` if a camera is ever
    recalibrated between runs.
    """
    incident = session.get(Incident, case_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    run = session.get(ProcessingRun, incident.run_id)
    if run is None:  # the foreign key makes this unreachable short of a broken database
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"case {case_id!r} has no run")
    return Replay(
        run_id=run.run_id,
        window_start_s=incident.window_start_s,
        window_end_s=incident.window_end_s,
        detected_at_s=incident.detected_at_s,
        cameras=[
            ReplayCamera(
                camera_id=c.camera_id,
                name=c.name,
                media_url=(
                    f"{PREFIX}/cases/{case_id}/media/{c.camera_id}"
                    if c.camera_id in run.media_uris
                    else None
                ),
                clock_offset_s=c.clock_offset_s,
                fps=c.fps,
                width=c.width,
                height=c.height,
            )
            for c in session.scalars(select(Camera).order_by(Camera.camera_id))
        ],
    )


@app.get(
    f"{PREFIX}/cases/{{case_id}}/media/{{camera_id}}",
    response_class=FileResponse,
    tags=["cases"],
)
def get_media(case_id: CaseId, camera_id: str, session: DbSession) -> FileResponse:
    """Stream one camera's clip for a case, with range support so the browser can seek.

    The one route raw footage leaves by (ADR-0006). The path comes from the run's record,
    never from the request, and must resolve inside the samples root: a recorded path
    anywhere else is refused, as is one whose file is gone. Both are a 404 so a probe
    learns nothing about the filesystem. E10.3 adds the role check and the evidence
    access log here, and nowhere else has to change.
    """
    incident = session.get(Incident, case_id)
    run = session.get(ProcessingRun, incident.run_id) if incident is not None else None
    recorded = run.media_uris.get(camera_id) if run is not None else None
    if recorded is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"case {case_id!r} has no recorded footage for {camera_id!r}"
        )
    path = pathlib.Path(recorded).resolve()
    if not path.is_relative_to(SAMPLES.resolve()) or not path.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"footage for {camera_id!r} in case {case_id!r} is unavailable",
        )
    return FileResponse(path, media_type="video/mp4")


class CaseReport(BaseModel):
    """A case's report together with the ranked hypotheses it draws on."""

    report: Report
    hypotheses: list[Hypothesis]


@app.get(f"{PREFIX}/cases/{{case_id}}/report", response_model=CaseReport, tags=["cases"])
def get_report(case_id: CaseId, session: DbSession) -> CaseReport:
    """Return a case's evidence-grounded report, with the hypotheses it ranks.

    Generated once, when the run that opened the incident finished (E7.4), and served
    as issued. A case whose run predates the generator has no report: that is a 404
    saying so, not an empty report that would read as "nothing to say".
    """
    if session.get(Incident, case_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    report = report_for_incident(session, case_id)
    if report is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"case {case_id!r} has no report; reprocess its run"
        )
    return CaseReport(report=report, hypotheses=hypotheses_for_incident(session, case_id))


@app.post(f"{PREFIX}/cases/{{case_id}}/reprocess", tags=["cases"])
def reprocess_case(case_id: CaseId) -> dict[str, object]:
    """Re-run a case with a different model or config version.

    Not yet implemented — delivered by E2.2.
    """
    raise _pending("E2.2")
