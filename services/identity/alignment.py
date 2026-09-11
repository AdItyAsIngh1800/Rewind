"""Check that the cameras' clocks agree, using what they saw.

E5.1. The configured per-camera clock offsets are applied at ingestion; nothing there
can tell whether they are correct. The same physical zone crossing seen by two
cameras can: with correct offsets the two timestamps agree to within the
localisation error, and with a wrong offset they disagree by exactly the error in the
offset. Collecting those disagreements over a run and taking the median gives the
residual offset of each camera relative to a reference, robust to the odd crossing
that only one camera saw.

This is a *check* on the configured offsets, not a replacement for them: a residual
above tolerance is a configuration error to raise, not a value to silently apply.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from packages.schemas import EventType, SemanticEvent

log = logging.getLogger(__name__)

CROSSINGS = {EventType.ZONE_ENTRY, EventType.ZONE_EXIT}


@dataclass(frozen=True)
class OffsetEstimate:
    """One camera's clock relative to the reference, as the events show it."""

    camera_id: str
    reference: str
    #: Positive means this camera stamps the same crossing later than the reference.
    residual_s: float
    samples: int
    #: Median absolute deviation of the samples; the localisation noise floor.
    spread_s: float


def _crossings(events: list[SemanticEvent]) -> dict[str, list[SemanticEvent]]:
    """Raw per-camera crossings whose time was observed, not bounded."""
    out: dict[str, list[SemanticEvent]] = defaultdict(list)
    for e in events:
        if e.event_type not in CROSSINGS or e.camera_id is None:
            continue
        if "at_first_sight" in e.payload or "during_gap" in e.payload:
            continue
        out[e.camera_id].append(e)
    return out


def estimate_offsets(
    events: list[SemanticEvent], reference: str, search_window_s: float = 2.0
) -> dict[str, OffsetEstimate]:
    """Estimate each camera's residual clock offset from shared zone crossings.

    ``events`` must be the per-camera stream *before* ``merge_across_cameras``, which
    would otherwise have already collapsed the pairs this needs. A camera that shares
    no crossing with the reference gets no estimate rather than a guess.
    """
    by_camera = _crossings(events)
    ref = by_camera.get(reference, [])
    estimates: dict[str, OffsetEstimate] = {}
    for camera_id, own in by_camera.items():
        if camera_id == reference:
            continue
        deltas: list[float] = []
        for e in own:
            same = [
                r.timestamp_s
                for r in ref
                if r.event_type == e.event_type
                and r.zone_id == e.zone_id
                and r.payload.get("entity_class") == e.payload.get("entity_class")
                and abs(r.timestamp_s - e.timestamp_s) <= search_window_s
            ]
            if same:
                nearest = min(same, key=lambda t: abs(t - e.timestamp_s))
                deltas.append(e.timestamp_s - nearest)
        if not deltas:
            log.warning("%s shares no zone crossing with %s; clock unchecked", camera_id, reference)
            continue
        arr = np.asarray(deltas)
        median = float(np.median(arr))
        estimates[camera_id] = OffsetEstimate(
            camera_id=camera_id,
            reference=reference,
            residual_s=median,
            samples=len(deltas),
            spread_s=float(np.median(np.abs(arr - median))),
        )
    return estimates


def misaligned(estimates: dict[str, OffsetEstimate], tolerance_s: float = 0.3) -> list[str]:
    """Cameras whose residual exceeds what localisation noise alone explains.

    0.3 s is above the per-camera localisation bias measured in EXP-0006 (≤ 0.5 s
    spread across three cameras, so ≤ 0.25 s from any one to the median) and well
    below the 0.5 s a wrong offset typically introduces.
    """
    return sorted(c for c, e in estimates.items() if abs(e.residual_s) > tolerance_s)
