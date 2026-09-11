"""Turn per-camera trajectories into ``SemanticEvent`` records.

E4.2 of the roadmap. Everything here is deterministic and cites its evidence: each
event carries the ids of the observations it was read from, so a reader can go from
"P01 entered Z2 at 11.6 s" to the frame that shows it in one step. An event without
an ``evidence_refs`` entry cannot be produced by this module, which is the property
the report generator relies on later.

Occlusion is a first-class event, not an error. A track that vanishes for longer than
``occlusion_gap_s`` and returns produces a start/end pair, and the interval between
them is exactly what the uncertainty engine (E7.3) later renders as "cannot determine".

Positions come from ``Observation.world_xyz`` when present (ground truth, the perfect
stand-in) and otherwise from back-projecting the box centre through the camera model
at half the class height. Cross-camera duplicates are collapsed by a deliberately naive
rule in ``merge_across_cameras``; the identity layer (E5) replaces that rule with real
linking, and until then the merge is labelled for what it is in the event payload.
"""

from __future__ import annotations

import itertools
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely

from packages.common import geometry
from packages.common.camera import CameraModel
from packages.schemas import SCHEMA_VERSION, EventType, Observation, SemanticEvent

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Zone:
    """A named floor polygon in world metres, from the scene config."""

    zone_id: str
    name: str
    polygon: shapely.Polygon


def load_zones(scene: dict[str, Any]) -> list[Zone]:
    """Read the zone polygons from ``ml/configs/scene_v1.json``."""
    return [Zone(z["id"], z["name"], shapely.Polygon(z["polygon"])) for z in scene["zones"]]


def class_heights(scene: dict[str, Any]) -> dict[str, float]:
    """Entity height per class, the plane a box centre is back-projected onto."""
    return {k: float(v["height"]) for k, v in scene["entities"].items() if not k.startswith("_")}


@dataclass(frozen=True)
class EventConfig:
    """Every threshold that decides whether a trajectory feature is an event.

    Defaults come from the geometry primitives' documented values; they are tuned on
    the tune cases in E4.4 and the golden cases never see them until E9.1.
    """

    stop_max_speed: float = 0.1
    stop_min_duration: float = 1.0
    turn_min_angle_deg: float = 60.0
    turn_min_speed: float = 0.2
    proximity_distance: float = 1.5
    proximity_min_duration: float = 0.0
    occlusion_gap_s: float = 0.5
    #: Heading is measured between samples at least this far apart. At 10 fps a
    #: frame-to-frame heading flips on a few centimetres of localisation jitter;
    #: over half a second a walking person has moved far enough for the heading to
    #: mean something.
    turn_baseline_s: float = 0.5
    #: Cameras time the same crossing differently because each localises with its
    #: own bias direction; the window has to cover that spread or one crossing
    #: becomes two events. EXP-0006 first measured 0.7 s of spread and set 1.0; that
    #: spread was mostly spurious clock offsets (scene spec §4.1). With correct clocks
    #: the real spread is under 0.5 s and 0.8 is the smallest window that covers it.
    merge_tolerance_s: float = 0.8

    @property
    def version(self) -> str:
        """Identifier recorded on the run so an event stream is reproducible."""
        return (
            f"events:stop{self.stop_max_speed}/{self.stop_min_duration}"
            f":turn{self.turn_min_angle_deg}/{self.turn_baseline_s}:prox{self.proximity_distance}"
            f":occ{self.occlusion_gap_s}:merge{self.merge_tolerance_s}"
        )


@dataclass
class _Track:
    """One camera-local track with its world-plane trajectory."""

    camera_id: str
    track_id: str
    entity_class: str
    rows: list[Observation]
    xy: list[tuple[float, float]]

    @property
    def array(self) -> geometry.Track:
        return np.array(
            [(o.timestamp_s, x, y) for o, (x, y) in zip(self.rows, self.xy, strict=True)],
            dtype=np.float64,
        )


def localise(
    observation: Observation, cameras: dict[str, CameraModel], heights: dict[str, float]
) -> tuple[float, float] | None:
    """World-plane position of one observation, or None if it cannot be placed.

    Truth positions are used verbatim so the extractor can be scored with a perfect
    localiser; otherwise the box centre is back-projected at half the class height.
    A box above the horizon returns None and is dropped with a log line rather than
    given a made-up position.
    """
    if observation.world_xyz is not None:
        return observation.world_xyz[0], observation.world_xyz[1]
    camera = cameras[observation.camera_id]
    b = observation.bbox
    try:
        return camera.back_project(
            (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2, heights[observation.entity_class] / 2
        )
    except ValueError as exc:
        log.debug("dropping %s: %s", observation.observation_id, exc)
        return None


def localise_all(
    observations: list[Observation], cameras: dict[str, CameraModel], heights: dict[str, float]
) -> dict[str, tuple[float, float]]:
    """World-plane position per observation id, omitting any that cannot be placed."""
    out: dict[str, tuple[float, float]] = {}
    for o in observations:
        xy = localise(o, cameras, heights)
        if xy is not None:
            out[o.observation_id] = xy
    return out


def _tracks(
    observations: list[Observation], cameras: dict[str, CameraModel], heights: dict[str, float]
) -> list[_Track]:
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for o in observations:
        if o.track_id:
            grouped[(o.camera_id, o.track_id)].append(o)
    tracks: list[_Track] = []
    for (camera_id, track_id), rows in sorted(grouped.items()):
        rows.sort(key=lambda o: o.timestamp_s)
        placed = [(o, localise(o, cameras, heights)) for o in rows]
        kept = [(o, xy) for o, xy in placed if xy is not None]
        if len(kept) < 2:
            continue
        tracks.append(
            _Track(
                camera_id,
                track_id,
                rows[0].entity_class.value,
                [o for o, _ in kept],
                [xy for _, xy in kept],
            )
        )
    return tracks


class _Emitter:
    """Builds events with sequential ids and the boilerplate fields filled in."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[SemanticEvent] = []
        self._seq: dict[str, int] = defaultdict(int)

    def emit(
        self,
        event_type: EventType,
        track: _Track,
        at: Observation,
        *,
        zone_id: str | None = None,
        refs: list[Observation] | None = None,
        entity_ids: list[str] | None = None,
        confidence: float | None = None,
        **payload: Any,
    ) -> None:
        self._seq[track.camera_id] += 1
        self.events.append(
            SemanticEvent(
                schema_version=SCHEMA_VERSION,
                event_id=f"EVT-{self.run_id}-{track.camera_id}-{self._seq[track.camera_id]:04d}",
                run_id=self.run_id,
                event_type=event_type,
                timestamp_s=at.timestamp_s,
                camera_id=track.camera_id,
                entity_ids=entity_ids or [track.track_id],
                zone_id=zone_id,
                confidence=at.confidence if confidence is None else confidence,
                evidence_refs=[o.observation_id for o in (refs or [at])],
                payload={"entity_class": track.entity_class, **payload},
            )
        )


def _thin(track: geometry.Track, min_dt: float) -> geometry.Track:
    """Keep samples at least ``min_dt`` apart, always including the first."""
    keep = [0]
    for i in range(1, len(track)):
        if track[i, 0] - track[keep[-1], 0] >= min_dt:
            keep.append(i)
    return track[keep]


def _index_at(track: _Track, timestamp: float) -> int:
    """Row index of the sample stamped ``timestamp``; timestamps are unique per track."""
    return next(i for i, o in enumerate(track.rows) if o.timestamp_s == timestamp)


def extract_events(
    run_id: str,
    observations: list[Observation],
    zones: list[Zone],
    cameras: dict[str, CameraModel],
    heights: dict[str, float],
    config: EventConfig | None = None,
) -> list[SemanticEvent]:
    """Extract every event type from tracked observations, one camera at a time."""
    cfg = config or EventConfig()
    out = _Emitter(run_id)
    tracks = _tracks(observations, cameras, heights)

    for track in tracks:
        arr = track.array

        for zone in zones:
            inside = geometry.inside_mask(arr, zone.polygon)
            if inside[0]:
                # Already inside when first seen: the entry is real, its time is only a
                # bound. Confidence is halved so downstream ranking treats it as such.
                out.emit(
                    EventType.ZONE_ENTRY,
                    track,
                    track.rows[0],
                    zone_id=zone.zone_id,
                    confidence=track.rows[0].confidence / 2,
                    at_first_sight=True,
                )
            for t, entered in geometry.zone_transitions(arr, zone.polygon):
                i = _index_at(track, t)
                before, after = track.rows[i - 1], track.rows[i]
                gap = after.timestamp_s - before.timestamp_s
                # A crossing that happened while the track was unseen has a time
                # bound, not a time. Say so, and halve the confidence, rather than
                # stamping the reappearance as if the crossing were watched.
                bounded = gap >= cfg.occlusion_gap_s
                payload: dict[str, Any] = (
                    {"during_gap": [before.timestamp_s, after.timestamp_s]} if bounded else {}
                )
                out.emit(
                    EventType.ZONE_ENTRY if entered else EventType.ZONE_EXIT,
                    track,
                    after,
                    zone_id=zone.zone_id,
                    refs=[before, after],  # the pair straddling the boundary
                    confidence=after.confidence / 2 if bounded else None,
                    **payload,
                )

        for start, end in geometry.stop_intervals(arr, cfg.stop_max_speed, cfg.stop_min_duration):
            i, j = _index_at(track, start), _index_at(track, end)
            out.emit(
                EventType.STOP,
                track,
                track.rows[i],
                refs=[track.rows[i], track.rows[j]],
                duration_s=round(end - start, 3),
                end_s=end,
            )

        thinned = _thin(arr, cfg.turn_baseline_s)
        for t in geometry.direction_changes(thinned, cfg.turn_min_angle_deg, cfg.turn_min_speed):
            i = _index_at(track, t)
            out.emit(
                EventType.DIRECTION_CHANGE, track, track.rows[i], refs=track.rows[i - 1 : i + 1]
            )

        for prev, curr in itertools.pairwise(track.rows):
            if curr.timestamp_s - prev.timestamp_s >= cfg.occlusion_gap_s:
                out.emit(
                    EventType.OCCLUSION_START,
                    track,
                    prev,
                    gap_s=round(curr.timestamp_s - prev.timestamp_s, 3),
                )
                out.emit(
                    EventType.OCCLUSION_END,
                    track,
                    curr,
                    gap_s=round(curr.timestamp_s - prev.timestamp_s, 3),
                )

    by_camera: dict[str, list[_Track]] = defaultdict(list)
    for track in tracks:
        by_camera[track.camera_id].append(track)
    for camera_tracks in by_camera.values():
        for a, b in itertools.combinations(camera_tracks, 2):
            arr_a, arr_b = a.array, b.array
            for start, end in geometry.proximity_intervals(
                arr_a, arr_b, cfg.proximity_distance, cfg.proximity_min_duration
            ):
                i = _index_at(a, start)
                _t, d = geometry.distances(arr_a[i : i + 1], arr_b)
                out.emit(
                    EventType.PROXIMITY,
                    a,
                    a.rows[i],
                    refs=[
                        a.rows[i],
                        b.rows[
                            min(
                                range(len(b.rows)), key=lambda k: abs(b.rows[k].timestamp_s - start)
                            )
                        ],
                    ],
                    entity_ids=[a.track_id, b.track_id],
                    confidence=min(a.rows[i].confidence, b.rows[0].confidence),
                    other_class=b.entity_class,
                    distance_m=round(float(d[0]), 3) if d.size else None,
                    end_s=end,
                )

    out.events.sort(key=lambda e: (e.timestamp_s, e.event_id))
    return out.events


def _identity_key(groups: dict[str, str] | None) -> Callable[[SemanticEvent], object]:
    """How two events are judged to be about the same entity.

    With groups, the first entity id's group (proximity events name two entities;
    the first is the track the event was emitted for). Without, the entity class.
    """
    if groups is None:
        return lambda e: e.payload.get("entity_class")
    return lambda e: groups.get(e.entity_ids[0], e.entity_ids[0]) if e.entity_ids else None


def merge_across_cameras(
    events: list[SemanticEvent],
    tolerance_s: float = EventConfig().merge_tolerance_s,
    groups: dict[str, str] | None = None,
) -> list[SemanticEvent]:
    """Collapse the same physical event seen from several cameras into one record.

    With ``groups`` (local track id to cross-camera entity, from E5.3) two events
    merge only when their tracks are the same entity. Without it the rule falls back
    to "same class", which cannot tell two people entering one zone together apart;
    the rule used is named in every merged event's payload.
    """
    identity = _identity_key(groups)
    merged: list[tuple[SemanticEvent, list[str]]] = []
    stamps: list[list[float]] = []
    # Zone occupancy by class, so a camera that first sees an entity already inside a
    # zone another camera watched it enter adds evidence to that entry rather than
    # inventing a second one. Cleared by the matching exit.
    occupied: dict[tuple[str | None, object], int] = {}
    for event in sorted(events, key=lambda e: e.timestamp_s):
        key = (event.zone_id, identity(event))
        if event.event_type is EventType.ZONE_EXIT:
            occupied.pop(key, None)
        first_sight = bool(event.payload.get("at_first_sight"))
        if first_sight and key in occupied:
            target, cameras = merged[occupied[key]]
            if event.camera_id not in cameras:
                cameras.append(str(event.camera_id))
                target.evidence_refs.extend(
                    r for r in event.evidence_refs if r not in target.evidence_refs
                )
            continue
        for idx, (target, cameras) in enumerate(merged):
            if (
                target.event_type == event.event_type
                and target.zone_id == event.zone_id
                and identity(target) == identity(event)
                and abs(target.timestamp_s - event.timestamp_s) <= tolerance_s
                and event.camera_id not in cameras
            ):
                cameras.append(str(event.camera_id))
                stamps[idx].append(event.timestamp_s)
                target.entity_ids.extend(i for i in event.entity_ids if i not in target.entity_ids)
                target.evidence_refs.extend(
                    r for r in event.evidence_refs if r not in target.evidence_refs
                )
                break
        else:
            cameras = [str(event.camera_id)]
            merged.append(
                (
                    event.model_copy(
                        update={
                            "camera_id": None,
                            "entity_ids": list(event.entity_ids),
                            "evidence_refs": list(event.evidence_refs),
                            "payload": {
                                **event.payload,
                                "merge_rule": (
                                    "type+zone+identity within tolerance"
                                    if groups
                                    else "type+zone+class within tolerance"
                                ),
                                "merged_from_cameras": cameras,
                            },
                        }
                    ),
                    cameras,
                )
            )
            stamps.append([event.timestamp_s])
            if event.event_type is EventType.ZONE_ENTRY:
                occupied[key] = len(merged) - 1
    # The median camera time is the estimate least moved by one camera's bias. It
    # is applied after merging so the window test above always compared against the
    # first sighting, which keeps the merge order-independent.
    return [
        event.model_copy(update={"timestamp_s": float(np.median(times))})
        for (event, _), times in zip(merged, stamps, strict=True)
    ]
