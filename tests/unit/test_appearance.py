"""Appearance descriptors must separate colours and ignore brightness."""

from __future__ import annotations

import numpy as np
import pytest

from packages.schemas import BBox
from services.identity.appearance import TrackDescriptors, describe_crop, similarity


def solid(bgr: tuple[int, int, int], size: int = 64) -> np.ndarray:
    """Build a frame that is one colour everywhere."""
    return np.full((size, size, 3), bgr, dtype=np.uint8)


BOX = BBox(x1=8, y1=8, x2=56, y2=56)

pytest.importorskip("cv2")


def test_same_colour_is_identical_and_different_hue_is_not() -> None:
    """Two green crops match fully; green against orange barely at all."""
    green = describe_crop(solid((20, 200, 30)), BOX)
    green2 = describe_crop(solid((25, 190, 35)), BOX)
    orange = describe_crop(solid((10, 120, 250)), BOX)
    assert green is not None and green2 is not None and orange is not None
    assert similarity(green, green2) == 1.0
    assert similarity(green, orange) < 0.05


def test_brightness_does_not_change_the_descriptor_much() -> None:
    """The same hue under a shadow is still the same hue."""
    lit = describe_crop(solid((20, 200, 30)), BOX)
    shaded = describe_crop(solid((8, 90, 12)), BOX)
    assert lit is not None and shaded is not None
    assert similarity(lit, shaded) == 1.0


def test_tiny_boxes_are_not_described() -> None:
    """A 4-pixel box is noise, not appearance."""
    assert describe_crop(solid((0, 0, 255)), BBox(x1=0, y1=0, x2=4, y2=4)) is None


def test_track_descriptor_is_the_mean_over_frames() -> None:
    """Half green frames and half orange frames average to a half-and-half histogram."""
    tracks = TrackDescriptors()
    for _ in range(3):
        tracks.add(solid((20, 200, 30)), "T1", BOX)
        tracks.add(solid((10, 120, 250)), "T1", BOX)
    tracks.add(solid((20, 200, 30)), "T2", BOX)
    result = tracks.result()
    green = describe_crop(solid((20, 200, 30)), BOX)
    assert green is not None
    assert similarity(result["T1"], green) == 0.5
    assert similarity(result["T2"], green) == 1.0
