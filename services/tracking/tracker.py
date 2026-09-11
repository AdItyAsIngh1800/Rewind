"""Per-camera multi-object tracking.

Groups per-frame observations into track segments — a stable identity for one entity
within one camera across time. Cross-camera identity is a separate, harder problem
that lives in ``services.identity`` and is allowed to refuse.

Wraps the ByteTrack implementation that ships with Ultralytics. The ``supervision``
copy was rejected: deprecated in 0.28 and removed in 0.31 with no in-package
replacement, so building on it would mean rebuilding on the next minor version.
Ultralytics is already the detector dependency, which keeps the two versions aligned.

The tracker operates on boxes alone. It never sees pixels, which is what makes it
testable against ray-cast ground truth: feed it perfect boxes with the identities
stripped, and its ability to recover them is measured on its own, independent of
detector quality.
"""

from __future__ import annotations

import itertools
import logging
from argparse import Namespace
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from packages.schemas import SCHEMA_VERSION, EntityClass, Observation, TrackSegment

log = logging.getLogger(__name__)


class TrackerError(RuntimeError):
    """Raised when the tracker cannot be constructed or fed."""


@dataclass(frozen=True)
class TrackerConfig:
    """Everything that affects track assignment, recorded on the run.

    Defaults follow Ultralytics' shipped ``bytetrack.yaml`` with one change, made on
    measurement rather than instinct.

    ``match_thresh`` is 0.9, not the shipped 0.8. In this implementation it bounds
    IoU *distance*, so higher is more permissive, which is the opposite of how it
    reads. On perfect ground-truth boxes across six cases, 0.8 produced 13 identity
    switches, nine of them after a single missed frame; 0.9 produced 6, of which 4
    were re-acquisitions after multi-second gaps that no single-camera tracker can
    bridge. Lowering it, the intuitive move, made things worse at every step.

    ``track_buffer`` was swept from 30 to 100 and changed nothing. A lost track's
    Kalman prediction drifts far from where an entity reappears after seconds of
    unseen motion, so the buffer expiring is never what loses it. Left at the default.

    ``frame_rate`` is recorded for the run; the Ultralytics tracker does not read it.
    """

    track_high_thresh: float = 0.25
    track_low_thresh: float = 0.10
    new_track_thresh: float = 0.25
    track_buffer: int = 30
    match_thresh: float = 0.90
    fuse_score: bool = True
    frame_rate: int = 10

    @property
    def version(self) -> str:
        """Identifier recorded in ``ProcessingRun.model_versions``."""
        return f"bytetrack:buf{self.track_buffer}:match{self.match_thresh}:fps{self.frame_rate}"


class _FrameDetections:
    """The minimal Results-like object ByteTrack reads.

    Ultralytics' tracker was written against its own ``Boxes`` class and reads only
    ``xywh``, ``conf`` and ``cls``, plus ``len()`` and boolean indexing. Supplying
    exactly that, and nothing more, keeps the dependency surface honest.
    """

    def __init__(self, xywh: np.ndarray, conf: np.ndarray, cls: np.ndarray) -> None:
        """Hold one frame's detections as arrays."""
        self.xywh = xywh
        self.conf = conf
        self.cls = cls

    def __len__(self) -> int:
        """Return the number of detections in the frame."""
        return len(self.conf)

    def __getitem__(self, mask: Any) -> _FrameDetections:
        """Boolean-index every array in step, as the tracker expects."""
        return _FrameDetections(self.xywh[mask], self.conf[mask], self.cls[mask])


CLASS_INDEX: dict[EntityClass, int] = {cls: i for i, cls in enumerate(EntityClass)}


class Tracker:
    """A stateful ByteTrack instance for one camera.

    One instance per camera, never shared: the tracker's identity counter and lost-
    track pool are per stream, and feeding two cameras through one would let a
    person in CAM_A inherit a track id from a forklift in CAM_B.
    """

    def __init__(self, camera_id: str, config: TrackerConfig | None = None) -> None:
        """Create a tracker bound to one camera."""
        self.camera_id = camera_id
        self.config = config or TrackerConfig()
        try:
            from ultralytics.trackers.byte_tracker import BYTETracker
        except ImportError as exc:
            raise TrackerError("ultralytics is not installed; run `uv sync --all-extras`") from exc

        args = Namespace(
            track_high_thresh=self.config.track_high_thresh,
            track_low_thresh=self.config.track_low_thresh,
            new_track_thresh=self.config.new_track_thresh,
            track_buffer=self.config.track_buffer,
            match_thresh=self.config.match_thresh,
            fuse_score=self.config.fuse_score,
        )
        # Ultralytics does not type this constructor; the narrow Namespace above is
        # exactly what its bytetrack.yaml would have produced.
        self._tracker = BYTETracker(args)  # type: ignore[no-untyped-call]
        self._history: dict[int, list[Observation]] = defaultdict(list)

    def update(self, observations: list[Observation]) -> list[Observation]:
        """Assign track ids to one frame's observations.

        Args:
            observations: Every observation from this camera for one frame. May be
                empty, which still advances the tracker's frame counter and ages
                lost tracks correctly.

        Returns:
            The same observations with ``track_id`` set, in the same order. An
            observation the tracker chose not to associate keeps ``track_id=None``.

        """
        if any(o.camera_id != self.camera_id for o in observations):
            raise TrackerError(f"tracker for {self.camera_id} was fed another camera's frame")

        if not observations:
            self._tracker.update(_FrameDetections(np.zeros((0, 4)), np.zeros(0), np.zeros(0)))
            return []

        xywh = np.array(
            [
                [*o.bbox.centroid, o.bbox.x2 - o.bbox.x1, o.bbox.y2 - o.bbox.y1]
                for o in observations
            ],
            dtype=np.float32,
        )
        conf = np.array([o.confidence for o in observations], dtype=np.float32)
        cls = np.array([CLASS_INDEX[o.entity_class] for o in observations], dtype=np.float32)

        rows = self._tracker.update(_FrameDetections(xywh, conf, cls))

        assigned: dict[int, int] = {}
        for row in rows:
            # Columns: x1, y1, x2, y2, track_id, score, cls, idx. The last is the
            # index into the detections we passed in, which is the only reliable
            # way to map a track back to its observation.
            assigned[int(row[7])] = int(row[4])

        out: list[Observation] = []
        for index, observation in enumerate(observations):
            track = assigned.get(index)
            updated = observation.model_copy(
                update={"track_id": f"{self.camera_id}-T{track:03d}" if track is not None else None}
            )
            out.append(updated)
            if track is not None:
                self._history[track].append(updated)
        return out

    def segments(self, run_id: str) -> list[TrackSegment]:
        """Collapse every track seen so far into a segment record."""
        return segments_from_observations(
            run_id, [o for rows in self._history.values() for o in rows]
        )


def segments_from_observations(run_id: str, observations: list[Observation]) -> list[TrackSegment]:
    """One segment per (camera, track id), spanning the observations that carry it.

    Shared by the live tracker and by evaluation code that rebuilds segments from a
    persisted or relabelled observation list, so both produce identical ids.
    """
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for o in observations:
        if o.track_id:
            grouped[(o.camera_id, o.track_id)].append(o)
    result: list[TrackSegment] = []
    for (camera_id, track_id), rows in sorted(grouped.items()):
        rows.sort(key=lambda o: o.timestamp_s)
        classes = {o.entity_class for o in rows}
        # A track that changed class mid-way is a tracker error worth surfacing
        # rather than silently taking the majority.
        if len(classes) > 1:
            log.warning(
                "%s track %s spans classes %s; taking the first",
                camera_id,
                track_id,
                sorted(c.value for c in classes),
            )
        result.append(
            TrackSegment(
                schema_version=SCHEMA_VERSION,
                segment_id=f"SEG-{run_id}-{track_id}",
                run_id=run_id,
                camera_id=camera_id,
                local_track_id=track_id,
                entity_class=rows[0].entity_class,
                start_time_s=rows[0].timestamp_s,
                end_time_s=rows[-1].timestamp_s,
                observation_ids=[o.observation_id for o in rows],
                mean_confidence=float(np.mean([o.confidence for o in rows])),
            )
        )
    return result


@dataclass
class TrackingReport:
    """How well assigned track ids recovered true identities on one camera."""

    camera_id: str
    frames: int
    observations: int
    assigned: int
    id_switches: int
    tracks_created: int
    true_entities: int
    fragmentation: dict[str, int] = field(default_factory=dict)


def score_against_truth(camera_id: str, tracked: list[Observation]) -> TrackingReport:
    """Score tracker output where ``entity_id`` carries the true identity.

    Only meaningful on ground-truth observations, where every row knows which entity
    it really was. An id switch is counted whenever consecutive observations of one
    true entity carry different track ids. Fragmentation is how many distinct track
    ids each entity was split across, which is the number a tracker with too short a
    buffer makes worse.
    """
    by_entity: dict[str, list[Observation]] = defaultdict(list)
    for o in tracked:
        if o.entity_id:
            by_entity[o.entity_id].append(o)

    switches = 0
    fragmentation: dict[str, int] = {}
    for entity, rows in by_entity.items():
        rows.sort(key=lambda o: o.timestamp_s)
        ids = [o.track_id for o in rows if o.track_id]
        fragmentation[entity] = len(set(ids))
        switches += sum(1 for a, b in itertools.pairwise(ids) if a != b)

    return TrackingReport(
        camera_id=camera_id,
        frames=len({o.frame_index for o in tracked}),
        observations=len(tracked),
        assigned=sum(1 for o in tracked if o.track_id),
        id_switches=switches,
        tracks_created=len({o.track_id for o in tracked if o.track_id}),
        true_entities=len(by_entity),
        fragmentation=fragmentation,
    )
