"""Object detection over sampled frames.

Wraps a YOLO checkpoint and emits :class:`Observation` records. Knows nothing about
tracking, zones or incidents: its only job is turning pixels into boxes with classes.

THE CLASS MAPPING IS THE INTERESTING PART. A COCO-pretrained checkpoint has 80
classes, and only one of the project's four entity classes is among them. ``robot``
and ``pallet`` do not exist in COCO at all, and ``forklift`` is reachable only through
``truck``, which is a poor stand-in for a warehouse forklift. That gap is why
ADR-0004 permits fine-tuning, and why the zero-shot number is recorded first: without
it, a fine-tuned score has nothing honest to be compared against.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from packages.schemas import SCHEMA_VERSION, BBox, EntityClass, Observation

log = logging.getLogger(__name__)


class DetectorError(RuntimeError):
    """Raised when a checkpoint cannot be loaded or run."""


#: How COCO class names map onto the project's four entity classes.
#:
#: ``truck`` to ``forklift`` is a deliberate, documented stretch. A warehouse forklift
#: is not a truck, and treating it as one will produce poor recall and some confusion
#: with other vehicles. It is included so the baseline reports a real number for
#: forklift rather than a structural zero, which would understate what a pretrained
#: model can do and overstate what fine-tuning added.
COCO_TO_ENTITY: dict[str, EntityClass] = {
    "person": EntityClass.PERSON,
    "truck": EntityClass.FORKLIFT,
}

#: Entity classes COCO cannot express at all. Reported explicitly so a reader of the
#: baseline sees "no class exists" rather than inferring "the model failed".
UNREACHABLE_ZERO_SHOT: frozenset[EntityClass] = frozenset({EntityClass.ROBOT, EntityClass.PALLET})


@dataclass(frozen=True)
class DetectorConfig:
    """Everything that affects a detector's output, recorded on the run.

    Held together in one object so a processing run can store it verbatim. A
    benchmark that cannot say which confidence threshold produced it is not
    reproducible.
    """

    checkpoint: str = "yolo11n.pt"
    confidence: float = 0.25
    #: NMS IoU. Ultralytics' default of 0.7 let a partially occluded person produce
    #: two surviving boxes, one for the visible part and one for the full extent, at
    #: IoU ~0.65 between them; the duplicate seeded phantom tracks (EXP-0004). 0.5
    #: removes those while leaving two people who genuinely overlap less than half.
    iou: float = 0.5
    #: Boxes cut by the frame edge whose shorter side is under this many pixels are
    #: dropped. An actor rising into view from the bottom edge is detected as a 4 px,
    #: then 13 px sliver; each grew too fast between frames for ByteTrack to match, so
    #: each opened a new track and `case_03 CAM_B` scored 4 id switches (EXP-0004,
    #: re-run). Such a box cannot be localised either, since its centre is not the
    #: entity's. Edge-only because interior people at range measure 13.8 px wide.
    edge_min_side_px: float = 16.0
    #: A box with this share of its area inside a larger box of the same class is a
    #: second box on one object, and dropped. NMS misses it: the small box's IoU with
    #: the large one is low. In case_02 a half-visible forklift at the frame edge got a
    #: second box on its dark front face, which became a track of its own and was
    #: linked to the real forklift on two other cameras (EXP-0010, F4). Two objects of
    #: one class never nest in the image, so no case has to choose the value.
    nested_min_share: float = 0.9
    device: str = "mps"
    #: Fine-tuned checkpoints predict the project's classes directly, so the COCO
    #: name mapping is bypassed. Set by the training run, not guessed at inference.
    native_classes: bool = False

    @property
    def version(self) -> str:
        """Identifier recorded in ``ProcessingRun.model_versions``."""
        suffix = "native" if self.native_classes else "coco"
        return (
            f"{self.checkpoint}:{suffix}:conf{self.confidence}:iou{self.iou}"
            f":edge{self.edge_min_side_px:g}:nest{self.nested_min_share:g}"
        )


def cut_by_edge(
    box: tuple[float, float, float, float], width: int, height: int, min_side: float
) -> bool:
    """Whether a box touches the frame border and is too thin to track or localise."""
    x1, y1, x2, y2 = box
    touches = x1 <= 1.0 or y1 <= 1.0 or x2 >= width - 1.0 or y2 >= height - 1.0
    return touches and min(x2 - x1, y2 - y1) < min_side


Box = tuple[float, float, float, float]


def nested_in_larger(box: Box, others: list[Box], min_share: float) -> bool:
    """Whether ``box`` has at least ``min_share`` of its area inside a larger box in ``others``."""
    x1, y1, x2, y2 = box
    area = (x2 - x1) * (y2 - y1)
    for ox1, oy1, ox2, oy2 in others:
        if (ox2 - ox1) * (oy2 - oy1) <= area:
            continue
        inter = max(0.0, min(x2, ox2) - max(x1, ox1)) * max(0.0, min(y2, oy2) - max(y1, oy1))
        if inter / area >= min_share:
            return True
    return False


class Detector:
    """A loaded YOLO checkpoint, ready to run over frames."""

    def __init__(self, config: DetectorConfig | None = None) -> None:
        """Load the checkpoint described by ``config``.

        Args:
            config: Detector settings. Defaults to the compact COCO baseline.

        Raises:
            DetectorError: if ultralytics is unavailable or the checkpoint fails to load.

        """
        self.config = config or DetectorConfig()
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorError("ultralytics is not installed; run `uv sync --all-extras`") from exc
        try:
            self._model = YOLO(self.config.checkpoint)
        except Exception as exc:
            raise DetectorError(f"could not load {self.config.checkpoint}: {exc}") from exc
        log.info("loaded %s on %s", self.config.checkpoint, self.config.device)

    @property
    def class_names(self) -> dict[int, str]:
        """The checkpoint's own class index to name mapping."""
        names: dict[int, str] = self._model.names
        return names

    def _to_entity_class(self, label: str) -> EntityClass | None:
        """Map a predicted label onto an entity class, or ``None`` to discard it.

        Returning ``None`` rather than raising matters: a COCO model detects chairs
        and handbags in a warehouse, and those are correct predictions of things the
        project simply does not track. Treating them as errors would make precision
        meaningless.
        """
        if self.config.native_classes:
            try:
                return EntityClass(label)
            except ValueError:
                return None
        return COCO_TO_ENTITY.get(label)

    def detect(
        self,
        frames: list[Any],
        *,
        run_id: str,
        camera_id: str,
        frame_indices: list[int],
        timestamps: list[float],
    ) -> Iterator[Observation]:
        """Run detection over a batch of frames and yield observations.

        Args:
            frames: Decoded frames as numpy arrays, in BGR order as OpenCV returns them.
            run_id: Processing run these observations belong to.
            camera_id: Which camera produced the frames.
            frame_indices: Source frame index for each frame, for traceability.
            timestamps: Shared-timebase timestamp for each frame.

        Yields:
            One observation per accepted detection.

        Raises:
            DetectorError: if the frame, index and timestamp lists disagree in length.

        """
        if not (len(frames) == len(frame_indices) == len(timestamps)):
            raise DetectorError(
                "frames, frame_indices and timestamps must be the same length; "
                f"got {len(frames)}, {len(frame_indices)}, {len(timestamps)}"
            )

        results = self._model.predict(
            frames,
            conf=self.config.confidence,
            iou=self.config.iou,
            device=self.config.device,
            verbose=False,
        )

        for position, result in enumerate(results):
            source_index = frame_indices[position]
            timestamp = timestamps[position]
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue

            kept: list[tuple[int, EntityClass, Box, float]] = []
            for detection_index, box in enumerate(boxes):
                label = self.class_names[int(box.cls.item())]
                entity_class = self._to_entity_class(label)
                if entity_class is None:
                    continue

                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                # A checkpoint can emit a zero-area box at the frame edge. The BBox
                # contract rejects those, so they are dropped here rather than
                # crashing a 450-frame run on one degenerate prediction.
                if x2 - x1 < 1.0 or y2 - y1 < 1.0:
                    continue
                height, width = frames[position].shape[:2]
                if cut_by_edge((x1, y1, x2, y2), width, height, self.config.edge_min_side_px):
                    continue
                kept.append(
                    (detection_index, entity_class, (x1, y1, x2, y2), float(box.conf.item()))
                )

            for detection_index, entity_class, (x1, y1, x2, y2), confidence in kept:
                same_class = [b for _, c, b, _ in kept if c is entity_class]
                if nested_in_larger((x1, y1, x2, y2), same_class, self.config.nested_min_share):
                    continue
                yield Observation(
                    schema_version=SCHEMA_VERSION,
                    observation_id=f"{run_id}-{camera_id}-{source_index:05d}-{detection_index:02d}",
                    run_id=run_id,
                    camera_id=camera_id,
                    frame_index=source_index,
                    timestamp_s=timestamp,
                    entity_class=entity_class,
                    bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    confidence=confidence,
                )
