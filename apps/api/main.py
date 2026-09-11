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
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.queue import enqueue_run
from packages.database.models import Incident, ProcessingRun
from packages.database.session import get_session
from packages.schemas import SCHEMA_VERSION, IdentityLink, SemanticEvent, TrackSegment
from services.events import events_for_run, to_contract
from services.ingestion import create_run
from services.perception.persistence import segment_to_contract, segments_for_run

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
    """The metric set from specification §N.

    Zeroed until the pipeline runs. The shape is fixed now so the System Health
    screen can be built against it.
    """

    queue_depth: int = 0
    queue_oldest_age_s: float = 0.0
    frames_per_second: float = 0.0
    tracking_id_switch_rate: float = 0.0
    event_generation_rate: float = 0.0
    incident_detection_rate: float = 0.0
    report_generation_latency_s: float = 0.0
    api_error_rate: float = 0.0
    worker_retries: int = 0
    dead_letter_jobs: int = 0
    evidence_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    unsupported_claim_rate: float = Field(default=0.0, ge=0.0, le=1.0)


@app.get(f"{PREFIX}/metrics", response_model=Metrics, tags=["operations"])
def metrics() -> Metrics:
    """Operational metrics. Real values arrive with the worker in E10.2."""
    return Metrics()


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

    clips = sorted(case_dir.glob("*.mp4"))
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


@app.get(f"{PREFIX}/cases", tags=["cases"])
def list_cases(
    severity: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, object]:
    """List incidents for the case inbox, filtered by severity and status.

    Not present in specification §F, which jumps straight to fetching one case by
    id. The Case Inbox screen in §G filters incidents by severity, time, location
    and status, and cannot be built without a collection endpoint — so §F is
    incomplete rather than this being new scope.

    Not yet implemented — delivered by E6.2.
    """
    raise _pending("E6.2")


@app.get(f"{PREFIX}/cases/{{case_id}}", tags=["cases"])
def get_case(case_id: CaseId) -> dict[str, object]:
    """Return the case summary.

    Not yet implemented — delivered by E6.2.
    """
    raise _pending("E6.2")


class Timeline(BaseModel):
    """The event stream of one run with the tracks behind it, clipped if asked.

    Segments are included because the timeline view draws an entity lane per track
    and an event lane on top; serving them together saves the UI a second round trip
    for every seek. Identity links are empty until E5 links segments across cameras.
    """

    run_id: str
    start_s: float | None
    end_s: float | None
    events: list[SemanticEvent]
    segments: list[TrackSegment]
    identity_links: list[IdentityLink]


def _run_for_case(session: Session, case_id: str) -> str:
    """Resolve a case id to the run whose data backs it.

    A case is an incident (E6). Until incidents exist, and for debugging after, a run
    id is accepted in the same position so the timeline of any processed run can be
    read. Unknown ids are a 404, never an empty timeline.
    """
    incident = session.get(Incident, case_id)
    if incident is not None:
        return incident.run_id
    if session.get(ProcessingRun, case_id) is not None:
        return case_id
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case or run {case_id!r}")


@app.get(f"{PREFIX}/cases/{{case_id}}/timeline", tags=["cases"])
def get_timeline(
    case_id: CaseId,
    session: DbSession,
    start_s: Annotated[float | None, Query(description="Window start, seconds")] = None,
    end_s: Annotated[float | None, Query(description="Window end, seconds")] = None,
) -> Timeline:
    """Return the cross-camera semantic event timeline of a case's run."""
    run_id = _run_for_case(session, case_id)
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
        identity_links=[],
    )


@app.get(f"{PREFIX}/cases/{{case_id}}/evidence", tags=["cases"])
def get_evidence(case_id: CaseId) -> dict[str, object]:
    """Return the evidence graph, with provenance on every node and edge.

    Not yet implemented — delivered by E7.1.
    """
    raise _pending("E7.1")


@app.get(f"{PREFIX}/cases/{{case_id}}/replay", tags=["cases"])
def get_replay(case_id: CaseId) -> dict[str, object]:
    """Return synchronized replay metadata: clips, offsets and the shared timebase.

    Not yet implemented — delivered by E8.2.
    """
    raise _pending("E8.2")


@app.get(f"{PREFIX}/cases/{{case_id}}/report", tags=["cases"])
def get_report(case_id: CaseId) -> dict[str, object]:
    """Return the evidence-grounded report for this case.

    Not yet implemented — delivered by E7.4.
    """
    raise _pending("E7.4")


@app.post(f"{PREFIX}/cases/{{case_id}}/reprocess", tags=["cases"])
def reprocess_case(case_id: CaseId) -> dict[str, object]:
    """Re-run a case with a different model or config version.

    Not yet implemented — delivered by E2.2.
    """
    raise _pending("E2.2")
