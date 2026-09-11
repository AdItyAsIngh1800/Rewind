"""The worker must recognise the fine-tuned checkpoint by its directory, not its filename."""

from __future__ import annotations

import pathlib

from apps.worker.settings import WorkerSettings


def test_fine_tuned_checkpoint_is_native(tmp_path: pathlib.Path) -> None:
    """Ultralytics names every checkpoint ``best.pt``; the run name is the parent dir."""
    weights = tmp_path / "yolo11n-rewind-v1" / "best.pt"
    weights.parent.mkdir()
    weights.touch()
    assert WorkerSettings(detector_checkpoint=weights).detector_native_classes


def test_coco_checkpoint_is_not_native(tmp_path: pathlib.Path) -> None:
    """A bare COCO checkpoint goes through the class map; a missing one too."""
    coco = tmp_path / "yolo11n.pt"
    coco.touch()
    assert not WorkerSettings(detector_checkpoint=coco).detector_native_classes
    assert not WorkerSettings(detector_checkpoint=tmp_path / "missing.pt").detector_native_classes
