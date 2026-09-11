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
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray
from sqlalchemy.orm import Session

from packages.common.camera import CameraModel
from packages.schemas import Observation, RunStatus, TrackSegment
from services.events import (
    EventConfig,
    class_heights,
    extract_events,
    load_zones,
    localise_all,
    merge_across_cameras,
    write_events,
)
from services.identity import (
    associate,
    build_segment_tracks,
    estimate_offsets,
    misaligned,
    write_links,
)
from services.identity.appearance import TrackDescriptors
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
class CameraOutput:
    """Everything one camera's pass produced."""

    observations: list[Observation]
    segments: list[TrackSegment]
    frames: int
    #: Mean appearance descriptor per local track id (E5.2), an intermediate for
    #: cross-camera association within the same run; not persisted.
    descriptors: dict[str, NDArray[np.float64]]


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
    events: int = 0
    events_written: int = 0
    #: Residual clock offset per camera against the first camera, from shared zone
    #: crossings (E5.1). A value beyond tolerance means the configured offset is wrong.
    clock_residuals_s: dict[str, float] = field(default_factory=dict)
    links: int = 0
    links_linked: int = 0


def process_camera(
    clip: pathlib.Path,
    *,
    run_id: str,
    camera_id: str,
    clock_offset_s: float,
    target_fps: float,
    detector: DetectorLike,
    tracker_config: TrackerConfig,
) -> CameraOutput:
    """Detect, track and describe one camera's clip.

    Frames are decoded sequentially and fed to the tracker in order, including frames
    where the detector found nothing, so lost tracks age at the true rate. Appearance
    descriptors are taken in the same pass because the frames are in hand here and
    nowhere else.
    """
    metadata = probe(clip)
    plan = plan_sampling(
        metadata, camera_id=camera_id, target_fps=target_fps, clock_offset_s=clock_offset_s
    )
    by_index = {frame.source_index: frame for frame in plan}
    tracker = Tracker(camera_id, tracker_config)
    descriptors = TrackDescriptors()

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
        for frame, index in zip(batch_frames, batch_indices, strict=True):
            assigned = tracker.update(by_frame[index])
            tracked.extend(assigned)
            for o in assigned:
                if o.track_id:
                    descriptors.add(frame, o.track_id, o.bbox)
        batch_frames.clear()
        batch_indices.clear()

    for source_index, frame in decode_frames(clip, [f.source_index for f in plan]):
        batch_frames.append(frame)
        batch_indices.append(source_index)
        processed += 1
        if len(batch_frames) >= BATCH:
            flush()
    flush()

    return CameraOutput(tracked, tracker.segments(run_id), processed, descriptors.result())


def process_run(
    session: Session,
    *,
    run_id: str,
    case_dir: pathlib.Path,
    camera_offsets: dict[str, float],
    detector: DetectorLike,
    tracker_config: TrackerConfig | None = None,
    target_fps: float = 10.0,
    scene: dict[str, Any] | None = None,
) -> PipelineResult:
    """Run perception and event extraction for one run and persist the result.

    Moves the run to RUNNING first and to COMPLETE or FAILED at the end. A failure
    leaves the run marked FAILED with the error text, never silently QUEUED, so a
    stuck run is visible rather than indistinguishable from one that never started.

    ``scene`` is the scene config with zones, cameras and entity heights. Without it
    the run still produces observations and segments but no events, and says so.
    """
    config = tracker_config or TrackerConfig()
    result = PipelineResult(run_id=run_id)
    transition(session, run_id, RunStatus.RUNNING)
    session.commit()

    try:
        all_observations: list[Observation] = []
        all_segments: list[TrackSegment] = []
        descriptors: dict[str, NDArray[np.float64]] = {}
        for clip in sorted(case_dir.glob("*.mp4")):
            camera_id = clip.stem
            log.info("run %s: %s", run_id, camera_id)
            out = process_camera(
                clip,
                run_id=run_id,
                camera_id=camera_id,
                clock_offset_s=camera_offsets.get(camera_id, 0.0),
                target_fps=target_fps,
                detector=detector,
                tracker_config=config,
            )
            result.cameras.append(camera_id)
            result.frames_processed += out.frames
            all_observations.extend(out.observations)
            all_segments.extend(out.segments)
            descriptors.update(out.descriptors)

        result.observations = len(all_observations)
        result.segments = len(all_segments)
        result.observations_written = write_observations(session, all_observations)
        result.segments_written = write_segments(session, all_segments)
        if scene is None:
            log.warning("run %s: no scene config, skipping event extraction", run_id)
        else:
            config_events = EventConfig()
            cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
            heights = class_heights(scene)
            raw_events = extract_events(
                run_id,
                all_observations,
                load_zones(scene),
                cameras,
                heights,
                config_events,
            )
            if result.cameras:
                estimates = estimate_offsets(raw_events, reference=result.cameras[0])
                result.clock_residuals_s = {c: e.residual_s for c, e in estimates.items()}
                for camera_id in misaligned(estimates):
                    log.warning(
                        "run %s: %s is %.2f s off %s; check its clock_offset_s",
                        run_id,
                        camera_id,
                        estimates[camera_id].residual_s,
                        result.cameras[0],
                    )
            events = merge_across_cameras(raw_events, config_events.merge_tolerance_s)
            result.events = len(events)
            result.events_written = write_events(session, events)
            # Cross-camera identity (E5): links and refusals, both persisted.
            speeds = {
                k: float(v["max_speed_mps"])
                for k, v in scene["entities"].items()
                if not k.startswith("_") and "max_speed_mps" in v
            }
            links = associate(
                run_id,
                build_segment_tracks(
                    all_segments,
                    all_observations,
                    localise_all(all_observations, cameras, heights),
                    descriptors,
                ),
                speeds,
            )
            result.links = len(links)
            result.links_linked = sum(link.decision.value == "linked" for link in links)
            write_links(session, links)
        transition(session, run_id, RunStatus.COMPLETE)
        session.commit()
    except Exception as exc:
        session.rollback()
        transition(session, run_id, RunStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        session.commit()
        raise

    log.info(
        "run %s complete: %d frames, %d observations, %d segments, %d events",
        run_id,
        result.frames_processed,
        result.observations,
        result.segments,
        result.events,
    )
    return result
