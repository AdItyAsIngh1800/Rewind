"""Export the rendered cases as a YOLO-format dataset for fine-tuning.

Writes images and label files under ``data/yolo/`` plus the ``data.yaml`` that
Ultralytics reads. Labels come straight from the ground truth that the evaluation
harness scores against, so the detector is trained on exactly the definition of
"correct" it will later be measured by.

SPLIT INTEGRITY IS ASSERTED, NOT ASSUMED. The two golden cases are never opened until
E9.1 in Week 17. This script refuses to run if either appears in the train or val
split, and the check is on case ids rather than on anything a reader would have to
inspect by eye. One leaked golden frame would silently inflate every number reported
at Gate 7.

    uv run python scripts/ml/export_yolo_dataset.py
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import shutil
from collections import Counter
from typing import Any

from packages.schemas import EntityClass
from services.ingestion import decode_frames, probe
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

SAMPLES = pathlib.Path("data/samples")
OUT = pathlib.Path("data/yolo")
MANIFEST = pathlib.Path("data/manifests/v1.json")

#: Class index order. Fixed here and written into data.yaml, so a checkpoint's
#: numeric output can always be mapped back to an entity class.
CLASS_ORDER: list[EntityClass] = [
    EntityClass.PERSON,
    EntityClass.ROBOT,
    EntityClass.FORKLIFT,
    EntityClass.PALLET,
]

#: The split. Validation is the negative case on purpose: it contains every entity
#: class in motion but no incident, so a detector that only learned "the thing near
#: the intersection at 13 s" scores badly here rather than looking good on a case
#: it has effectively memorised.
TRAIN_CASES = ["case_01", "case_03", "case_04"]
VAL_CASES = ["case_05"]

#: Consecutive frames at 10 FPS are near-duplicates. Every fifth frame gives a
#: 2 FPS sample that covers the same motion with a fifth of the disk and training
#: time, and no loss of pose variety a box-shaped entity could offer anyway.
STRIDE = 5

#: JPEG at this quality is a fifth the size of PNG and indistinguishable to a
#: detector trained on it. Disk headroom is a live risk (R19).
JPEG_QUALITY = 88


class SplitLeakError(RuntimeError):
    """Raised when a golden case would enter a training or validation split."""


def golden_cases() -> set[str]:
    """Read which cases are golden from the dataset manifest.

    Read from the manifest rather than hardcoded here, so this script cannot drift
    from the split policy the manifest records.
    """
    manifest = json.loads(MANIFEST.read_text())
    return set(manifest["split_policy"]["golden"])


def assert_no_leak(train: list[str], val: list[str]) -> None:
    """Refuse to proceed if any golden case is in a split."""
    golden = golden_cases()
    leaked = (set(train) | set(val)) & golden
    if leaked:
        raise SplitLeakError(
            f"golden case(s) {sorted(leaked)} must not be used for training or "
            "validation before E9.1. Refusing to export."
        )
    overlap = set(train) & set(val)
    if overlap:
        raise SplitLeakError(f"case(s) {sorted(overlap)} appear in both train and val")


def to_yolo_line(row: dict[str, Any], width: int, height: int) -> str:
    """Convert one ground-truth observation to a YOLO label line.

    YOLO wants class, centre-x, centre-y, width, height, all normalised to [0, 1].
    """
    box = row["bbox"]
    x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
    cx = ((x1 + x2) / 2) / width
    cy = ((y1 + y2) / 2) / height
    w = (x2 - x1) / width
    h = (y2 - y1) / height
    class_index = CLASS_ORDER.index(EntityClass(row["entity_class"]))
    return f"{class_index} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def export_case(case_id: str, split: str, counts: Counter[str]) -> int:
    """Write every sampled frame and its labels for one case."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv is required; run `uv sync --all-extras`") from exc

    case_dir = SAMPLES / case_id
    truth = json.loads((case_dir / "observations_gt.json").read_text())
    by_frame: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in truth:
        by_frame.setdefault((row["camera_id"], row["frame_index"]), []).append(row)

    images_dir = OUT / "images" / split
    labels_dir = OUT / "labels" / split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for clip in sorted(case_dir.glob("*.mp4")):
        camera_id = clip.stem
        metadata = probe(clip)
        wanted = list(range(0, metadata.frame_count, STRIDE))

        for source_index, frame in decode_frames(clip, wanted):
            stem = f"{case_id}_{camera_id}_{source_index:04d}"
            cv2.imwrite(
                str(images_dir / f"{stem}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            rows = by_frame.get((camera_id, source_index), [])
            lines = [to_yolo_line(r, metadata.width, metadata.height) for r in rows]
            # An empty label file is written deliberately. A frame with nothing in it
            # is a negative example, and Ultralytics treats a missing file as "no
            # labels" only if told to; an explicit empty file is unambiguous.
            (labels_dir / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            for r in rows:
                counts[r["entity_class"]] += 1
            written += 1

    log.info("  %s -> %s: %d frames", case_id, split, written)
    return written


def write_data_yaml() -> pathlib.Path:
    """Write the dataset descriptor Ultralytics trains from."""
    path = OUT / "data.yaml"
    names = "\n".join(f"  {i}: {c.value}" for i, c in enumerate(CLASS_ORDER))
    path.write_text(
        f"# Generated by scripts/ml/export_yolo_dataset.py. Do not edit by hand.\n"
        f"path: {OUT.resolve()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"names:\n{names}\n"
    )
    return path


def main() -> int:
    """Export the dataset, refusing on any split leak."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="remove a previous export first")
    args = parser.parse_args()

    assert_no_leak(TRAIN_CASES, VAL_CASES)
    log.info("split verified: golden cases %s are excluded", sorted(golden_cases()))

    if args.clean and OUT.exists():
        shutil.rmtree(OUT)

    counts: Counter[str] = Counter()
    total = 0
    for case_id in TRAIN_CASES:
        total += export_case(case_id, "train", counts)
    for case_id in VAL_CASES:
        total += export_case(case_id, "val", counts)

    descriptor = write_data_yaml()
    size_mb = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1048576

    log.info("")
    log.info("exported %d frames (%.0f MB) to %s", total, size_mb, OUT)
    log.info("labels per class: %s", dict(counts))
    log.info("descriptor: %s", descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
