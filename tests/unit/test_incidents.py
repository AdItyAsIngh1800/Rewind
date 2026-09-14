"""Incident triggers fire on both MVP classes, open the right window, and are otherwise silent."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from packages.schemas import SCHEMA_VERSION, EventType, IncidentClass, SemanticEvent, Severity
from services.events import load_zones
from services.incidents import IncidentConfig, detect_incidents, state_changes

ZONES = load_zones(json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text()))
RUN_END = 44.9


def _event(n: int, kind: EventType, t: float, **payload: Any) -> SemanticEvent:
    """Build one minimal merged event."""
    return SemanticEvent(
        schema_version=SCHEMA_VERSION,
        event_id=f"EVT-r-{n:04d}",
        run_id="r",
        event_type=kind,
        timestamp_s=t,
        entity_ids=[f"T{n}"],
        zone_id="Z2" if kind in (EventType.ZONE_ENTRY, EventType.ZONE_EXIT) else None,
        confidence=0.9,
        evidence_refs=[f"OBS-{n}"],
        payload=payload,
    )


def _estop(t: float = 13.4) -> SemanticEvent:
    return _event(
        1,
        EventType.STATE_CHANGE,
        t,
        entity_class="robot",
        to="estop",
        source="telemetry",
        **{"from": "moving"},
    )


def test_robot_state_channel_becomes_telemetry_events() -> None:
    """Only state changes are emitted; a person's script contributes nothing."""
    case = {
        "actors": [
            {
                "entity_id": "R12",
                "class": "robot",
                "waypoints": [
                    {"t": 0.0, "state": "moving"},
                    {"t": 11.4, "state": "moving"},
                    {"t": 13.4, "state": "estop"},
                    {"t": 24.0, "state": "idle"},
                ],
            },
            {"entity_id": "P01", "class": "person", "waypoints": [{"t": 0.0, "x": 1, "y": 1}]},
        ]
    }
    events = state_changes("r", case)
    assert [(e.timestamp_s, e.payload["to"]) for e in events] == [(13.4, "estop"), (24.0, "idle")]
    assert all(e.evidence_refs and e.entity_ids == ["R12"] for e in events)
    assert "x" not in events[0].payload, "telemetry must not carry script positions"


def test_estop_opens_a_symmetric_high_severity_window() -> None:
    """Scene spec §6.1: the trigger is the stop, rewound ten seconds either side."""
    [incident] = detect_incidents("r", [_estop()], ZONES, RUN_END)
    assert incident.incident_class is IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION
    assert incident.severity is Severity.HIGH
    assert incident.trigger_event_id == "EVT-r-0001"
    assert (
        incident.window_start_s,
        incident.detected_at_s,
        incident.window_end_s,
    ) == pytest.approx((3.4, 13.4, 23.4))


def test_leaving_estop_is_not_an_incident() -> None:
    """Recovering from a stop is not a second incident."""
    recover = _event(
        2, EventType.STATE_CHANGE, 24.0, entity_class="robot", to="idle", **{"from": "estop"}
    )
    assert detect_incidents("r", [recover], ZONES, RUN_END) == []


def test_window_is_clipped_to_the_recording() -> None:
    """A stop near the end cannot rewind into footage after the clip."""
    [incident] = detect_incidents("r", [_estop(40.0)], ZONES, RUN_END)
    assert incident.window_end_s == RUN_END


def test_pallet_left_in_keep_clear_zone_fires_at_the_threshold() -> None:
    """Scene spec §6.4: dropped at 14 s, fires at 34 s, window reaches back past the drop."""
    stop = _event(3, EventType.STOP, 14.0, entity_class="pallet", duration_s=30.9, x=12.0, y=8.0)
    [incident] = detect_incidents("r", [stop], ZONES, RUN_END)
    assert incident.incident_class is IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT
    assert incident.severity is Severity.MEDIUM
    assert incident.detected_at_s == pytest.approx(34.0)
    assert incident.window_start_s == pytest.approx(4.0) and incident.window_start_s < 14.0
    assert incident.window_end_s == pytest.approx(44.0)


@pytest.mark.parametrize(
    ("entity_class", "duration", "xy"),
    [
        ("pallet", 15.0, (12.0, 8.0)),  # dwell below threshold
        ("person", 30.0, (12.0, 8.0)),  # people stop in traffic; not an obstruction
        ("pallet", 30.0, (3.0, 0.5)),  # left in the loading bay, not a keep-clear zone
    ],
)
def test_stops_that_are_not_obstructions_stay_silent(
    entity_class: str, duration: float, xy: tuple[float, float]
) -> None:
    """Short dwells, people and objects outside keep-clear zones do not fire."""
    stop = _event(
        4, EventType.STOP, 14.0, entity_class=entity_class, duration_s=duration, x=xy[0], y=xy[1]
    )
    assert detect_incidents("r", [stop], ZONES, RUN_END) == []


def test_one_pallet_seen_by_two_cameras_is_one_incident() -> None:
    """Unmerged per-camera stops of the same object overlap in time and zone."""
    a = _event(5, EventType.STOP, 14.0, entity_class="pallet", duration_s=30.9, x=12.0, y=8.0)
    b = _event(6, EventType.STOP, 15.2, entity_class="pallet", duration_s=29.7, x=12.1, y=8.1)
    assert len(detect_incidents("r", [a, b], ZONES, RUN_END)) == 1


def test_near_miss_stream_opens_nothing() -> None:
    """Scene spec §6.5: zone entry, proximity and a stopped person, but no e-stop."""
    stream = [
        _event(7, EventType.ZONE_ENTRY, 8.0, entity_class="person"),
        _event(8, EventType.PROXIMITY, 18.5, entity_class="person", distance_m=2.1),
        _event(9, EventType.STOP, 9.0, entity_class="person", duration_s=11.0, x=12.0, y=10.2),
    ]
    assert detect_incidents("r", stream, ZONES, RUN_END) == []


def test_config_version_names_every_window_value() -> None:
    """A run's incident list must be traceable to the values that produced it."""
    assert IncidentConfig().version == "incidents:estop10/10:dwell20+10/10:zonesZ2"


def test_window_reaches_back_to_the_object_first_rest() -> None:
    """Scene spec §6.6: set down, nudged, set down again; the window opens before the first rest."""
    first = _event(
        7, EventType.STOP, 20.3, entity_class="pallet", duration_s=11.7, end_s=32.0, x=11.0, y=6.2
    )
    final = _event(
        8, EventType.STOP, 34.1, entity_class="pallet", duration_s=20.8, end_s=54.9, x=12.0, y=7.5
    )
    # Ended 15 s before the first rest: moved for longer than the pre-margin, another obstruction.
    unrelated = _event(
        9, EventType.STOP, 2.0, entity_class="pallet", duration_s=3.0, end_s=5.0, x=11.0, y=6.5
    )
    [incident] = detect_incidents("r", [unrelated, first, final], ZONES, 60.0)
    assert incident.detected_at_s == pytest.approx(54.1)
    assert incident.window_start_s == pytest.approx(10.3), (
        "10 s before the first rest, not the last"
    )
