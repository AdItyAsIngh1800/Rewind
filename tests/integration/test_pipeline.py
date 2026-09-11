"""End-to-end tests for the perception pipeline.

Run against real rendered video and a real database, with a detector stand-in that
returns ray-cast ground truth for whatever frames it is handed. That isolates the
pipeline's own behaviour: sampling, batching, tracker feeding, persistence and run
state transitions. The only thing not exercised is the model, which is deliberate;
the model has its own evaluation.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from packages.database.models import Camera, ProcessingRun
from packages.schemas import Observation, RunStatus
from services.events import events_for_run
from services.ingestion import Frame, RunConflictError
from services.perception import (
    observations_in_window,
    process_run,
    segments_for_run,
)
from tests.integration.conftest import needs_db

CASE_DIR = pathlib.Path("data/samples/case_01")
#: Deliberately wrong offsets. The clips are frame-synchronous (scene spec §4.1), so
#: applying these shifts CAM_B and CAM_C off the true clock by exactly these amounts;
#: the tests below assert both that the shift is applied and that E5.1 catches it.
OFFSETS = {"CAM_A": 0.0, "CAM_B": 0.4, "CAM_C": -0.2}
NO_OFFSETS = {"CAM_A": 0.0, "CAM_B": 0.0, "CAM_C": 0.0}


class GroundTruthDetector:
    """Return ray-cast ground truth for the frames it is asked about.

    Never looks at the pixels. Its output is exactly what a perfect detector would
    produce, which makes everything downstream of it measurable on its own.
    """

    def __init__(self, run_id: str) -> None:
        """Index the case's ground truth by camera and frame."""
        rows = json.loads((CASE_DIR / "observations_gt.json").read_text())
        self._by_key: dict[tuple[str, int], list[dict[str, object]]] = {}
        for row in rows:
            key = (str(row["camera_id"]), int(row["frame_index"]))
            self._by_key.setdefault(key, []).append({**row, "run_id": run_id, "track_id": None})

    def detect(
        self,
        frames: list[Frame],
        *,
        run_id: str,
        camera_id: str,
        frame_indices: list[int],
        timestamps: list[float],
    ) -> Iterator[Observation]:
        """Yield the ground truth for each requested frame, with the run's timestamps."""
        for index, timestamp in zip(frame_indices, timestamps, strict=True):
            for row in self._by_key.get((camera_id, index), []):
                yield Observation.model_validate({**row, "timestamp_s": timestamp})


class ExplodingDetector:
    """Fail on the first batch, to exercise the pipeline's failure path."""

    def detect(
        self,
        frames: list[Frame],
        *,
        run_id: str,
        camera_id: str,
        frame_indices: list[int],
        timestamps: list[float],
    ) -> Iterator[Observation]:
        """Raise as a model with a corrupt checkpoint would."""
        raise RuntimeError("simulated detector failure")
        yield  # pragma: no cover - makes this a generator


@pytest.fixture
def queued_run(session: Session) -> ProcessingRun:
    """Create a queued run with its cameras registered."""
    if not any(CASE_DIR.glob("*.mp4")):
        pytest.skip("case_01 video has not been rendered")
    for camera_id in OFFSETS:
        session.add(
            Camera(
                camera_id=camera_id,
                name=camera_id,
                source_uri="file:///x",
                clock_offset_s=OFFSETS[camera_id],
                width=1280,
                height=720,
                fps=10.0,
            )
        )
    run = ProcessingRun(
        run_id="run-pipeline-test",
        input_hash="sha256:t",
        dataset_version="v1",
        config_version="t",
        status=RunStatus.QUEUED.value,
    )
    session.add(run)
    session.flush()
    return run


@needs_db
def test_pipeline_processes_a_case_end_to_end(session: Session, queued_run: ProcessingRun) -> None:
    """Assert real video flows through sampling, tracking and persistence to COMPLETE."""
    result = process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=OFFSETS,
        detector=GroundTruthDetector(queued_run.run_id),
    )
    assert result.cameras == ["CAM_A", "CAM_B", "CAM_C"]
    assert result.frames_processed == 3 * 450
    # Every ground-truth observation should have been re-emitted and persisted.
    truth_count = len(json.loads((CASE_DIR / "observations_gt.json").read_text()))
    assert result.observations == truth_count
    assert result.observations_written == truth_count
    assert result.segments > 0
    session.refresh(queued_run)
    assert queued_run.status == RunStatus.COMPLETE.value
    assert queued_run.started_at is not None and queued_run.finished_at is not None


@needs_db
def test_pipeline_extracts_and_persists_events(session: Session, queued_run: ProcessingRun) -> None:
    """Assert a run given the scene config ends with an event stream in the database."""
    scene = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
    result = process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=NO_OFFSETS,
        detector=GroundTruthDetector(queued_run.run_id),
        scene=scene,
    )
    assert result.events > 0
    assert result.events_written == result.events
    rows = events_for_run(session, queued_run.run_id)
    assert len(rows) == result.events
    assert all(r.evidence_refs for r in rows), "an event without evidence must not exist"
    # The e-stop case: the robot stops inside the intersection after the person enters.
    kinds = {r.event_type for r in rows}
    assert {"zone_entry", "zone_exit", "stop"} <= kinds
    assert events_for_run(session, queued_run.run_id, start_s=10.0, end_s=14.0)
    assert not events_for_run(session, queued_run.run_id, start_s=900.0)
    # The clips are synchronous and no offset was applied, so no camera shows a residual.
    assert set(result.clock_residuals_s) == {"CAM_B", "CAM_C"}
    assert all(abs(r) <= 0.3 for r in result.clock_residuals_s.values())


@needs_db
def test_wrong_clock_offsets_are_detected_from_the_events(
    session: Session, queued_run: ProcessingRun
) -> None:
    """Assert E5.1 recovers an injected clock error from shared zone crossings."""
    scene = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
    result = process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=OFFSETS,
        detector=GroundTruthDetector(queued_run.run_id),
        scene=scene,
    )
    # Subtracting a spurious +0.4 s makes CAM_B stamp everything 0.4 s early.
    assert result.clock_residuals_s["CAM_B"] == pytest.approx(-0.4, abs=0.15)
    assert result.clock_residuals_s["CAM_C"] == pytest.approx(0.2, abs=0.15)


@needs_db
def test_pipeline_applies_clock_offsets(session: Session, queued_run: ProcessingRun) -> None:
    """Assert persisted timestamps are on the shared timebase, not clip-local.

    CAM_B runs 0.4 s fast, so its frame 135 (13.5 s clip time) must land at 13.1 s.
    Skipping the correction would be invisible in a single-camera test and would
    misorder every cross-camera event.
    """
    process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=OFFSETS,
        detector=GroundTruthDetector(queued_run.run_id),
    )
    rows = observations_in_window(session, queued_run.run_id, "CAM_B", 13.05, 13.15)
    assert rows, "expected CAM_B observations near 13.1 s on the shared timebase"
    assert all(r.frame_index == 135 for r in rows)


@needs_db
def test_pipeline_produces_stable_tracks(session: Session, queued_run: ProcessingRun) -> None:
    """Assert perfect boxes yield few segments per camera.

    With ground truth in, the tracker sees two entities per camera. Some
    fragmentation across the long visibility gap is expected; an explosion of
    segments would mean the pipeline is feeding the tracker out of order.
    """
    process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=OFFSETS,
        detector=GroundTruthDetector(queued_run.run_id),
    )
    per_camera: dict[str, int] = {}
    for segment in segments_for_run(session, queued_run.run_id):
        per_camera[segment.camera_id] = per_camera.get(segment.camera_id, 0) + 1
    assert set(per_camera) == {"CAM_A", "CAM_B", "CAM_C"}
    assert all(count <= 5 for count in per_camera.values()), per_camera


@needs_db
def test_a_failing_detector_marks_the_run_failed(
    session: Session, queued_run: ProcessingRun
) -> None:
    """Assert a crash mid-run is recorded as FAILED with its reason.

    A run left QUEUED after a crash is indistinguishable from one that never
    started, which is how a stuck job hides for a week.
    """
    with pytest.raises(RuntimeError, match="simulated detector failure"):
        process_run(
            session,
            run_id=queued_run.run_id,
            case_dir=CASE_DIR,
            camera_offsets=OFFSETS,
            detector=ExplodingDetector(),
        )
    session.refresh(queued_run)
    assert queued_run.status == RunStatus.FAILED.value
    assert queued_run.error is not None and "simulated detector failure" in queued_run.error


@needs_db
def test_a_completed_run_cannot_be_reprocessed_in_place(
    session: Session, queued_run: ProcessingRun
) -> None:
    """Assert running the pipeline twice on one run is refused.

    A completed run may already be cited. Reprocessing creates a new run instead.
    """
    detector = GroundTruthDetector(queued_run.run_id)
    process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=OFFSETS,
        detector=detector,
    )
    with pytest.raises(RunConflictError, match="cannot move from complete"):
        process_run(
            session,
            run_id=queued_run.run_id,
            case_dir=CASE_DIR,
            camera_offsets=OFFSETS,
            detector=detector,
        )
