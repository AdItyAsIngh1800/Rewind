"""Robot telemetry: the state channel a robot reports about itself.

The ESTOP that triggers incident class 1 is read from this channel, never inferred
from video (scene spec §5). A real robot reports its own stop; inferring one from
velocity would make the trigger depend on the tracker.

In the simulated dataset the channel is the ``state`` field on a robot's scripted
waypoints in ``ml/configs/cases_v1.json``, the same source the renderer wrote the
ground-truth state changes from. Only that field is read. The positions in the same
script are ground truth, and a processing run must never see them.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from packages.schemas import SCHEMA_VERSION, EventType, SemanticEvent


def load_case_script(cases_config: pathlib.Path, case_id: str) -> dict[str, Any]:
    """Return one case's script from the cases config.

    Raises:
        KeyError: if the config has no case with that id.

    """
    for case in json.loads(cases_config.read_text())["cases"]:
        if case["id"] == case_id:
            return dict(case)
    raise KeyError(f"no case {case_id!r} in {cases_config}")


def state_changes(run_id: str, case: dict[str, Any]) -> list[SemanticEvent]:
    """One ``STATE_CHANGE`` event per change on any actor's state channel, in time order.

    The evidence reference is the telemetry record itself, ``telemetry:<entity>:<t>``.
    Every stored event cites something (E4.2), and a state report has no pixels to cite;
    the prefix tells the evidence graph (E7.1) which kind of source it is.
    """
    changes: list[tuple[float, str, str, str, str]] = []
    for actor in case["actors"]:
        previous: str | None = None
        for waypoint in actor["waypoints"]:
            state = waypoint.get("state")
            if state is None:
                continue
            if previous is not None and state != previous:
                changes.append(
                    (float(waypoint["t"]), actor["entity_id"], actor["class"], previous, state)
                )
            previous = state

    return [
        SemanticEvent(
            schema_version=SCHEMA_VERSION,
            event_id=f"EVT-{run_id}-TEL-{n:04d}",
            run_id=run_id,
            event_type=EventType.STATE_CHANGE,
            timestamp_s=t,
            camera_id=None,
            entity_ids=[entity_id],
            confidence=1.0,
            evidence_refs=[f"telemetry:{entity_id}:{t:g}"],
            payload={"entity_class": entity_class, "from": old, "to": new, "source": "telemetry"},
        )
        for n, (t, entity_id, entity_class, old, new) in enumerate(sorted(changes), start=1)
    ]
