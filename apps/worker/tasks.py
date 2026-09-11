"""Worker tasks.

One task: process a case. It is a thin wrapper around ``process_run`` so that the
pipeline logic stays testable without a queue, and the queue stays a transport
rather than a place where behaviour lives.

Idempotency comes from the layers beneath. The run registry refuses to restart a
completed run, and persistence skips rows already present, so a redelivered message
for a finished run is a no-op and a redelivered message for a half-finished one
resumes safely.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from apps.worker.settings import worker_settings
from packages.database.session import make_engine
from packages.schemas import RunStatus
from services.ingestion import RunConflictError
from services.perception import Detector, DetectorConfig, process_run

log = logging.getLogger(__name__)


def build_detector() -> Detector:
    """Construct the detector the worker is configured to use.

    Falls back to the COCO checkpoint with a loud warning if the fine-tuned weights
    are absent, rather than failing to start. A worker that cannot start processes
    nothing; a worker on the wrong model at least records which model it used.
    """
    settings = worker_settings
    if settings.detector_checkpoint.exists():
        config = DetectorConfig(
            checkpoint=str(settings.detector_checkpoint),
            confidence=settings.detector_confidence,
            device=settings.detector_device,
            native_classes=settings.detector_native_classes,
        )
    else:
        log.warning(
            "fine-tuned checkpoint %s not found; falling back to COCO yolo11n, which "
            "cannot detect robot or pallet",
            settings.detector_checkpoint,
        )
        config = DetectorConfig(
            checkpoint="yolo11n.pt",
            confidence=settings.detector_confidence,
            device=settings.detector_device,
            native_classes=False,
        )
    return Detector(config)


def camera_offsets() -> dict[str, float]:
    """Read per-camera clock offsets from the scene config."""
    scene = json.loads(worker_settings.scene_config.read_text())
    return {camera["id"]: float(camera["clock_offset_s"]) for camera in scene["cameras"]}


async def process_case(ctx: dict[str, Any], run_id: str, case_ref: str) -> dict[str, Any]:
    """Run perception for one queued run.

    Args:
        ctx: ARQ's context; unused, but part of the task signature.
        run_id: The processing run to execute.
        case_ref: Which case directory under ``samples_dir`` holds the media.

    Returns:
        A summary dict, which ARQ stores as the job result.

    """
    case_dir = worker_settings.samples_dir / case_ref
    log.info("job: run %s on %s", run_id, case_ref)

    engine = make_engine()
    with Session(engine) as session:
        try:
            result = process_run(
                session,
                run_id=run_id,
                case_dir=case_dir,
                camera_offsets=camera_offsets(),
                detector=build_detector(),
            )
        except RunConflictError as exc:
            # A redelivered message for a run that already finished. Not an error:
            # the work is done and the message can be acknowledged.
            log.info("run %s: %s; nothing to do", run_id, exc)
            return {"run_id": run_id, "status": RunStatus.COMPLETE.value, "skipped": True}

    return {
        "run_id": result.run_id,
        "status": RunStatus.COMPLETE.value,
        "frames": result.frames_processed,
        "observations": result.observations_written,
        "segments": result.segments_written,
    }
