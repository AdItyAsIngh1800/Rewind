"""Failure tests (E9.4, specification §L): the pipeline under the things that go wrong.

Each test names one failure the roadmap lists — a worker that stops mid-run, a corrupt
clip, a queue that is down, a camera that is missing — and asserts the system's
answer is visible and honest: a run ends FAILED with its reason, or completes with
what it had, and never sits RUNNING forever or reports success it did not have.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api import queue
from packages.database.models import ProcessingRun
from packages.schemas import RunStatus
from services.incidents import list_incidents, load_case_script, state_changes
from services.ingestion import RunConflictError, transition
from services.perception import process_run
from services.reporting import report_for_incident
from tests.integration.conftest import CASE_DIR, needs_db
from tests.integration.test_pipeline import NO_OFFSETS, GroundTruthDetector

SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())


def telemetry(run_id: str) -> list:  # type: ignore[type-arg]
    """case_01's robot state channel as events."""
    return state_changes(
        run_id, load_case_script(pathlib.Path("ml/configs/cases_v1.json"), "case_01")
    )


@needs_db
def test_a_run_interrupted_by_a_worker_restart_is_failed_not_skipped(
    session: Session, queued_run: ProcessingRun
) -> None:
    """A run found RUNNING when a worker picks it up was interrupted; say so.

    ARQ redelivers a job whose worker died. The run is still RUNNING from the first
    attempt, and the state machine forbids RUNNING -> RUNNING, so the second attempt
    cannot simply proceed. Reporting it as complete-and-skipped, as a redelivered
    *finished* run is, would hide a run that never produced anything.
    """
    transition(session, queued_run.run_id, RunStatus.RUNNING)
    with pytest.raises(RunConflictError, match="interrupted"):
        process_run(
            session,
            run_id=queued_run.run_id,
            case_dir=CASE_DIR,
            camera_offsets=NO_OFFSETS,
            detector=GroundTruthDetector(queued_run.run_id),
        )
    session.refresh(queued_run)
    assert queued_run.status == RunStatus.FAILED.value
    assert queued_run.error is not None and "interrupted" in queued_run.error
    assert queued_run.finished_at is not None


@needs_db
def test_a_corrupt_clip_fails_the_run_with_the_file_named(
    session: Session, queued_run: ProcessingRun, tmp_path: pathlib.Path
) -> None:
    """A clip that cannot be read ends the run FAILED, naming the clip, never RUNNING."""
    case_dir = tmp_path / "case_01"
    case_dir.mkdir()
    for clip in CASE_DIR.glob("*.mp4"):
        (case_dir / clip.name).symlink_to(clip.resolve())
    (case_dir / "CAM_B.mp4").unlink()
    (case_dir / "CAM_B.mp4").write_bytes(b"\x00" * 4096)
    with pytest.raises(Exception, match="CAM_B"):
        process_run(
            session,
            run_id=queued_run.run_id,
            case_dir=case_dir,
            camera_offsets=NO_OFFSETS,
            detector=GroundTruthDetector(queued_run.run_id),
        )
    session.refresh(queued_run)
    assert queued_run.status == RunStatus.FAILED.value
    assert queued_run.error is not None and "CAM_B" in queued_run.error


@needs_db
def test_a_corrupt_clip_on_a_clean_database_still_fails_the_run(
    session: Session, tmp_path: pathlib.Path
) -> None:
    """The same corrupt clip, met while registering cameras, must not strand the run.

    On a clean database the pipeline probes each clip to register its camera before
    any frame is read. A probe that raises there is as much a failure of the run as a
    decode error later, and the run must say so rather than stay RUNNING.
    """
    if not any(CASE_DIR.glob("*.mp4")):
        pytest.skip("case_01 video has not been rendered")
    run = ProcessingRun(
        run_id="run-corrupt-clean",
        input_hash="sha256:t",
        dataset_version="v1",
        config_version="t",
        status=RunStatus.QUEUED.value,
    )
    session.add(run)
    session.flush()
    case_dir = tmp_path / "case_01"
    case_dir.mkdir()
    for clip in CASE_DIR.glob("*.mp4"):
        (case_dir / clip.name).symlink_to(clip.resolve())
    (case_dir / "CAM_B.mp4").unlink()
    (case_dir / "CAM_B.mp4").write_bytes(b"\x00" * 4096)
    with pytest.raises(Exception, match="CAM_B"):
        process_run(
            session,
            run_id=run.run_id,
            case_dir=case_dir,
            camera_offsets=NO_OFFSETS,
            detector=GroundTruthDetector(run.run_id),
        )
    session.refresh(run)
    assert run.status == RunStatus.FAILED.value
    assert run.error is not None and "CAM_B" in run.error


@needs_db
def test_a_missing_camera_still_yields_a_report(
    session: Session, queued_run: ProcessingRun, tmp_path: pathlib.Path
) -> None:
    """With one of three cameras absent the run completes on the two it has.

    The incident still opens (the e-stop is telemetry) and its report is generated;
    the missing camera shows up as less evidence, not as a failure.
    """
    case_dir = tmp_path / "case_01"
    case_dir.mkdir()
    for clip in CASE_DIR.glob("*.mp4"):
        if clip.stem != "CAM_B":
            (case_dir / clip.name).symlink_to(clip.resolve())
    result = process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=case_dir,
        camera_offsets=NO_OFFSETS,
        detector=GroundTruthDetector(queued_run.run_id),
        scene=SCENE,
        telemetry=telemetry(queued_run.run_id),
    )
    assert result.cameras == ["CAM_A", "CAM_C"]
    session.refresh(queued_run)
    assert queued_run.status == RunStatus.COMPLETE.value
    assert set(queued_run.media_uris) == {"CAM_A", "CAM_C"}
    incidents = [i for i in list_incidents(session)[0] if i.run_id == queued_run.run_id]
    assert len(incidents) == 1
    report = report_for_incident(session, incidents[0].incident_id)
    assert report is not None and report.claims


@needs_db
def test_a_case_is_created_and_queued_when_redis_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run is the durable record; a dead queue costs the dispatch, not the run."""
    if not any(CASE_DIR.glob("*.mp4")):
        pytest.skip("case_01 video has not been rendered")

    async def refused(run_id: str, case_ref: str) -> bool:
        raise ConnectionRefusedError("redis is down")

    monkeypatch.setattr(queue, "_pool", None)
    monkeypatch.setattr(queue.worker_settings, "redis_url", "redis://127.0.0.1:1/0")
    response = client.post(
        "/api/v1/cases",
        json={"dataset_version": "v1", "case_ref": "case_01", "config_version": "failure-test"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["created"] is True
    assert body["dispatched"] is False
    assert body["status"] == RunStatus.QUEUED.value


@needs_db
def test_metrics_say_the_queue_is_unreachable_when_redis_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A health screen with Redis down reads 'unknown', never 'empty and healthy'."""
    monkeypatch.setattr(queue, "_pool", None)
    monkeypatch.setattr(queue.worker_settings, "redis_url", "redis://127.0.0.1:1/0")
    body = client.get("/api/v1/metrics").json()
    assert body["queue_depth"] is None
    assert body["worker_last_seen_s"] is None
