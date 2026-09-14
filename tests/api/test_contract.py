"""API contract tests.

These assert the *shape* of the API, not its behaviour — most endpoints are 501
until their phase lands. The point is that the contract the frontend is built
against in Week 4 cannot drift without a test failing.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from apps.api import main
from apps.api.main import PREFIX, app
from packages.database.session import get_session
from packages.schemas import SCHEMA_VERSION

client = TestClient(app)


def _no_database() -> object:
    """Stand in for a session on paths that reject before touching the database.

    FastAPI resolves dependencies before the handler runs, so without this override
    even a 404 for an unknown case would need a live connection. Overriding keeps the
    contract tests hermetic; the real session is exercised in the integration suite.
    """
    return object()


app.dependency_overrides[get_session] = _no_database

#: Endpoints still awaiting their phase. `POST /cases` left this list in E2.2, the
#: timeline in E4.3 and the replay in E8.2.
PENDING_ENDPOINTS = [
    ("post", f"{PREFIX}/cases/abc/reprocess"),
]


def test_health_reports_the_frozen_schema_version() -> None:
    """Assert that health reports the frozen schema version."""
    r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == SCHEMA_VERSION


def test_metrics_declares_the_specification_metric_set() -> None:
    """Assert the §N metric names are in the contract; the values are tested against a database."""
    declared = app.openapi()["components"]["schemas"]["Metrics"]["properties"]
    required = {
        "queue_depth",
        "frames_per_second",
        "tracking_id_switch_rate",
        "report_generation_latency_s",
        "evidence_coverage",
        "unsupported_claim_rate",
    }
    assert required <= set(declared)


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


def test_creating_a_case_for_unknown_media_returns_404() -> None:
    """Assert an unknown case reference is rejected with its own name in the message."""
    r = client.post(
        f"{PREFIX}/cases",
        json={"dataset_version": "v1", "case_ref": "case_99", "config_version": "v0.1.0"},
    )
    assert r.status_code == 404
    assert "case_99" in r.json()["detail"]


def test_creating_a_case_without_rendered_video_returns_409(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert a case with ground truth but no video is a conflict, not a 404.

    The distinction is useful to the caller: 404 means the case does not exist, 409
    means it exists and is not ready. Collapsing them would send someone hunting for
    a missing directory that is right there.

    The case directory is fabricated rather than borrowed from ``data/samples``. An
    earlier version of this test pointed at a real unrendered case and started
    failing the moment that case was rendered, which made a passing suite depend on
    how far the render had progressed.
    """
    unrendered = tmp_path / "case_pending"
    unrendered.mkdir()
    (unrendered / "observations_gt.json").write_text("[]")
    monkeypatch.setattr(main, "SAMPLES", tmp_path)

    r = client.post(
        f"{PREFIX}/cases",
        json={"dataset_version": "v1", "case_ref": "case_pending", "config_version": "v0.1.0"},
    )
    assert r.status_code == 409
    assert "make render" in r.json()["detail"]


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
        f"{PREFIX}/cases/{{case_id}}/media/{{camera_id}}",
        f"{PREFIX}/cases/{{case_id}}/reprocess",
        f"{PREFIX}/health",
        f"{PREFIX}/metrics",
        f"{PREFIX}/runs",
    }
    assert expected == set(spec["paths"])
