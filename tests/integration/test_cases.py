"""The case endpoints against a real database: the inbox, one case, and its rewind."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api import main
from apps.api.main import PREFIX
from apps.api.request_stats import requests as request_window
from packages.database.models import Camera, EvidenceAccessLog, ProcessingRun
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
from tests.accounts import ANALYST
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
            # 90 s before the report below is issued, so report latency has a known answer.
            started_at=datetime(2026, 9, 12, 23, 58, 30, tzinfo=UTC),
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


def _issue_report(session: Session) -> None:
    """Build and store the e-stop incident's graph, hypotheses and report, as a run would."""
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


@needs_db
@pytest.mark.usefixtures("cases")
def test_report_is_served_with_its_ranked_hypotheses(client: TestClient, session: Session) -> None:
    """Assert the stored report and its hypotheses come back together, and 404 without one."""
    _issue_report(session)

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


@needs_db
@pytest.mark.usefixtures("cases")
def test_metrics_measure_what_is_stored_and_leave_the_rest_unmeasured(
    client: TestClient, session: Session
) -> None:
    """Assert stored reports are measured, and what nothing observes yet is null, not zero."""
    request_window.clear()
    before = client.get(f"{PREFIX}/metrics").json()
    assert before["api_error_rate"] is None and before["api_latency_p95_ms"] is None
    assert before["evidence_coverage"] is None and before["report_generation_latency_s"] is None

    _issue_report(session)
    body = client.get(f"{PREFIX}/metrics").json()
    assert (body["evidence_coverage"], body["unsupported_claim_rate"]) == (1.0, 0.0)
    assert body["report_generation_latency_s"] == 90.0
    assert body["event_generation_rate"] is None, "no observations, so no footage to divide by"
    assert body["frames_per_second"] is None, "no run has recorded its cost"
    assert body["peak_memory_mb"] is None and body["tracking_id_switch_rate"] is None
    # The first /metrics call was served and recorded; a 404 is not a server error.
    assert client.get(f"{PREFIX}/cases/no-such-case").status_code == 404
    body = client.get(f"{PREFIX}/metrics").json()
    assert body["api_error_rate"] == 0.0 and body["api_latency_p95_ms"] is not None


@needs_db
@pytest.mark.usefixtures("cases")
def test_a_run_is_served_with_what_it_cost(client: TestClient, session: Session) -> None:
    """Assert the frames, stage seconds and memory a run recorded reach the API (ADR-0008).

    The contract is rebuilt field by field from the row, so a field added to both and
    left out of the mapping reads as null to every client without failing anything.
    """
    run = session.get(ProcessingRun, RUN)
    assert run is not None
    run.frames_processed = 1350
    run.stages_s = {"perception:CAM_A": 2.6, "events": 0.01}
    run.peak_memory_mb = 1137.0
    session.flush()
    (served,) = client.get(f"{PREFIX}/runs").json()["runs"]
    assert served["frames_processed"] == 1350
    assert served["stages_s"] == {"perception:CAM_A": 2.6, "events": 0.01}
    assert served["peak_memory_mb"] == 1137.0


@needs_db
@pytest.mark.usefixtures("cases")
def test_runs_are_listed_for_the_health_screen(client: TestClient) -> None:
    """Assert runs come back as contracts with their total, and the limit is validated."""
    body = client.get(f"{PREFIX}/runs").json()
    assert body["total"] == 1
    assert [r["run_id"] for r in body["runs"]] == [RUN]
    assert client.get(f"{PREFIX}/runs", params={"limit": 0}).status_code == 422


@needs_db
@pytest.mark.usefixtures("cases")
def test_dismissing_a_case_changes_its_status_and_nothing_else(client: TestClient) -> None:
    """Assert a dismissal is stored and filterable, keeps the window, and rejects bad input."""
    r = client.patch(f"{PREFIX}/cases/{ESTOP}", json={"status": "dismissed"})
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["window_start_s"]) == ("dismissed", 3.4)
    dismissed = client.get(f"{PREFIX}/cases", params={"status": "dismissed"}).json()
    assert [c["incident_id"] for c in dismissed["cases"]] == [ESTOP]
    assert client.patch(f"{PREFIX}/cases/{ESTOP}", json={"status": "closed"}).status_code == 422
    assert client.patch(f"{PREFIX}/cases/INC-nope", json={"status": "resolved"}).status_code == 404


@needs_db
@pytest.mark.usefixtures("cases")
def test_replay_streams_recorded_footage_and_refuses_anything_else(
    client: TestClient, session: Session, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert a recorded clip gets a pane URL and streams by range; unrecorded or outside is 404."""
    clip = tmp_path / "case_x" / "CAM_A.mp4"
    clip.parent.mkdir()
    clip.write_bytes(bytes(range(256)) * 4)
    monkeypatch.setattr(main, "SAMPLES", tmp_path)
    run = session.get(ProcessingRun, RUN)
    assert run is not None
    run.media_uris = {"CAM_A": str(clip), "CAM_B": "/etc/hosts"}
    session.flush()

    body = client.get(f"{PREFIX}/cases/{ESTOP}/replay").json()
    panes = {c["camera_id"]: c["media_url"] for c in body["cameras"]}
    assert panes["CAM_A"] == f"{PREFIX}/cases/{ESTOP}/media/CAM_A"
    assert (body["window_start_s"], body["detected_at_s"]) == (3.4, 13.4)

    part = client.get(panes["CAM_A"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and part.content == clip.read_bytes()[:100]
    assert client.get(f"{PREFIX}/cases/{ESTOP}/media/CAM_B").status_code == 404, "outside samples"
    assert client.get(f"{PREFIX}/cases/{ESTOP}/media/CAM_Z").status_code == 404, "not recorded"


@needs_db
@pytest.mark.usefixtures("cases")
def test_footage_is_the_analysts_boundary_and_every_read_is_logged(
    client: TestClient,
    session: Session,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Assert an analyst reads the report and graph but not the clip, and each read is logged.

    The log is what spec §M asks for: who read which evidence. It names the account and
    the camera, so a review of the stream can answer "who watched CAM_A of this case".
    """
    clip = tmp_path / "case_x" / "CAM_A.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"\0" * 64)
    monkeypatch.setattr(main, "SAMPLES", tmp_path)
    run = session.get(ProcessingRun, RUN)
    assert run is not None
    run.media_uris = {"CAM_A": str(clip)}
    session.flush()
    _issue_report(session)

    with caplog.at_level("INFO", logger="apps.api.auth"):
        assert client.get(f"{PREFIX}/cases/{ESTOP}/report", headers=ANALYST).status_code == 200
        assert client.get(f"{PREFIX}/cases/{ESTOP}/evidence", headers=ANALYST).status_code == 200
        assert client.get(f"{PREFIX}/cases/{ESTOP}/media/CAM_A", headers=ANALYST).status_code == 403
        assert client.get(f"{PREFIX}/cases/{ESTOP}/media/CAM_A").status_code == 200
    access = [r for r in caplog.records if getattr(r, "action", None) == "evidence.access"]
    assert [(r.user, r.resource) for r in access] == [  # type: ignore[attr-defined]
        ("analyst", "report"),
        ("analyst", "evidence"),
        ("investigator", "footage"),
    ]
    assert access[-1].camera_id == "CAM_A"  # type: ignore[attr-defined]
    assert f"read footage of case {ESTOP} camera_id=CAM_A" in access[-1].getMessage()
    rows = session.scalars(select(EvidenceAccessLog).order_by(EvidenceAccessLog.accessed_at)).all()
    assert [(r.actor, r.resource_type, r.resource_ref) for r in rows] == [
        ("analyst", "report", ESTOP),
        ("analyst", "evidence", ESTOP),
        ("investigator", "footage", "CAM_A"),
    ], "the audit table, not only the log, has every read"
