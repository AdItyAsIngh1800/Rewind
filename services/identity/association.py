"""Link track segments across cameras, or refuse to (E5.3).

Three signals, each in [0, 1], combined into one score against one threshold:

* **temporal** - do the two segments overlap in time, or follow each other closely
  enough for one entity to have produced both?
* **geometric** - while both cameras saw it, was it in the same place? Or, for a
  hand-over, could it have walked from where one lost it to where the other found it?
* **appearance** - do the two tracks look alike (E5.2 histogram intersection)?

The decision is deliberately conservative. A pair is ``LINKED`` only when its score
clears the threshold *and* no other candidate for the same segment comes close. Two
candidates within ``ambiguity_margin`` of each other is an ``UNKNOWN``, whatever
their scores: picking one would manufacture a trajectory the evidence does not
support, and the charter treats a false link as worse than a missed one. Every
comparison that reached a decision is recorded, refusals included.
"""

from __future__ import annotations

import itertools
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from packages.common import geometry
from packages.schemas import SCHEMA_VERSION, IdentityLink, LinkDecision, Observation, TrackSegment
from services.identity.appearance import similarity

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssociationConfig:
    """Thresholds and weights. Every value is tuned in E5.4 and recorded on the run."""

    threshold: float = 0.75
    #: A runner-up this close to the best candidate makes the pair ambiguous.
    ambiguity_margin: float = 0.10
    #: Weights of the three signals; they sum to one.
    w_temporal: float = 0.35
    w_geometric: float = 0.40
    w_appearance: float = 0.25
    #: Longest gap, in seconds, across which a hand-over between cameras is considered.
    max_gap_s: float = 15.0
    #: Distance at which co-visible geometric agreement scores 1/e. Localisation is
    #: good to ~0.4 m on the worst camera (EXP-0005), so 1 m is two of those.
    sigma_m: float = 1.0
    #: Slack added to the reachable distance during a hand-over, in metres.
    slack_m: float = 1.5

    @property
    def version(self) -> str:
        """Identifier recorded on the run."""
        return (
            f"assoc:thr{self.threshold}:amb{self.ambiguity_margin}"
            f":w{self.w_temporal}/{self.w_geometric}/{self.w_appearance}:gap{self.max_gap_s}"
        )


@dataclass
class SegmentTrack:
    """A segment with what association needs: its trajectory and its look."""

    segment: TrackSegment
    track: geometry.Track
    observation_ids: list[str]
    descriptor: NDArray[np.float64] | None = None


@dataclass
class Signals:
    """The three component scores for one pair."""

    temporal: float
    geometric: float
    appearance: float
    evidence: list[str] = field(default_factory=list)


def build_segment_tracks(
    segments: list[TrackSegment],
    observations: list[Observation],
    positions: dict[str, tuple[float, float]],
    descriptors: dict[str, NDArray[np.float64]],
) -> list[SegmentTrack]:
    """Attach world-plane trajectories and descriptors to segments.

    ``positions`` maps observation id to world (x, y) as the event extractor
    localised them; observations it could not place are left out of the track.
    """
    by_id = {o.observation_id: o for o in observations}
    out: list[SegmentTrack] = []
    for seg in segments:
        rows = [
            (by_id[i].timestamp_s, *positions[i], i)
            for i in seg.observation_ids
            if i in by_id and i in positions
        ]
        if len(rows) < 2:
            continue
        rows.sort()
        out.append(
            SegmentTrack(
                segment=seg,
                track=np.array([(t, x, y) for t, x, y, _ in rows], dtype=np.float64),
                observation_ids=[i for *_, i in rows],
                descriptor=descriptors.get(seg.local_track_id),
            )
        )
    return out


def score_pair(
    a: SegmentTrack, b: SegmentTrack, cfg: AssociationConfig, speed: float
) -> Signals | None:
    """Score one cross-camera pair, or None if they cannot be the same entity at all.

    ``speed`` is the class's top speed in m/s, which bounds how far a hand-over can
    travel in the gap between the segments.
    """
    ta0, ta1 = a.track[0, 0], a.track[-1, 0]
    tb0, tb1 = b.track[0, 0], b.track[-1, 0]
    overlap = min(ta1, tb1) - max(ta0, tb0)
    if overlap > 0:
        # Co-visible: geometric agreement is the mean distance over the shared span.
        _times, dists = geometry.distances(a.track, b.track)
        if dists.size == 0:
            return None
        mean_d = float(dists.mean())
        temporal = (
            min(1.0, overlap / min(ta1 - ta0, tb1 - tb0)) if min(ta1 - ta0, tb1 - tb0) > 0 else 1.0
        )
        geometric = math.exp(-mean_d / cfg.sigma_m)
        ia, ib = (
            int(np.argmin(np.abs(a.track[:, 0] - max(ta0, tb0)))),
            int(np.argmin(np.abs(b.track[:, 0] - max(ta0, tb0)))),
        )
    else:
        # Hand-over: one camera lost it, the other found it later.
        gap = -overlap
        if gap > cfg.max_gap_s:
            return None
        first, second = (a, b) if ta1 <= tb0 else (b, a)
        dx = first.track[-1, 1] - second.track[0, 1]
        dy = first.track[-1, 2] - second.track[0, 2]
        d = math.hypot(dx, dy)
        reach = speed * gap + cfg.slack_m
        if d > reach:
            return None
        temporal = 1.0 - gap / cfg.max_gap_s
        # Nothing is known about the blind interval, so the geometric question is
        # only whether the hand-over was physically possible: fully plausible up to
        # what the class covers at top speed, fading to zero across the slack.
        geometric = 1.0 - max(0.0, d - speed * gap) / cfg.slack_m
        ia = len(a.observation_ids) - 1 if first is a else 0
        ib = len(b.observation_ids) - 1 if first is b else 0
    appearance = (
        similarity(a.descriptor, b.descriptor)
        if a.descriptor is not None and b.descriptor is not None
        else 0.5  # no evidence either way
    )
    return Signals(temporal, geometric, appearance, [a.observation_ids[ia], b.observation_ids[ib]])


def combine(s: Signals, cfg: AssociationConfig) -> float:
    """Weighted mean of the three signals."""
    return (
        cfg.w_temporal * s.temporal
        + cfg.w_geometric * s.geometric
        + cfg.w_appearance * s.appearance
    )


def associate(
    run_id: str,
    tracks: list[SegmentTrack],
    speeds: dict[str, float],
    cfg: AssociationConfig | None = None,
) -> list[IdentityLink]:
    """Decide, for every cross-camera same-class pair worth considering, LINKED or UNKNOWN.

    Each segment gets at most one link per other camera, chosen greedily by score;
    a second candidate within the ambiguity margin turns that decision into UNKNOWN
    for both. Pairs that could not be the same entity at all (wrong time, too far)
    produce no record: there was no decision to record.
    """
    config = cfg or AssociationConfig()
    scored: dict[tuple[str, str], tuple[float, Signals]] = {}
    for a, b in itertools.combinations(tracks, 2):
        if a.segment.camera_id == b.segment.camera_id:
            continue
        if a.segment.entity_class != b.segment.entity_class:
            continue
        signals = score_pair(a, b, config, speeds.get(a.segment.entity_class.value, 2.0))
        if signals is None:
            continue
        scored[(a.segment.segment_id, b.segment.segment_id)] = (combine(signals, config), signals)

    # Best candidate per (segment, other camera), and whether it was contested.
    camera_of = {t.segment.segment_id: t.segment.camera_id for t in tracks}
    candidates: dict[tuple[str, str], list[tuple[float, str]]] = defaultdict(list)
    for (sa, sb), (score, _) in scored.items():
        candidates[(sa, camera_of[sb])].append((score, sb))
        candidates[(sb, camera_of[sa])].append((score, sa))

    def contested(segment: str, other: str, score: float) -> bool:
        others = sorted(candidates[(segment, camera_of[other])], reverse=True)
        return any(s >= score - config.ambiguity_margin and o != other for s, o in others)

    links: list[IdentityLink] = []
    taken: set[tuple[str, str]] = set()
    for (sa, sb), (score, signals) in sorted(scored.items(), key=lambda kv: -kv[1][0]):
        if (sa, camera_of[sb]) in taken or (sb, camera_of[sa]) in taken:
            continue
        taken.add((sa, camera_of[sb]))
        taken.add((sb, camera_of[sa]))
        linked = (
            score >= config.threshold
            and not contested(sa, sb, score)
            and not contested(sb, sa, score)
        )
        links.append(
            IdentityLink(
                schema_version=SCHEMA_VERSION,
                link_id=f"LNK-{run_id}-{len(links) + 1:04d}",
                run_id=run_id,
                segment_a=sa,
                segment_b=sb,
                decision=LinkDecision.LINKED if linked else LinkDecision.UNKNOWN,
                score=round(score, 4),
                threshold=config.threshold,
                components={
                    "temporal": round(signals.temporal, 4),
                    "geometric": round(signals.geometric, 4),
                    "appearance": round(signals.appearance, 4),
                },
                evidence_refs=signals.evidence,
            )
        )
    log.info(
        "%d pairs compared, %d linked, %d unknown",
        len(links),
        sum(link.decision is LinkDecision.LINKED for link in links),
        sum(link.decision is LinkDecision.UNKNOWN for link in links),
    )
    return links
