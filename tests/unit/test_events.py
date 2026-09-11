"""Event extraction on hand-built tracks where every expected event is known."""

from __future__ import annotations

import json
import pathlib

import shapely

from packages.common.camera import CameraModel
from packages.schemas import BBox, EntityClass, EventType, Observation, SemanticEvent
from services.events import EventConfig, Zone, extract_events, merge_across_cameras

SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
CAMERAS = {c["id"]: CameraModel.from_scene(SCENE, c["id"]) for c in SCENE["cameras"]}
HEIGHTS = {"person": 1.75, "robot": 1.2, "forklift": 2.2, "pallet": 0.15}
SQUARE = Zone("Z", "SQUARE", shapely.Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]))


def obs(
    t: float, x: float, y: float, track: str = "CAM_A-T001", camera: str = "CAM_A"
) -> Observation:
    """Build a ground-truth-style observation with a known world position."""
    return Observation(
        schema_version="1.0.0",
        observation_id=f"OBS-{camera}-{track}-{t:05.1f}",
        run_id="r",
        camera_id=camera,
        frame_index=int(t * 10),
        timestamp_s=t,
        entity_class=EntityClass.PERSON,
        bbox=BBox(x1=0, y1=0, x2=10, y2=10),
        confidence=0.9,
        track_id=track,
        world_xyz=(x, y, 0.875),
    )


def walk(xs: list[float], y: float = 5.0, **kw: str) -> list[Observation]:
    """One sample per 0.1 s along ``xs``."""
    return [obs(round(i * 0.1, 1), x, y, **kw) for i, x in enumerate(xs)]


def events_of(rows: list[Observation], **cfg: float) -> list[SemanticEvent]:
    """Run the extractor on one square zone with the given config overrides."""
    return extract_events("r", rows, [SQUARE], CAMERAS, HEIGHTS, EventConfig(**cfg))


def test_zone_crossing_cites_the_straddling_pair() -> None:
    """An entry names the last sample outside and the first inside."""
    rows = walk([-2, -1, 1, 2, 3, 11, 12])
    zone = [e for e in events_of(rows) if e.zone_id == "Z"]
    assert [(e.event_type, e.timestamp_s) for e in zone] == [
        (EventType.ZONE_ENTRY, 0.2),
        (EventType.ZONE_EXIT, 0.5),
    ]
    assert zone[0].evidence_refs == [rows[1].observation_id, rows[2].observation_id]
    assert zone[0].confidence == 0.9
    assert zone[0].payload["entity_class"] == "person"


def test_first_sight_inside_is_a_bounded_entry() -> None:
    """Starting inside gives an entry at first sight, flagged and half-confidence."""
    rows = walk([5, 6, 7])
    entry = next(e for e in events_of(rows) if e.event_type is EventType.ZONE_ENTRY)
    assert entry.timestamp_s == 0.0
    assert entry.payload["at_first_sight"] is True
    assert entry.confidence == 0.45


def test_crossing_during_a_gap_is_bounded_and_occlusion_is_emitted() -> None:
    """Unseen for 2 s while crossing: the exit carries the gap and the gap is an event."""
    rows = [obs(0.0, 8, 5), obs(0.1, 9, 5), obs(2.1, 12, 5), obs(2.2, 13, 5)]
    ev = events_of(rows)
    exit_ = next(e for e in ev if e.event_type is EventType.ZONE_EXIT)
    assert exit_.timestamp_s == 2.1
    assert exit_.payload["during_gap"] == [0.1, 2.1]
    assert exit_.confidence == 0.45
    occ = [(e.event_type, e.timestamp_s) for e in ev if "occlusion" in e.event_type.value]
    assert occ == [(EventType.OCCLUSION_START, 0.1), (EventType.OCCLUSION_END, 2.1)]


def test_stop_and_proximity_between_two_tracks() -> None:
    """A held pause becomes one STOP; two tracks within 1.5 m become one PROXIMITY."""
    a = walk([1] * 15 + [2, 3, 4])
    b = walk(
        [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3], y=5.5, track="CAM_A-T002"
    )
    ev = events_of(a + b)
    stops = [e for e in ev if e.event_type is EventType.STOP]
    # Speed is attributed to the later sample, so 15 still samples are 14 still steps.
    assert len(stops) == 1 and stops[0].payload["duration_s"] == 1.3
    prox = [e for e in ev if e.event_type is EventType.PROXIMITY]
    assert len(prox) == 1
    assert set(prox[0].entity_ids) == {"CAM_A-T001", "CAM_A-T002"}
    assert prox[0].payload["distance_m"] is not None and prox[0].payload["distance_m"] <= 1.5


def test_merge_folds_a_later_first_sight_into_the_watched_entry() -> None:
    """CAM_B first sees the entity already inside: evidence added, no second entry."""
    seen_enter = walk([-1, 1, 2, 3], camera="CAM_A", track="CAM_A-T001")
    seen_inside = [
        obs(0.3, 3, 5, camera="CAM_B", track="CAM_B-T007"),
        obs(0.4, 4, 5, camera="CAM_B", track="CAM_B-T007"),
    ]
    merged = merge_across_cameras(events_of(seen_enter + seen_inside))
    entries = [e for e in merged if e.event_type is EventType.ZONE_ENTRY]
    assert len(entries) == 1
    assert entries[0].payload["merged_from_cameras"] == ["CAM_A", "CAM_B"]
    assert entries[0].camera_id is None
    assert seen_inside[0].observation_id in entries[0].evidence_refs


def test_merge_collapses_the_same_crossing_from_two_cameras() -> None:
    """Both cameras watch the crossing a frame apart: one event, two cameras cited."""
    a = walk([-1, 1, 2], camera="CAM_A", track="CAM_A-T001")
    b = [
        obs(0.0, -1, 5, camera="CAM_B", track="CAM_B-T003"),
        obs(0.2, 1, 5, camera="CAM_B", track="CAM_B-T003"),
    ]
    merged = merge_across_cameras(events_of(a + b))
    entries = [e for e in merged if e.event_type is EventType.ZONE_ENTRY]
    assert len(entries) == 1
    assert sorted(entries[0].payload["merged_from_cameras"]) == ["CAM_A", "CAM_B"]
    assert sorted(entries[0].entity_ids) == ["CAM_A-T001", "CAM_B-T003"]
