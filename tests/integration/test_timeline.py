"""The timeline endpoint against a real database."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.main import PREFIX, app
from packages.database.models import Camera, ProcessingRun
from packages.database.session import get_session
from packages.schemas import SCHEMA_VERSION, EventType, RunStatus, SemanticEvent
from services.events import write_events
from tests.integration.conftest import needs_db


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """Build an API client whose requests share the test's rolled-back session."""
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous


def _event(run_id: str, n: int, t: float, kind: EventType = EventType.ZONE_ENTRY) -> SemanticEvent:
    """Build one minimal, valid event for the run."""
    return SemanticEvent(
        schema_version=SCHEMA_VERSION,
        event_id=f"EVT-{run_id}-{n:04d}",
        run_id=run_id,
        event_type=kind,
        timestamp_s=t,
        camera_id=None,
        entity_ids=["CAM_A-T001"],
        zone_id="Z2" if kind in (EventType.ZONE_ENTRY, EventType.ZONE_EXIT) else None,
        confidence=0.9,
        evidence_refs=[f"OBS-{n}"],
        payload={"entity_class": "person"},
    )


@pytest.fixture
def run_with_events(session: Session) -> ProcessingRun:
    """Create a completed run with three events at 5, 12 and 30 seconds."""
    session.add(Camera(camera_id="CAM_A", name="A", source_uri="x", width=1, height=1, fps=10.0))
    run = ProcessingRun(
        run_id="run-timeline-test",
        input_hash="sha256:t",
        dataset_version="v1",
        config_version="t",
        status=RunStatus.COMPLETE.value,
    )
    session.add(run)
    session.flush()
    write_events(
        session,
        [
            _event(run.run_id, 1, 5.0),
            _event(run.run_id, 2, 12.0, EventType.STOP),
            _event(run.run_id, 3, 30.0, EventType.ZONE_EXIT),
        ],
    )
    return run


@needs_db
def test_timeline_of_a_run_is_ordered_and_windowed(
    client: TestClient, run_with_events: ProcessingRun
) -> None:
    """Assert the full stream comes back in time order and a window clips it."""
    body = client.get(f"{PREFIX}/cases/{run_with_events.run_id}/timeline").json()
    assert body["run_id"] == run_with_events.run_id
    assert [e["timestamp_s"] for e in body["events"]] == [5.0, 12.0, 30.0]
    assert body["segments"] == [] and body["identity_links"] == []
    # Every event validates as the frozen contract on the way out.
    assert all(SemanticEvent.model_validate(e) for e in body["events"])

    window = client.get(
        f"{PREFIX}/cases/{run_with_events.run_id}/timeline", params={"start_s": 10, "end_s": 20}
    ).json()
    assert [e["event_type"] for e in window["events"]] == ["stop"]
    assert window["start_s"] == 10.0 and window["end_s"] == 20.0


@needs_db
def test_unknown_case_is_a_404_not_an_empty_timeline(client: TestClient) -> None:
    """Assert asking for a case that does not exist is an error, not silence."""
    r = client.get(f"{PREFIX}/cases/no-such-case/timeline")
    assert r.status_code == 404
    assert "no-such-case" in r.json()["detail"]
