"""Mock API serving the golden fixtures at the real endpoint paths.

This is the decoupler. The investigator UI is built against this from Week 4 and does
not wait for the perception pipeline; every backend sub-phase gets a ready-made input
and a ready-made expected output.

Because both sides are built against the same frozen contract, swapping the frontend
from this to the real API in E8.6 should be a base-URL change rather than a rewrite.
If it is not, the contract leaked and that is worth knowing early.

    make mock          # http://localhost:8000/docs
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from apps.api.main import API_VERSION, PREFIX
from packages.schemas import SCHEMA_VERSION

GOLDEN = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden"

app = FastAPI(
    title="REWIND (mock)",
    version=f"{API_VERSION}+mock",
    summary="Golden fixtures served at the real endpoints",
    description=(
        "Every response is the golden fixture set, regardless of the case id "
        "requested. Useful for building the investigator UI before the pipeline "
        "exists; never a substitute for the real API in a test that claims to "
        "exercise the pipeline."
    ),
)

# The Vite dev server runs on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def fixture(name: str) -> Any:
    """Load one golden fixture, failing loudly if it is missing.

    A missing fixture is a setup error, not a 404: it means the mock is running
    against an incomplete fixture set and every response after it is suspect.
    """
    path = GOLDEN / name
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Golden fixture {name!r} is missing. Run "
                "`uv run python scripts/dataset/make_golden_fixtures.py`."
            ),
        )
    return json.loads(path.read_text())


@app.get(f"{PREFIX}/health", tags=["operations"])
def health() -> dict[str, object]:
    """Report liveness, flagged so a caller cannot mistake this for the real API."""
    return {
        "status": "ok",
        "api_version": f"{API_VERSION}+mock",
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "mock": True,
    }


@app.get(f"{PREFIX}/me", tags=["operations"])
def me() -> dict[str, str]:
    """Sign everyone in as an investigator; the mock has no accounts to check."""
    return {"name": "mock", "role": "investigator"}


@app.get(f"{PREFIX}/sources", tags=["operations"])
def sources() -> list[dict[str, object]]:
    """Offer one source, already processed, so the inbox's dialog has something to show."""
    return [
        {
            "case_ref": "case_01",
            "clips": 3,
            "latest_run_id": "RUN-0001",
            "latest_run_status": "complete",
        }
    ]


@app.get(f"{PREFIX}/metrics", tags=["operations"])
def metrics() -> dict[str, object]:
    """Return plausible metrics so the System Health screen has shape.

    Zeroes would render as an empty dashboard and hide layout problems. The ID-switch
    rate is ``None`` here as in the real API, which never measures it live, so the
    screen's "not measured" state is exercised against the mock as well.
    """
    return {
        "queue_depth": 2,
        "queue_oldest_age_s": 14.2,
        "worker_last_seen_s": 8.0,
        "frames_per_second": 168.4,
        "peak_memory_mb": 1824.0,
        "tracking_id_switch_rate": None,
        "event_generation_rate": 1.7,
        "incident_detection_rate": 0.08,
        "report_generation_latency_s": 2.4,
        "api_error_rate": 0.0,
        "api_latency_p95_ms": 9.2,
        "worker_retries": 0,
        "dead_letter_jobs": 0,
        "evidence_coverage": 1.0,
        "unsupported_claim_rate": 0.0,
    }


@app.get(f"{PREFIX}/runs", tags=["operations"])
def list_runs(limit: int = 50) -> dict[str, Any]:
    """List the golden run as the only processing run."""
    return {"runs": [fixture("01_run.json")][:limit], "total": 1}


@app.get(f"{PREFIX}/cases", tags=["cases"])
def list_cases(
    severity: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List incidents for the case inbox, applying the filters the UI sends."""
    incident = fixture("50_incident.json")
    rows = [incident]
    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]
    return {"cases": rows[:limit], "total": len(rows)}


@app.post(f"{PREFIX}/cases", status_code=status.HTTP_202_ACCEPTED, tags=["cases"])
def create_case(body: dict[str, Any]) -> dict[str, Any]:
    """Accept a case creation request and return the golden run immediately."""
    run = fixture("01_run.json")
    return {
        "run_id": run["run_id"],
        "incident_id": fixture("50_incident.json")["incident_id"],
        "status": "queued",
    }


@app.get(f"{PREFIX}/cases/{{case_id}}", tags=["cases"])
def get_case(case_id: str) -> dict[str, Any]:
    """Return the golden case summary with its cameras and run metadata."""
    incident = fixture("50_incident.json")
    return {
        "incident": incident,
        "run": fixture("01_run.json"),
        "cameras": fixture("00_cameras.json"),
    }


@app.patch(f"{PREFIX}/cases/{{case_id}}", tags=["cases"])
def update_case_status(case_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Echo the golden incident with the requested status; nothing is stored."""
    incident: dict[str, Any] = fixture("50_incident.json")
    return {**incident, "status": body.get("status", incident["status"])}


@app.get(f"{PREFIX}/cases/{{case_id}}/timeline", tags=["cases"])
def get_timeline(case_id: str) -> dict[str, Any]:
    """Return the semantic event timeline plus the track segments behind it."""
    return {
        "run_id": fixture("01_run.json")["run_id"],
        "start_s": None,
        "end_s": None,
        "events": fixture("40_events.json"),
        "segments": fixture("20_track_segments.json"),
        "identity_links": fixture("30_identity_links.json"),
    }


@app.get(f"{PREFIX}/cases/{{case_id}}/evidence", tags=["cases"])
def get_evidence(case_id: str) -> dict[str, Any]:
    """Return the evidence graph, nodes and edges together."""
    graph: dict[str, Any] = fixture("60_evidence_graph.json")
    return graph


@app.get(f"{PREFIX}/cases/{{case_id}}/replay", tags=["cases"])
def get_replay(case_id: str) -> dict[str, Any]:
    """Return synchronized replay metadata for the three camera panes.

    ``clock_offset_s`` is carried per camera rather than pre-applied, because
    correcting the offset is the client's job during scrubbing and hiding it here
    would let a desynchronised player look correct against the mock.
    """
    incident = fixture("50_incident.json")
    return {
        "run_id": fixture("01_run.json")["run_id"],
        "window_start_s": incident["window_start_s"],
        "window_end_s": incident["window_end_s"],
        "detected_at_s": incident["detected_at_s"],
        "cameras": [
            {
                "camera_id": c["camera_id"],
                "name": c["name"],
                "media_url": f"{PREFIX}/cases/{case_id}/media/{c['camera_id']}",
                "clock_offset_s": c["clock_offset_s"],
                "fps": c["fps"],
                "width": c["width"],
                "height": c["height"],
            }
            for c in fixture("00_cameras.json")
        ],
    }


@app.get(f"{PREFIX}/cases/{{case_id}}/media/{{camera_id}}", tags=["cases"])
def get_media(case_id: str, camera_id: str) -> dict[str, Any]:
    """Refuse: the golden fixtures ship no footage, so every pane shows its unavailable state."""
    raise HTTPException(status.HTTP_404_NOT_FOUND, "the golden fixtures carry no footage")


@app.get(f"{PREFIX}/cases/{{case_id}}/report", tags=["cases"])
def get_report(case_id: str) -> dict[str, Any]:
    """Return the report together with the ranked hypotheses it draws on."""
    return {
        "report": fixture("80_report.json"),
        "hypotheses": fixture("70_hypotheses.json"),
    }


@app.post(f"{PREFIX}/cases/{{case_id}}/reprocess", tags=["cases"])
def reprocess_case(case_id: str) -> dict[str, Any]:
    """Acknowledge a reprocess request without doing anything."""
    return {"run_id": fixture("01_run.json")["run_id"], "status": "queued"}
