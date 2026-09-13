"""The case endpoints against a real database: the inbox, one case, and its rewind."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.main import PREFIX
from packages.database.models import Camera, ProcessingRun
from packages.database.models import Incident as IncidentRow
from packages.schemas import (
    SCHEMA_VERSION,
    EventType,
    Incident,
    IncidentClass,
    IncidentStatus,
    RunStatus,
    SemanticEvent,
    Severity,
)
from services.events import write_events
from services.evidence import build_graph, write_graph
from services.incidents import incident_to_contract, write_incidents
from services.reasoning.hypotheses import rank_hypotheses
from services.reasoning.persistence import write_hypotheses
from services.reporting import generate_report, write_report
from tests.integration.conftest import needs_db

RUN = "run-cases-test"
ESTOP = f"INC-{RUN}-01"
BLOCKED = f"INC-{RUN}-02"


def _event(n: int, kind: EventType, t: float) -> SemanticEvent:
    """Build one minimal event for the run."""
    return SemanticEvent(
        schema_version=SCHEMA_VERSION,
        event_id=f"EVT-{RUN}-{n:04d}",
        run_id=RUN,
        event_type=kind,
        timestamp_s=t,
        entity_ids=["R12"],
        zone_id="Z2" if kind is EventType.ZONE_ENTRY else None,
        confidence=1.0,
        evidence_refs=[f"OBS-{n}"],
    )


@pytest.fixture
def cases(session: Session) -> None:
    """Create a completed run with an e-stop incident (high) and a blocked zone (medium)."""
    for camera_id in ("CAM_B", "CAM_A"):
        session.add(
            Camera(camera_id=camera_id, name=camera_id, source_uri="x", width=1, height=1, fps=10.0)
        )
    session.add(
        ProcessingRun(
            run_id=RUN,
            input_hash="sha256:t",
            dataset_version="v1",
            model_versions={"detector": "d"},
            config_version="t",
            status=RunStatus.COMPLETE.value,
        )
    )
    session.flush()
    write_events(
        session,
        [
            _event(1, EventType.ZONE_ENTRY, 5.0),
            _event(2, EventType.STATE_CHANGE, 13.4),
            _event(3, EventType.STOP, 14.0),
            _event(4, EventType.STOP, 40.0),
        ],
    )
    write_incidents(
        session,
        [
            Incident(
                incident_id=BLOCKED,
                run_id=RUN,
                incident_class=IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT,
                trigger_event_id=f"EVT-{RUN}-0003",
                detected_at_s=34.0,
                window_start_s=4.0,
                window_end_s=44.0,
                severity=Severity.MEDIUM,
                status=IncidentStatus.INVESTIGATING,
            ),
            Incident(
                incident_id=ESTOP,
                run_id=RUN,
                incident_class=IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION,
                trigger_event_id=f"EVT-{RUN}-0002",
                detected_at_s=13.4,
                window_start_s=3.4,
                window_end_s=23.4,
                severity=Severity.HIGH,
            ),
        ],
    )


@needs_db
@pytest.mark.usefixtures("cases")
def test_inbox_lists_most_severe_first_and_filters(client: TestClient) -> None:
    """Assert triage order and that severity and status filters narrow the list."""
    body = client.get(f"{PREFIX}/cases").json()
    assert body["total"] == 2
    assert [c["incident_id"] for c in body["cases"]] == [ESTOP, BLOCKED]
    assert all(Incident.model_validate(c) for c in body["cases"])

    medium = client.get(f"{PREFIX}/cases", params={"severity": "medium"}).json()
    assert [c["incident_id"] for c in medium["cases"]] == [BLOCKED]
    investigating = client.get(f"{PREFIX}/cases", params={"status": "investigating"}).json()
    assert investigating["total"] == 1
    assert client.get(f"{PREFIX}/cases", params={"severity": "urgent"}).status_code == 422


@needs_db
@pytest.mark.usefixtures("cases")
def test_one_case_carries_its_run_and_cameras(client: TestClient) -> None:
    """Assert the case detail joins the incident, its run and the cameras in id order."""
    body = client.get(f"{PREFIX}/cases/{ESTOP}").json()
    assert body["incident"]["window_start_s"] == 3.4
    assert body["run"]["run_id"] == RUN and body["run"]["status"] == "complete"
    assert [c["camera_id"] for c in body["cameras"]] == ["CAM_A", "CAM_B"]
    assert client.get(f"{PREFIX}/cases/INC-nope").status_code == 404


@needs_db
@pytest.mark.usefixtures("cases")
def test_opening_a_case_rewinds_to_its_window(client: TestClient) -> None:
    """Assert a case timeline defaults to the incident window and an explicit one wins."""
    rewind = client.get(f"{PREFIX}/cases/{ESTOP}/timeline").json()
    assert (rewind["start_s"], rewind["end_s"]) == (3.4, 23.4)
    assert [e["timestamp_s"] for e in rewind["events"]] == [5.0, 13.4, 14.0]

    widened = client.get(
        f"{PREFIX}/cases/{ESTOP}/timeline", params={"start_s": 0, "end_s": 45}
    ).json()
    assert len(widened["events"]) == 4


@needs_db
@pytest.mark.usefixtures("cases")
def test_evidence_graph_is_served_with_provenance(client: TestClient, session: Session) -> None:
    """Assert a stored graph comes back whole, every node and edge validated, and 404s."""
    row = session.get(IncidentRow, ESTOP)
    assert row is not None
    graph = build_graph(
        incident_to_contract(row),
        events=[_event(2, EventType.STATE_CHANGE, 13.4)],
        observations=[],
        segments=[],
        links=[],
        groups={},
        zones=[],
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    write_graph(session, graph)

    body = client.get(f"{PREFIX}/cases/{ESTOP}/evidence").json()
    assert {n["node_id"] for n in body["nodes"]} == {n.node_id for n in graph.nodes}
    assert len(body["edges"]) == len(graph.edges) > 0
    assert all(n["provenance"]["run_id"] == RUN for n in body["nodes"])
    assert client.get(f"{PREFIX}/cases/INC-nope/evidence").status_code == 404


@needs_db
@pytest.mark.usefixtures("cases")
def test_report_is_served_with_its_ranked_hypotheses(client: TestClient, session: Session) -> None:
    """Assert the stored report and its hypotheses come back together, and 404 without one."""
    row = session.get(IncidentRow, ESTOP)
    assert row is not None
    incident = incident_to_contract(row)
    built_at = datetime(2026, 9, 13, tzinfo=UTC)
    events = [_event(2, EventType.STATE_CHANGE, 13.4)]
    graph = build_graph(
        incident,
        events=events,
        observations=[],
        segments=[],
        links=[],
        groups={},
        zones=[],
        created_at=built_at,
    )
    hypotheses = rank_hypotheses(incident, graph, events, [], built_at)
    write_graph(session, graph)
    write_hypotheses(session, hypotheses)
    write_report(session, generate_report(incident, graph, hypotheses, events, built_at))

    body = client.get(f"{PREFIX}/cases/{ESTOP}/report").json()
    assert (
        body["report"]["claims"][0]["text"]
        == "Observed: robot R12 reported an emergency stop at 13.4 s"
    )
    assert [h["hypothesis_id"] for h in body["hypotheses"]] == body["report"]["ranked_hypotheses"]
    assert body["hypotheses"][0]["evidence_level"] == "unknown", (
        "no candidate, so no cause is claimed"
    )
    assert client.get(f"{PREFIX}/cases/{BLOCKED}/report").status_code == 404
