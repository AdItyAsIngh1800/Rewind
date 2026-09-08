"""REWIND API — the contract surface.

Every endpoint from specification §F exists here with its real path, response model
and status codes. The ones that need a working pipeline return 501 for now.

This is deliberate. The generated `openapi.json` is a frozen contract from Week 1,
which is what lets the frontend be built against a mock from Week 4 without waiting
for the perception pipeline. An endpoint that 501s but has the right shape is far
more useful than one that does not exist.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, status
from pydantic import BaseModel, Field

from packages.schemas import SCHEMA_VERSION

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


# --------------------------------------------------------------------------
# Operational endpoints — these work now
# --------------------------------------------------------------------------


class Health(BaseModel):
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
    dataset_version: str
    case_ref: str = Field(description="Which rendered case or media set to process")
    config_version: str = "v0.1.0"


class CreateCaseResponse(BaseModel):
    run_id: str
    incident_id: str | None = None
    status: str


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
def create_case(body: CreateCaseRequest) -> CreateCaseResponse:
    """Create a processing run and queue the pipeline. **Not yet implemented.**"""
    raise _pending("E2.2")


@app.get(f"{PREFIX}/cases/{{case_id}}", tags=["cases"])
def get_case(case_id: CaseId) -> dict[str, object]:
    """Case summary. **Not yet implemented.**"""
    raise _pending("E6.2")


@app.get(f"{PREFIX}/cases/{{case_id}}/timeline", tags=["cases"])
def get_timeline(case_id: CaseId) -> dict[str, object]:
    """Cross-camera semantic event timeline. **Not yet implemented.**"""
    raise _pending("E4.3")


@app.get(f"{PREFIX}/cases/{{case_id}}/evidence", tags=["cases"])
def get_evidence(case_id: CaseId) -> dict[str, object]:
    """Evidence graph with provenance. **Not yet implemented.**"""
    raise _pending("E7.1")


@app.get(f"{PREFIX}/cases/{{case_id}}/replay", tags=["cases"])
def get_replay(case_id: CaseId) -> dict[str, object]:
    """Synchronized replay metadata: clips, offsets, shared timebase. **Not yet implemented.**"""
    raise _pending("E8.2")


@app.get(f"{PREFIX}/cases/{{case_id}}/report", tags=["cases"])
def get_report(case_id: CaseId) -> dict[str, object]:
    """Evidence-grounded report. **Not yet implemented.**"""
    raise _pending("E7.4")


@app.post(f"{PREFIX}/cases/{{case_id}}/reprocess", tags=["cases"])
def reprocess_case(case_id: CaseId) -> dict[str, object]:
    """Re-run a case with a different model or config version. **Not yet implemented.**"""
    raise _pending("E2.2")
