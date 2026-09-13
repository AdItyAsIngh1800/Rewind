"""Score cross-camera association: false-link rate first, recall second (E5.4).

Two runs per case. **Perfect tracks** use ground-truth boxes with the true entity as
track id and no appearance descriptors, isolating the time-and-geometry logic.
**Real pipeline** runs detector, tracker and descriptors as a worker would. Truth for
a real segment is the entity its boxes overlap most (IoU ≥ 0.5), as in EXP-0004.

The primary metric is the **false-link rate**: of the pairs the system chose to link,
how many joined two different entities. The charter treats one of those as worse
than a missed link, because it manufactures a trajectory. Recall is over the true
same-entity pairs that were *comparable*: both segments localised and within the
hand-over window. Refusals (UNKNOWN) are reported, never counted as errors.

    uv run python scripts/evaluation/identity_on_detections.py
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from collections import Counter
from datetime import UTC, datetime

import numpy as np
from numpy.typing import NDArray

from packages.common.camera import CameraModel
from packages.schemas import LinkDecision, Observation, TrackSegment
from scripts.evaluation.events_on_detections import run_perception
from scripts.evaluation.events_on_truth import SAMPLES, SCENE, perfect_tracks
from scripts.evaluation.tracking_on_detections import assign_identities
from services.events import class_heights, localise_all
from services.identity import AssociationConfig, associate, build_segment_tracks
from services.observability.logging import configure_logging
from services.tracking import segments_from_observations

log = logging.getLogger(__name__)
REPORTS = pathlib.Path("artifacts/benchmark-reports")


def score_links(
    case_id: str,
    observations: list[Observation],
    segments: list[TrackSegment],
    descriptors: dict[str, NDArray[np.float64]],
    truth_of_segment: dict[str, str],
    label: str,
    cfg: AssociationConfig,
) -> dict[str, object]:
    """Associate and score one case."""
    scene = json.loads(SCENE.read_text())
    cameras = {c["id"]: CameraModel.from_scene(scene, c["id"]) for c in scene["cameras"]}
    speeds = {
        k: float(v["max_speed_mps"]) for k, v in scene["entities"].items() if not k.startswith("_")
    }
    tracks = build_segment_tracks(
        segments,
        observations,
        localise_all(observations, cameras, class_heights(scene)),
        descriptors,
    )
    links = associate("eval", tracks, speeds, cfg)

    linked = [link for link in links if link.decision is LinkDecision.LINKED]
    false_links = [
        link
        for link in linked
        if truth_of_segment.get(link.segment_a) != truth_of_segment.get(link.segment_b)
    ]
    # True same-entity cross-camera pairs among the comparable segments.
    seg_by_id = {t.segment.segment_id: t.segment for t in tracks}
    true_pairs = {
        (a, b)
        for a in seg_by_id
        for b in seg_by_id
        if a < b
        and seg_by_id[a].camera_id != seg_by_id[b].camera_id
        and truth_of_segment.get(a) is not None
        and truth_of_segment.get(a) == truth_of_segment.get(b)
    }
    found = {tuple(sorted((link.segment_a, link.segment_b))) for link in linked}
    recalled = sum(1 for p in true_pairs if p in found)
    return {
        "case_id": case_id,
        "mode": label,
        "compared": len(links),
        "linked": len(linked),
        "unknown": len(links) - len(linked),
        "false_links": len(false_links),
        "false_link_rate": len(false_links) / len(linked) if linked else 0.0,
        "true_pairs": len(true_pairs),
        "recall": recalled / len(true_pairs) if true_pairs else None,
        "segments": len(tracks),
    }


def main() -> int:
    """Score the tune cases on perfect tracks and on the real pipeline."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", default=["case_01", "case_03", "case_04", "case_05"])
    args = parser.parse_args()
    cfg = AssociationConfig()
    log.info("config: %s", cfg.version)
    results = []
    for case_id in args.cases:
        perfect = perfect_tracks(SAMPLES / case_id, projected=False)
        segs = segments_from_observations("eval", perfect)
        truth = {s.segment_id: s.local_track_id.split("-", 1)[1] for s in segs}
        results.append(score_links(case_id, perfect, segs, {}, truth, "perfect", cfg))
        log_result(results[-1])

        observations, segments, descriptors = run_perception(case_id)
        truth_rows = [
            Observation.model_validate(r)
            for r in json.loads((SAMPLES / case_id / "observations_gt.json").read_text())
        ]
        relabelled: list[Observation] = []
        for camera_id in sorted({o.camera_id for o in observations}):
            rel, _ = assign_identities(
                [o for o in observations if o.camera_id == camera_id],
                [t for t in truth_rows if t.camera_id == camera_id],
            )
            relabelled.extend(rel)
        votes: dict[str, Counter[str]] = {}
        for o in relabelled:
            if o.track_id and o.entity_id:
                votes.setdefault(f"SEG-eval-{o.track_id}", Counter())[o.entity_id] += 1
        truth_real = {seg_id: c.most_common(1)[0][0] for seg_id, c in votes.items()}
        results.append(
            score_links(case_id, observations, segments, descriptors, truth_real, "detections", cfg)
        )
        log_result(results[-1])
        # Same perception output with descriptors withheld: the spec §D4 baseline the
        # colour histogram has to beat to earn its weight in the score.
        results.append(
            score_links(case_id, observations, segments, {}, truth_real, "no-appear", cfg)
        )
        log_result(results[-1])
    out = REPORTS / f"identity-{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}.json"
    out.write_text(json.dumps({"config": cfg.version, "results": results}, indent=2))
    log.info("written to %s", out)
    return 0


def log_result(r: dict[str, object]) -> None:
    """One line per case and mode."""
    log.info(
        "%-10s %s  segments %2d  compared %2d  linked %2d  unknown %2d  "
        "false links %d (rate %.2f)  true pairs %d  recall %s",
        r["mode"],
        r["case_id"],
        r["segments"],
        r["compared"],
        r["linked"],
        r["unknown"],
        r["false_links"],
        r["false_link_rate"],
        r["true_pairs"],
        "n/a" if r["recall"] is None else f"{r['recall']:.2f}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
