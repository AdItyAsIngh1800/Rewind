"""API contract tests.

These assert the *shape* of the API, not its behaviour — most endpoints are 501
until their phase lands. The point is that the contract the frontend is built
against in Week 4 cannot drift without a test failing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import PREFIX, app
from packages.schemas import SCHEMA_VERSION

client = TestClient(app)

#: Every endpoint from specification §F, with the phase that implements it.
PENDING_ENDPOINTS = [
    ("post", f"{PREFIX}/cases/abc/reprocess"),
    ("get", f"{PREFIX}/cases/abc"),
    ("get", f"{PREFIX}/cases/abc/timeline"),
    ("get", f"{PREFIX}/cases/abc/evidence"),
    ("get", f"{PREFIX}/cases/abc/replay"),
    ("get", f"{PREFIX}/cases/abc/report"),
]


def test_health_reports_the_frozen_schema_version() -> None:
    """Assert that health reports the frozen schema version."""
    r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == SCHEMA_VERSION


def test_metrics_exposes_the_specification_metric_set() -> None:
    """The System Health screen is built against this shape from Week 4."""
    r = client.get(f"{PREFIX}/metrics")
    assert r.status_code == 200
    required = {
        "queue_depth",
        "frames_per_second",
        "tracking_id_switch_rate",
        "report_generation_latency_s",
        "evidence_coverage",
        "unsupported_claim_rate",
    }
    assert required <= set(r.json())


@pytest.mark.parametrize(("method", "path"), PENDING_ENDPOINTS)
def test_unimplemented_endpoints_return_501_not_404(method: str, path: str) -> None:
    """Return 501 rather than 404 for endpoints whose phase has not landed.

    501 means "this exists and is coming"; 404 would mean the contract is wrong. The
    frontend treats 501 as "use the mock" and 404 as "you have the path wrong".
    """
    r = getattr(client, method)(path)
    assert r.status_code == 501, f"{method.upper()} {path} returned {r.status_code}"
    assert "ROADMAP" in r.json()["detail"]


def test_create_case_validates_its_request_body() -> None:
    """Validate the request body before reporting the endpoint as unimplemented.

    A malformed request is a 422 regardless of whether the pipeline behind it
    exists yet.
    """
    r = client.post(f"{PREFIX}/cases", json={"case_ref": "C01"})
    assert r.status_code == 422


def test_create_case_accepts_a_valid_body_and_reports_pending() -> None:
    """Assert that create case accepts a valid body and reports pending."""
    r = client.post(
        f"{PREFIX}/cases",
        json={"dataset_version": "v1", "case_ref": "C01", "config_version": "v0.1.0"},
    )
    assert r.status_code == 501


def test_openapi_covers_every_specification_endpoint() -> None:
    """Assert that openapi covers every specification endpoint."""
    spec = app.openapi()
    expected = {
        f"{PREFIX}/cases",
        f"{PREFIX}/cases/{{case_id}}",
        f"{PREFIX}/cases/{{case_id}}/timeline",
        f"{PREFIX}/cases/{{case_id}}/evidence",
        f"{PREFIX}/cases/{{case_id}}/replay",
        f"{PREFIX}/cases/{{case_id}}/report",
        f"{PREFIX}/cases/{{case_id}}/reprocess",
        f"{PREFIX}/health",
        f"{PREFIX}/metrics",
    }
    assert expected == set(spec["paths"])
