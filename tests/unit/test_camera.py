"""The camera model must reproduce Blender's projection, not merely a plausible one."""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from packages.common.camera import CameraModel

SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
SAMPLES = pathlib.Path("data/samples")


def test_project_and_back_project_are_inverses() -> None:
    """A world point projected then back-projected at its own height returns."""
    cam = CameraModel.from_scene(SCENE, "CAM_A")
    for point in [(12.0, 8.0, 0.0), (18.0, 15.0, 0.875), (8.0, 4.0, 0.6)]:
        px, py = cam.project(point)
        x, y = cam.back_project(px, py, point[2])
        assert (x, y) == pytest.approx(point[:2], abs=1e-6)


def test_aim_point_lands_on_the_principal_point() -> None:
    """The camera looks at its configured aim, so the aim projects to the image centre."""
    spec = next(c for c in SCENE["cameras"] if c["id"] == "CAM_B")
    cam = CameraModel.from_scene(SCENE, "CAM_B")
    assert cam.project(tuple(spec["aim"])) == pytest.approx((cam.cx, cam.cy), abs=1e-6)


def test_rays_above_the_horizon_are_refused() -> None:
    """A pixel that never meets the floor has no world position to report."""
    cam = CameraModel.from_scene(SCENE, "CAM_A")
    with pytest.raises(ValueError, match="does not meet"):
        cam.back_project(cam.cx, 0.0, 0.0)


@pytest.mark.skipif(
    not (SAMPLES / "case_01" / "observations_gt.json").exists(), reason="needs case_01"
)
def test_matches_ray_cast_ground_truth() -> None:
    """Projected truth positions sit on truth boxes, horizontally to the pixel."""
    rows = json.loads((SAMPLES / "case_01" / "observations_gt.json").read_text())
    heights = {k: v["height"] for k, v in SCENE["entities"].items() if not k.startswith("_")}
    dx: list[float] = []
    world: list[float] = []
    for row in rows:
        if row["visibility"] < 0.95 or row["camera_id"] == "CAM_C":
            continue  # partially visible boxes and the steep overhead view are known biases
        cam = CameraModel.from_scene(SCENE, row["camera_id"])
        b = row["bbox"]
        cx, cy = (b["x1"] + b["x2"]) / 2, (b["y1"] + b["y2"]) / 2
        px, _ = cam.project(tuple(row["world_xyz"]))
        dx.append(abs(px - cx))
        x, y = cam.back_project(cx, cy, heights[row["entity_class"]] / 2)
        world.append(float(np.hypot(x - row["world_xyz"][0], y - row["world_xyz"][1])))
    assert np.percentile(dx, 95) < 2.0
    assert np.percentile(world, 95) < 0.1
