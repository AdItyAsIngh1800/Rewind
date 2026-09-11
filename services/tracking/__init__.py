"""Per-camera multi-object tracking.

Produces TrackSegment records from per-frame observations.
"""

from .tracker import (
    Tracker,
    TrackerConfig,
    TrackerError,
    TrackingReport,
    score_against_truth,
)

__all__ = ["Tracker", "TrackerConfig", "TrackerError", "TrackingReport", "score_against_truth"]
