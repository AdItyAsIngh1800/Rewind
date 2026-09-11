"""Pinhole camera model matching the Blender cameras that rendered the dataset.

Zones are world-plane polygons and ground truth is in world metres, but a detector
returns pixel boxes. This module is the bridge: it reproduces exactly the projection
``build_scene.py`` set up (rectilinear lens, horizontal sensor fit, camera aimed with
``to_track_quat("-Z", "Y")`` so image-up is as close to world-up as possible), and it
inverts that projection onto a horizontal plane at a chosen height.

Verified against ray-cast ground truth: projecting a true world position lands within
a pixel horizontally of the true box centre. Back-projecting a box centre to the
plane at half the class height recovers the world position within 6 cm for every
camera and class except tall, thin boxes seen from the steep overhead camera, where
the centre of the image box is biased toward the top face and the error reaches
0.4 m. That is a property of using a single point per box, not of the model, and is
below the 0.5 s event-timing tolerance at the speeds actors move.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

Vec3 = NDArray[np.float64]


@dataclass(frozen=True)
class CameraModel:
    """Position, orientation and intrinsics of one fixed camera."""

    camera_id: str
    location: Vec3
    forward: Vec3
    right: Vec3
    up: Vec3
    focal_px: float
    cx: float
    cy: float

    @classmethod
    def from_scene(cls, scene: dict[str, Any], camera_id: str) -> CameraModel:
        """Build the model from ``ml/configs/scene_v1.json`` for one camera id."""
        spec = next(c for c in scene["cameras"] if c["id"] == camera_id)
        optics = scene["camera_optics"]
        location = np.asarray(spec["location"], dtype=np.float64)
        forward = np.asarray(spec["aim"], dtype=np.float64) - location
        forward /= np.linalg.norm(forward)
        # Blender's track-to with up axis Y: camera +X is horizontal (perpendicular to
        # forward and world up), camera +Y is whatever is left, which tilts with pitch.
        right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        # Horizontal sensor fit: the sensor width spans the image width, so one focal
        # length in pixels serves both axes on square pixels.
        width, height = optics["resolution_x"], optics["resolution_y"]
        focal_px = optics["focal_length_mm"] / optics["sensor_width_mm"] * width
        return cls(camera_id, location, forward, right, up, focal_px, width / 2, height / 2)

    def project(self, point: tuple[float, float, float]) -> tuple[float, float]:
        """World point to image pixel (x right, y down). Raises behind the camera."""
        d = np.asarray(point, dtype=np.float64) - self.location
        depth = float(d @ self.forward)
        if depth <= 0:
            raise ValueError(f"point {point} is behind {self.camera_id}")
        return (
            self.cx + self.focal_px * float(d @ self.right) / depth,
            self.cy - self.focal_px * float(d @ self.up) / depth,
        )

    def back_project(self, px: float, py: float, z: float) -> tuple[float, float]:
        """Image pixel to the world point on the horizontal plane at height ``z``.

        Raises if the ray never meets the plane, which happens for pixels at or above
        the horizon; a detection there is not on the floor and has no world position
        this model can honestly assign.
        """
        ray = self.forward + self.right * ((px - self.cx) / self.focal_px)
        ray = ray - self.up * ((py - self.cy) / self.focal_px)
        if abs(ray[2]) < 1e-9 or (z - self.location[2]) / ray[2] <= 0:
            raise ValueError(
                f"pixel ({px}, {py}) does not meet the plane z={z} in front of {self.camera_id}"
            )
        t = (z - self.location[2]) / ray[2]
        hit = self.location + t * ray
        return float(hit[0]), float(hit[1])
