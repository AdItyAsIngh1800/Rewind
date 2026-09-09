"""Smoke tests for the mock API.

The mock is development infrastructure, not product code, but a broken mock silently
blocks frontend work for however long it takes someone to notice. These tests keep
it honest: it must serve every endpoint the real API declares, and it must be
identifiable as a mock so nobody demos against it by accident.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from apps.api.main import PREFIX
from apps.api.main import app as real_app
from scripts.mock_api import app as mock_app

client = TestClient(mock_app)
CASE = "INC-0001"


def test_mock_serves_every_path_the_real_api_declares() -> None:
    """Assert the mock covers the real contract, so the UI never hits a hole."""
    real_paths = set(real_app.openapi()["paths"])
    mock_paths = set(mock_app.openapi()["paths"])
    missing = real_paths - mock_paths
    assert not missing, f"mock is missing {missing}"


def test_mock_identifies_itself() -> None:
    """Assert health flags the mock, so it cannot be mistaken for the real API."""
    body = client.get(f"{PREFIX}/health").json()
    assert body["mock"] is True
    assert body["api_version"].endswith("+mock")


def test_timeline_returns_events_and_the_links_behind_them() -> None:
    """Assert the timeline carries events, segments and identity links together."""
    body = client.get(f"{PREFIX}/cases/{CASE}/timeline").json()
    assert body["events"] and body["segments"] and body["identity_links"]
    assert any(link["decision"] == "unknown" for link in body["identity_links"])


def test_evidence_graph_includes_the_gap_node() -> None:
    """Assert the served graph exposes the uncertainty state to the UI."""
    graph = client.get(f"{PREFIX}/cases/{CASE}/evidence").json()
    assert any(n["node_type"] == "gap" for n in graph["nodes"])


def test_replay_exposes_per_camera_clock_offsets() -> None:
    """Assert offsets are surfaced rather than pre-applied.

    Correcting the offset is the client's job while scrubbing. If the mock applied
    it silently, a desynchronised player would look correct here and fail only
    against real footage.
    """
    body = client.get(f"{PREFIX}/cases/{CASE}/replay").json()
    offsets = {c["camera_id"]: c["clock_offset_s"] for c in body["cameras"]}
    assert len(offsets) == 3
    assert any(v != 0.0 for v in offsets.values())


def test_report_carries_an_unknown_claim() -> None:
    """Assert the served report exercises the uncertainty path."""
    body = client.get(f"{PREFIX}/cases/{CASE}/report").json()
    levels = {c["evidence_level"] for c in body["report"]["claims"]}
    assert "unknown" in levels
    assert body["hypotheses"], "ranked hypotheses must accompany the report"


def test_case_inbox_filters_are_honoured() -> None:
    """Assert the inbox endpoint applies the filters the UI sends."""
    everything = client.get(f"{PREFIX}/cases").json()
    assert everything["total"] == 1
    filtered = client.get(f"{PREFIX}/cases", params={"severity": "low"}).json()
    assert filtered["total"] == 0


def test_mock_responses_are_json_serialisable() -> None:
    """Assert every endpoint returns something the browser can actually parse."""
    for path in (
        f"{PREFIX}/cases",
        f"{PREFIX}/cases/{CASE}",
        f"{PREFIX}/cases/{CASE}/timeline",
        f"{PREFIX}/cases/{CASE}/evidence",
        f"{PREFIX}/cases/{CASE}/replay",
        f"{PREFIX}/cases/{CASE}/report",
        f"{PREFIX}/metrics",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        json.loads(response.content)
