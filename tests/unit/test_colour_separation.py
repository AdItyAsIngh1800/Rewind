"""The colour linter must reject palettes a detector or a histogram could confuse."""

from __future__ import annotations

import copy
import json
import pathlib

from scripts.dataset.validate_cases import check_colour_separation

SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())


def test_shipped_palette_passes() -> None:
    """Assert the committed class and actor colours clear every constraint."""
    assert check_colour_separation(SCENE) == []


def test_actor_colour_too_close_to_its_class_is_rejected() -> None:
    """A second worker in the same green as the first has no appearance signal."""
    scene = copy.deepcopy(SCENE)
    scene["actor_colours"]["P02"] = scene["entities"]["person"]["colour"]
    problems = check_colour_separation(scene)
    assert any("P02" in p and "its class person" in p for p in problems)


def test_actor_colour_camouflaged_against_a_surface_is_rejected() -> None:
    """An actor painted floor-yellow is invisible on the floor paint."""
    scene = copy.deepcopy(SCENE)
    scene["actor_colours"]["F02"] = scene["surfaces"]["floor_paint"]
    problems = check_colour_separation(scene)
    assert any("F02" in p and "floor_paint" in p for p in problems)
