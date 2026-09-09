"""Validate the golden fixtures against the frozen contracts.

These tests are the drift detector. The fixtures are what the frontend, the mock API
and every downstream sub-phase are built against, so a contract change that silently
invalidates them has to fail loudly here rather than surface in Week 14.

Two separate things are checked:

1. **Shape** — every record parses as its contract.
2. **Coherence** — the ten files describe *one* incident. Cross-file references
   actually resolve. A fixture set that validates individually but references
   nonexistent IDs would still mislead everything built on it.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from packages.schemas import (
    Camera,
    EvidenceEdge,
    EvidenceLevel,
    EvidenceNode,
    Hypothesis,
    IdentityLink,
    Incident,
    Observation,
    ProcessingRun,
    Report,
    SemanticEvent,
    TrackSegment,
)

GOLDEN = pathlib.Path("tests/fixtures/golden")


def load(name: str) -> Any:
    """Read one golden fixture file and return its parsed JSON."""
    return json.loads((GOLDEN / name).read_text())


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "contract", "is_list"),
    [
        ("00_cameras.json", Camera, True),
        ("01_run.json", ProcessingRun, False),
        ("10_observations.json", Observation, True),
        ("20_track_segments.json", TrackSegment, True),
        ("30_identity_links.json", IdentityLink, True),
        ("40_events.json", SemanticEvent, True),
        ("50_incident.json", Incident, False),
        ("70_hypotheses.json", Hypothesis, True),
        ("80_report.json", Report, False),
    ],
)
def test_fixture_validates_against_its_contract(
    filename: str, contract: type, is_list: bool
) -> None:
    """Assert that every fixture record parses as its frozen contract."""
    payload = load(filename)
    records = payload if is_list else [payload]
    assert records, f"{filename} is empty"
    for record in records:
        contract.model_validate(record)


def test_evidence_graph_validates() -> None:
    """Assert that the evidence graph's nodes and edges parse as their contracts."""
    graph = load("60_evidence_graph.json")
    assert graph["nodes"] and graph["edges"]
    for node in graph["nodes"]:
        EvidenceNode.model_validate(node)
    for edge in graph["edges"]:
        EvidenceEdge.model_validate(edge)


def test_every_boundary_has_a_fixture() -> None:
    """Assert that no pipeline boundary is missing its fixture.

    A missing file means some sub-phase has nothing to be built or tested against,
    which is precisely the coupling the fixture set exists to remove.
    """
    expected = {
        "00_cameras.json",
        "01_run.json",
        "10_observations.json",
        "20_track_segments.json",
        "30_identity_links.json",
        "40_events.json",
        "50_incident.json",
        "60_evidence_graph.json",
        "70_hypotheses.json",
        "80_report.json",
    }
    assert expected == {p.name for p in GOLDEN.glob("*.json")}


# --------------------------------------------------------------------------
# Coherence — the ten files must describe one incident
# --------------------------------------------------------------------------


def test_every_record_belongs_to_the_same_run() -> None:
    """Assert that no fixture record carries a foreign run_id."""
    run_id = load("01_run.json")["run_id"]
    for name in (
        "10_observations.json",
        "20_track_segments.json",
        "30_identity_links.json",
        "40_events.json",
        "70_hypotheses.json",
    ):
        for record in load(name):
            assert record["run_id"] == run_id, f"{name} references a different run"


def test_track_segments_reference_real_observations() -> None:
    """Assert that every observation id named by a segment actually exists."""
    known = {o["observation_id"] for o in load("10_observations.json")}
    for segment in load("20_track_segments.json"):
        missing = set(segment["observation_ids"]) - known
        assert not missing, f"{segment['segment_id']} references unknown {missing}"


def test_identity_links_reference_real_segments() -> None:
    """Assert that both sides of every identity link resolve to a real segment."""
    known = {s["segment_id"] for s in load("20_track_segments.json")}
    for link in load("30_identity_links.json"):
        assert {link["segment_a"], link["segment_b"]} <= known


def test_incident_trigger_resolves_to_a_real_event() -> None:
    """Assert that the incident's trigger event exists in the timeline."""
    events = {e["event_id"] for e in load("40_events.json")}
    assert load("50_incident.json")["trigger_event_id"] in events


def test_evidence_edges_connect_real_nodes() -> None:
    """Assert that no edge dangles off a node that does not exist."""
    graph = load("60_evidence_graph.json")
    nodes = {n["node_id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert {edge["from_node"], edge["to_node"]} <= nodes, edge["edge_id"]


def test_hypotheses_reference_real_evidence() -> None:
    """Assert that support and contradiction references resolve to graph nodes."""
    nodes = {n["node_id"] for n in load("60_evidence_graph.json")["nodes"]}
    for hypothesis in load("70_hypotheses.json"):
        refs = set(hypothesis["support_refs"]) | set(hypothesis["contradiction_refs"])
        assert refs <= nodes, f"{hypothesis['hypothesis_id']} references unknown {refs - nodes}"


def test_report_claims_reference_real_evidence() -> None:
    """Assert that every cited claim resolves to an event, node or hypothesis."""
    known = (
        {e["event_id"] for e in load("40_events.json")}
        | {n["node_id"] for n in load("60_evidence_graph.json")["nodes"]}
        | {h["hypothesis_id"] for h in load("70_hypotheses.json")}
    )
    for claim in load("80_report.json")["claims"]:
        missing = set(claim["evidence_refs"]) - known
        assert not missing, f"{claim['claim_id']} cites unknown {missing}"


# --------------------------------------------------------------------------
# The fixture must exercise the uncertainty path
# --------------------------------------------------------------------------


def test_fixture_contains_a_genuine_evidence_gap() -> None:
    """Assert that the fixture carries a GAP node with a real interval.

    Without one, a frontend built against these fixtures would never render the
    uncertainty state, which is the single most important thing this product shows.
    """
    gaps = [n for n in load("60_evidence_graph.json")["nodes"] if n["node_type"] == "gap"]
    assert gaps, "golden fixture has no gap node"
    start, end = gaps[0]["interval_s"]
    assert end > start


def test_gap_falls_inside_the_investigation_window() -> None:
    """Assert the gap sits within the rewind window, not outside the case."""
    incident = load("50_incident.json")
    gap = next(n for n in load("60_evidence_graph.json")["nodes"] if n["node_type"] == "gap")
    start, end = gap["interval_s"]
    assert incident["window_start_s"] <= start < end <= incident["window_end_s"]


def test_report_exercises_multiple_evidence_levels() -> None:
    """Assert the report spans confirmed, inferred and unknown claims."""
    levels = {c["evidence_level"] for c in load("80_report.json")["claims"]}
    assert {
        EvidenceLevel.CONFIRMED.value,
        EvidenceLevel.STRONGLY_INFERRED.value,
        EvidenceLevel.UNKNOWN.value,
    } <= levels


def test_identity_links_include_a_refusal() -> None:
    """Assert the fixture records a deliberate refusal to link.

    Refusing to link is a normal outcome, not a failure. If the fixture only ever
    showed successful links, the UI state for an unresolved identity would go
    unbuilt.
    """
    decisions = {link["decision"] for link in load("30_identity_links.json")}
    assert "unknown" in decisions


def test_report_evidence_coverage_is_total() -> None:
    """Assert every material claim is either cited or explicitly unknown."""
    report = Report.model_validate(load("80_report.json"))
    assert report.evidence_coverage == 1.0
