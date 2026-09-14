"""Incident triggers (E6.1) and the rewind window each one opens (E6.2).

Both MVP classes are deterministic rules over the merged event stream. A rule can be
read, tested and argued with; an incident a model decided on cannot be audited.

- **Class 1, robot e-stop.** A robot's telemetry reports a change *into* ``estop``.
  Why it stopped is not decided here: that is the hypothesis ranking of E7.2, and a
  trigger that also named the cause would be asserting it without evidence.
- **Class 2, blocked keep-clear zone.** A pallet or forklift stands still inside a
  keep-clear zone for the dwell threshold. The incident is detected at the moment the
  threshold is crossed, not when the object stopped.

The window is not symmetric for class 2. The cause of a blocked zone is the placement,
a whole dwell before the trigger; a window of ten seconds either side of the trigger
would rewind to a stationary pallet and miss the forklift that left it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import shapely

from packages.schemas import (
    SCHEMA_VERSION,
    EventType,
    Incident,
    IncidentClass,
    SemanticEvent,
    Severity,
)
from services.events import Zone

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncidentConfig:
    """Every value that decides whether, when and how wide an incident is opened."""

    estop_pre_s: float = 10.0
    estop_post_s: float = 10.0
    #: Scene spec §6.4: a pallet left in the intersection past 20 s is an obstruction.
    dwell_threshold_s: float = 20.0
    #: How far before the object stopped the class 2 window reaches, so the rewind
    #: shows it arriving and whoever left it, not only the dwell.
    dwell_pre_margin_s: float = 10.0
    dwell_post_s: float = 10.0
    keep_clear_zones: tuple[str, ...] = ("Z2",)
    #: People and robots stop in the intersection as part of normal traffic, which is
    #: exactly what the `C05` near-miss does; only objects can be left there.
    obstruction_classes: tuple[str, ...] = ("pallet", "forklift")
    #: A person was in a robot's path: higher than an obstruction nobody has met yet.
    estop_severity: Severity = Severity.HIGH
    blocked_severity: Severity = Severity.MEDIUM

    @property
    def version(self) -> str:
        """Identifier recorded on the run so an incident list is reproducible."""
        return (
            f"incidents:estop{self.estop_pre_s:g}/{self.estop_post_s:g}"
            f":dwell{self.dwell_threshold_s:g}+{self.dwell_pre_margin_s:g}/{self.dwell_post_s:g}"
            f":zones{','.join(self.keep_clear_zones)}"
        )


@dataclass(frozen=True)
class _Candidate:
    incident_class: IncidentClass
    trigger: SemanticEvent
    detected_at_s: float
    window_start_s: float
    window_end_s: float
    severity: Severity


def _first_rest(
    events: Sequence[SemanticEvent],
    trigger: SemanticEvent,
    zone_id: str,
    polygon: shapely.Polygon,
    cfg: IncidentConfig,
) -> float:
    """Return when the object first came to rest in the zone, walking back through earlier stops.

    An object that was set down, nudged and set down again triggers on its last rest, and
    a window measured from that rest cuts off whoever placed it first (EXP-0010, F7). Any
    earlier stop of the same class in the same zone that ended within the pre-margin of
    the next one is the same obstruction, moved; the window opens before the earliest.
    Events carry track ids, not identities, so the chain is by class and place.
    """
    earliest = trigger.timestamp_s
    stops = sorted(
        (
            e
            for e in events
            if e.event_type is EventType.STOP
            and e.payload.get("entity_class") == trigger.payload.get("entity_class")
            and e.timestamp_s < trigger.timestamp_s
        ),
        key=lambda e: e.timestamp_s,
        reverse=True,
    )
    for e in stops:
        end = _number(e.payload.get("end_s"))
        x, y = _number(e.payload.get("x")), _number(e.payload.get("y"))
        if end is None or x is None or y is None or not polygon.covers(shapely.Point(x, y)):
            continue
        if end < earliest - cfg.dwell_pre_margin_s:
            continue
        earliest = min(earliest, e.timestamp_s)
    return earliest


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def detect_incidents(
    run_id: str,
    events: Sequence[SemanticEvent],
    zones: Sequence[Zone],
    run_end_s: float,
    config: IncidentConfig | None = None,
) -> list[Incident]:
    """Find every incident in a run's event stream and open its investigation window.

    Windows are clipped to ``[0, run_end_s]``: a rewind cannot show footage that was
    never recorded, and claiming it would put an interval in the report that no
    camera covered for a reason unrelated to occlusion.
    """
    cfg = config or IncidentConfig()
    keep_clear = {z.zone_id: z.polygon for z in zones if z.zone_id in cfg.keep_clear_zones}
    candidates: list[_Candidate] = []
    # (zone, stop start, stop end) of each obstruction already opened. Stops of one
    # object seen by several cameras can survive the merge as separate events when
    # their start times differ by more than its tolerance; they are one incident.
    obstructions: list[tuple[str, float, float]] = []

    for event in sorted(events, key=lambda e: (e.timestamp_s, e.event_id)):
        if (
            event.event_type is EventType.STATE_CHANGE
            and event.payload.get("to") == "estop"
            and event.payload.get("from") != "estop"
        ):
            t = event.timestamp_s
            candidates.append(
                _Candidate(
                    IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION,
                    event,
                    t,
                    t - cfg.estop_pre_s,
                    t + cfg.estop_post_s,
                    cfg.estop_severity,
                )
            )
            continue

        if (
            event.event_type is not EventType.STOP
            or event.payload.get("entity_class") not in cfg.obstruction_classes
        ):
            continue
        duration = _number(event.payload.get("duration_s"))
        x, y = _number(event.payload.get("x")), _number(event.payload.get("y"))
        if duration is None or x is None or y is None or duration < cfg.dwell_threshold_s:
            continue
        zone_id = next(
            (z for z, poly in keep_clear.items() if poly.covers(shapely.Point(x, y))), None
        )
        if zone_id is None:
            continue
        start, end = event.timestamp_s, event.timestamp_s + duration
        if any(z == zone_id and s < end and start < e for z, s, e in obstructions):
            continue
        obstructions.append((zone_id, start, end))
        first_rest = _first_rest(events, event, zone_id, keep_clear[zone_id], cfg)
        candidates.append(
            _Candidate(
                IncidentClass.ZONE_BLOCKED_UNATTENDED_OBJECT,
                event,
                start + cfg.dwell_threshold_s,
                first_rest - cfg.dwell_pre_margin_s,
                start + cfg.dwell_threshold_s + cfg.dwell_post_s,
                cfg.blocked_severity,
            )
        )

    incidents: list[Incident] = []
    for c in sorted(candidates, key=lambda c: (c.detected_at_s, c.trigger.event_id)):
        start, end = max(0.0, c.window_start_s), min(run_end_s, c.window_end_s)
        if not start <= c.detected_at_s <= end or end <= start:
            log.warning(
                "run %s: %s at %.1f s falls outside the recorded %.1f s; not opened",
                run_id,
                c.incident_class.value,
                c.detected_at_s,
                run_end_s,
            )
            continue
        incidents.append(
            Incident(
                schema_version=SCHEMA_VERSION,
                incident_id=f"INC-{run_id}-{len(incidents) + 1:02d}",
                run_id=run_id,
                incident_class=c.incident_class,
                trigger_event_id=c.trigger.event_id,
                detected_at_s=round(c.detected_at_s, 3),
                window_start_s=round(start, 3),
                window_end_s=round(end, 3),
                severity=c.severity,
            )
        )
    return incidents
