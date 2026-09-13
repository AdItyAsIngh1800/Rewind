"""The alignment guard must accept shaded entities and still reject empty boxes."""

from __future__ import annotations

import numpy as np
import pytest

# The guard reads video through OpenCV, which ships with the `ml` extra CI does not
# install; the guard itself only ever runs on a machine that rendered the clips.
pytest.importorskip("cv2")

from scripts.dataset import verify_alignment as va

FORKLIFT = [0.8, 0.05, 0.02]  # linear RGB, hue ~13 deg
ROBOT = [0.95, 0.9, 0.9]  # near-white, no usable hue


def _solid(bgr: tuple[int, int, int]) -> np.ndarray:
    """Build a 4x4 crop of one colour, as OpenCV would decode it."""
    return np.full((4, 4, 3), bgr, dtype=np.uint8)


def test_shaded_forklift_matches_by_hue() -> None:
    """Washed-out top face and near-black flank both read as forklift."""
    bgr, hs = va.srgb8(FORKLIFT), va.hue_sat(FORKLIFT)
    assert va.matches(_solid((140, 140, 240)), bgr, hs).all()  # pink highlight
    assert va.matches(_solid((10, 15, 110)), bgr, hs).all()  # deep shadow


def test_background_never_matches() -> None:
    """Concrete, wall, racking and floor paint all fail against a forklift box."""
    bgr, hs = va.srgb8(FORKLIFT), va.hue_sat(FORKLIFT)
    for surface in ((130, 130, 130), (177, 172, 170), (220, 150, 90), (60, 225, 245)):
        assert not va.matches(_solid(surface), bgr, hs).any(), surface


def test_achromatic_entity_keeps_rgb_path_only() -> None:
    """A near-white robot has no hue; a saturated pixel of any hue must not pass."""
    bgr, hs = va.srgb8(ROBOT), va.hue_sat(ROBOT)
    assert va.matches(_solid((200, 200, 200)), bgr, hs).all()  # shaded white
    assert not va.matches(_solid((0, 0, 255)), bgr, hs).any()  # pure red


def test_occluded_box_needs_only_half_its_visible_fraction() -> None:
    """An actor at visibility 0.18 behind another passes at 17%, not the full 35%."""
    required = va.required_fraction((480, 239, 506, 323), 0.18, 1280, 720)
    assert required is not None
    assert 0.08 < required < 0.17
    assert va.required_fraction((480, 239, 506, 323), 1.0, 1280, 720) == va.MIN_MATCH_FRACTION


def test_box_cut_by_frame_edge_is_not_judged() -> None:
    """A box touching the frame border is skipped rather than failed."""
    assert va.required_fraction((1040, 686, 1145, 720), 0.55, 1280, 720) is None
    assert va.required_fraction((0, 100, 40, 200), 0.9, 1280, 720) is None
