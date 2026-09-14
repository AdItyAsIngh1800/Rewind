"""The report says only what the evidence supports, in the words its level allows."""

from __future__ import annotations

import pytest

from packages.evaluation.metrics import evidence_coverage, unsupported_claim_rate
from packages.schemas import EvidenceLevel, Hypothesis, Incident, NodeType, Report, SemanticEvent
from services.evidence import EvidenceGraph
from services.reasoning.hypotheses import rank_hypotheses
from services.reporting import ReportError, generate_report
from services.tracking import segments_from_observations
from tests.unit.test_evidence_graph import NOW, ZONES, _scene, _track
from tests.unit.test_hypotheses import _graph


def _report(
    scene: dict[str, object],
) -> tuple[Incident, EvidenceGraph, list[SemanticEvent], list[Hypothesis], Report]:
    """Build graph, hypotheses and report for a scene."""
    incident, graph, events = _graph(scene)
    hypotheses = rank_hypotheses(incident, graph, events, ZONES, NOW)
    return (
        incident,
        graph,
        events,
        hypotheses,
        generate_report(incident, graph, hypotheses, events, NOW),
    )


def test_every_claim_cites_evidence_that_exists() -> None:
    """Coverage 1.0 and unsupported-claim rate 0.0, measured with the benchmark's own metrics."""
    _, graph, events, hypotheses, report = _report(_scene())
    claims = [c.model_dump(mode="json") for c in report.claims]
    known = (
        {n.node_id for n in graph.nodes}
        | {e.event_id for e in events}
        | {h.hypothesis_id for h in hypotheses}
    )
    assert evidence_coverage(claims) == 1.0
    assert unsupported_claim_rate(claims, known) == 0.0


def test_report_runs_observed_then_inferred_then_unknown() -> None:
    """The stop is observed first, the cause is likely, and what nobody saw is named."""
    _, graph, _, hypotheses, report = _report(_scene())
    first = report.claims[0]
    assert first.evidence_level is EvidenceLevel.CONFIRMED
    assert first.text == "Observed: robot R12 reported an emergency stop at 13.4 s"
    [cause] = [c for c in report.claims if hypotheses[0].hypothesis_id in c.evidence_refs]
    assert cause.text.startswith("Likely contributed: Person (CAM_A-T001, CAM_B-T001) entered Z1")
    unknown = [c for c in report.claims if c.evidence_level is EvidenceLevel.UNKNOWN]
    assert unknown and all(c.text.startswith("Cannot determine") for c in unknown)
    assert {r for c in unknown for r in c.evidence_refs} & {
        n.node_id for n in graph.of_type(NodeType.GAP)
    }
    assert report.ranked_hypotheses == [h.hypothesis_id for h in hypotheses]
    assert report.summary.startswith(
        "Robot R12 reported an emergency stop at 13.4 s. Likely contributed:"
    )
    assert report.limitations


def test_an_unseen_approach_is_reported_as_possible_not_likely() -> None:
    """The gap-capped hypothesis keeps its lower wording all the way into the report."""
    scene = _scene()
    observations = scene["observations"]
    assert isinstance(observations, list)
    scene["observations"] = [
        o for o in observations if not (o.track_id == "CAM_A-T001" and 10.0 <= o.timestamp_s < 14.0)
    ]
    scene["segments"] = segments_from_observations("r", scene["observations"])  # type: ignore[arg-type]
    _, _, _, hypotheses, report = _report(scene)
    [cause] = [c for c in report.claims if hypotheses[0].hypothesis_id in c.evidence_refs]
    assert cause.text.startswith("Possible:")
    assert not any(c.text.startswith("Likely contributed") for c in report.claims)


def test_a_citation_to_missing_evidence_stops_the_report() -> None:
    """A hypothesis pointing at a node the graph does not hold is not written up."""
    incident, graph, events = _graph(_scene())
    forged = Hypothesis(
        hypothesis_id="INC-r-01/H01",
        run_id="r",
        incident_id=incident.incident_id,
        description="Something nobody observed",
        evidence_level=EvidenceLevel.POSSIBLE,
        score=0.5,
        support_refs=["NODE-THAT-DOES-NOT-EXIST"],
    )
    with pytest.raises(ReportError, match="does not contain"):
        generate_report(incident, graph, [forged], events, NOW)


def test_an_unseen_interval_before_the_trigger_is_claimed_whoever_it_hides() -> None:
    """A gap before the stop is written as cannot-determine even when no cause names its entity.

    case_02 named the interval nobody saw in the graph but never said it in a claim,
    because the person it hid was in no hypothesis (EXP-0010, F6).
    """
    scene = _scene()
    observations = scene["observations"]
    groups = scene["groups"]
    assert isinstance(observations, list) and isinstance(groups, dict)
    scene["observations"] = [
        *observations,
        *_track("r", "CAM_C-T009", "pallet", [(4.0, 7.0), (11.0, 20.0)]),
    ]
    scene["segments"] = segments_from_observations("r", scene["observations"])  # type: ignore[arg-type]
    groups["CAM_C-T009"] = "CAM_C-T009"
    _, _, _, hypotheses, report = _report(scene)
    assert not any("Pallet" in h.description for h in hypotheses)
    [claim] = [c for c in report.claims if "pallet (CAM_C-T009) between 7" in c.text]
    assert claim.evidence_level is EvidenceLevel.UNKNOWN
    assert claim.text.startswith("Cannot determine: what happened to pallet")
    assert not any("between 20" in c.text and "pallet" in c.text for c in report.claims), (
        "a gap after the trigger is not about the moments before it"
    )
