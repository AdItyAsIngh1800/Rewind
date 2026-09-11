"""Tests for the processing-run registry.

Idempotency is the property under test. A worker that dies mid-job and has its
message redelivered must not create a second run and process everything twice, and a
retried worker must not be able to move a finished run backwards.

Database fixtures live in ``conftest.py``.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy.orm import Session

from packages.database.models import ProcessingRun
from packages.schemas import RunStatus
from services.ingestion import (
    RunConflictError,
    create_run,
    find_by_input,
    run_identity,
    transition,
)
from tests.integration.conftest import needs_db


@pytest.fixture
def clips(tmp_path: pathlib.Path) -> list[pathlib.Path]:
    """Three stand-in camera files with stable contents."""
    paths = []
    for name in ("CAM_A.mp4", "CAM_B.mp4", "CAM_C.mp4"):
        path = tmp_path / name
        path.write_bytes(f"contents of {name}".encode())
        paths.append(path)
    return paths


# --------------------------------------------------------------------------
# Run identity, no database required
# --------------------------------------------------------------------------


def test_identity_is_stable_for_the_same_submission() -> None:
    """Assert the same inputs and versions always produce the same run id."""
    args = ("sha256:abc", "v1", "cfg-1", {"detector": "yolo11n"})
    assert run_identity(*args) == run_identity(*args)


def test_identity_changes_with_the_model_version() -> None:
    """Assert re-running with a new model is a different run.

    Comparing two detectors over identical footage is the normal way to justify a
    change, so those must be two runs rather than one overwritten one.
    """
    base = run_identity("sha256:abc", "v1", "cfg-1", {"detector": "yolo11n"})
    other = run_identity("sha256:abc", "v1", "cfg-1", {"detector": "yolo11s"})
    assert base != other


def test_identity_changes_with_the_config_version() -> None:
    """Assert a threshold change produces a distinct run."""
    base = run_identity("sha256:abc", "v1", "cfg-1", {})
    assert base != run_identity("sha256:abc", "v1", "cfg-2", {})


def test_identity_ignores_model_ordering() -> None:
    """Assert dictionary order does not leak into the identity."""
    first = run_identity("sha256:abc", "v1", "cfg", {"a": "1", "b": "2"})
    second = run_identity("sha256:abc", "v1", "cfg", {"b": "2", "a": "1"})
    assert first == second


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


@needs_db
def test_a_new_submission_creates_a_queued_run(session: Session, clips: list[pathlib.Path]) -> None:
    """Assert a first submission creates a run in the queued state."""
    run, created = create_run(
        session, input_paths=clips, dataset_version="v1", config_version="cfg-1"
    )
    assert created is True
    assert run.status == RunStatus.QUEUED.value
    assert run.input_hash.startswith("sha256:")


@needs_db
def test_resubmitting_the_same_work_does_not_duplicate_it(
    session: Session, clips: list[pathlib.Path]
) -> None:
    """Assert a redelivered submission returns the existing run.

    This is what makes the queue safe to retry. Without it, a worker crash between
    dequeue and acknowledgement would process the same footage twice and leave two
    runs claiming to be the truth about one incident.
    """
    first, created_first = create_run(
        session, input_paths=clips, dataset_version="v1", config_version="cfg-1"
    )
    second, created_second = create_run(
        session, input_paths=clips, dataset_version="v1", config_version="cfg-1"
    )
    assert created_first is True
    assert created_second is False
    assert first.run_id == second.run_id
    assert session.query(ProcessingRun).count() == 1


@needs_db
def test_the_same_footage_with_a_new_config_is_a_new_run(
    session: Session, clips: list[pathlib.Path]
) -> None:
    """Assert reprocessing under a different config creates a second run."""
    create_run(session, input_paths=clips, dataset_version="v1", config_version="cfg-1")
    _run, created = create_run(
        session, input_paths=clips, dataset_version="v1", config_version="cfg-2"
    )
    assert created is True
    assert session.query(ProcessingRun).count() == 2


# --------------------------------------------------------------------------
# Status transitions
# --------------------------------------------------------------------------


@needs_db
def test_a_run_progresses_through_the_normal_path(
    session: Session, clips: list[pathlib.Path]
) -> None:
    """Assert queued to running to complete works and stamps the timestamps."""
    run, _ = create_run(session, input_paths=clips, dataset_version="v1", config_version="c")
    transition(session, run.run_id, RunStatus.RUNNING)
    assert run.started_at is not None
    transition(session, run.run_id, RunStatus.COMPLETE)
    assert run.status == RunStatus.COMPLETE.value
    assert run.finished_at is not None


@needs_db
def test_a_finished_run_cannot_be_restarted(session: Session, clips: list[pathlib.Path]) -> None:
    """Assert a completed run is terminal.

    A report may already cite this run. An audit trail that changes underneath a
    citation is not an audit trail, so reprocessing creates a new run instead.
    """
    run, _ = create_run(session, input_paths=clips, dataset_version="v1", config_version="c")
    transition(session, run.run_id, RunStatus.RUNNING)
    transition(session, run.run_id, RunStatus.COMPLETE)
    with pytest.raises(RunConflictError, match="cannot move from complete"):
        transition(session, run.run_id, RunStatus.RUNNING)


@needs_db
def test_a_queued_run_cannot_skip_straight_to_complete(
    session: Session, clips: list[pathlib.Path]
) -> None:
    """Assert the running state cannot be bypassed.

    A run that reached complete without ever running did no work, and accepting it
    would hide a worker that acknowledged a job it never processed.
    """
    run, _ = create_run(session, input_paths=clips, dataset_version="v1", config_version="c")
    with pytest.raises(RunConflictError):
        transition(session, run.run_id, RunStatus.COMPLETE)


@needs_db
def test_a_failure_records_its_reason(session: Session, clips: list[pathlib.Path]) -> None:
    """Assert a failed run keeps the error text for the postmortem."""
    run, _ = create_run(session, input_paths=clips, dataset_version="v1", config_version="c")
    transition(session, run.run_id, RunStatus.RUNNING)
    transition(session, run.run_id, RunStatus.FAILED, error="corrupt video on CAM_B")
    assert run.status == RunStatus.FAILED.value
    assert run.error == "corrupt video on CAM_B"


@needs_db
def test_transitioning_an_unknown_run_names_it(session: Session) -> None:
    """Assert an unknown run id fails clearly rather than silently."""
    with pytest.raises(RunConflictError, match="no such run"):
        transition(session, "run-does-not-exist", RunStatus.RUNNING)


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------


@needs_db
def test_runs_over_the_same_footage_are_findable(
    session: Session, clips: list[pathlib.Path]
) -> None:
    """Assert every run over one input set can be listed.

    Comparing a baseline against an improved model means finding both runs over the
    same footage, which is exactly what the evaluation plan requires.
    """
    first, _ = create_run(session, input_paths=clips, dataset_version="v1", config_version="c1")
    second, _ = create_run(session, input_paths=clips, dataset_version="v1", config_version="c2")
    found = find_by_input(session, first.input_hash)
    assert {r.run_id for r in found} == {first.run_id, second.run_id}
