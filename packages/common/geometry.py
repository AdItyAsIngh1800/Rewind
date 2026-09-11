"""Pure spatial primitives over world-plane trajectories.

E4.1 of the roadmap: every function here is deterministic, does no I/O and knows
nothing about cameras, runs or the database. E4.2 composes these into
``SemanticEvent`` records; keeping the maths separate means the thresholds that
decide what counts as a "stop" or a "direction change" are tested in isolation,
with hand-built trajectories where the right answer is known exactly.

Trajectories are ``(N, 3)`` float arrays of ``(t, x, y)`` in **world** metres, not
pixels. Zones in ``ml/configs/scene_v1.json`` are world-plane polygons, and a
proximity of 1.5 m only means something in world units; the image→world mapping is
E4.2's problem, not this module's.

Every threshold is a parameter with a documented default. The defaults are tuned to
the simulated scene's actor speeds and will need re-tuning against real detections
whose positions jitter — that is expected, and the reason nothing here is hard-coded.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import shapely
from numpy.typing import NDArray

Track = NDArray[np.float64]
"""Shape ``(N, 3)``: columns ``t`` (seconds, strictly increasing), ``x``, ``y`` (metres)."""

Interval = tuple[float, float]
"""``(start_s, end_s)`` closed interval on the trajectory's own timestamps."""

type PolygonLike = Sequence[tuple[float, float]] | shapely.Polygon


def _polygon(polygon: PolygonLike) -> shapely.Polygon:
    """Accept either the JSON-native vertex list or a prepared shapely polygon."""
    return polygon if isinstance(polygon, shapely.Polygon) else shapely.Polygon(polygon)


def point_in_polygon(x: float, y: float, polygon: PolygonLike) -> bool:
    """Whether ``(x, y)`` lies inside or on the boundary of ``polygon``.

    Boundary counts as inside: a keep-clear zone's painted edge is still keep-clear,
    and a strict ``contains`` would let an actor stand exactly on the line unpunished.
    """
    return bool(_polygon(polygon).covers(shapely.Point(x, y)))


def inside_mask(track: Track, polygon: PolygonLike) -> NDArray[np.bool_]:
    """Per-sample inside/outside flags for a whole trajectory, boundary inclusive."""
    return np.asarray(shapely.covers(_polygon(polygon), shapely.points(track[:, 1:3])), dtype=bool)


def _runs(
    timestamps: NDArray[np.float64], mask: NDArray[np.bool_], min_duration: float
) -> list[Interval]:
    """Collapse a boolean mask into ``(start, end)`` intervals of consecutive True samples.

    Shared by stop, dwell and proximity detection: each is "a predicate held for at
    least this long", so the interval logic lives once. An interval's duration is
    measured between its first and last True sample; a single isolated sample has
    zero duration and is dropped by any positive ``min_duration``.
    """
    if mask.size == 0:
        return []
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    starts, ends = edges[0::2], edges[1::2] - 1
    return [
        (float(timestamps[s]), float(timestamps[e]))
        for s, e in zip(starts, ends, strict=True)
        if timestamps[e] - timestamps[s] >= min_duration
    ]


def zone_transitions(track: Track, polygon: PolygonLike) -> list[tuple[float, bool]]:
    """Timestamps at which the trajectory crosses the zone boundary.

    Returns ``(t, entered)`` pairs in time order, stamped with the first sample on the
    new side. A trajectory that starts inside produces no entry event — being inside at
    t=0 is a state, not a transition, and E4.2 reads the initial state separately.
    """
    inside = inside_mask(track, polygon)
    flips = np.flatnonzero(inside[1:] != inside[:-1]) + 1
    return [(float(track[i, 0]), bool(inside[i])) for i in flips]


def dwell_intervals(
    track: Track, polygon: PolygonLike, min_duration: float = 0.0
) -> list[Interval]:
    """Intervals during which the trajectory stays inside the zone."""
    return _runs(track[:, 0], inside_mask(track, polygon), min_duration)


def speeds(track: Track) -> NDArray[np.float64]:
    """Speed in m/s between consecutive samples, shape ``(N-1,)``.

    Attributed to the *later* sample of each pair, so ``speeds(track)[i]`` describes
    the motion that arrived at ``track[i + 1]``.
    """
    dt = np.diff(track[:, 0])
    if np.any(dt <= 0):
        raise ValueError("track timestamps must be strictly increasing")
    return np.hypot(np.diff(track[:, 1]), np.diff(track[:, 2])) / dt


def stop_intervals(
    track: Track, max_speed: float = 0.1, min_duration: float = 1.0
) -> list[Interval]:
    """Intervals where the entity moved slower than ``max_speed`` for ``min_duration``.

    0.1 m/s is well under a walking pace and above the positional jitter a 720p
    detector produces at 10 fps on the far side of the scene; it separates "stopped"
    from "creeping". One second filters the momentary zero at a direction reversal.
    """
    if len(track) < 2:
        return []
    return _runs(track[1:, 0], speeds(track) <= max_speed, min_duration)


def direction_changes(
    track: Track, min_angle_deg: float = 60.0, min_speed: float = 0.2
) -> list[float]:
    """Timestamps where the heading turned by at least ``min_angle_deg``.

    Heading is undefined when stationary — a jittering stopped actor would otherwise
    "turn" every frame — so steps slower than ``min_speed`` are skipped and the turn is
    measured between the last two *moving* steps. The turn is stamped on the sample
    where the new heading begins.
    """
    if len(track) < 3:
        return []
    step = np.diff(track[:, 1:3], axis=0)
    moving = speeds(track) >= min_speed
    headings = np.arctan2(step[:, 1], step[:, 0])[moving]
    stamps = track[1:, 0][moving]
    turn = np.abs(np.angle(np.exp(1j * np.diff(headings))))  # wrapped to [0, pi]
    return [float(t) for t in stamps[1:][turn >= np.radians(min_angle_deg)]]


def distances(track_a: Track, track_b: Track) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Distance between two entities over the time both are observed.

    ``track_b`` is linearly interpolated onto ``track_a``'s timestamps; samples outside
    the overlap are dropped rather than extrapolated, because a guessed position is
    exactly the kind of evidence this system must not manufacture. Returns
    ``(timestamps, distances)``, both possibly empty.
    """
    t0, t1 = max(track_a[0, 0], track_b[0, 0]), min(track_a[-1, 0], track_b[-1, 0])
    a = track_a[(track_a[:, 0] >= t0) & (track_a[:, 0] <= t1)]
    if a.size == 0:
        return np.empty(0), np.empty(0)
    bx = np.interp(a[:, 0], track_b[:, 0], track_b[:, 1])
    by = np.interp(a[:, 0], track_b[:, 0], track_b[:, 2])
    return a[:, 0], np.hypot(a[:, 1] - bx, a[:, 2] - by)


def proximity_intervals(
    track_a: Track, track_b: Track, max_distance: float = 1.5, min_duration: float = 0.0
) -> list[Interval]:
    """Intervals where two entities were within ``max_distance`` metres of each other.

    1.5 m is the human-robot separation the scene spec treats as an incursion;
    E4.2 overrides it per entity pair.
    """
    t, d = distances(track_a, track_b)
    return _runs(t, d <= max_distance, min_duration)
