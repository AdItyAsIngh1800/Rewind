"""Contract tests for packages.schemas.

These are the tests that matter most in the whole project. The claim REWIND makes
is that a conclusion cannot be stated more confidently than its evidence permits.
That claim is enforced by validators, and these tests are what stop those
validators from being quietly weakened later.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.schemas import (
    ALLOWED_LANGUAGE,
    SCHEMA_VERSION,
    BBox,
    Claim,
    EntityClass,
    EventType,
    EvidenceLevel,
    Hypothesis,
    IdentityLink,
    Incident,
    IncidentClass,
    LinkDecision,
    Observation,
    Report,
    SemanticEvent,
    Severity,
    TrackSegment,
)

NOW = datetime(2026, 9, 9, 10, 32, 10, tzinfo=UTC)


# --------------------------------------------------------------------------
# The anti-hallucination guarantees
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level",
    [
        EvidenceLevel.CONFIRMED,
        EvidenceLevel.STRONGLY_INFERRED,
        EvidenceLevel.POSSIBLE,
        EvidenceLevel.CONFLICTING,
    ],
)
def test_claim_without_evidence_cannot_be_constructed(level: EvidenceLevel) -> None:
    """Reject a claim above UNKNOWN that cites no evidence.

    This is the core guarantee of the whole system.
    """
    with pytest.raises(ValidationError, match="no evidence_refs"):
        Claim(
            claim_id="c1",
            text=f"{ALLOWED_LANGUAGE[level]}: worker entered zone B",
            evidence_level=level,
            evidence_refs=[],
        )


def test_unknown_claim_may_stand_without_evidence() -> None:
    """Allow an UNKNOWN claim to stand without any citation.

    "Cannot determine" is a claim *about* absent evidence. Demanding a citation for
    it would be incoherent, and would punish the honest answer.
    """
    claim = Claim(
        claim_id="c2",
        text="Cannot determine whether contact occurred between 11.0s and 16.0s",
        evidence_level=EvidenceLevel.UNKNOWN,
        evidence_refs=[],
    )
    assert claim.evidence_level is EvidenceLevel.UNKNOWN


def test_claim_phrasing_is_bound_to_its_evidence_level() -> None:
    """Reject phrasing that overstates the claim's evidence level.

    A CONFIRMED claim may not hedge, and an inferred claim may not be phrased as a
    direct observation.
    """
    with pytest.raises(ValidationError, match="requires the phrase"):
        Claim(
            claim_id="c3",
            text="The worker definitely caused the robot to stop",
            evidence_level=EvidenceLevel.STRONGLY_INFERRED,
            evidence_refs=["ev-1"],
        )


def test_correctly_phrased_claim_is_accepted() -> None:
    """Assert that correctly phrased claim is accepted."""
    claim = Claim(
        claim_id="c4",
        text="Likely contributed: worker P01 entering the robot lane at 12.8s",
        evidence_level=EvidenceLevel.STRONGLY_INFERRED,
        evidence_refs=["ev-1", "ev-2"],
    )
    assert claim.evidence_refs == ["ev-1", "ev-2"]


def test_allowed_language_covers_every_evidence_level() -> None:
    """Require every evidence level to have a phrasing rule.

    A level with no entry would silently bypass the phrasing validator, so the
    mapping must stay exhaustive.
    """
    assert set(ALLOWED_LANGUAGE) == set(EvidenceLevel)


def test_hypothesis_above_unknown_requires_support() -> None:
    """Assert that hypothesis above unknown requires support."""
    with pytest.raises(ValidationError, match="no support_refs"):
        Hypothesis(
            hypothesis_id="h1",
            run_id="r1",
            incident_id="i1",
            description="Forklift F01 placed the pallet",
            evidence_level=EvidenceLevel.POSSIBLE,
            score=0.4,
            support_refs=[],
        )


# --------------------------------------------------------------------------
# Refusing to link is a first-class outcome
# --------------------------------------------------------------------------


def test_identity_link_cannot_claim_a_link_below_its_own_threshold() -> None:
    """Assert that identity link cannot claim a link below its own threshold."""
    with pytest.raises(ValidationError, match="below threshold"):
        IdentityLink(
            link_id="l1",
            run_id="r1",
            segment_a="s1",
            segment_b="s2",
            decision=LinkDecision.LINKED,
            score=0.30,
            threshold=0.75,
        )


def test_identity_link_may_refuse_to_link() -> None:
    """A low-scoring UNKNOWN is a valid, recorded result — not a failure."""
    link = IdentityLink(
        link_id="l2",
        run_id="r1",
        segment_a="s1",
        segment_b="s2",
        decision=LinkDecision.UNKNOWN,
        score=0.30,
        threshold=0.75,
    )
    assert link.decision is LinkDecision.UNKNOWN


# --------------------------------------------------------------------------
# Structural invariants
# --------------------------------------------------------------------------


def test_degenerate_bbox_is_rejected() -> None:
    """Assert that degenerate bbox is rejected."""
    with pytest.raises(ValidationError, match="degenerate bbox"):
        BBox(x1=10, y1=10, x2=10, y2=20)


def test_bbox_geometry() -> None:
    """Assert that bbox geometry."""
    box = BBox(x1=0, y1=0, x2=4, y2=2)
    assert box.area == 8
    assert box.centroid == (2.0, 1.0)


def test_zone_event_must_name_a_zone() -> None:
    """Assert that zone event must name a zone."""
    with pytest.raises(ValidationError, match="requires a zone_id"):
        SemanticEvent(
            event_id="e1",
            run_id="r1",
            event_type=EventType.ZONE_ENTRY,
            timestamp_s=12.8,
            confidence=0.9,
        )


def test_investigation_window_must_contain_its_trigger() -> None:
    """Assert that investigation window must contain its trigger."""
    with pytest.raises(ValidationError, match="does not contain its own trigger"):
        Incident(
            incident_id="i1",
            run_id="r1",
            incident_class=IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION,
            trigger_event_id="e1",
            detected_at_s=13.4,
            window_start_s=20.0,
            window_end_s=40.0,
            severity=Severity.HIGH,
        )


def test_track_segment_cannot_end_before_it_starts() -> None:
    """Assert that track segment cannot end before it starts."""
    with pytest.raises(ValidationError, match="ends before it starts"):
        TrackSegment(
            segment_id="s1",
            run_id="r1",
            camera_id="CAM_A",
            local_track_id="1",
            entity_class=EntityClass.PERSON,
            start_time_s=10.0,
            end_time_s=5.0,
            observation_ids=[],
            mean_confidence=0.9,
        )


def test_contracts_reject_unknown_fields() -> None:
    """Reject unknown fields on a contract.

    A stage that quietly adds a field should fail fast rather than drift away from
    the frozen contract unnoticed.
    """
    with pytest.raises(ValidationError):
        BBox(x1=0, y1=0, x2=1, y2=1, confidence=0.9)  # type: ignore[call-arg]


# --------------------------------------------------------------------------
# Round-trip and versioning
# --------------------------------------------------------------------------


def test_observation_round_trips_through_json() -> None:
    """Assert that observation round trips through json."""
    obs = Observation(
        observation_id="o1",
        run_id="r1",
        camera_id="CAM_A",
        frame_index=128,
        timestamp_s=12.8,
        entity_class=EntityClass.PERSON,
        bbox=BBox(x1=100, y1=200, x2=160, y2=380),
        confidence=0.94,
        track_id="t7",
        world_xyz=(12.0, 9.5, 0.0),
        visibility=0.8,
    )
    assert Observation.model_validate_json(obs.model_dump_json()) == obs


def test_every_contract_carries_the_schema_version() -> None:
    """Assert that every contract carries the schema version."""
    obs = Observation(
        observation_id="o1",
        run_id="r1",
        camera_id="CAM_A",
        frame_index=0,
        timestamp_s=0.0,
        entity_class=EntityClass.ROBOT,
        bbox=BBox(x1=0, y1=0, x2=10, y2=10),
        confidence=1.0,
    )
    assert obs.schema_version == SCHEMA_VERSION


# --------------------------------------------------------------------------
# Evidence coverage
# --------------------------------------------------------------------------


def test_evidence_coverage_counts_unknown_as_covered() -> None:
    """Assert that evidence coverage counts unknown as covered."""
    report = Report(
        report_id="rep1",
        run_id="r1",
        incident_id="i1",
        generator_version="deterministic-0.1.0",
        created_at=NOW,
        summary="Robot R12 stopped at 13.4s.",
        claims=[
            Claim(
                claim_id="c1",
                text="Observed: robot R12 changed state to ESTOP at 13.4s",
                evidence_level=EvidenceLevel.CONFIRMED,
                evidence_refs=["ev-1"],
            ),
            Claim(
                claim_id="c2",
                text="Cannot determine whether P01 entered the lane during 11.0-16.0s",
                evidence_level=EvidenceLevel.UNKNOWN,
                evidence_refs=[],
            ),
        ],
        limitations="Camera C was occluded by forklift F01 for the critical interval.",
    )
    assert report.evidence_coverage == 1.0
