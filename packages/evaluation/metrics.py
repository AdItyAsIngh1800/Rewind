"""Metric implementations for the REWIND benchmark.

Every function here is pure: it takes predictions and ground truth and returns a
number. No I/O, no globals, no model loading. That is deliberate — these are the
functions that decide whether the project worked, so they need to be trivially
testable in isolation.

Two of them carry the project's actual thesis rather than standard detection
bookkeeping:

- :func:`false_link_rate` — how often the identity layer invented a connection that
  does not exist. A false link fabricates a trajectory and every downstream
  conclusion inherits it, which makes it worse than a missed link.
- :func:`unsupported_claim_rate` — how often a report states something it cannot
  point at. This is the number that must stay at zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Ground truth and predictions are both compared as plain mappings so the harness can
# score records that came from JSON fixtures, the database, or a model, without
# forcing every producer through the same object type.
Record = dict[str, object]


@dataclass(frozen=True)
class Counts:
    """True positives, false positives and false negatives for one comparison."""

    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        """Fraction of predictions that were correct; 1.0 when nothing was predicted."""
        denominator = self.tp + self.fp
        return 1.0 if denominator == 0 else self.tp / denominator

    @property
    def recall(self) -> float:
        """Fraction of truth that was found; 1.0 when there was nothing to find."""
        denominator = self.tp + self.fn
        return 1.0 if denominator == 0 else self.tp / denominator

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall."""
        p, r = self.precision, self.recall
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection over union of two ``(x1, y1, x2, y2)`` boxes.

    Returns 0.0 for disjoint boxes rather than raising, because non-overlap is the
    common case when matching a frame's worth of detections.
    """
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - intersection
    return 0.0 if union <= 0 else intersection / union


def _box(record: Record) -> list[float]:
    """Extract a box as a flat list from either a nested or flattened record."""
    bbox = record.get("bbox")
    if isinstance(bbox, dict):
        return [float(bbox[k]) for k in ("x1", "y1", "x2", "y2")]
    return [float(record[k]) for k in ("x1", "y1", "x2", "y2")]  # type: ignore[arg-type]


def match_detections(
    predicted: Sequence[Record],
    truth: Sequence[Record],
    iou_threshold: float = 0.5,
) -> Counts:
    """Match predicted boxes to ground truth greedily by descending IoU.

    Matching is greedy rather than optimal (Hungarian). At the densities this
    project works with — a handful of entities per frame — the two agree, and greedy
    matching is far easier to reason about when a number looks wrong.

    Predictions and truth are matched within the same ``camera_id``, ``frame_index``
    and ``entity_class``. Matching across classes would let a forklift detection
    count as a person.
    """
    tp = 0
    unmatched_truth = list(truth)
    unmatched_pred = list(predicted)
    matched_truth: set[int] = set()

    pairs: list[tuple[float, int, int]] = []
    for pi, p in enumerate(unmatched_pred):
        for ti, t in enumerate(unmatched_truth):
            if (p.get("camera_id"), p.get("frame_index"), p.get("entity_class")) != (
                t.get("camera_id"),
                t.get("frame_index"),
                t.get("entity_class"),
            ):
                continue
            score = iou(_box(p), _box(t))
            if score >= iou_threshold:
                pairs.append((score, pi, ti))

    pairs.sort(reverse=True)
    matched_pred: set[int] = set()
    for _score, pi, ti in pairs:
        if pi in matched_pred or ti in matched_truth:
            continue
        matched_pred.add(pi)
        matched_truth.add(ti)
        tp += 1

    return Counts(tp=tp, fp=len(unmatched_pred) - tp, fn=len(unmatched_truth) - tp)


def count_id_switches(track: Sequence[tuple[float, str, str]]) -> int:
    """Count identity switches along one ground-truth entity's timeline.

    ``track`` is ``(timestamp, true_entity_id, assigned_track_id)`` sorted by time.
    A switch is any point where the assigned track id changes while the true entity
    stays the same — the tracker lost the thread and started a new one.

    Full IDF1 and HOTA arrive with real tracking output in E3.2 via ``motmetrics``.
    This is the cheap signal that is meaningful right now, and it is the one that
    gates whether cross-camera identity is even worth attempting.
    """
    switches = 0
    last_assigned: dict[str, str] = {}
    for _t, entity, assigned in track:
        previous = last_assigned.get(entity)
        if previous is not None and previous != assigned:
            switches += 1
        last_assigned[entity] = assigned
    return switches


def match_event_pairs(
    predicted: Sequence[Record],
    truth: Sequence[Record],
    tolerance_s: float = 0.5,
) -> list[tuple[int, int, float]]:
    """Pair predicted and true events by type, zone and time, closest first.

    Returns ``(predicted_index, truth_index, signed_error_s)`` triples. Exposed
    separately from the counts so a caller can see *which* predictions went unmatched,
    which matters when some predictions are deliberately hedged.
    """
    candidates: list[tuple[float, int, int]] = []
    for pi, p in enumerate(predicted):
        for ti, t in enumerate(truth):
            if p.get("event_type") != t.get("event_type"):
                continue
            if p.get("zone_id") != t.get("zone_id"):
                continue
            delta = float(p["timestamp_s"]) - float(t["timestamp_s"])  # type: ignore[arg-type]
            if abs(delta) <= tolerance_s:
                candidates.append((abs(delta), pi, ti))

    candidates.sort()
    matched_pred: set[int] = set()
    matched_truth: set[int] = set()
    pairs: list[tuple[int, int, float]] = []
    for _distance, pi, ti in candidates:
        if pi in matched_pred or ti in matched_truth:
            continue
        matched_pred.add(pi)
        matched_truth.add(ti)
        pairs.append(
            (pi, ti, float(predicted[pi]["timestamp_s"]) - float(truth[ti]["timestamp_s"]))  # type: ignore[arg-type]
        )
    return pairs


def match_events(
    predicted: Sequence[Record],
    truth: Sequence[Record],
    tolerance_s: float = 0.5,
) -> tuple[Counts, list[float]]:
    """Match semantic events by type and timestamp, within a tolerance.

    Returns the counts and the signed timing errors of the matched pairs, in
    seconds. Timing error is reported separately from precision and recall because
    an event found half a second late is a different failure from one not found at
    all, and averaging them together hides which is happening.
    """
    pairs = match_event_pairs(predicted, truth, tolerance_s)
    tp = len(pairs)
    return Counts(tp=tp, fp=len(predicted) - tp, fn=len(truth) - tp), [e for _, _, e in pairs]


def false_link_rate(predicted_links: Sequence[Record], true_pairs: set[frozenset[str]]) -> float:
    """Fraction of accepted cross-camera links that are wrong.

    Only links the system actually *accepted* count. A recorded refusal is not a
    false link — refusing to link is the correct answer whenever the evidence does
    not support one, and penalising it here would push the threshold in exactly the
    wrong direction.

    Returns 0.0 when nothing was linked: a system that links nothing invents nothing.
    """
    accepted = [link for link in predicted_links if link.get("decision") == "linked"]
    if not accepted:
        return 0.0
    wrong = sum(
        1
        for link in accepted
        if frozenset({str(link["segment_a"]), str(link["segment_b"])}) not in true_pairs
    )
    return wrong / len(accepted)


def top_k_accuracy(ranked_ids: Sequence[str], true_id: str, k: int = 1) -> float:
    """Return 1.0 if the annotated cause appears in the top ``k`` ranked hypotheses.

    Scored per incident and averaged across incidents by the caller. Binary rather
    than graded because a cause is either surfaced to the investigator or it is not.
    """
    return 1.0 if true_id in list(ranked_ids)[:k] else 0.0


def evidence_coverage(claims: Iterable[Record]) -> float:
    """Fraction of material claims that carry at least one evidence reference.

    An ``unknown`` claim counts as covered. "Cannot determine" is a supported
    statement *about* absent evidence, and penalising it would reward a system that
    stays quiet about what it could not see.
    """
    rows = list(claims)
    if not rows:
        return 1.0
    covered = sum(1 for c in rows if c.get("evidence_refs") or c.get("evidence_level") == "unknown")
    return covered / len(rows)


def unsupported_claim_rate(claims: Iterable[Record], known_ids: set[str]) -> float:
    """Fraction of claims citing evidence that does not exist.

    This is stricter than :func:`evidence_coverage`, and it is the number that
    matters. Coverage asks whether a claim cited *something*; this asks whether the
    thing it cited is real. A report citing ``EVT-9999`` looks perfectly covered and
    is entirely unsupported.

    Target is zero, and it should be zero structurally rather than statistically —
    the ``Claim`` contract makes an uncited claim impossible to construct, and this
    metric catches the remaining case of a citation that dangles.
    """
    rows = list(claims)
    if not rows:
        return 0.0
    bad = 0
    for claim in rows:
        refs = claim.get("evidence_refs") or []
        if not isinstance(refs, list):
            continue
        if claim.get("evidence_level") == "unknown" and not refs:
            continue
        if any(str(ref) not in known_ids for ref in refs):
            bad += 1
    return bad / len(rows)
