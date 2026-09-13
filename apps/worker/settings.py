"""Worker configuration: which detector to run and where the queue lives."""

from __future__ import annotations

import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Runtime settings for the perception worker, read from the environment.

    The checkpoint path is the important one. A run records the detector version it
    used, so changing this changes the run identity, which is exactly right: a
    different model is a different experiment.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="REWIND_", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    detector_checkpoint: pathlib.Path = pathlib.Path("ml/models/yolo11n-rewind-v1/best.pt")
    detector_confidence: float = 0.25
    detector_device: str = "mps"
    samples_dir: pathlib.Path = pathlib.Path("data/samples")
    scene_config: pathlib.Path = pathlib.Path("ml/configs/scene_v1.json")
    #: Case scripts; the worker reads only the robot state channel from them, as the
    #: stand-in for live robot telemetry (`services/incidents/telemetry.py`).
    cases_config: pathlib.Path = pathlib.Path("ml/configs/cases_v1.json")
    #: How often the worker writes its ARQ heartbeat. ARQ's default is an hour, which
    #: would let the System Health screen call a dead worker alive for most of one. Read
    #: by both the worker and the API, which is why it lives here.
    heartbeat_interval_s: int = 30

    @property
    def detector_native_classes(self) -> bool:
        """Whether the checkpoint predicts the project's classes directly.

        The fine-tuned checkpoint does; a bare COCO checkpoint does not and must go
        through the COCO name mapping. Decided by whether the fine-tuned file exists
        rather than by a separate flag that could disagree with the path.

        The marker is searched in the whole path, not the filename: Ultralytics
        always writes ``best.pt``, and the run name lives in the directory above it.
        Testing the filename alone once routed the fine-tuned model through the COCO
        map, which silently discarded every robot, forklift and pallet.
        """
        return self.detector_checkpoint.exists() and "rewind" in str(self.detector_checkpoint)


worker_settings = WorkerSettings()
