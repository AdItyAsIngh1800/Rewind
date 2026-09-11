"""Association must link what the evidence supports and refuse what it does not."""

from __future__ import annotations

import numpy as np

from packages.schemas import SCHEMA_VERSION, EntityClass, LinkDecision, TrackSegment
from services.identity.association import AssociationConfig, SegmentTrack, associate

SPEEDS = {"person": 1.5, "robot": 1.0}


def seg(
    sid: str,
    camera: str,
    points: list[tuple[float, float, float]],
    cls: EntityClass = EntityClass.PERSON,
    descriptor: list[float] | None = None,
) -> SegmentTrack:
    """Build a segment whose trajectory is ``points`` as (t, x, y)."""
    ids = [f"{sid}-{i}" for i in range(len(points))]
    segment = TrackSegment(
        schema_version=SCHEMA_VERSION,
        segment_id=sid,
        run_id="r",
        camera_id=camera,
        local_track_id=f"{camera}-{sid}",
        entity_class=cls,
        start_time_s=points[0][0],
        end_time_s=points[-1][0],
        observation_ids=ids,
        mean_confidence=0.9,
    )
    return SegmentTrack(
        segment,
        np.array(points, dtype=np.float64),
        ids,
        None if descriptor is None else np.array(descriptor),
    )


def walk(
    t0: float, x0: float, n: int = 20, dt: float = 0.1, v: float = 1.0, y: float = 5.0
) -> list[tuple[float, float, float]]:
    """Straight walk along x starting at (x0, y) at t0."""
    return [(round(t0 + i * dt, 2), x0 + i * dt * v, y) for i in range(n)]


def test_co_visible_same_place_is_linked_with_evidence() -> None:
    """Two cameras seeing one walker at the same spot link, citing a frame each."""
    a, b = seg("A", "CAM_A", walk(0, 0)), seg("B", "CAM_B", walk(0, 0.2))
    [link] = associate("r", [a, b], SPEEDS)
    assert link.decision is LinkDecision.LINKED
    assert link.components["geometric"] > 0.8 and link.components["temporal"] == 1.0
    assert link.components["appearance"] == 0.5  # no descriptors: no evidence either way
    assert len(link.evidence_refs) == 2


def test_co_visible_far_apart_is_a_recorded_refusal() -> None:
    """Two walkers 8 m apart at the same time are compared and left UNKNOWN."""
    a, b = seg("A", "CAM_A", walk(0, 0)), seg("B", "CAM_B", walk(0, 8))
    [link] = associate("r", [a, b], SPEEDS)
    assert link.decision is LinkDecision.UNKNOWN
    assert link.score < link.threshold


def test_plausible_handover_is_linked_and_impossible_one_is_not_compared() -> None:
    """Lost at x=2, found 3 s later at x=5: fine. Found 30 m away: not the same walker."""
    a = seg("A", "CAM_A", walk(0, 0))
    near = seg("B", "CAM_B", walk(5.0, 5))
    far = seg("C", "CAM_C", walk(5.0, 35))
    links = associate("r", [a, near, far], SPEEDS)
    by_pair = {(link.segment_a, link.segment_b): link for link in links}
    assert by_pair[("A", "B")].decision is LinkDecision.LINKED
    assert ("A", "C") not in by_pair


def test_two_close_candidates_make_the_decision_unknown() -> None:
    """Two walkers side by side in CAM_B: CAM_A's walker could be either, so neither."""
    a = seg("A", "CAM_A", walk(0, 0))
    b1 = seg("B1", "CAM_B", walk(0, 0.1, y=5.0))
    b2 = seg("B2", "CAM_B", walk(0, 0.1, y=5.3))
    links = associate("r", [a, b1, b2], SPEEDS)
    assert links and all(link.decision is LinkDecision.UNKNOWN for link in links)


def test_appearance_breaks_the_tie() -> None:
    """Same two candidates, but only one looks like CAM_A's walker: link that one."""
    green = [1.0, 0.0]
    orange = [0.0, 1.0]
    a = seg("A", "CAM_A", walk(0, 0), descriptor=green)
    b1 = seg("B1", "CAM_B", walk(0, 0.1, y=5.0), descriptor=green)
    b2 = seg("B2", "CAM_B", walk(0, 0.1, y=5.3), descriptor=orange)
    links = associate("r", [a, b1, b2], SPEEDS, AssociationConfig(ambiguity_margin=0.1))
    decisions = {(link.segment_a, link.segment_b): link.decision for link in links}
    assert decisions[("A", "B1")] is LinkDecision.LINKED


def test_same_camera_and_different_class_are_never_compared() -> None:
    """Association is across cameras and within a class by definition."""
    a = seg("A", "CAM_A", walk(0, 0))
    same_cam = seg("A2", "CAM_A", walk(0, 0))
    robot = seg("R", "CAM_B", walk(0, 0), cls=EntityClass.ROBOT)
    assert associate("r", [a, same_cam, robot], SPEEDS) == []
