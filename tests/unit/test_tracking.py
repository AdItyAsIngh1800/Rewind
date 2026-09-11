"""Tests for per-camera tracking.

The tracker only ever sees boxes, so it can be tested with synthetic boxes that move
in known ways. The property that matters is identity stability: the same entity
keeps the same track id across frames, and different entities get different ones.
"""

from __future__ import annotations

import pytest

from packages.schemas import BBox, EntityClass, Observation
from services.tracking import Tracker, TrackerConfig, TrackerError, score_against_truth


def obs(
    frame: int, x: float, y: float, entity: str = "P01", camera: str = "CAM_A", size: float = 60.0
) -> Observation:
    """Build one observation of a box centred at (x, y)."""
    return Observation(
        observation_id=f"{camera}-{entity}-{frame:04d}",
        run_id="test",
        camera_id=camera,
        frame_index=frame,
        timestamp_s=frame / 10,
        entity_class=EntityClass.PERSON,
        bbox=BBox(x1=x - size / 2, y1=y - size, x2=x + size / 2, y2=y + size),
        confidence=0.95,
        entity_id=entity,
    )


def test_a_moving_box_keeps_one_track_id() -> None:
    """Assert a box drifting steadily across frames keeps its identity."""
    tracker = Tracker("CAM_A")
    ids = set()
    for frame in range(30):
        (tracked,) = tracker.update([obs(frame, x=100 + frame * 4, y=300)])
        assert tracked.track_id is not None
        ids.add(tracked.track_id)
    assert len(ids) == 1


def test_two_separated_boxes_get_two_track_ids() -> None:
    """Assert distinct entities are never merged when they are far apart."""
    tracker = Tracker("CAM_A")
    for frame in range(20):
        a, b = tracker.update(
            [obs(frame, x=100, y=300, entity="P01"), obs(frame, x=900, y=300, entity="P02")]
        )
        assert a.track_id != b.track_id


def test_a_short_gap_does_not_create_a_new_track() -> None:
    """Assert one or two missed frames do not fragment a track.

    This was the dominant failure at the shipped match threshold: nine of thirteen
    switches on perfect boxes happened after a single missed frame.
    """
    tracker = Tracker("CAM_A")
    ids = []
    for frame in range(30):
        if frame in (12, 13):
            tracker.update([])  # the entity is briefly below the visibility floor
            continue
        (tracked,) = tracker.update([obs(frame, x=100 + frame * 4, y=300)])
        ids.append(tracked.track_id)
    assert len(set(ids)) == 1, f"track fragmented across a 2-frame gap: {set(ids)}"


def test_empty_frames_still_advance_the_tracker() -> None:
    """Assert feeding an empty frame is legal and returns nothing."""
    tracker = Tracker("CAM_A")
    assert tracker.update([]) == []


def test_feeding_another_cameras_frame_is_refused() -> None:
    """Assert a tracker cannot be fed observations from a different camera.

    Trackers are per camera. Sharing one would let a person in CAM_A inherit a
    track id from a forklift in CAM_B.
    """
    tracker = Tracker("CAM_A")
    with pytest.raises(TrackerError, match="another camera"):
        tracker.update([obs(0, x=100, y=300, camera="CAM_B")])


def test_segments_span_the_frames_a_track_was_seen() -> None:
    """Assert a segment records first and last sighting and every observation."""
    tracker = Tracker("CAM_A")
    for frame in range(5, 25):
        tracker.update([obs(frame, x=100 + frame * 4, y=300)])
    (segment,) = tracker.segments(run_id="run-x")
    assert segment.camera_id == "CAM_A"
    assert segment.start_time_s == pytest.approx(0.5)
    assert segment.end_time_s == pytest.approx(2.4)
    assert len(segment.observation_ids) == 20
    assert segment.entity_class is EntityClass.PERSON


def test_config_version_records_the_tuned_threshold() -> None:
    """Assert the run-recorded version string carries the settings that matter."""
    assert "match0.9" in TrackerConfig().version


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def test_scoring_counts_a_switch_when_an_entity_changes_track() -> None:
    """Assert a change of track id on one true entity is one switch."""
    rows = [
        obs(0, 100, 300).model_copy(update={"track_id": "CAM_A-T001"}),
        obs(1, 104, 300).model_copy(update={"track_id": "CAM_A-T001"}),
        obs(2, 108, 300).model_copy(update={"track_id": "CAM_A-T002"}),
    ]
    report = score_against_truth("CAM_A", rows)
    assert report.id_switches == 1
    assert report.fragmentation == {"P01": 2}


def test_scoring_a_stable_track_reports_no_switches() -> None:
    """Assert a consistently tracked entity scores zero switches."""
    rows = [
        obs(f, 100 + f * 4, 300).model_copy(update={"track_id": "CAM_A-T001"}) for f in range(10)
    ]
    report = score_against_truth("CAM_A", rows)
    assert report.id_switches == 0
    assert report.tracks_created == 1
    assert report.true_entities == 1
