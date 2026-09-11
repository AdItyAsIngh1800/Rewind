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
    segments_for_run,
    timed_window_query,
    write_observations,
    write_segments,
)

__all__ = [
    "COCO_TO_ENTITY",
    "UNREACHABLE_ZERO_SHOT",
    "Detector",
    "DetectorConfig",
    "DetectorError",
    "observations_in_window",
    "segments_for_run",
    "timed_window_query",
    "write_observations",
    "write_segments",
]
