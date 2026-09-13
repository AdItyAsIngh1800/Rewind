"""Edge slivers are dropped before tracking; small interior boxes are not."""

from __future__ import annotations

from services.perception.detector import DetectorConfig, cut_by_edge

MIN = DetectorConfig().edge_min_side_px


def test_sliver_rising_from_bottom_edge_is_dropped() -> None:
    """The 4 px and 13 px P02 boxes from case_03 CAM_B frames 136-146."""
    assert cut_by_edge((1064.0, 716.0, 1141.0, 720.0), 1280, 720, MIN)
    assert cut_by_edge((1050.0, 707.0, 1140.0, 720.0), 1280, 720, MIN)


def test_grown_edge_box_is_kept() -> None:
    """Once the actor is 44 px into frame the box is trackable again."""
    assert not cut_by_edge((1040.0, 676.0, 1145.0, 720.0), 1280, 720, MIN)


def test_small_interior_person_at_range_is_kept() -> None:
    """A distant person 13.8 px wide away from every edge is a real detection."""
    assert not cut_by_edge((480.0, 259.0, 493.8, 365.0), 1280, 720, MIN)


def test_version_records_the_edge_rule() -> None:
    """A run's model version must say which edge rule produced its boxes."""
    assert DetectorConfig().version.endswith(":edge16")
