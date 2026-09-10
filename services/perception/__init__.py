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

__all__ = [
    "COCO_TO_ENTITY",
    "UNREACHABLE_ZERO_SHOT",
    "Detector",
    "DetectorConfig",
    "DetectorError",
]
