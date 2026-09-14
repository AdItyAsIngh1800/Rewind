"""Measure how far real-detection positions sit from truth, and how much they wobble.

The evidence behind `EventConfig.zone_edge_margin_m` (EXP-0011, F3). Every detector box
matched to a true box (same frame and class, IoU >= 0.5) is back-projected exactly as
the event extractor does, and compared with the true world position:

- **Absolute error** per class: bias and wobble together.
- **Still wobble** per class: while the true object is stationary (under 0.05 m/s),
  each camera-entity pair's distance from its own median position. This is what makes
  a still object on a zone edge cross it back and forth, and what the margin must cover.

Tune cases only by default; the golden pair must not choose a threshold.

    uv run python scripts/evaluation/localisation_jitter.py
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
from collections import defaultdict
from typing import Any

import numpy as np
from numpy.typing import NDArray

from packages.common.camera import CameraModel
from packages.evaluation.metrics import iou
from scripts.evaluation.events_on_detections import run_perception
from scripts.evaluation.events_on_truth import SAMPLES, SCENE
from services.events import class_heights, localise_all
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

TUNE = ["case_01", "case_03", "case_04", "case_05"]
STILL_MPS = 0.05
MIN_STILL_SAMPLES = 20


def _box(row: dict[str, Any]) -> list[float]:
    """Return a ground-truth row's box as a flat list."""
    return [float(row["bbox"][k]) for k in ("x1", "y1", "x2", "y2")]


def measure(case_id: str) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Absolute errors and still-wobble deviations per class for one case."""
    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    truth = json.loads((SAMPLES / case_id / "observations_gt.json").read_text())

    positions: dict[str, dict[float, NDArray[np.float64]]] = defaultdict(dict)
    by_frame: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in truth:
        positions[row["entity_id"]][row["timestamp_s"]] = np.array(row["world_xyz"][:2])
        by_frame[(row["camera_id"], row["frame_index"])].append(row)
    speed: dict[tuple[str, float], float] = {}
    for entity, trace in positions.items():
        times = sorted(trace)
        for a, b in itertools.pairwise(times):
            speed[(entity, b)] = float(np.linalg.norm(trace[b] - trace[a]) / (b - a))

    observations, _, _ = run_perception(case_id)
    placed = localise_all(observations, cameras, class_heights(scene))
    errors: dict[str, list[float]] = defaultdict(list)
    still: dict[tuple[str, str, str], list[NDArray[np.float64]]] = defaultdict(list)
    for o in observations:
        if o.observation_id not in placed:
            continue
        box = [o.bbox.x1, o.bbox.y1, o.bbox.x2, o.bbox.y2]
        candidates = by_frame[(o.camera_id, o.frame_index)]
        best = max(candidates, key=lambda r: iou(box, _box(r)), default=None)
        if best is None or best["entity_class"] != o.entity_class.value:
            continue
        if iou(box, _box(best)) < 0.5:
            continue
        offset = np.subtract(placed[o.observation_id], best["world_xyz"][:2])
        errors[o.entity_class.value].append(float(np.linalg.norm(offset)))
        if speed.get((str(best["entity_id"]), float(best["timestamp_s"])), 1.0) < STILL_MPS:
            still[(o.camera_id, str(best["entity_id"]), o.entity_class.value)].append(offset)

    wobble: dict[str, list[float]] = defaultdict(list)
    for (_, _, cls), offsets in still.items():
        if len(offsets) >= MIN_STILL_SAMPLES:
            stacked = np.array(offsets)
            wobble[cls].extend(
                np.linalg.norm(stacked - np.median(stacked, axis=0), axis=1).tolist()
            )
    return errors, wobble


def main() -> int:
    """Pool every requested case and log percentiles per class."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=TUNE)
    args = parser.parse_args()
    errors: dict[str, list[float]] = defaultdict(list)
    wobble: dict[str, list[float]] = defaultdict(list)
    for case_id in args.cases:
        case_errors, case_wobble = measure(case_id)
        for cls, values in case_errors.items():
            errors[cls].extend(values)
        for cls, values in case_wobble.items():
            wobble[cls].extend(values)
    for cls in sorted(errors):
        a = np.array(errors[cls])
        still = np.array(wobble.get(cls) or [np.nan])
        log.info(
            "%-9s abs error n=%d p50 %.2f p95 %.2f max %.2f | still wobble n=%d p95 %.2f max %.2f",
            cls,
            a.size,
            np.percentile(a, 50),
            np.percentile(a, 95),
            a.max(),
            0 if np.isnan(still).all() else still.size,
            np.nanpercentile(still, 95),
            np.nanmax(still),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
