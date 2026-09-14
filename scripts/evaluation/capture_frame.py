"""Save one camera frame with ground-truth and detector boxes drawn on it.

The failure catalogue (E9.2) and the experiment records need a frame a reader can look
at beside a number: what the detector saw, what was there. Truth boxes are drawn in
green with the entity id and its visibility; detector boxes in red with class and
confidence. A box in green with no red partner is a miss; red with no green is a
false box.

    uv run python scripts/evaluation/capture_frame.py case_06 CAM_C 130 \
        --out docs/failures/F1-case_06-CAM_C-f130.jpg
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib

import cv2

from apps.worker.settings import worker_settings
from scripts.evaluation.events_on_truth import SAMPLES
from services.ingestion import decode_frames
from services.observability.logging import configure_logging
from services.perception import Detector, DetectorConfig

log = logging.getLogger(__name__)

GREEN = (0, 200, 0)
RED = (0, 0, 230)


def main() -> int:
    """Decode the frame, run the worker's detector on it, draw both, write the file."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    parser.add_argument("camera_id")
    parser.add_argument("frame_index", type=int)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--checkpoint", default=str(worker_settings.detector_checkpoint))
    args = parser.parse_args()

    clip = SAMPLES / args.case_id / f"{args.camera_id}.mp4"
    _, frame = next(iter(decode_frames(clip, [args.frame_index])))
    truth = json.loads((SAMPLES / args.case_id / "observations_gt.json").read_text())
    detector = Detector(DetectorConfig(checkpoint=args.checkpoint, native_classes=True))
    predicted = list(
        detector.detect(
            [frame],
            run_id="capture",
            camera_id=args.camera_id,
            frame_indices=[args.frame_index],
            timestamps=[0.0],
        )
    )

    for row in truth:
        if row["camera_id"] != args.camera_id or row["frame_index"] != args.frame_index:
            continue
        b = row["bbox"]
        x1, y1, x2, y2 = (int(b[k]) for k in ("x1", "y1", "x2", "y2"))
        cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 2)
        label = f"{row['entity_id']} vis {row['visibility']:.2f}"
        cv2.putText(frame, label, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 1)
    for o in predicted:
        x1, y1, x2, y2 = int(o.bbox.x1), int(o.bbox.y1), int(o.bbox.x2), int(o.bbox.y2)
        cv2.rectangle(frame, (x1, y1), (x2, y2), RED, 2)
        label = f"{o.entity_class.value} {o.confidence:.2f}"
        cv2.putText(
            frame,
            label,
            (x1, min(y2 + 16, frame.shape[0] - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            RED,
            1,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    log.info(
        "%s: %d truth boxes, %d detections -> %s",
        clip.name,
        sum(
            1
            for r in truth
            if r["camera_id"] == args.camera_id and r["frame_index"] == args.frame_index
        ),
        len(predicted),
        args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
