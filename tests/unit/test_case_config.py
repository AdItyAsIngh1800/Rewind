"""Tests for the case-configuration linter.

Written against the bugs that actually shipped. Four of the six cases had actors
walking through solid racking; the renders looked plausible and the ground truth
validated against the contracts, because a schema cannot know where a wall is. These
tests feed the linter the shape of those bugs and assert it complains.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from scripts.dataset.validate_cases import (
    SPEED_LIMITS,
    check_inside_warehouse,
    check_monotonic_time,
    check_solid_geometry,
    check_speeds,
    interpolate,
    validate,
)

SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
CASES = json.loads(pathlib.Path("ml/configs/cases_v1.json").read_text())
BLOCKS = SCENE["racking"]["blocks"]
HOUSE = SCENE["warehouse"]


def track(
    entity: str, entity_class: str, points: list[tuple[float, float, float]]
) -> dict[str, Any]:
    """Build one actor track from (t, x, y) tuples."""
    return {
        "entity_id": entity,
        "class": entity_class,
        "waypoints": [{"t": t, "x": x, "y": y} for t, x, y in points],
    }


def case(*tracks: dict[str, Any]) -> dict[str, Any]:
    """Wrap actor tracks in a minimal case."""
    return {"id": "case_test", "actors": list(tracks)}


# --------------------------------------------------------------------------
# Interpolation must match the renderer, or the linter checks a different path
# --------------------------------------------------------------------------


def test_interpolation_clamps_outside_the_waypoint_range() -> None:
    """Assert positions before the first and after the last waypoint are held."""
    points = [{"t": 1.0, "x": 5.0, "y": 5.0}, {"t": 2.0, "x": 7.0, "y": 5.0}]
    assert interpolate(points, 0.0) == (5.0, 5.0)
    assert interpolate(points, 9.0) == (7.0, 5.0)


def test_interpolation_is_linear_between_waypoints() -> None:
    """Assert the midpoint is halfway, matching the renderer's motion exactly."""
    points = [{"t": 0.0, "x": 0.0, "y": 0.0}, {"t": 2.0, "x": 10.0, "y": 4.0}]
    assert interpolate(points, 1.0) == (5.0, 2.0)


# --------------------------------------------------------------------------
# The bug that shipped
# --------------------------------------------------------------------------


def test_an_actor_walking_through_racking_is_caught() -> None:
    """Assert a path crossing a rack footprint is reported.

    This is the exact bug: RACK_2 spans x 6.0-9.5, y 10.5-13.5, and a person routed
    along y=12 walks straight through it.
    """
    walker = track("P01", "person", [(0.0, 2.0, 12.0), (10.0, 12.0, 12.0)])
    problems = check_solid_geometry(case(walker), BLOCKS, duration_s=10.0)
    assert problems
    assert "RACK_2" in " ".join(problems)


def test_the_problem_names_the_entity_the_block_and_the_interval() -> None:
    """Assert the message is actionable rather than just a failure."""
    walker = track("P01", "person", [(0.0, 7.0, 12.0), (5.0, 8.0, 12.0)])
    message = check_solid_geometry(case(walker), BLOCKS, duration_s=5.0)[0]
    assert "P01" in message
    assert "RACK_2" in message
    assert "frames" in message


def test_a_path_along_the_open_corridor_is_accepted() -> None:
    """Assert the 1 m corridor between the aisle and the racking is not flagged.

    The corridor at y ~= 10 is genuinely open. A linter that rejected it would push
    every route into the aisle and destroy the occlusion cases.
    """
    walker = track("P01", "person", [(0.0, 2.0, 10.0), (10.0, 12.0, 10.0)])
    assert check_solid_geometry(case(walker), BLOCKS, duration_s=10.0) == []


def test_the_north_cross_aisle_gap_is_open() -> None:
    """Assert the gap between RACK_2 and RACK_3 is passable.

    RACK_2 ends at x=9.5 and RACK_3 starts at x=14.5, so x=12 is the route actors
    take from the walkway down to the intersection.
    """
    walker = track("P01", "person", [(0.0, 12.0, 13.5), (5.0, 12.0, 10.0)])
    assert check_solid_geometry(case(walker), BLOCKS, duration_s=5.0) == []


# --------------------------------------------------------------------------
# Other authoring mistakes
# --------------------------------------------------------------------------


def test_an_actor_leaving_the_building_is_caught() -> None:
    """Assert a waypoint outside the warehouse is reported."""
    walker = track("P01", "person", [(0.0, 2.0, 8.0), (5.0, 30.0, 8.0)])
    problems = check_inside_warehouse(case(walker), HOUSE)
    assert problems and "outside the warehouse" in problems[0]


def test_a_teleporting_actor_is_caught() -> None:
    """Assert an implausible speed is reported.

    A person crossing the warehouse in one second still renders, still validates and
    still produces ground truth. It looks wrong only to a human watching the video,
    which is far too late.
    """
    walker = track("P01", "person", [(0.0, 2.0, 8.0), (1.0, 20.0, 8.0)])
    problems = check_speeds(case(walker), SPEED_LIMITS)
    assert problems and "above the" in problems[0]


def test_walking_pace_is_accepted() -> None:
    """Assert a normal 1.3 m/s walk is not flagged."""
    walker = track("P01", "person", [(0.0, 2.0, 8.0), (10.0, 15.0, 8.0)])
    assert check_speeds(case(walker), SPEED_LIMITS) == []


def test_waypoints_out_of_time_order_are_caught() -> None:
    """Assert time running backwards is reported."""
    walker = track("P01", "person", [(0.0, 2.0, 8.0), (5.0, 6.0, 8.0), (3.0, 8.0, 8.0)])
    problems = check_monotonic_time(case(walker))
    assert problems and "time order" in problems[0]


# --------------------------------------------------------------------------
# The shipped configuration
# --------------------------------------------------------------------------


def test_every_committed_case_is_geometrically_valid() -> None:
    """Assert the real configuration passes.

    This is the regression guard. It failed for four of six cases before the routes
    were corrected, and it is what stops a future waypoint edit reintroducing the
    same bug.
    """
    assert validate(SCENE, CASES) == {}


def test_all_six_cases_are_defined() -> None:
    """Assert the charter's six cases are present with their splits."""
    ids = {c["id"] for c in CASES["cases"]}
    assert ids == {f"case_0{n}" for n in range(1, 7)}
    golden = {c["id"] for c in CASES["cases"] if c["split"] == "golden"}
    assert golden == {"case_02", "case_06"}


def test_the_negative_case_has_no_incident_class() -> None:
    """Assert case_05 is genuinely a negative.

    Without a case where nothing happens, the false-alert rate cannot be measured and
    a detector that fires on everything scores perfectly.
    """
    negative = next(c for c in CASES["cases"] if c["id"] == "case_05")
    assert negative["incident_class"] is None
    assert negative["cause_gt"] is None
