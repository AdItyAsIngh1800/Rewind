"""E4.1 geometry primitives, checked on hand-built trajectories with known answers."""

from __future__ import annotations

import numpy as np
import pytest

from packages.common import geometry as g

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _track(*points: tuple[float, float, float]) -> g.Track:
    """Build a ``(t, x, y)`` trajectory from literals."""
    return np.array(points, dtype=np.float64)


def test_boundary_counts_as_inside() -> None:
    """Standing on the painted line of a keep-clear zone is still a violation."""
    assert g.point_in_polygon(10.0, 5.0, SQUARE)
    assert g.point_in_polygon(5.0, 5.0, SQUARE)
    assert not g.point_in_polygon(10.01, 5.0, SQUARE)


def test_zone_transitions_stamp_first_sample_on_new_side() -> None:
    """Entry/exit edges carry the timestamp of the first sample inside/outside."""
    track = _track((0, -1, 5), (1, 1, 5), (2, 5, 5), (3, 11, 5), (4, 12, 5))
    assert g.zone_transitions(track, SQUARE) == [(1.0, True), (3.0, False)]


def test_starting_inside_is_not_an_entry() -> None:
    """Being inside at t=0 is state, not an event."""
    track = _track((0, 5, 5), (1, 6, 5), (2, 11, 5))
    assert g.zone_transitions(track, SQUARE) == [(2.0, False)]
    assert g.dwell_intervals(track, SQUARE) == [(0.0, 1.0)]


def test_speeds_are_per_step() -> None:
    """3-4-5 triangle: 5 m in 1 s."""
    track = _track((0, 0, 0), (1, 3, 4), (3, 3, 4))
    assert g.speeds(track).tolist() == [5.0, 0.0]
    with pytest.raises(ValueError, match="strictly increasing"):
        g.speeds(_track((0, 0, 0), (0, 1, 1)))


def test_stop_requires_min_duration() -> None:
    """A momentary zero at a reversal is not a stop; a held pause is."""
    track = _track(
        (0, 0, 0), (1, 1, 0), (2, 1, 0), (3, 1, 0), (4, 1, 0), (5, 2, 0), (6, 2, 0), (7, 3, 0)
    )
    assert g.stop_intervals(track, min_duration=1.0) == [(2.0, 4.0)]
    assert g.stop_intervals(track, min_duration=3.0) == []


def test_direction_change_ignores_stationary_jitter() -> None:
    """A 90-degree turn is found; jitter while stopped is not a turn."""
    turn = _track((0, 0, 0), (1, 1, 0), (2, 2, 0), (3, 2, 1), (4, 2, 2))
    assert g.direction_changes(turn) == [3.0]
    jitter = _track((0, 0, 0), (1, 1, 0), (2, 1.01, 0.01), (3, 1.0, 0.0), (4, 2, 0))
    assert g.direction_changes(jitter) == []


def test_direction_change_wraps_around_pi() -> None:
    """Heading -170 degrees to +170 degrees is a 20-degree turn, not 340."""
    track = _track((0, 0, 0), (1, -1, -0.176), (2, -2, 0.0))
    assert g.direction_changes(track, min_angle_deg=60) == []
    assert g.direction_changes(track, min_angle_deg=10) == [2.0]


def test_proximity_uses_overlap_only() -> None:
    """Distances are computed on the shared time span; no extrapolation."""
    a = _track((0, 0, 0), (1, 1, 0), (2, 2, 0), (3, 3, 0))
    b = _track((1, 1, 0.5), (2, 2, 0.5), (5, 2, 10))
    t, d = g.distances(a, b)
    assert t.tolist() == [1.0, 2.0, 3.0]
    assert d[:2].tolist() == [0.5, 0.5]
    assert g.proximity_intervals(a, b, max_distance=1.0) == [(1.0, 2.0)]
    assert g.distances(a, _track((10, 0, 0), (11, 0, 0)))[0].size == 0


def test_runs_drop_zero_duration_singletons() -> None:
    """One isolated True sample has no duration and cannot satisfy a positive minimum."""
    t = np.arange(5, dtype=np.float64)
    m = np.array([False, True, False, True, True])
    assert g._runs(t, m, 0.0) == [(1.0, 1.0), (3.0, 4.0)]
    assert g._runs(t, m, 0.5) == [(3.0, 4.0)]


SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _along_x(xs: list[float]) -> np.ndarray:
    """Build a track sampled every 0.1 s along ``xs`` at y = 5."""
    return np.array([[round(i * 0.1, 1), x, 5.0] for i, x in enumerate(xs)])


def test_jitter_on_an_edge_confirms_nothing() -> None:
    """An object parked on the edge, wobbling 0.2 m across it, never re-enters or leaves."""
    track = _along_x([-3.0, -1.0, 2.0, 1.0, 0.1, -0.2, 0.1, -0.2, 0.2, -0.1, 0.1])
    assert g.confirmed_transitions(track, SQUARE, margin=0.5) == [(0.2, True)]
    assert len(g.zone_transitions(track, SQUARE)) == 7


def test_a_confirmed_crossing_keeps_its_original_time() -> None:
    """The exit is stamped at the first outside sample, though depth is reached later."""
    track = _along_x([5.0, 1.0, -0.1, -0.3, -2.0])
    assert g.confirmed_transitions(track, SQUARE, margin=0.5) == [(0.2, False)]


def test_zero_margin_is_the_raw_crossings() -> None:
    """With no margin every flip is kept, exactly as zone_transitions reports."""
    track = _along_x([-3.0, -1.0, 2.0, 1.0, 0.1, -0.2, 0.1, -0.2, 0.2, -0.1, 0.1])
    assert g.confirmed_transitions(track, SQUARE, margin=0.0) == g.zone_transitions(track, SQUARE)


def test_a_shallow_crossing_by_a_moving_object_is_kept() -> None:
    """Walking along the edge, 0.1 m inside for a while, is a real entry and a real exit."""
    track = np.array(
        [
            [round(i * 0.1, 1), float(i) * 0.3, y]
            for i, y in enumerate([-2.0, -1.0, -0.2, 0.1, 0.1, 0.1, 0.1, -1.0, -3.0, -3.0])
        ]
    )
    assert g.confirmed_transitions(track, SQUARE, margin=0.5) == [(0.3, True), (0.7, False)]
