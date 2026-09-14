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

import numpy as np
from numpy.typing import NDArray

from apps.worker.tasks import build_detector, camera_offsets
from packages.common.camera import CameraModel
from packages.schemas import Observation, TrackSegment
from scripts.evaluation.events_on_truth import REPORTS, SAMPLES, SCENE, log_result, score_events
from services.events import EventConfig, class_heights, localise_all
from services.identity import associate, build_segment_tracks, entity_groups
from services.ingestion import case_clips
from services.observability.logging import configure_logging
from services.perception.pipeline import process_camera
from services.tracking import TrackerConfig

log = logging.getLogger(__name__)


def run_perception(
    case_id: str,
) -> tuple[list[Observation], list[TrackSegment], dict[str, NDArray[np.float64]]]:
    """Run detector, tracker and descriptors over every clip, as the worker would."""
    detector = build_detector()
    offsets = camera_offsets()
    rows: list[Observation] = []
    segments: list[TrackSegment] = []
    descriptors: dict[str, NDArray[np.float64]] = {}
    for clip in case_clips(SAMPLES / case_id):
        out = process_camera(
            clip,
            run_id="eval",
            camera_id=clip.stem,
            clock_offset_s=offsets[clip.stem],
            target_fps=10.0,
            detector=detector,
            tracker_config=TrackerConfig(),
        )
        rows.extend(out.observations)
        segments.extend(out.segments)
        descriptors.update(out.descriptors)
    return rows, segments, descriptors


def tracked_observations(case_id: str) -> list[Observation]:
    """Just the tracked observations, for harnesses that need nothing else."""
    return run_perception(case_id)[0]


def main() -> int:
    """Score the tune cases on real perception output and write a JSON report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=["case_01", "case_03", "case_04", "case_05"])
    args = parser.parse_args()
    config = EventConfig()
    log.info("config: %s", config.version)

    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    speeds = {
        k: float(v["max_speed_mps"]) for k, v in scene["entities"].items() if not k.startswith("_")
    }
    results = []
    for case_id in args.cases:
        observations, segments, descriptors = run_perception(case_id)
        # The same identity step a processing run performs, so merged events here
        # are the events a run would persist.
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
        groups = entity_groups(links, segments)
        r = score_events(case_id, observations, config, label="detections", groups=groups)
        results.append(r)
        log_result(r)
    out = REPORTS / f"events-on-detections-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"config": config.version, "results": results}, indent=2))
    log.info("written to %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
