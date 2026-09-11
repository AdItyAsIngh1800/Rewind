"""Measure the tracker against ground truth used as a perfect detector.

Ray-cast ground truth carries every entity's true identity. Strip it, feed the boxes
through ByteTrack one frame at a time, and compare the ids it assigns with the ids it
was not shown. Everything the tracker gets wrong here is the tracker's own doing,
because the boxes were exact.

This isolates tracking from detection. Once a real detector is in front of it the
tracker will look worse, and this number is what says how much of that was the
detector's fault.

    uv run python scripts/evaluation/tracking_on_truth.py
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from collections import defaultdict

from packages.schemas import Observation
from services.observability.logging import configure_logging
from services.tracking import Tracker, TrackerConfig, score_against_truth

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")


def track_case(case_id: str, config: TrackerConfig) -> dict[str, object]:
    """Run one case through per-camera trackers and score every camera."""
    rows = json.loads((SAMPLES / case_id / "observations_gt.json").read_text())
    by_camera_frame: dict[str, dict[int, list[Observation]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        # The true track id is stripped; the true entity id is kept so the result
        # can be scored. The tracker never reads entity_id.
        observation = Observation.model_validate({**row, "track_id": None})
        by_camera_frame[observation.camera_id][observation.frame_index].append(observation)

    summary: dict[str, object] = {"case_id": case_id, "cameras": {}}
    total_switches = 0
    for camera_id in sorted(by_camera_frame):
        tracker = Tracker(camera_id, config)
        tracked: list[Observation] = []
        frames = by_camera_frame[camera_id]
        # Every frame is fed, including empty ones, so lost tracks age at the right
        # rate. Skipping empty frames would freeze the buffer during an occlusion
        # and make the tracker look better at bridging gaps than it is.
        for frame_index in range(max(frames) + 1):
            tracked.extend(tracker.update(frames.get(frame_index, [])))
        report = score_against_truth(camera_id, tracked)
        total_switches += report.id_switches
        cameras = summary["cameras"]
        assert isinstance(cameras, dict)
        cameras[camera_id] = {
            "observations": report.observations,
            "assigned": report.assigned,
            "id_switches": report.id_switches,
            "tracks_created": report.tracks_created,
            "true_entities": report.true_entities,
            "fragmentation": report.fragmentation,
        }
        log.info(
            "  %s  %4d obs  %4d assigned  %2d switches  %2d tracks for %d entities  %s",
            camera_id,
            report.observations,
            report.assigned,
            report.id_switches,
            report.tracks_created,
            report.true_entities,
            report.fragmentation,
        )
    summary["id_switches"] = total_switches
    return summary


def main() -> int:
    """Score every case and report the totals."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=[])
    parser.add_argument("--track-buffer", type=int, default=30)
    parser.add_argument("--match-thresh", type=float, default=0.8)
    args = parser.parse_args()

    config = TrackerConfig(track_buffer=args.track_buffer, match_thresh=args.match_thresh)
    case_ids = args.cases or sorted(d.name for d in SAMPLES.glob("case_*"))

    log.info("tracker: %s", config.version)
    total = 0
    for case_id in case_ids:
        log.info("%s", case_id)
        summary = track_case(case_id, config)
        switches = summary["id_switches"]
        assert isinstance(switches, int)
        total += switches

    log.info("")
    log.info("total id switches across %d cases, perfect boxes: %d", len(case_ids), total)
    log.info("charter floor: at most 2 per case per camera")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
