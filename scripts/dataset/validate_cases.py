"""Lint the case configuration against the scene geometry.

Runs in seconds and needs no Blender. Its job is to catch authoring mistakes before
anything is rendered, because the alternative is discovering them in ground truth
after a three-hour render.

It exists because of a real bug: four of the six cases had actors walking straight
through solid racking. The renders looked plausible, the ground truth validated
against the contracts, and nothing complained. Geometry that is legal per the schema
can still be physically impossible, and only a check against the scene catches that.

    uv run python scripts/dataset/validate_cases.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
from typing import Any

SCENE = pathlib.Path("ml/configs/scene_v1.json")
CASES = pathlib.Path("ml/configs/cases_v1.json")

#: Sample interval when walking a path, in seconds. Matches the render frame rate, so
#: a violation the renderer would produce is a violation this finds.
STEP_S = 0.1


def interpolate(waypoints: list[dict[str, Any]], t: float) -> tuple[float, float]:
    """Position at time ``t``, matching the renderer's linear interpolation."""
    if t <= waypoints[0]["t"]:
        return waypoints[0]["x"], waypoints[0]["y"]
    if t >= waypoints[-1]["t"]:
        return waypoints[-1]["x"], waypoints[-1]["y"]
    for start, end in itertools.pairwise(waypoints):
        if start["t"] <= t <= end["t"]:
            span = end["t"] - start["t"]
            ratio = 0.0 if span == 0 else (t - start["t"]) / span
            return (
                start["x"] + ratio * (end["x"] - start["x"]),
                start["y"] + ratio * (end["y"] - start["y"]),
            )
    return waypoints[-1]["x"], waypoints[-1]["y"]


def inside_block(x: float, y: float, block: dict[str, Any]) -> bool:
    """Whether a world point falls inside a racking block's footprint."""
    return block["x"][0] <= x <= block["x"][1] and block["y"][0] <= y <= block["y"][1]


def check_solid_geometry(
    case: dict[str, Any], blocks: list[dict[str, Any]], duration_s: float
) -> list[str]:
    """Report actors whose path passes through solid racking."""
    problems: list[str] = []
    steps = int(duration_s / STEP_S) + 1
    for track in case["actors"]:
        collisions: dict[str, list[float]] = {}
        for step in range(steps):
            t = step * STEP_S
            x, y = interpolate(track["waypoints"], t)
            for block in blocks:
                if inside_block(x, y, block):
                    collisions.setdefault(block["id"], []).append(round(t, 1))
        for block_id, times in collisions.items():
            problems.append(
                f"{track['entity_id']} passes through {block_id} "
                f"from {times[0]}s to {times[-1]}s ({len(times)} frames)"
            )
    return problems


def check_inside_warehouse(case: dict[str, Any], house: dict[str, Any]) -> list[str]:
    """Report actors that leave the building."""
    problems: list[str] = []
    for track in case["actors"]:
        for point in track["waypoints"]:
            if not (0.0 <= point["x"] <= house["size_x"]):
                problems.append(
                    f"{track['entity_id']} is outside the warehouse at t={point['t']}s "
                    f"(x={point['x']})"
                )
            if not (0.0 <= point["y"] <= house["size_y"]):
                problems.append(
                    f"{track['entity_id']} is outside the warehouse at t={point['t']}s "
                    f"(y={point['y']})"
                )
    return problems


def check_speeds(case: dict[str, Any], limits: dict[str, float]) -> list[str]:
    """Report actors moving implausibly fast between waypoints.

    A person teleporting across the floor still renders, still validates and still
    produces ground truth. It only looks wrong to a human watching the video, which
    is far too late to find out.
    """
    problems: list[str] = []
    for track in case["actors"]:
        limit = limits.get(track["class"])
        if limit is None:
            continue
        for start, end in zip(track["waypoints"], track["waypoints"][1:], strict=False):
            span = end["t"] - start["t"]
            if span <= 0:
                continue
            distance = ((end["x"] - start["x"]) ** 2 + (end["y"] - start["y"]) ** 2) ** 0.5
            speed = distance / span
            if speed > limit:
                problems.append(
                    f"{track['entity_id']} moves at {speed:.2f} m/s between "
                    f"t={start['t']}s and t={end['t']}s, above the {limit} m/s limit "
                    f"for a {track['class']}"
                )
    return problems


def check_monotonic_time(case: dict[str, Any]) -> list[str]:
    """Report waypoints that go backwards in time."""
    problems: list[str] = []
    for track in case["actors"]:
        times = [point["t"] for point in track["waypoints"]]
        if times != sorted(times):
            problems.append(f"{track['entity_id']} has waypoints out of time order")
    return problems


#: Plausible maxima, generous rather than strict. The point is catching a typo that
#: sends an actor across the warehouse in one frame, not enforcing realistic gait.
SPEED_LIMITS: dict[str, float] = {"person": 2.5, "robot": 2.0, "forklift": 3.5, "pallet": 3.5}


def validate(scene: dict[str, Any], cases: dict[str, Any]) -> dict[str, list[str]]:
    """Validate every case, returning problems keyed by case id."""
    blocks = scene["racking"]["blocks"]
    house = scene["warehouse"]
    duration = cases["duration_s"]

    found: dict[str, list[str]] = {}
    for case in cases["cases"]:
        problems = (
            check_solid_geometry(case, blocks, duration)
            + check_inside_warehouse(case, house)
            + check_speeds(case, SPEED_LIMITS)
            + check_monotonic_time(case)
        )
        if problems:
            found[case["id"]] = problems
    return found


def main() -> int:
    """Lint the case config and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=pathlib.Path, default=SCENE)
    parser.add_argument("--cases", type=pathlib.Path, default=CASES)
    args = parser.parse_args()

    scene = json.loads(args.scene.read_text())
    cases = json.loads(args.cases.read_text())
    found = validate(scene, cases)

    for case in cases["cases"]:
        problems = found.get(case["id"], [])
        print(f"{case['id']:9s} {'FAIL' if problems else 'ok'}")
        for problem in problems:
            print(f"    - {problem}")

    print()
    if found:
        total = sum(len(v) for v in found.values())
        print(f"FAILED — {total} problem(s) across {len(found)} case(s). Do not render yet.")
        return 1
    print(f"OK — {len(cases['cases'])} cases are geometrically valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
