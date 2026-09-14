"""Fine-tune the detector on the exported dataset.

Starts from COCO-pretrained ``yolo11n`` weights and adapts the head to the four
entity classes. This is fine-tuning, not training from scratch: pretrained
initialisation, a few thousand frames, minutes of compute (ADR-0004).

Every setting that affects the result is recorded alongside the weights, so the
checkpoint can be tied back to what produced it. A model whose training config is
lost is a model whose numbers cannot be reproduced.

    uv run python scripts/ml/train_detector.py --epochs 20
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import platform
import shutil
import time
from datetime import UTC, datetime
from typing import Any

from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

DATA = pathlib.Path("data/yolo/data.yaml")
MODELS = pathlib.Path("ml/models")
RUNS = pathlib.Path("artifacts/training-runs")


def train(args: argparse.Namespace) -> dict[str, Any]:
    """Run one fine-tuning job and return its recorded settings and results."""
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is not installed; run `uv sync --all-extras`") from exc

    if not DATA.exists():
        raise RuntimeError(f"no dataset at {DATA}; run scripts/ml/export_yolo_dataset.py first")

    started = time.time()
    model = YOLO(args.base)
    results = model.train(
        data=str(DATA),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(RUNS.resolve()),
        name=args.name,
        exist_ok=True,
        # Reproducibility over speed: a fixed seed and deterministic ops mean two
        # runs with the same config give the same weights, which is what lets an
        # experiment record claim a number rather than a range.
        seed=args.seed,
        deterministic=True,
        # Augmentation is a training-time transform on frames, and does not conflict
        # with the scene spec's constant-lighting rule, which fixes the *rendered*
        # scene so detection failures stay attributable.
        #
        # Hue jitter is the fraction of the hue wheel a frame may be shifted by. At the
        # Ultralytics default of 0.015 the detector learned *forklift* as F01's colour
        # and never detected the navy F02 (EXP-0010, F1); at 0.5 every hue occurs in
        # training, so class has to come from shape.
        hsv_h=args.hsv_h,
        hsv_s=0.5,
        hsv_v=0.4,
        fliplr=0.5,
        mosaic=1.0,
        verbose=False,
    )
    elapsed = time.time() - started

    # Ultralytics resolves the run directory itself and prepends `runs/detect/` to a
    # relative project path. Reading the resolved path back rather than reconstructing
    # it is the only way to be certain where the weights actually went.
    save_dir = getattr(results, "save_dir", None) or getattr(model.trainer, "save_dir", None)
    if save_dir is None:
        raise RuntimeError("training finished but ultralytics reported no save_dir")
    run_dir = pathlib.Path(str(save_dir))
    best = run_dir / "weights" / "best.pt"
    if not best.exists():
        raise RuntimeError(f"training finished but no weights at {best}")

    # Promote the checkpoint to a stable, named location. Ultralytics writes into
    # its run directory, which is a build artefact; ml/models/ is where the pipeline
    # looks for a checkpoint by version.
    target_dir = MODELS / args.name
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, target_dir / "best.pt")

    metrics: dict[str, float] = {}
    box = getattr(results, "box", None)
    if box is not None:
        for key in ("map50", "map", "mp", "mr"):
            value = getattr(box, key, None)
            if value is not None:
                metrics[key] = float(value)

    record: dict[str, Any] = {
        "name": args.name,
        "base_checkpoint": args.base,
        "trained_at": datetime.now(UTC).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "seed": args.seed,
        "hsv_h": args.hsv_h,
        "device": args.device,
        "platform": f"{platform.system()} {platform.machine()}",
        "dataset": str(DATA),
        "validation_metrics": metrics,
        "weights": str(target_dir / "best.pt"),
    }
    (target_dir / "training.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> int:
    """Fine-tune the detector and record the run."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="yolo11n.pt")
    parser.add_argument("--name", default="yolo11n-rewind-v1")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--hsv-h",
        type=float,
        default=0.015,
        help="hue jitter as a fraction of the hue wheel; v1 used the 0.015 default",
    )
    args = parser.parse_args()

    log.info(
        "fine-tuning %s -> %s for %d epochs on %s", args.base, args.name, args.epochs, args.device
    )
    record = train(args)

    log.info("")
    log.info("done in %.0fs", record["elapsed_s"])
    for key, value in record["validation_metrics"].items():
        log.info("  %-6s %.3f", key, value)
    log.info("weights: %s", record["weights"])
    log.info("record:  %s", pathlib.Path(record["weights"]).parent / "training.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
