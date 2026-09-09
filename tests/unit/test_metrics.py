"""Tests for the benchmark metrics.

These functions decide whether the project worked, so they are tested against
hand-computed values rather than against their own output. A metric that quietly
drifts is worse than a missing one, because every later comparison inherits it.
"""

from __future__ import annotations

import pytest

from packages.evaluation.metrics import (
    Counts,
    count_id_switches,
    evidence_coverage,
    false_link_rate,
    iou,
    match_detections,
    match_events,
    top_k_accuracy,
    unsupported_claim_rate,
)


def det(camera: str, frame: int, cls: str, box: tuple[float, float, float, float]) -> dict:
    """Build a detection record for the matching tests."""
    return {
        "camera_id": camera,
        "frame_index": frame,
        "entity_class": cls,
        "bbox": {"x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]},
    }


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def test_identical_boxes_have_unit_iou() -> None:
    """Assert that identical boxes score 1.0."""
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_disjoint_boxes_have_zero_iou() -> None:
    """Assert that non-overlapping boxes score 0.0 rather than raising."""
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_touching_boxes_have_zero_iou() -> None:
    """Assert that edge-touching boxes have no area of intersection."""
    assert iou([0, 0, 10, 10], [10, 0, 20, 10]) == 0.0


def test_half_overlap_iou_is_one_third() -> None:
    """Assert a hand-computed overlap: intersection 50, union 150."""
    assert iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(50 / 150)


# --------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------


def test_counts_are_perfect_when_nothing_is_missed() -> None:
    """Assert precision, recall and F1 all reach 1.0 on a clean match."""
    counts = Counts(tp=4, fp=0, fn=0)
    assert (counts.precision, counts.recall, counts.f1) == (1.0, 1.0, 1.0)


def test_counts_handle_empty_input_without_dividing_by_zero() -> None:
    """Assert an empty comparison is scored 1.0, not NaN.

    Predicting nothing when there is nothing to find is correct behaviour, and it
    must not poison an averaged benchmark with a NaN.
    """
    counts = Counts(tp=0, fp=0, fn=0)
    assert counts.precision == 1.0
    assert counts.recall == 1.0


def test_f1_is_zero_when_precision_and_recall_are_both_zero() -> None:
    """Assert F1 degrades to 0.0 rather than raising."""
    assert Counts(tp=0, fp=3, fn=3).f1 == 0.0


# --------------------------------------------------------------------------
# Detection matching
# --------------------------------------------------------------------------


def test_perfect_detections_score_perfectly() -> None:
    """Assert identical predictions and truth produce no errors."""
    truth = [det("CAM_A", 1, "person", (0, 0, 10, 20))]
    assert match_detections(truth, truth) == Counts(tp=1, fp=0, fn=0)


def test_detections_of_the_wrong_class_do_not_match() -> None:
    """Assert a forklift box cannot be credited as a person.

    Cross-class matching would inflate every score and hide the exact confusion
    that matters in a scene containing both.
    """
    truth = [det("CAM_A", 1, "person", (0, 0, 10, 20))]
    predicted = [det("CAM_A", 1, "forklift", (0, 0, 10, 20))]
    assert match_detections(predicted, truth) == Counts(tp=0, fp=1, fn=1)


def test_detections_in_the_wrong_camera_do_not_match() -> None:
    """Assert matching is scoped per camera."""
    truth = [det("CAM_A", 1, "person", (0, 0, 10, 20))]
    predicted = [det("CAM_B", 1, "person", (0, 0, 10, 20))]
    assert match_detections(predicted, truth) == Counts(tp=0, fp=1, fn=1)


def test_detections_below_the_iou_threshold_do_not_match() -> None:
    """Assert a barely-overlapping box is a false positive, not a hit."""
    truth = [det("CAM_A", 1, "person", (0, 0, 10, 10))]
    predicted = [det("CAM_A", 1, "person", (9, 9, 19, 19))]
    assert match_detections(predicted, truth, iou_threshold=0.5).tp == 0


def test_each_truth_box_is_claimed_only_once() -> None:
    """Assert two predictions on one target yield one hit and one false positive."""
    truth = [det("CAM_A", 1, "person", (0, 0, 10, 10))]
    predicted = [
        det("CAM_A", 1, "person", (0, 0, 10, 10)),
        det("CAM_A", 1, "person", (1, 1, 11, 11)),
    ]
    assert match_detections(predicted, truth) == Counts(tp=1, fp=1, fn=0)


# --------------------------------------------------------------------------
# Tracking
# --------------------------------------------------------------------------


def test_stable_track_has_no_id_switches() -> None:
    """Assert a consistently-tracked entity records zero switches."""
    track = [(0.0, "P01", "t1"), (0.1, "P01", "t1"), (0.2, "P01", "t1")]
    assert count_id_switches(track) == 0


def test_reassigned_track_id_counts_as_a_switch() -> None:
    """Assert the tracker losing and re-acquiring an entity is counted."""
    track = [(0.0, "P01", "t1"), (0.1, "P01", "t2"), (0.2, "P01", "t2")]
    assert count_id_switches(track) == 1


def test_two_entities_do_not_contaminate_each_other() -> None:
    """Assert switches are counted per true entity, not globally."""
    track = [(0.0, "P01", "t1"), (0.0, "R12", "t2"), (0.1, "P01", "t1"), (0.1, "R12", "t2")]
    assert count_id_switches(track) == 0


# --------------------------------------------------------------------------
# Event matching
# --------------------------------------------------------------------------


def test_events_within_tolerance_match_and_report_timing_error() -> None:
    """Assert a slightly-late event matches and its error is surfaced."""
    truth = [{"event_type": "zone_entry", "zone_id": "Z1", "timestamp_s": 12.8}]
    predicted = [{"event_type": "zone_entry", "zone_id": "Z1", "timestamp_s": 13.0}]
    counts, errors = match_events(predicted, truth, tolerance_s=0.5)
    assert counts.tp == 1
    assert errors == pytest.approx([0.2])


def test_events_outside_tolerance_do_not_match() -> None:
    """Assert an event two seconds late is a miss, not a hit."""
    truth = [{"event_type": "zone_entry", "zone_id": "Z1", "timestamp_s": 12.8}]
    predicted = [{"event_type": "zone_entry", "zone_id": "Z1", "timestamp_s": 14.8}]
    counts, errors = match_events(predicted, truth, tolerance_s=0.5)
    assert counts == Counts(tp=0, fp=1, fn=1)
    assert errors == []


def test_events_in_the_wrong_zone_do_not_match() -> None:
    """Assert zone identity is part of event identity."""
    truth = [{"event_type": "zone_entry", "zone_id": "Z1", "timestamp_s": 12.8}]
    predicted = [{"event_type": "zone_entry", "zone_id": "Z2", "timestamp_s": 12.8}]
    assert match_events(predicted, truth)[0].tp == 0


# --------------------------------------------------------------------------
# Identity — the metric that matters most
# --------------------------------------------------------------------------


def test_a_correct_link_is_not_a_false_link() -> None:
    """Assert an accepted link matching truth scores zero false-link rate."""
    links = [{"segment_a": "A", "segment_b": "B", "decision": "linked"}]
    assert false_link_rate(links, {frozenset({"A", "B"})}) == 0.0


def test_an_invented_link_is_penalised() -> None:
    """Assert linking two segments that are not the same entity is caught."""
    links = [{"segment_a": "A", "segment_b": "C", "decision": "linked"}]
    assert false_link_rate(links, {frozenset({"A", "B"})}) == 1.0


def test_a_refusal_is_not_counted_as_a_false_link() -> None:
    """Assert declining to link is never penalised.

    Refusing is the correct answer when evidence is insufficient. Counting it here
    would push the threshold toward linking everything, which is the failure this
    metric exists to detect.
    """
    links = [{"segment_a": "A", "segment_b": "C", "decision": "unknown"}]
    assert false_link_rate(links, {frozenset({"A", "B"})}) == 0.0


def test_linking_nothing_invents_nothing() -> None:
    """Assert an empty link set scores 0.0 rather than dividing by zero."""
    assert false_link_rate([], {frozenset({"A", "B"})}) == 0.0


# --------------------------------------------------------------------------
# Cause ranking
# --------------------------------------------------------------------------


def test_top_1_hit_when_the_true_cause_ranks_first() -> None:
    """Assert the annotated cause at rank one scores 1.0."""
    assert top_k_accuracy(["HYP-1", "HYP-2"], "HYP-1", k=1) == 1.0


def test_top_1_miss_but_top_2_hit() -> None:
    """Assert a close second is a miss at k=1 and a hit at k=2."""
    assert top_k_accuracy(["HYP-2", "HYP-1"], "HYP-1", k=1) == 0.0
    assert top_k_accuracy(["HYP-2", "HYP-1"], "HYP-1", k=2) == 1.0


# --------------------------------------------------------------------------
# Evidence quality — the project's thesis, measured
# --------------------------------------------------------------------------


def test_unknown_claims_count_as_covered() -> None:
    """Assert honesty about absent evidence is not penalised."""
    claims = [{"evidence_level": "unknown", "evidence_refs": []}]
    assert evidence_coverage(claims) == 1.0


def test_uncited_confirmed_claim_lowers_coverage() -> None:
    """Assert a confident claim with no citation is counted as uncovered."""
    claims = [
        {"evidence_level": "confirmed", "evidence_refs": ["E1"]},
        {"evidence_level": "confirmed", "evidence_refs": []},
    ]
    assert evidence_coverage(claims) == 0.5


def test_dangling_citation_is_an_unsupported_claim() -> None:
    """Assert citing an id that does not exist is caught.

    This is the difference between coverage and support. A claim citing EVT-9999
    looks perfectly covered and is entirely unsupported.
    """
    claims = [{"evidence_level": "confirmed", "evidence_refs": ["EVT-9999"]}]
    assert unsupported_claim_rate(claims, known_ids={"EVT-0001"}) == 1.0


def test_valid_citations_are_supported() -> None:
    """Assert claims citing real evidence score zero."""
    claims = [{"evidence_level": "confirmed", "evidence_refs": ["EVT-0001"]}]
    assert unsupported_claim_rate(claims, known_ids={"EVT-0001"}) == 0.0


def test_unknown_claim_without_refs_is_not_unsupported() -> None:
    """Assert an UNKNOWN claim citing nothing is exempt, by design."""
    claims = [{"evidence_level": "unknown", "evidence_refs": []}]
    assert unsupported_claim_rate(claims, known_ids=set()) == 0.0
