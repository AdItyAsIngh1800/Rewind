"""The uncertainty engine (E7.3): what the evidence cannot see, named as evidence.

Two kinds, both first-class graph nodes rather than warnings in a log:

- **Coverage gaps.** For each entity, the stretches of the investigation window in
  which no camera observed it. One camera losing an entity that another still sees is
  not a gap in knowledge; every camera losing it is. Leading and trailing stretches
  count too: an entity first seen at 14 s was somewhere before that, and the evidence
  cannot say where. `gaps_gt.json` is annotated the same way.
- **Identity conflicts.** Cross-camera comparisons that refused to link (E5.3). Two
  tracks that may or may not be one entity are exactly where a reconstruction could
  otherwise invent a trajectory, so the refusal travels into the graph with its score.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from packages.schemas import IdentityLink, LinkDecision, Observation, TrackSegment

#: Shorter holes are sampling, not blindness: the extractor already treats a 0.5 s
#: break as the start of an occlusion (`EventConfig.occlusion_gap_s`).
MIN_GAP_S = 0.5

#: A group seen in fewer frames than this is a phantom track (a second of footage at
#: 10 FPS); reporting the whole window as a gap in its coverage would be noise.
MIN_TRACK_OBSERVATIONS = 10


@dataclass(frozen=True)
class CoverageGap:
    """An interval in which no camera observed one entity."""

    entity: str
    entity_class: str
    start_s: float
    end_s: float
    #: The observations either side of the hole, where they exist. Empty at a window
    #: edge the entity was never seen across.
    bounded_by: tuple[str, ...]


@dataclass(frozen=True)
class IdentityConflict:
    """A refused cross-camera link whose tracks both fall inside the window."""

    link_id: str
    segment_a: str
    segment_b: str
    entity_class: str
    start_s: float
    end_s: float
    score: float


def tracked_entities(observations: Sequence[Observation], groups: Mapping[str, str]) -> set[str]:
    """Entity groups with enough observations in the run to be more than a phantom."""
    counts: dict[str, int] = defaultdict(int)
    for o in observations:
        if o.track_id:
            counts[groups.get(o.track_id, o.track_id)] += 1
    return {g for g, n in counts.items() if n >= MIN_TRACK_OBSERVATIONS}


def coverage_gaps(
    observations: Sequence[Observation],
    groups: Mapping[str, str],
    start_s: float,
    end_s: float,
    entities: set[str] | None = None,
) -> list[CoverageGap]:
    """Every stretch of ``[start_s, end_s]`` in which no camera saw an entity.

    ``entities`` restricts the result to those groups; by default every tracked
    entity with at least one observation inside the window is considered.
    """
    seen: dict[str, list[tuple[float, str]]] = defaultdict(list)
    classes: dict[str, str] = {}
    for o in observations:
        if not o.track_id:
            continue
        group = groups.get(o.track_id, o.track_id)
        seen[group].append((o.timestamp_s, o.observation_id))
        classes[group] = o.entity_class.value

    wanted = entities if entities is not None else tracked_entities(observations, groups)
    gaps: list[CoverageGap] = []
    for group in sorted(wanted):
        times = sorted(seen.get(group, []))
        if entities is None and not any(start_s <= t <= end_s for t, _ in times):
            continue
        cursor, cursor_ref = start_s, ""
        for t, ref in times:
            if t <= start_s:
                cursor_ref = ref
                continue
            if t > end_s:
                if end_s - cursor >= MIN_GAP_S:
                    gaps.append(_gap(group, classes, cursor, end_s, cursor_ref, ref))
                break
            if t - cursor >= MIN_GAP_S:
                gaps.append(_gap(group, classes, cursor, t, cursor_ref, ref))
            cursor, cursor_ref = t, ref
        else:
            if end_s - cursor >= MIN_GAP_S:
                gaps.append(_gap(group, classes, cursor, end_s, cursor_ref, ""))
    return gaps


def _gap(
    group: str, classes: Mapping[str, str], start: float, end: float, before: str, after: str
) -> CoverageGap:
    return CoverageGap(
        entity=group,
        entity_class=classes.get(group, "unknown"),
        start_s=round(start, 3),
        end_s=round(end, 3),
        bounded_by=tuple(r for r in (before, after) if r),
    )


def identity_conflicts(
    links: Sequence[IdentityLink],
    segments: Sequence[TrackSegment],
    start_s: float,
    end_s: float,
) -> list[IdentityConflict]:
    """Refused links whose undecided interval falls inside the window.

    The undecided interval is when the identity question actually matters: the overlap
    of two segments seen at once, or the hand-over gap between one ending and the other
    starting. Using the whole span of both would cast doubt over every moment either
    track exists, and downgrade hypotheses the refusal says nothing about.
    """
    by_id = {s.segment_id: s for s in segments}
    conflicts: list[IdentityConflict] = []
    for link in links:
        if link.decision is not LinkDecision.UNKNOWN:
            continue
        a, b = by_id.get(link.segment_a), by_id.get(link.segment_b)
        if a is None or b is None:
            continue
        overlap_lo = max(a.start_time_s, b.start_time_s)
        overlap_hi = min(a.end_time_s, b.end_time_s)
        if overlap_hi > overlap_lo:
            undecided = (overlap_lo, overlap_hi)
        else:
            # A hand-over: the gap between the segments, at least one frame wide.
            undecided = (overlap_hi, max(overlap_lo, overlap_hi + 0.1))
        lo, hi = max(start_s, undecided[0]), min(end_s, undecided[1])
        if hi <= lo:
            continue
        conflicts.append(
            IdentityConflict(
                link_id=link.link_id,
                segment_a=a.segment_id,
                segment_b=b.segment_id,
                entity_class=a.entity_class.value,
                start_s=round(lo, 3),
                end_s=round(hi, 3),
                score=link.score,
            )
        )
    return conflicts
