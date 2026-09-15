"""Score incident triggers and their rewind windows on the tune cases (E6.1, E6.2).

Two modes per case, as for events. **Perfect** feeds ground-truth tracks with exact
positions; **detections** runs detector, tracker and identity as a worker would.
Telemetry is identical in both, the robot's scripted state channel, because it is not
perception.

Scored per case against the scene spec's expected outcome:

- the incident class, or no incident at all for the `C05` near-miss, which is the
  only case that can measure a false alert;
- **latency**, detected time minus the true trigger time;
- **window covers cause**, whether the rewind window contains the annotated cause.
  An incident opened on time but rewound past its cause would hand the report an
  investigation window with the answer cut out.

    uv run python scripts/evaluation/incidents_on_detections.py
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from datetime import UTC, datetime

from packages.common.camera import CameraModel
from packages.schemas import IncidentClass, Observation
from scripts.evaluation.events_on_detections import run_perception
from scripts.evaluation.events_on_truth import REPORTS, SAMPLES, SCENE, perfect_tracks
from services.events import (
    EventConfig,
    class_heights,
    extract_events,
    load_zones,
    localise_all,
    merge_across_cameras,
)
from services.identity import associate, build_segment_tracks, entity_groups
from services.incidents import IncidentConfig, detect_incidents, load_case_script, state_changes
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

CASES_CONFIG = pathlib.Path("ml/configs/cases_v1.json")

#: Expected outcome per tune case: class, true trigger time, annotated cause time.
#: Trigger times are the robot's scripted e-stop (`cases_v1.json`) and, for C04, the
#: drop at 14 s plus the 20 s dwell (scene spec §6.4). Cause times are the ones
#: `cause_gt.json` states. The golden pair was added at E9.1 from the case scripts and
#: pre-registered in EXP-0010 before either case was opened; it is not a default.
TRUTH: dict[str, tuple[IncidentClass, float, float] | None] = {
    "case_01": (IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION, 13.4, 12.8),
    "case_03": (IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION, 17.4, 16.9),
    "case_04": (IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT, 34.0, 14.0),
    "case_05": None,
    # case_07 is case_04's script with F02 as the forklift (EXP-0013): same drop, same dwell.
    "case_07": (IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT, 34.0, 14.0),
}
GOLDEN_TRUTH: dict[str, tuple[IncidentClass, float, float] | None] = {
    "case_02": (IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION, 13.5, 13.0),
    "case_06": (IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT, 44.0, 24.0),
}
TRUTH.update(GOLDEN_TRUTH)


def score_incidents(
    case_id: str, observations: list[Observation], groups: dict[str, str], label: str
) -> dict[str, object]:
    """Extract events, add telemetry, open incidents and score them for one case."""
    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    zones = load_zones(scene)
    config = EventConfig()
    events = merge_across_cameras(
        extract_events("eval", observations, zones, cameras, class_heights(scene), config),
        config.merge_tolerance_s,
        groups,
    )
    telemetry = state_changes("eval", load_case_script(CASES_CONFIG, case_id))
    run_end_s = max(o.timestamp_s for o in observations)
    incidents = detect_incidents("eval", [*events, *telemetry], zones, run_end_s, IncidentConfig())

    truth = TRUTH[case_id]
    matched = [i for i in incidents if truth is not None and i.incident_class is truth[0]]
    first = matched[0] if matched else None
    return {
        "case_id": case_id,
        "mode": label,
        "incidents": [i.model_dump(mode="json") for i in incidents],
        "tp": int(first is not None),
        "fp": len(incidents) - int(first is not None),
        "fn": int(truth is not None and first is None),
        "latency_s": (
            round(first.detected_at_s - truth[1], 3) if first and truth is not None else None
        ),
        "window_covers_cause": (
            first.window_start_s <= truth[2] <= first.window_end_s
            if first and truth is not None
            else None
        ),
    }


def main() -> int:
    """Score both modes on every tune case and write a JSON report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=[c for c in TRUTH if c not in GOLDEN_TRUTH])
    args = parser.parse_args()
    log.info("config: %s", IncidentConfig().version)

    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    speeds = {
        k: float(v["max_speed_mps"]) for k, v in scene["entities"].items() if not k.startswith("_")
    }
    results = []
    for case_id in args.cases:
        perfect = perfect_tracks(SAMPLES / case_id, projected=False)
        groups = {str(o.track_id): str(o.entity_id) for o in perfect}
        results.append(score_incidents(case_id, perfect, groups, "perfect"))
        log_result(results[-1])

        observations, segments, descriptors = run_perception(case_id)
        links = associate(
            "eval",
            build_segment_tracks(
                segments,
                observations,
                localise_all(observations, cameras, class_heights(scene)),
                descriptors,
            ),
            speeds,
        )
        results.append(
            score_incidents(case_id, observations, entity_groups(links, segments), "detections")
        )
        log_result(results[-1])

    out = REPORTS / f"incidents-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"config": IncidentConfig().version, "results": results}, indent=2))
    log.info("written to %s", out)
    return 0


def log_result(r: dict[str, object]) -> None:
    """One line per case and mode."""
    incidents = r["incidents"]
    assert isinstance(incidents, list)
    log.info(
        "%-10s %s  opened %d  tp %s fp %s fn %s  latency %s  window covers cause %s  %s",
        r["mode"],
        r["case_id"],
        len(incidents),
        r["tp"],
        r["fp"],
        r["fn"],
        r["latency_s"],
        r["window_covers_cause"],
        [
            (i["incident_class"], i["detected_at_s"], i["window_start_s"], i["window_end_s"])
            for i in incidents
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
