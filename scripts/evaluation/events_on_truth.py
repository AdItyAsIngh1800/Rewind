"""Score semantic event extraction against the ground-truth event timeline.

Two runs per case, both on perfect tracks (ground-truth observations with
``track_id`` set to the true entity):

* **truth positions** - ``world_xyz`` used verbatim, isolating the event logic;
* **projected positions** - ``world_xyz`` stripped so every position comes from the
  camera model, which adds the localisation error real detections will carry.

The difference between the two is the cost of localisation. Ground-truth
``state_change`` events come from robot telemetry the scenario scripted, not from
anything visible, so they are reported separately rather than counted as misses.

    uv run python scripts/evaluation/events_on_truth.py
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from collections import Counter, defaultdict
from datetime import UTC, datetime

from packages.common.camera import CameraModel
from packages.evaluation.metrics import Counts, match_event_pairs
from packages.schemas import Observation
from services.events import (
    EventConfig,
    class_heights,
    extract_events,
    load_zones,
    merge_across_cameras,
)
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")
SCENE = pathlib.Path("ml/configs/scene_v1.json")
REPORTS = pathlib.Path("artifacts/benchmark-reports")

#: Event types the video pipeline is expected to recover. Telemetry-only types are
#: excluded from recall so a structural gap is not misread as a model failure.
VISIBLE_TYPES = {"zone_entry", "zone_exit"}

TOLERANCE_S = 0.5


def perfect_tracks(case_dir: pathlib.Path, *, projected: bool) -> list[Observation]:
    """Ground-truth observations as a perfect tracker would have labelled them."""
    rows = json.loads((case_dir / "observations_gt.json").read_text())
    out = []
    for row in rows:
        row = {**row, "track_id": row["entity_id"]}
        if projected:
            row["world_xyz"] = None
        out.append(Observation.model_validate(row))
    return out


def score_case(case_id: str, config: EventConfig, *, projected: bool) -> dict[str, object]:
    """Extract, merge and score one case; returns the numbers for the report."""
    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    case_dir = SAMPLES / case_id
    observations = perfect_tracks(case_dir, projected=projected)
    events = merge_across_cameras(
        extract_events(
            "eval", observations, load_zones(scene), cameras, class_heights(scene), config
        )
    )
    truth = json.loads((case_dir / "events_gt.json").read_text())
    seen = observed_times(observations)
    # A truth event is observable only if some camera saw the entity within the
    # tolerance of it. The rest are coverage gaps: a property of the camera layout,
    # reported on its own line so it is not misread as an extraction miss.
    visible = [t for t in truth if t["event_type"] in VISIBLE_TYPES]
    observable = [
        t
        for t in visible
        if any(abs(s - t["timestamp_s"]) <= TOLERANCE_S for e in t["entity_ids"] for s in seen[e])
    ]
    # Predictions that admit their time is a bound (first sight, or a crossing during
    # an occlusion) are scored separately; counting them as false positives would
    # penalise the extractor for being honest about what it did not see.
    scored = [e for e in events if e.event_type.value in VISIBLE_TYPES]
    is_bounded = [("at_first_sight" in e.payload or "during_gap" in e.payload) for e in scored]
    pairs = match_event_pairs(
        [e.model_dump(mode="json") for e in scored], observable, tolerance_s=TOLERANCE_S
    )
    matched = {pi for pi, _, _ in pairs}
    errors = [err for _, _, err in pairs]
    tp = len(pairs)
    fp = sum(1 for i in range(len(scored)) if i not in matched and not is_bounded[i])
    unmatched_bounded = sum(1 for i in range(len(scored)) if i not in matched and is_bounded[i])
    counts = Counts(tp=tp, fp=fp, fn=len(observable) - tp)
    by_type = Counter(e.event_type.value for e in events)
    return {
        "case_id": case_id,
        "projected": projected,
        "tp": counts.tp,
        "fp": counts.fp,
        "fn": counts.fn,
        "precision": counts.precision,
        "recall": counts.recall,
        "mean_abs_timing_error_s": sum(abs(e) for e in errors) / len(errors) if errors else None,
        "max_abs_timing_error_s": max((abs(e) for e in errors), default=None),
        "truth_unobservable": len(visible) - len(observable),
        "truth_telemetry_only": len(truth) - len(visible),
        "predicted_bounded": sum(is_bounded),
        "predicted_bounded_unmatched": unmatched_bounded,
        "events_by_type": dict(sorted(by_type.items())),
    }


def observed_times(observations: list[Observation]) -> dict[str, list[float]]:
    """Timestamps at which each entity was observed by any camera."""
    seen: dict[str, list[float]] = defaultdict(list)
    for o in observations:
        seen[str(o.track_id)].append(o.timestamp_s)
    return seen


def main() -> int:
    """Score every tune case both ways and write a JSON report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    # Tune cases only. The golden pair stays sealed until E9.1; passing them here is
    # a split-discipline breach and the reason the default is explicit.
    parser.add_argument("cases", nargs="*", default=["case_01", "case_03", "case_04", "case_05"])
    args = parser.parse_args()
    config = EventConfig()
    log.info("config: %s", config.version)

    results = []
    for projected in (False, True):
        label = "projected" if projected else "truth-xy"
        for case_id in args.cases:
            r = score_case(case_id, config, projected=projected)
            results.append(r)
            log.info(
                "%-9s %s  tp %2d fp %2d fn %2d  P %.2f R %.2f  timing max %.2fs  "
                "unobservable %d  telemetry %d  bounded %d (%d unmatched)",
                label,
                case_id,
                r["tp"],
                r["fp"],
                r["fn"],
                r["precision"],
                r["recall"],
                r["max_abs_timing_error_s"] or 0.0,
                r["truth_unobservable"],
                r["truth_telemetry_only"],
                r["predicted_bounded"],
                r["predicted_bounded_unmatched"],
            )
            log.info("            %s", r["events_by_type"])
    out = REPORTS / f"events-on-truth-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"config": config.version, "results": results}, indent=2))
    log.info("written to %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
