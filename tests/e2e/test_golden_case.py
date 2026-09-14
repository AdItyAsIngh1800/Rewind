"""The golden case the project is named for, end to end (E9.4, specification §L).

``case_02``: a person enters the robot lane while no camera can see them, and the
robot stops. The scene spec (§6.2) says what a correct system must do with it, and
EXP-0010/0011 measured it. This test pins those behaviours so they cannot regress
silently: the incident, the expected timeline inside its window, the gap named as a
claim, and the cause worded *Possible*, no stronger.

Perfect tracks (ray-cast ground truth as the detector), so it exercises everything
but the model and runs in CI without the ``ml`` extra. The model's own numbers live in
the benchmark reports.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import shapely
from sqlalchemy.orm import Session

from packages.database.models import ProcessingRun
from packages.evaluation.metrics import match_event_pairs
from packages.schemas import EvidenceLevel, RunStatus
from services.events import EventConfig, events_for_run, load_zones
from services.evidence import graph_for_incident
from services.incidents import list_incidents, load_case_script, state_changes
from services.perception import process_run
from services.reasoning.persistence import hypotheses_for_incident
from services.reporting import report_for_incident
from tests.integration.conftest import needs_db
from tests.integration.test_pipeline import GroundTruthDetector

CASE = "case_02"
CASE_DIR = pathlib.Path("data/samples") / CASE
SCENE = json.loads(pathlib.Path("ml/configs/scene_v1.json").read_text())
OFFSETS = {c["id"]: float(c["clock_offset_s"]) for c in SCENE["cameras"]}
#: Truth events a camera could have seen; telemetry and annotation-only rows are not
#: the extractor's to find (scene spec §6.2 marks the Z1 entry "observed by no camera").
VISIBLE = {"zone_entry", "zone_exit", "stop"}


@needs_db
def test_the_occluded_incursion_is_reconstructed_as_the_spec_requires(
    session: Session, queued_run: ProcessingRun
) -> None:
    """Run case_02 and check every behaviour the scene spec lists for it."""
    if not any(CASE_DIR.glob("*.mp4")):
        pytest.skip("case_02 video has not been rendered")
    detector = GroundTruthDetector(queued_run.run_id, CASE_DIR)
    result = process_run(
        session,
        run_id=queued_run.run_id,
        case_dir=CASE_DIR,
        camera_offsets=OFFSETS,
        detector=detector,
        scene=SCENE,
        telemetry=state_changes(
            queued_run.run_id, load_case_script(pathlib.Path("ml/configs/cases_v1.json"), CASE)
        ),
    )
    session.refresh(queued_run)
    assert queued_run.status == RunStatus.COMPLETE.value
    assert result.incidents == 1

    # 1. One e-stop incident, opened at the robot's stop, its window covering the entry.
    incidents, _ = list_incidents(session)
    (incident,) = [i for i in incidents if i.run_id == queued_run.run_id]
    truth_cause = json.loads((CASE_DIR / "cause_gt.json").read_text())
    assert incident.incident_class == truth_cause["incident_class"]
    assert abs(incident.detected_at_s - 13.5) <= 0.5
    assert incident.window_start_s <= 13.0 <= incident.window_end_s

    # 2. The expected timeline: every observable truth event inside the window has a
    #    stored event of the same kind and zone within half a second. Left out: events
    #    inside a gap (nobody saw them), and a zone event after which the entity stays
    #    within the edge margin of the boundary: F01 parks with its centre exactly on
    #    Z1's edge at 8.0 s, and the extractor declines to call settling on a line a
    #    crossing (EXP-0011, F3). That is the rule's documented cost, not a regression.
    truth = json.loads((CASE_DIR / "events_gt.json").read_text())
    gaps = json.loads((CASE_DIR / "gaps_gt.json").read_text())
    boundaries = {z.zone_id: z.polygon.boundary for z in load_zones(SCENE)}
    margin = EventConfig().zone_edge_margin_m
    positions: dict[str, list[tuple[float, shapely.Point]]] = {}
    for row in json.loads((CASE_DIR / "observations_gt.json").read_text()):
        x, y, _ = row["world_xyz"]
        positions.setdefault(row["entity_id"], []).append((row["timestamp_s"], shapely.Point(x, y)))

    def settles_on_the_edge(t: dict[str, object]) -> bool:
        """Whether the entity stays within the margin of the zone's edge for the next 3 s."""
        if t.get("zone_id") not in boundaries:
            return False
        boundary = boundaries[str(t["zone_id"])]
        stamp = float(t["timestamp_s"])  # type: ignore[arg-type]
        entity_ids = t["entity_ids"]
        assert isinstance(entity_ids, list)
        after = [
            p for e in entity_ids for s, p in positions.get(str(e), []) if stamp < s <= stamp + 3.0
        ]
        return bool(after) and all(boundary.distance(p) < margin for p in after)

    expected = [
        t
        for t in truth
        if t["event_type"] in VISIBLE
        and incident.window_start_s <= t["timestamp_s"] <= incident.window_end_s
        and not any(
            lo <= t["timestamp_s"] <= hi for e in t["entity_ids"] for lo, hi in gaps.get(e, [])
        )
        and not settles_on_the_edge(t)
    ]
    assert len(expected) == 2, (
        "F01 entering Z1 and R12 leaving Z2; the rest is unseen or on an edge"
    )
    stored = [
        {"event_type": e.event_type, "zone_id": e.zone_id, "timestamp_s": e.timestamp_s}
        for e in events_for_run(
            session,
            queued_run.run_id,
            start_s=incident.window_start_s,
            end_s=incident.window_end_s,
        )
    ]
    pairs = match_event_pairs(stored, expected, tolerance_s=0.5)
    missed = [expected[ti] for ti in set(range(len(expected))) - {ti for _, ti, _ in pairs}]
    assert not missed, f"truth events without a stored match: {missed}"

    # 3. The unseen interval is a claim, not a footnote: *Cannot determine*, citing a gap.
    report = report_for_incident(session, incident.incident_id)
    assert report is not None
    unknown = [c for c in report.claims if c.evidence_level is EvidenceLevel.UNKNOWN]
    assert unknown, "the gap around the entry must be written as a Cannot-determine claim"
    assert any(ref in report.gaps for c in unknown for ref in c.evidence_refs)
    # A cited gap must cover the true entry (about 13.0 s, cause_gt.json). Its exact
    # bounds depend on how the tracker fragments the person, so the interval is checked,
    # not the wording's numbers.
    graph = graph_for_incident(session, incident.incident_id)
    by_id = {n.node_id: n for n in graph.nodes}
    covering = [
        by_id[ref].interval_s
        for c in unknown
        for ref in c.evidence_refs
        if ref in by_id and by_id[ref].interval_s is not None
    ]
    assert any(lo <= 13.0 <= hi for lo, hi in covering), covering  # type: ignore[misc]

    # 4. The person is a ranked cause, worded *Possible* and no stronger, the wording
    #    saying the move was unseen; and nothing at all is ranked above *Possible*,
    #    because the decisive moment was seen by nobody. The person's rank against the
    #    forklift is a metric (charter §6, cause top-1), measured by the harness, not
    #    a behaviour pinned here: the person's crossing is bounded only by the window,
    #    so the ranking cannot honestly prefer it on timing.
    ranked = hypotheses_for_incident(session, incident.incident_id)
    person = [h for h in ranked if h.description.startswith("Person")]
    assert person, "the person must be ranked as a possible cause"
    assert person[0].evidence_level is EvidenceLevel.POSSIBLE
    assert "while no camera saw it" in person[0].description
    assert all(h.evidence_level is EvidenceLevel.POSSIBLE for h in ranked)
    assert not any(
        c.evidence_level in (EvidenceLevel.CONFIRMED, EvidenceLevel.STRONGLY_INFERRED)
        and "Person" in c.text
        and "entered Z1" in c.text
        for c in report.claims
    ), "the entry itself was never observed and must not be claimed as such"

    # 5. Grounded throughout.
    assert report.evidence_coverage == 1.0
