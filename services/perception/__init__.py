"""Object detection over sampled frames.

Produces Observation records. Knows nothing about tracking or incidents.
"""

from .detector import (
    COCO_TO_ENTITY,
    UNREACHABLE_ZERO_SHOT,
    Detector,
    DetectorConfig,
    DetectorError,
)
from .persistence import (
    observations_in_window,
    segment_to_contract,
    segments_for_run,
    timed_window_query,
    write_observations,
    write_segments,
)
from .pipeline import DetectorLike, PipelineResult, process_camera, process_run

__all__ = [
    "COCO_TO_ENTITY",
    "UNREACHABLE_ZERO_SHOT",
    "Detector",
    "DetectorConfig",
    "DetectorError",
    "DetectorLike",
    "PipelineResult",
    "observations_in_window",
    "process_camera",
    "process_run",
    "segment_to_contract",
    "segments_for_run",
    "timed_window_query",
    "write_observations",
    "write_segments",
]
