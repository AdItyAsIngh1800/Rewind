"""Appearance descriptors for track segments: the cheap baseline (E5.2).

Spec §D4: every learned method is compared against a simpler baseline, and the
baseline is measured first. This is that baseline. A descriptor is a hue-saturation
histogram of the middle of the box, averaged over the frames a track was seen in.
Hue and saturation are kept, value is dropped, because lighting changes brightness
between cameras far more than it changes hue, and the centre crop is used because the
edges of a box are mostly floor.

Nothing here knows about cameras or geometry. Whether two descriptors are "the same
entity" is E5.3's decision, made together with time and position; this module only
says how alike they look, in [0, 1].
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from numpy.typing import NDArray

from packages.schemas import BBox
from services.ingestion import Frame

Descriptor = NDArray[np.float64]

HUE_BINS = 12
SAT_BINS = 4
#: Fraction of the box kept on each axis, centred. Half the width and half the
#: height keeps a quarter of the area, which on an upright box primitive is entirely
#: entity and on a real person is mostly torso.
CENTRE_FRACTION = 0.5
#: Boxes smaller than this on either side carry too few pixels to histogram.
MIN_SIDE_PX = 8


def describe_crop(frame: Frame, bbox: BBox) -> Descriptor | None:
    """Hue-saturation histogram of the centre of one box, L1-normalised.

    Returns None for boxes too small to describe, rather than a histogram of noise.
    """
    w, h = bbox.x2 - bbox.x1, bbox.y2 - bbox.y1
    if w < MIN_SIDE_PX or h < MIN_SIDE_PX:
        return None
    inset_x, inset_y = w * (1 - CENTRE_FRACTION) / 2, h * (1 - CENTRE_FRACTION) / 2
    x1, x2 = round(bbox.x1 + inset_x), round(bbox.x2 - inset_x)
    y1, y2 = round(bbox.y1 + inset_y), round(bbox.y2 - inset_y)
    crop = frame[max(0, y1) : y2, max(0, x1) : x2]
    if crop.size == 0:
        return None
    # OpenCV ships with the `ml` extra; importing it here keeps the API process,
    # which imports the pipeline for its result types, free of it.
    import cv2

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [HUE_BINS, SAT_BINS], [0, 180, 0, 256])
    flat = hist.astype(np.float64).ravel()
    total = flat.sum()
    return flat / total if total > 0 else None


class TrackDescriptors:
    """Running mean descriptor per local track id, fed one frame at a time."""

    def __init__(self) -> None:
        """Start with no tracks seen."""
        self._sum: dict[str, Descriptor] = defaultdict(lambda: np.zeros(HUE_BINS * SAT_BINS))
        self._count: dict[str, int] = defaultdict(int)

    def add(self, frame: Frame, track_id: str, bbox: BBox) -> None:
        """Fold one box of one track into its running mean."""
        d = describe_crop(frame, bbox)
        if d is not None:
            self._sum[track_id] += d
            self._count[track_id] += 1

    def result(self) -> dict[str, Descriptor]:
        """Mean descriptor per track, for tracks that had at least one usable box."""
        return {t: self._sum[t] / self._count[t] for t in self._sum if self._count[t]}


def similarity(a: Descriptor, b: Descriptor) -> float:
    """Histogram intersection of two L1-normalised descriptors, in [0, 1]."""
    return float(np.minimum(a, b).sum())
