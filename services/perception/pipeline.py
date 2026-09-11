"""The perception pipeline: video in, persisted observations and tracks out.

One function runs a whole processing run: for each camera, sample frames, detect,
track, and persist. It is the thing the worker calls and the thing an integration
test exercises end to end.

The detector is injected rather than constructed here. That is what lets the
pipeline be tested with a ground-truth-backed stand-in before any model exists, and
what lets a run record exactly which detector produced it. A pipeline that quietly
loaded a default checkpoint would be one whose results could not be tied to a model
version.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from packages.schemas import Observation, RunStatus, TrackSegment
from services.ingestion import Frame, decode_frames, plan_sampling, probe, transition
from services.perception.persistence import write_observations, write_segments
from services.tracking import Tracker, TrackerConfig

log = logging.getLogger(__name__)

#: Frames per detector call. Small on purpose: memory headroom on unified memory is
#: worth more than the marginal throughput of a larger batch, given the machine runs
#: roughly ten times faster than the dataset needs.
BATCH = 8


class DetectorLike(Protocol):
    """What the pipeline needs from a detector, and nothing more.

    Both the real YOLO wrapper and the ground-truth stand-in satisfy this, which is
    how the same pipeline code is tested without a model and run with one.
    """

    def detect(
        self,
        frames: list[Frame],
        *,
        run_id: str,
        camera_id: str,
        frame_indices: list[int],
        timestamps: list[float],
    ) -> Iterator[Observation]:
        """Yield observations for a batch of frames."""
        ...


@dataclass
class PipelineResult:
    """What one run produced, for the caller to log or assert on."""

    run_id: str
    cameras: list[str] = field(default_factory=list)
    frames_processed: int = 0
    observations: int = 0
    segments: int = 0
    observations_written: int = 0
    segments_written: int = 0


def process_camera(
    clip: pathlib.Path,
    *,
    run_id: str,
    camera_id: str,
    clock_offset_s: float,
    target_fps: float,
    detector: DetectorLike,
    tracker_config: TrackerConfig,
) -> tuple[list[Observation], list[TrackSegment], int]:
    """Detect and track one camera's clip.

    Returns the tracked observations, the segments, and the frame count. Frames are
    decoded sequentially and fed to the tracker in order, including frames where the
    detector found nothing, so lost tracks age at the true rate.
    """
    metadata = probe(clip)
    plan = plan_sampling(
        metadata, camera_id=camera_id, target_fps=target_fps, clock_offset_s=clock_offset_s
    )
    by_index = {frame.source_index: frame for frame in plan}
    tracker = Tracker(camera_id, tracker_config)

    tracked: list[Observation] = []
    batch_frames: list[Frame] = []
    batch_indices: list[int] = []
    processed = 0

    def flush() -> None:
        if not batch_frames:
            return
        detected = list(
            detector.detect(
                batch_frames,
                run_id=run_id,
                camera_id=camera_id,
                frame_indices=batch_indices,
                timestamps=[by_index[i].timestamp_s for i in batch_indices],
            )
        )
        # The tracker must see every frame in order, including empty ones, so
        # detections are regrouped by frame before being fed one frame at a time.
        by_frame: dict[int, list[Observation]] = {i: [] for i in batch_indices}
        for observation in detected:
            by_frame[observation.frame_index].append(observation)
        for index in batch_indices:
            tracked.extend(tracker.update(by_frame[index]))
        batch_frames.clear()
        batch_indices.clear()

    for source_index, frame in decode_frames(clip, [f.source_index for f in plan]):
        batch_frames.append(frame)
        batch_indices.append(source_index)
        processed += 1
        if len(batch_frames) >= BATCH:
            flush()
    flush()

    return tracked, tracker.segments(run_id), processed


def process_run(
    session: Session,
    *,
    run_id: str,
    case_dir: pathlib.Path,
    camera_offsets: dict[str, float],
    detector: DetectorLike,
    tracker_config: TrackerConfig | None = None,
    target_fps: float = 10.0,
) -> PipelineResult:
    """Run the full perception stage for one processing run and persist the result.

    Moves the run to RUNNING first and to COMPLETE or FAILED at the end. A failure
    leaves the run marked FAILED with the error text, never silently QUEUED, so a
    stuck run is visible rather than indistinguishable from one that never started.
    """
    config = tracker_config or TrackerConfig()
    result = PipelineResult(run_id=run_id)
    transition(session, run_id, RunStatus.RUNNING)
    session.commit()

    try:
        all_observations: list[Observation] = []
        all_segments: list[TrackSegment] = []
        for clip in sorted(case_dir.glob("*.mp4")):
            camera_id = clip.stem
            log.info("run %s: %s", run_id, camera_id)
            observations, segments, frames = process_camera(
                clip,
                run_id=run_id,
                camera_id=camera_id,
                clock_offset_s=camera_offsets.get(camera_id, 0.0),
                target_fps=target_fps,
                detector=detector,
                tracker_config=config,
            )
            result.cameras.append(camera_id)
            result.frames_processed += frames
            all_observations.extend(observations)
            all_segments.extend(segments)

        result.observations = len(all_observations)
        result.segments = len(all_segments)
        result.observations_written = write_observations(session, all_observations)
        result.segments_written = write_segments(session, all_segments)
        transition(session, run_id, RunStatus.COMPLETE)
        session.commit()
    except Exception as exc:
        session.rollback()
        transition(session, run_id, RunStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        session.commit()
        raise

    log.info(
        "run %s complete: %d frames, %d observations, %d segments",
        run_id,
        result.frames_processed,
        result.observations,
        result.segments,
    )
    return result
