"""Score a detector against ground truth, per entity class.

E3.1 requires the COCO zero-shot number to be recorded before any fine-tuning, so
that the fine-tuned result has an honest floor to be compared against (ADR-0004).

Results are reported **per class**, never as a single figure. A COCO checkpoint has
no class for ``robot`` or ``pallet``, so an aggregate score would blend "the model
missed it" with "no such class exists" into one number that means neither.

    uv run python scripts/evaluation/baseline_detection.py --case case_01
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from packages.evaluation.metrics import Counts, match_detections
from packages.schemas import EntityClass
from services.ingestion import case_clips, decode_frames, plan_sampling, probe
from services.observability.logging import configure_logging
from services.perception import UNREACHABLE_ZERO_SHOT, Detector, DetectorConfig

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")
SCENE_CONFIG = pathlib.Path("ml/configs/scene_v1.json")
REPORTS = pathlib.Path("artifacts/benchmark-reports")

#: Frames per detector call. Small because the win from larger batches was measured
#: at well under the margin already available: the machine runs roughly ten times
#: faster than the dataset needs, so memory headroom is worth more than throughput.
BATCH = 8


@dataclass
class ClassResult:
    """Detection counts for one entity class."""

    entity_class: EntityClass
    counts: Counts
    predicted: int
    truth: int
    reachable: bool
    note: str = ""


@dataclass
class BaselineResult:
    """Everything one baseline evaluation produced."""

    case_id: str
    model_version: str
    device: str
    generated_at: datetime
    frames_processed: int
    per_class: list[ClassResult] = field(default_factory=list)


def load_offsets() -> dict[str, float]:
    """Read each camera's clock offset from the scene config."""
    scene = json.loads(SCENE_CONFIG.read_text())
    return {camera["id"]: float(camera["clock_offset_s"]) for camera in scene["cameras"]}


def observations_for_case(
    case_id: str, detector: Detector, run_id: str, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """Run the detector over every camera in a case.

    Returns the predicted observations as plain dicts, matching the shape the metrics
    take, plus how many frames were processed.
    """
    offsets = load_offsets()
    predicted: list[dict[str, Any]] = []
    processed = 0

    for clip in case_clips(SAMPLES / case_id):
        camera_id = clip.stem
        metadata = probe(clip)
        plan = plan_sampling(
            metadata,
            camera_id=camera_id,
            target_fps=metadata.fps,
            clock_offset_s=offsets.get(camera_id, 0.0),
        )
        if limit:
            plan = plan[:limit]

        by_index = {frame.source_index: frame for frame in plan}
        batch_frames: list[Any] = []
        batch_indices: list[int] = []

        def flush(
            frames: list[Any],
            indices: list[int],
            camera: str = camera_id,
            lookup: dict[int, Any] = by_index,
        ) -> None:
            """Detect over one batch and collect the observations.

            Loop variables are passed as arguments rather than captured. A closure
            over the loop would read whichever camera the loop had reached by the
            time it ran, silently attributing one camera's detections to another.
            """
            if not frames:
                return
            for observation in detector.detect(
                frames,
                run_id=run_id,
                camera_id=camera,
                frame_indices=indices,
                timestamps=[lookup[i].timestamp_s for i in indices],
            ):
                predicted.append(observation.model_dump(mode="json"))
            frames.clear()
            indices.clear()

        for source_index, frame in decode_frames(clip, [f.source_index for f in plan]):
            batch_frames.append(frame)
            batch_indices.append(source_index)
            processed += 1
            if len(batch_frames) >= BATCH:
                flush(batch_frames, batch_indices)
        flush(batch_frames, batch_indices)
        log.info("  %s: %d frames, %d detections so far", camera_id, len(plan), len(predicted))

    return predicted, processed


def score(
    predicted: list[dict[str, Any]], truth: list[dict[str, Any]], native: bool
) -> list[ClassResult]:
    """Score per entity class, marking classes the checkpoint cannot express."""
    results: list[ClassResult] = []
    for entity_class in EntityClass:
        pred = [p for p in predicted if p["entity_class"] == entity_class.value]
        real = [t for t in truth if t["entity_class"] == entity_class.value]
        reachable = native or entity_class not in UNREACHABLE_ZERO_SHOT
        note = "" if reachable else "no COCO class exists for this entity"
        if reachable and entity_class is EntityClass.FORKLIFT and not native:
            note = "reached only via the COCO `truck` class, a poor stand-in"
        results.append(
            ClassResult(
                entity_class=entity_class,
                counts=match_detections(pred, real),
                predicted=len(pred),
                truth=len(real),
                reachable=reachable,
                note=note,
            )
        )
    return results


def render_markdown(result: BaselineResult) -> str:
    """Render a baseline result as a markdown report."""
    lines = [
        f"# Detection baseline — {result.case_id}",
        "",
        f"- **Generated:** {result.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **Model:** `{result.model_version}`",
        f"- **Device:** `{result.device}`",
        f"- **Frames processed:** {result.frames_processed}",
        "",
        "| Class | Truth | Predicted | TP | FP | FN | Precision | Recall | Note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in result.per_class:
        counts = row.counts
        lines.append(
            f"| `{row.entity_class.value}` | {row.truth} | {row.predicted} | "
            f"{counts.tp} | {counts.fp} | {counts.fn} | "
            f"{counts.precision:.3f} | {counts.recall:.3f} | {row.note} |"
        )
    lines += [
        "",
        "## Reading this",
        "",
        "A recall of zero against a non-zero truth count means one of two very "
        "different things, and the note column says which: the model looked and "
        "failed, or the checkpoint has no class for that entity at all. Aggregating "
        "these into one figure would hide the distinction, which is the whole reason "
        "ADR-0004 records this baseline separately.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Run the baseline and write a report."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="case_01")
    parser.add_argument("--checkpoint", default="yolo11n.pt")
    parser.add_argument("--device", default="mps")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--native-classes", action="store_true")
    parser.add_argument("--frames", type=int, default=0, help="limit frames per camera")
    args = parser.parse_args()

    truth_path = SAMPLES / args.case / "observations_gt.json"
    if not truth_path.exists():
        log.error("no ground truth at %s", truth_path)
        return 1
    truth = json.loads(truth_path.read_text())

    config = DetectorConfig(
        checkpoint=args.checkpoint,
        confidence=args.confidence,
        device=args.device,
        native_classes=args.native_classes,
    )
    detector = Detector(config)
    run_id = f"baseline-{args.case}"

    log.info("scoring %s with %s", args.case, config.version)
    predicted, processed = observations_for_case(args.case, detector, run_id, args.frames)

    result = BaselineResult(
        case_id=args.case,
        model_version=config.version,
        device=args.device,
        generated_at=datetime.now(UTC),
        frames_processed=processed,
        per_class=score(predicted, truth, native=args.native_classes),
    )

    report = render_markdown(result)
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = result.generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    label = "finetuned" if args.native_classes else "baseline"
    path = REPORTS / f"detection-{label}-{args.case}-{stamp}.md"
    path.write_text(report)

    # A machine-readable twin of the report, so the model card and the experiment
    # record are generated from the same numbers rather than retyped from a table.
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "case_id": result.case_id,
                "model_version": result.model_version,
                "checkpoint": args.checkpoint,
                "device": result.device,
                "generated_at": result.generated_at.isoformat(),
                "frames_processed": result.frames_processed,
                "per_class": {
                    row.entity_class.value: {
                        "truth": row.truth,
                        "predicted": row.predicted,
                        "tp": row.counts.tp,
                        "fp": row.counts.fp,
                        "fn": row.counts.fn,
                        "precision": round(row.counts.precision, 4),
                        "recall": round(row.counts.recall, 4),
                        "f1": round(row.counts.f1, 4),
                        "reachable": row.reachable,
                        "note": row.note,
                    }
                    for row in result.per_class
                },
            },
            indent=2,
        )
        + "\n"
    )
    log.info("\n%s", report)
    log.info("written to %s and %s", path, path.with_suffix(".json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
