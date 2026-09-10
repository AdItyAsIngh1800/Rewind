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
import logging
import pathlib
from typing import Any

from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

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
    inside_x = bool(block["x"][0] <= x <= block["x"][1])
    inside_y = bool(block["y"][0] <= y <= block["y"][1])
    return inside_x and inside_y


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


#: Minimum OKLab separation between an entity colour and any surface colour. Below
#: this an entity is effectively camouflaged against the thing it stands on.
ENTITY_SURFACE_MIN = 0.15

#: Minimum separation between two entity colours. Held lower than the surface floor
#: because geometry already separates the classes: a 0.15 m slab and a 1.75 m upright
#: are not confusable on shape alone, so colour carries less of that burden.
ENTITY_ENTITY_MIN = 0.17


def check_colour_separation(scene: dict[str, Any]) -> list[str]:
    """Check every entity colour is distinguishable from surfaces and other entities.

    Added after the hand-picked palette turned out to have nine collisions, the worst
    being a forklift 0.013 OKLab from the floor paint beneath it. Nothing complained:
    the render looked fine, ground truth is geometric and validated cleanly, and the
    problem would only have surfaced as unexplained detector confusion in Week 6.

    Surface-versus-surface pairs are deliberately not constrained. A floor and a wall
    being similar greys is realistic and harms nothing, and constraining them made the
    search unsatisfiable for reasons that had nothing to do with detectability.
    """
    from itertools import combinations

    from packages.common.color import perceptual_distance

    entities = {
        name: tuple(spec["colour"])
        for name, spec in scene["entities"].items()
        if not name.startswith("_")
    }
    surfaces = {
        name: tuple(value)
        for name, value in scene.get("surfaces", {}).items()
        if not name.startswith("_")
    }
    if not surfaces:
        return ["scene config defines no surfaces, so entity colours cannot be checked"]

    problems: list[str] = []
    for a, b in combinations(entities, 2):
        distance = perceptual_distance(entities[a], entities[b])
        if distance < ENTITY_ENTITY_MIN:
            problems.append(
                f"entities {a} and {b} are {distance:.3f} apart, below "
                f"{ENTITY_ENTITY_MIN}; a detector would confuse them on colour"
            )
    for entity, colour in entities.items():
        for surface, surface_colour in surfaces.items():
            distance = perceptual_distance(colour, surface_colour)
            if distance < ENTITY_SURFACE_MIN:
                problems.append(
                    f"{entity} is {distance:.3f} from surface {surface}, below "
                    f"{ENTITY_SURFACE_MIN}; it is camouflaged against it"
                )
    return problems


def validate(scene: dict[str, Any], cases: dict[str, Any]) -> dict[str, list[str]]:
    """Validate every case, returning problems keyed by case id."""
    blocks = scene["racking"]["blocks"]
    house = scene["warehouse"]
    duration = cases["duration_s"]

    found: dict[str, list[str]] = {}

    # Scene-wide rather than per-case, so it is reported once under its own key.
    colour_problems = check_colour_separation(scene)
    if colour_problems:
        found["scene colours"] = colour_problems

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
        log.info(f"{case['id']:9s} {'FAIL' if problems else 'ok'}")
        for problem in problems:
            log.info(f"    - {problem}")

    log.info("")
    if found:
        total = sum(len(v) for v in found.values())
        log.info(f"FAILED — {total} problem(s) across {len(found)} case(s). Do not render yet.")
        return 1
    log.info(f"OK — {len(cases['cases'])} cases are geometrically valid.")
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
