"""Validate a Blender ground-truth export against the frozen contracts.

Blender runs its own bundled Python and has no access to this project's environment,
so the render script emits plain JSON. This is the step that checks what it emitted
actually conforms to the contracts everything else is built on.

That split is deliberate rather than a workaround. The renderer produces data; the
contract decides whether the data is valid. If ground truth could bypass validation,
a malformed export would surface as a detector failure in Week 6 rather than as an
export bug in Week 3.

    uv run python scripts/dataset/validate_ground_truth.py data/samples/case_01
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from pydantic import ValidationError

from packages.schemas import (
    SCHEMA_VERSION,
    EntityClass,
    Observation,
    SemanticEvent,
)

#: Scene spec §7: an entity less than this visible is not emitted at all. Ground
#: truth must not claim to see what a camera cannot, otherwise every occlusion case
#: scores as a detector failure instead of as the evidence gap it is.
MIN_VISIBILITY = 0.15

#: Scene spec §3.1 and §7: a `pallet` entity is floor-level only. Stored goods in
#: racking are scenery. The scene is authored so no racked pallet is ever visible;
#: this is the safety net, and if it ever fires the scene is wrong rather than this
#: filter being useful.
MAX_PALLET_Z = 0.5


class GroundTruthError(Exception):
    """Raised when an export cannot be reconciled with the contracts."""


def _load(path: pathlib.Path) -> Any:
    """Read one JSON file, failing with the path included."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise GroundTruthError(f"missing export: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GroundTruthError(f"{path} is not valid JSON: {exc}") from exc


def validate_observations(rows: list[dict[str, Any]]) -> list[str]:
    """Validate observation records and return a list of problems.

    Every row is checked rather than failing on the first, because a renderer bug
    usually affects a whole class of frames and seeing one example of each is more
    useful than seeing the first.
    """
    problems: list[str] = []
    for index, row in enumerate(rows):
        row.setdefault("schema_version", SCHEMA_VERSION)
        try:
            observation = Observation.model_validate(row)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(p) for p in first["loc"])
            problems.append(f"row {index}: {location}: {first['msg']}")
            continue

        if observation.visibility < MIN_VISIBILITY:
            problems.append(
                f"row {index} ({observation.observation_id}): visibility "
                f"{observation.visibility:.2f} is below {MIN_VISIBILITY} and should "
                "not have been emitted at all"
            )

        if observation.entity_class is EntityClass.PALLET and observation.world_xyz:
            height = observation.world_xyz[2]
            if height > MAX_PALLET_Z:
                problems.append(
                    f"row {index} ({observation.observation_id}): pallet at z="
                    f"{height:.2f} is racked, not floor-level. The scene should hide "
                    "stored pallets rather than relying on this filter"
                )
    return problems


def validate_events(rows: list[dict[str, Any]]) -> list[str]:
    """Validate the annotated semantic-event timeline."""
    problems: list[str] = []
    for index, row in enumerate(rows):
        row.setdefault("schema_version", SCHEMA_VERSION)
        try:
            SemanticEvent.model_validate(row)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(p) for p in first["loc"])
            problems.append(f"event {index}: {location}: {first['msg']}")
    return problems


def check_coverage(observations: list[dict[str, Any]], cameras: int = 3) -> list[str]:
    """Check the export covers every camera and a plausible span of frames.

    An export that silently rendered one camera looks fine row by row and is useless
    as ground truth for a cross-camera system.
    """
    problems: list[str] = []
    seen = {row.get("camera_id") for row in observations}
    if len(seen) < cameras:
        problems.append(
            f"only {len(seen)} camera(s) present ({sorted(str(s) for s in seen)}); "
            f"the scene defines {cameras}. On a full case this means a camera saw "
            "nothing at all; on a truncated render it usually just means the action "
            "had not reached that camera's field of view yet"
        )
    if not observations:
        problems.append("export contains no observations at all")
    return problems


def validate_case(directory: pathlib.Path) -> list[str]:
    """Validate one rendered case directory and return every problem found."""
    problems: list[str] = []

    observations = _load(directory / "observations_gt.json")
    if not isinstance(observations, list):
        raise GroundTruthError("observations_gt.json must contain a list")
    problems += validate_observations(observations)
    problems += check_coverage(observations)

    events_path = directory / "events_gt.json"
    if events_path.exists():
        events = _load(events_path)
        if not isinstance(events, list):
            raise GroundTruthError("events_gt.json must contain a list")
        problems += validate_events(events)
    else:
        problems.append("events_gt.json is missing; the event timeline is annotated, not derived")

    for required in ("identities_gt.json", "cause_gt.json", "gaps_gt.json"):
        if not (directory / required).exists():
            problems.append(f"{required} is missing")

    return problems


def main() -> int:
    """Validate one or more case directories; return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="+", type=pathlib.Path)
    args = parser.parse_args()

    total = 0
    for directory in args.cases:
        print(f"\n{directory}")
        try:
            problems = validate_case(directory)
        except GroundTruthError as exc:
            print(f"  FAILED: {exc}")
            total += 1
            continue

        if problems:
            for problem in problems[:20]:
                print(f"  - {problem}")
            if len(problems) > 20:
                print(f"  ... and {len(problems) - 20} more")
            total += len(problems)
        else:
            print("  ok")

    print()
    if total:
        print(f"FAILED — {total} problem(s). Ground truth is not usable until these are fixed.")
        return 1
    print("OK — ground truth conforms to the frozen contracts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
