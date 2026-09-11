"""Per-camera multi-object tracking.

Produces TrackSegment records from per-frame observations.
"""

from .tracker import (
    Tracker,
    TrackerConfig,
    TrackerError,
    TrackingReport,
    score_against_truth,
    segments_from_observations,
)

__all__ = [
    "Tracker",
    "TrackerConfig",
    "TrackerError",
    "TrackingReport",
    "score_against_truth",
    "segments_from_observations",
]
