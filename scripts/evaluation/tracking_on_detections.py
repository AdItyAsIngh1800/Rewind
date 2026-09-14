"""Score per-camera tracking on real detector output, not perfect boxes.

EXP-0002 established what ByteTrack does when every box is exact. This is the number
that matters for Gate 1: the same tracker fed by the fine-tuned detector, whose boxes
jitter, flicker and occasionally vanish. The difference between the two runs is the
cost of imperfect detection, which is the thing E5's appearance features exist to
absorb.

Real detections carry no ``entity_id``, so each tracked box is first assigned to the
ground-truth entity it overlaps at IoU >= 0.5 in the same frame and class. After that
``score_against_truth`` applies unchanged. Boxes matching no truth are counted as
spurious; they cannot cause a switch but they can seed a phantom track.

    uv run python scripts/evaluation/tracking_on_detections.py case_01 case_05
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from collections import defaultdict
from datetime import UTC, datetime

from apps.worker.tasks import build_detector, camera_offsets
from packages.evaluation.metrics import iou
from packages.schemas import Observation
from services.ingestion import case_clips
from services.observability.logging import configure_logging
from services.perception.pipeline import process_camera
from services.tracking import TrackerConfig, score_against_truth

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")
REPORTS = pathlib.Path("artifacts/benchmark-reports")
IOU_THRESHOLD = 0.5


def assign_identities(
    tracked: list[Observation], truth: list[Observation]
) -> tuple[list[Observation], int]:
    """Copy the true ``entity_id`` onto each tracked box that overlaps it.

    Greedy by descending IoU within one frame, one class; the same simplification
    ``match_detections`` makes, for the same reason: a handful of entities per frame.
    Returns the relabelled observations and how many matched nothing.
    """
    by_key: dict[tuple[int, str], list[Observation]] = defaultdict(list)
    for t in truth:
        by_key[(t.frame_index, t.entity_class)].append(t)

    relabelled: list[Observation] = []
    unmatched = 0
    for key, group in _group(tracked).items():
        candidates = by_key.get(key, [])
        pairs = sorted(
            (
                (iou(_flat(p), _flat(t)), pi, ti)
                for pi, p in enumerate(group)
                for ti, t in enumerate(candidates)
            ),
            reverse=True,
        )
        taken_p: set[int] = set()
        taken_t: set[int] = set()
        entity_for: dict[int, str] = {}
        for score, pi, ti in pairs:
            if score < IOU_THRESHOLD or pi in taken_p or ti in taken_t:
                continue
            taken_p.add(pi)
            taken_t.add(ti)
            entity_for[pi] = candidates[ti].entity_id or ""
        for pi, p in enumerate(group):
            if pi in entity_for:
                relabelled.append(p.model_copy(update={"entity_id": entity_for[pi]}))
            else:
                unmatched += 1
                relabelled.append(p)
    return relabelled, unmatched


def _group(observations: list[Observation]) -> dict[tuple[int, str], list[Observation]]:
    """Bucket observations by (frame, class), the unit inside which boxes compete."""
    grouped: dict[tuple[int, str], list[Observation]] = defaultdict(list)
    for o in observations:
        grouped[(o.frame_index, o.entity_class)].append(o)
    return grouped


def _flat(o: Observation) -> list[float]:
    return [o.bbox.x1, o.bbox.y1, o.bbox.x2, o.bbox.y2]


def main() -> int:
    """Run detector + tracker on each case and score identities against truth."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="+")
    parser.add_argument("--match-thresh", type=float, default=TrackerConfig().match_thresh)
    args = parser.parse_args()

    detector = build_detector()
    offsets = camera_offsets()
    config = TrackerConfig(match_thresh=args.match_thresh)
    log.info("detector: %s  tracker: %s", detector.config.checkpoint, config.version)

    results: dict[str, object] = {
        "detector": detector.config.checkpoint,
        "tracker": config.version,
        "cases": {},
    }
    total_switches = 0
    for case_id in args.cases:
        truth = [
            Observation.model_validate(r)
            for r in json.loads((SAMPLES / case_id / "observations_gt.json").read_text())
        ]
        log.info("%s", case_id)
        cameras: dict[str, object] = {}
        for clip in case_clips(SAMPLES / case_id):
            camera_id = clip.stem
            out = process_camera(
                clip,
                run_id="eval",
                camera_id=camera_id,
                clock_offset_s=offsets[camera_id],
                target_fps=10.0,
                detector=detector,
                tracker_config=config,
            )
            tracked = out.observations
            relabelled, spurious = assign_identities(
                tracked, [t for t in truth if t.camera_id == camera_id]
            )
            report = score_against_truth(camera_id, relabelled)
            total_switches += report.id_switches
            cameras[camera_id] = {
                "tracked": len(tracked),
                "spurious": spurious,
                "id_switches": report.id_switches,
                "tracks_created": report.tracks_created,
                "true_entities": report.true_entities,
                "fragmentation": report.fragmentation,
            }
            log.info(
                "  %s  %4d tracked  %3d spurious  %2d switches  %2d tracks for %d entities  %s",
                camera_id,
                len(tracked),
                spurious,
                report.id_switches,
                report.tracks_created,
                report.true_entities,
                report.fragmentation,
            )
        cases = results["cases"]
        assert isinstance(cases, dict)
        cases[case_id] = cameras
    results["id_switches"] = total_switches
    log.info(
        "total id switches across %d cases, real detections: %d", len(args.cases), total_switches
    )

    report_path = REPORTS / f"tracking-on-detections-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    report_path.write_text(json.dumps(results, indent=2))
    log.info("written to %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
