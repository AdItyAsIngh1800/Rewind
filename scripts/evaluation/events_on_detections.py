"""Score semantic events extracted from the real pipeline: detector, tracker, then events.

The Gate 2 number. EXP-0005 established what the extractor does on perfect tracks;
this is the same table with ``yolo11n-rewind-v1`` boxes, ByteTrack ids and positions
back-projected through the camera model, which is exactly what a processing run
persists. The gap between the two tables is the cost of imperfect perception.

    uv run python scripts/evaluation/events_on_detections.py
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime

from apps.worker.tasks import build_detector, camera_offsets
from packages.schemas import Observation
from scripts.evaluation.events_on_truth import REPORTS, SAMPLES, log_result, score_events
from services.events import EventConfig
from services.observability.logging import configure_logging
from services.perception.pipeline import process_camera
from services.tracking import TrackerConfig

log = logging.getLogger(__name__)


def tracked_observations(case_id: str) -> list[Observation]:
    """Run detector and tracker over every clip of a case, as the worker would."""
    detector = build_detector()
    offsets = camera_offsets()
    rows: list[Observation] = []
    for clip in sorted((SAMPLES / case_id).glob("*.mp4")):
        tracked, _segments, _frames = process_camera(
            clip,
            run_id="eval",
            camera_id=clip.stem,
            clock_offset_s=offsets[clip.stem],
            target_fps=10.0,
            detector=detector,
            tracker_config=TrackerConfig(),
        )
        rows.extend(tracked)
    return rows


def main() -> int:
    """Score the tune cases on real perception output and write a JSON report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=["case_01", "case_03", "case_04", "case_05"])
    args = parser.parse_args()
    config = EventConfig()
    log.info("config: %s", config.version)

    results = []
    for case_id in args.cases:
        r = score_events(case_id, tracked_observations(case_id), config, label="detections")
        results.append(r)
        log_result(r)
    out = REPORTS / f"events-on-detections-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"config": config.version, "results": results}, indent=2))
    log.info("written to %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
