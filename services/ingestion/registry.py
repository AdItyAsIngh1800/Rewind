"""The processing-run registry.

A run is the unit of reproducibility. It records exactly which inputs, dataset,
models and configuration produced a set of results, so a benchmark number months
later can be tied back to the thing that produced it. A result without a run behind
it is an anecdote.

Runs are **idempotent by identity**. Submitting the same inputs with the same dataset,
config and model versions returns the existing run rather than creating a second one.
That is what makes the job queue safe to retry: a worker that dies mid-job and is
redelivered must not create a duplicate run and process everything twice.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.database.models import ProcessingRun
from packages.schemas import RunStatus
from services.ingestion.video import input_hash


class RunConflictError(RuntimeError):
    """Raised when a run is moved into a state it cannot legally reach."""


#: Legal status transitions. A finished run is terminal: re-running an input creates
#: a new run rather than mutating the old one, because the old one may already be
#: cited by a report and an audit trail that changes underneath a citation is not one.
ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.COMPLETE, RunStatus.FAILED},
    RunStatus.COMPLETE: set(),
    RunStatus.FAILED: set(),
}


def run_identity(
    input_hash_value: str, dataset_version: str, config_version: str, model_versions: dict[str, str]
) -> str:
    """Derive a stable run id from everything that affects the output.

    Deterministic rather than random, so the same submission maps to the same row
    without a database lookup, and so a run id is meaningful when it appears in a
    report months later.
    """
    import hashlib

    digest = hashlib.sha256()
    digest.update(input_hash_value.encode())
    digest.update(dataset_version.encode())
    digest.update(config_version.encode())
    for name in sorted(model_versions):
        digest.update(f"{name}={model_versions[name]}".encode())
    return f"run-{digest.hexdigest()[:16]}"


def create_run(
    session: Session,
    *,
    input_paths: list[pathlib.Path],
    dataset_version: str,
    config_version: str,
    model_versions: dict[str, str] | None = None,
    device: str = "unknown",
) -> tuple[ProcessingRun, bool]:
    """Create a processing run, or return the existing one.

    Returns the run and whether it was newly created. Callers use that flag to decide
    whether to enqueue work: an existing run has already been queued once, and
    enqueueing it again would duplicate the processing the identity check just
    prevented.
    """
    models = model_versions or {}
    hashed = input_hash(input_paths)
    run_id = run_identity(hashed, dataset_version, config_version, models)

    existing = session.get(ProcessingRun, run_id)
    if existing is not None:
        return existing, False

    run = ProcessingRun(
        run_id=run_id,
        input_hash=hashed,
        dataset_version=dataset_version,
        model_versions=models,
        config_version=config_version,
        status=RunStatus.QUEUED.value,
        device=device,
    )
    session.add(run)
    session.flush()
    return run, True


def transition(
    session: Session, run_id: str, target: RunStatus, error: str | None = None
) -> ProcessingRun:
    """Move a run to a new status, rejecting illegal transitions.

    Enforced rather than trusted. A worker retried after a crash may try to move a
    run that already completed back into running; silently allowing it would let two
    workers write results for the same run and leave no trace of which won.
    """
    run = session.get(ProcessingRun, run_id)
    if run is None:
        raise RunConflictError(f"no such run: {run_id}")

    current = RunStatus(run.status)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise RunConflictError(f"run {run_id} cannot move from {current.value} to {target.value}")

    run.status = target.value
    if target is RunStatus.RUNNING:
        run.started_at = datetime.now(UTC)
    if target in (RunStatus.COMPLETE, RunStatus.FAILED):
        run.finished_at = datetime.now(UTC)
    if error is not None:
        run.error = error
    session.flush()
    return run


def find_by_input(session: Session, input_hash_value: str) -> list[ProcessingRun]:
    """All runs over the same inputs, newest first.

    Reprocessing the same footage with a different model is the normal way to compare
    two approaches, so several runs legitimately share an input hash.
    """
    statement = (
        select(ProcessingRun)
        .where(ProcessingRun.input_hash == input_hash_value)
        .order_by(ProcessingRun.started_at.desc().nullslast())
    )
    return list(session.scalars(statement))
