"""Clock alignment must be recoverable from what the cameras saw."""

from __future__ import annotations

import json
import pathlib

import pytest

from packages.common.camera import CameraModel
from packages.schemas import Observation
from services.events import class_heights, extract_events, load_zones
from services.identity import estimate_offsets, misaligned

SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
CAMERAS = {c["id"]: CameraModel.from_scene(SCENE, c["id"]) for c in SCENE["cameras"]}
CASE = pathlib.Path("data/samples/case_01/observations_gt.json")


def perfect_tracks(shift: dict[str, float]) -> list[Observation]:
    """Ground-truth tracks with a deliberate clock error injected per camera."""
    rows = json.loads(CASE.read_text())
    return [
        Observation.model_validate(
            {
                **r,
                "track_id": r["entity_id"],
                "timestamp_s": round(r["timestamp_s"] + shift.get(r["camera_id"], 0.0), 3),
            }
        )
        for r in rows
    ]


def events_for(shift: dict[str, float]) -> list:
    """Raw per-camera events for case_01 under the injected shift."""
    return extract_events(
        "r", perfect_tracks(shift), load_zones(SCENE), CAMERAS, class_heights(SCENE)
    )


@pytest.mark.skipif(not CASE.exists(), reason="needs case_01 ground truth")
def test_correct_offsets_show_no_residual() -> None:
    """With the configured offsets applied, every camera agrees with the reference."""
    estimates = estimate_offsets(events_for({}), reference="CAM_A")
    assert set(estimates) == {"CAM_B", "CAM_C"}
    for e in estimates.values():
        assert abs(e.residual_s) <= 0.2, e
        assert e.samples >= 3
    assert misaligned(estimates) == []


@pytest.mark.skipif(not CASE.exists(), reason="needs case_01 ground truth")
def test_an_injected_half_second_is_detected() -> None:
    """CAM_B's clock 0.5 s late must be found, and only CAM_B flagged."""
    estimates = estimate_offsets(events_for({"CAM_B": 0.5}), reference="CAM_A")
    assert estimates["CAM_B"].residual_s == pytest.approx(0.5, abs=0.15)
    assert abs(estimates["CAM_C"].residual_s) <= 0.2
    assert misaligned(estimates) == ["CAM_B"]


@pytest.mark.skipif(not CASE.exists(), reason="needs case_01 ground truth")
def test_sign_convention_is_late_positive() -> None:
    """A camera stamping early has a negative residual."""
    estimates = estimate_offsets(events_for({"CAM_C": -0.5}), reference="CAM_A")
    assert estimates["CAM_C"].residual_s == pytest.approx(-0.5, abs=0.15)
