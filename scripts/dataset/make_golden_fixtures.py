"""Generate the golden fixture set from the frozen contracts.

One small, internally consistent incident described at every pipeline boundary. The
fixtures are built by instantiating the Pydantic contracts rather than by hand-writing
JSON, so they cannot drift out of shape: if a contract changes, this script fails at
the point of construction rather than producing a file that silently no longer
validates.

The scenario is a compressed `C01 ESTOP_CLEAN` with one deliberate addition — a
2.4 second occlusion gap on CAM_C. That gap is why this fixture is useful: it makes
every evidence level representable, so the frontend can build the uncertainty UI in
Week 4 without waiting for the perception pipeline.

    uv run python scripts/dataset/make_golden_fixtures.py
"""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import UTC, datetime

from packages.schemas import (
    BBox,
    Camera,
    Claim,
    EntityClass,
    EventType,
    EvidenceEdge,
    EvidenceLevel,
    EvidenceNode,
    Hypothesis,
    IdentityLink,
    Incident,
    IncidentClass,
    IncidentStatus,
    LinkDecision,
    NodeType,
    Observation,
    ProcessingRun,
    Provenance,
    Relation,
    Report,
    RunStatus,
    SemanticEvent,
    Severity,
    TrackSegment,
)
from services.observability.logging import configure_logging

log = logging.getLogger(__name__)

OUT = pathlib.Path("tests/fixtures/golden")

RUN_ID = "RUN-GOLD-001"
INCIDENT_ID = "INC-0001"
CREATED = datetime(2026, 9, 9, 10, 32, 10, tzinfo=UTC)

#: The trigger. Everything in the scenario is positioned relative to this instant.
ESTOP_S = 13.4

#: CAM_C loses sight of the intersection across this interval. The gap is the point.
GAP_START_S, GAP_END_S = 12.0, 14.4


def _prov(service: str, derived_from: list[str] | None = None) -> Provenance:
    """Build a provenance record for a derived artefact.

    Every evidence node and edge carries one. Without provenance the graph is a set
    of assertions; with it, the graph is auditable.
    """
    return Provenance(
        producer_service=service,
        producer_version="0.1.0",
        run_id=RUN_ID,
        derived_from=derived_from or [],
        created_at=CREATED,
    )


def build_cameras() -> list[Camera]:
    """Build the three cameras, including their injected clock offsets."""
    return [
        Camera(
            camera_id="CAM_A",
            name="North-west aisle",
            source_uri="file://data/samples/gold/CAM_A.mp4",
            clock_offset_s=0.0,
            width=1280,
            height=720,
            fps=10.0,
        ),
        Camera(
            camera_id="CAM_B",
            name="East end, looking west",
            source_uri="file://data/samples/gold/CAM_B.mp4",
            clock_offset_s=0.4,
            width=1280,
            height=720,
            fps=10.0,
        ),
        Camera(
            camera_id="CAM_C",
            name="Intersection overhead",
            source_uri="file://data/samples/gold/CAM_C.mp4",
            clock_offset_s=-0.2,
            width=1280,
            height=720,
            fps=10.0,
        ),
    ]


def build_run() -> ProcessingRun:
    """Build the processing run that every other record is stamped with."""
    return ProcessingRun(
        run_id=RUN_ID,
        input_hash="sha256:0000golden0000fixture0000set0000000000000000000000000000000000",
        dataset_version="golden-v1",
        model_versions={"detector": "yolo11n-ft-0.1.0", "tracker": "bytetrack-0.1.0"},
        config_version="v0.1.0",
        status=RunStatus.COMPLETE,
        device="mps",
        started_at=CREATED,
        finished_at=CREATED,
    )


def build_observations() -> list[Observation]:
    """Build a sparse observation trace for the person and the robot.

    Deliberately sparse — twelve rows, not thousands. A fixture exists to pin the
    shape of the data and to give the frontend something to render, not to stand in
    for a dataset.

    The CAM_C rows stop at the gap and resume after it. Ground truth must not claim
    to see what a camera cannot, otherwise the occlusion reads as a detector failure
    rather than as the evidence gap it is.
    """
    rows: list[Observation] = []
    n = 0

    def add(
        camera: str, t: float, cls: EntityClass, entity: str, box: tuple[float, ...], vis: float
    ) -> None:
        nonlocal n
        n += 1
        rows.append(
            Observation(
                observation_id=f"OBS-{n:04d}",
                run_id=RUN_ID,
                camera_id=camera,
                frame_index=int(t * 10),
                timestamp_s=t,
                entity_class=cls,
                bbox=BBox(x1=box[0], y1=box[1], x2=box[2], y2=box[3]),
                confidence=0.94,
                track_id=f"{camera}-{entity}",
                entity_id=entity,
                visibility=vis,
            )
        )

    # Person approaching the lane, seen from CAM_A throughout.
    for i, t in enumerate([11.5, 12.2, 12.8, 13.4, 14.0]):
        x = 620 + i * 14
        add("CAM_A", t, EntityClass.PERSON, "P01", (x, 300, x + 58, 470), 1.0)

    # Robot travelling east, seen from CAM_B.
    for i, t in enumerate([12.2, 12.8, 13.4, 14.0]):
        x = 540 - i * 22
        add("CAM_B", t, EntityClass.ROBOT, "R12", (x, 380, x + 96, 470), 1.0)

    # CAM_C sees the intersection before the gap, then again after it.
    add("CAM_C", 11.5, EntityClass.PERSON, "P01", (700, 250, 760, 420), 0.9)
    add("CAM_C", 11.5, EntityClass.ROBOT, "R12", (430, 300, 530, 392), 0.9)
    add("CAM_C", 14.4, EntityClass.ROBOT, "R12", (600, 300, 700, 392), 0.85)

    return rows


def build_segments(observations: list[Observation]) -> list[TrackSegment]:
    """Group observations into per-camera track segments."""
    segments: list[TrackSegment] = []
    buckets: dict[tuple[str, str], list[Observation]] = {}
    for obs in observations:
        buckets.setdefault((obs.camera_id, obs.entity_id or "?"), []).append(obs)

    for (camera, entity), group in buckets.items():
        group.sort(key=lambda o: o.timestamp_s)
        segments.append(
            TrackSegment(
                segment_id=f"SEG-{camera[-1]}-{entity}",
                run_id=RUN_ID,
                camera_id=camera,
                local_track_id=f"{camera}-{entity}",
                entity_class=group[0].entity_class,
                start_time_s=group[0].timestamp_s,
                end_time_s=group[-1].timestamp_s,
                observation_ids=[o.observation_id for o in group],
                mean_confidence=round(sum(o.confidence for o in group) / len(group), 3),
            )
        )
    segments.sort(key=lambda s: s.segment_id)
    return segments


def build_identity_links() -> list[IdentityLink]:
    """Build one accepted cross-camera link and one deliberate refusal.

    The refusal is the more important of the two. A pipeline that always links has
    not solved identity, it has only moved its error rate somewhere less visible, so
    the fixture carries a recorded `UNKNOWN` to make that state renderable.
    """
    return [
        IdentityLink(
            link_id="LNK-0001",
            run_id=RUN_ID,
            segment_a="SEG-A-P01",
            segment_b="SEG-C-P01",
            decision=LinkDecision.LINKED,
            score=0.91,
            threshold=0.75,
            components={"temporal": 0.98, "appearance": 0.88, "geometric": 0.87},
            evidence_refs=["OBS-0001", "OBS-0010"],
        ),
        IdentityLink(
            link_id="LNK-0002",
            run_id=RUN_ID,
            segment_a="SEG-B-R12",
            segment_b="SEG-C-P01",
            decision=LinkDecision.UNKNOWN,
            score=0.18,
            threshold=0.75,
            components={"temporal": 0.40, "appearance": 0.05, "geometric": 0.11},
            evidence_refs=["OBS-0006", "OBS-0010"],
        ),
    ]


def build_events() -> list[SemanticEvent]:
    """Build the semantic event timeline, including the occlusion interval."""
    return [
        SemanticEvent(
            event_id="EVT-0001",
            run_id=RUN_ID,
            event_type=EventType.ZONE_EXIT,
            timestamp_s=6.0,
            # No camera_id and no evidence refs: Z3 is covered by no camera, so this
            # is an annotated fact about what happened rather than an observation.
            # A system that reports it as observed has invented it.
            camera_id=None,
            entity_ids=["P01"],
            zone_id="Z3",
            confidence=0.0,
            evidence_refs=[],
        ),
        SemanticEvent(
            event_id="EVT-0002",
            run_id=RUN_ID,
            event_type=EventType.ZONE_ENTRY,
            timestamp_s=11.5,
            camera_id="CAM_C",
            entity_ids=["P01"],
            zone_id="Z2",
            confidence=0.93,
            evidence_refs=["OBS-0010"],
        ),
        SemanticEvent(
            event_id="EVT-0003",
            run_id=RUN_ID,
            event_type=EventType.OCCLUSION_START,
            timestamp_s=GAP_START_S,
            camera_id="CAM_C",
            entity_ids=["P01", "R12"],
            confidence=0.88,
            evidence_refs=["OBS-0011"],
            payload={"cause": "forklift F01 parked at (13.0, 11.0)"},
        ),
        SemanticEvent(
            event_id="EVT-0004",
            run_id=RUN_ID,
            event_type=EventType.ZONE_ENTRY,
            timestamp_s=12.8,
            camera_id="CAM_A",
            entity_ids=["P01"],
            zone_id="Z1",
            confidence=0.90,
            evidence_refs=["OBS-0003"],
        ),
        SemanticEvent(
            event_id="EVT-0005",
            run_id=RUN_ID,
            event_type=EventType.PROXIMITY,
            timestamp_s=13.0,
            entity_ids=["P01", "R12"],
            confidence=0.86,
            evidence_refs=["OBS-0003", "OBS-0007"],
            payload={"separation_m": 1.6, "closing": True},
        ),
        SemanticEvent(
            event_id="EVT-0006",
            run_id=RUN_ID,
            event_type=EventType.STATE_CHANGE,
            timestamp_s=ESTOP_S,
            entity_ids=["R12"],
            confidence=1.0,
            evidence_refs=["OBS-0008"],
            payload={"from": "moving", "to": "estop", "source": "telemetry"},
        ),
        SemanticEvent(
            event_id="EVT-0007",
            run_id=RUN_ID,
            event_type=EventType.OCCLUSION_END,
            timestamp_s=GAP_END_S,
            camera_id="CAM_C",
            entity_ids=["R12"],
            confidence=0.85,
            evidence_refs=["OBS-0012"],
        ),
    ]


def build_incident() -> Incident:
    """Build the incident and the rewind window opened around it."""
    return Incident(
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        incident_class=IncidentClass.ROBOT_ESTOP_HUMAN_INCURSION,
        trigger_event_id="EVT-0006",
        detected_at_s=ESTOP_S,
        window_start_s=ESTOP_S - 10.0,
        window_end_s=ESTOP_S + 10.0,
        severity=Severity.HIGH,
        status=IncidentStatus.INVESTIGATING,
    )


def build_graph() -> tuple[list[EvidenceNode], list[EvidenceEdge]]:
    """Build the evidence graph, including the gap node.

    The gap node is not bookkeeping. It is what allows the report to say "cannot
    determine" about a specific interval instead of quietly omitting it, and it is
    what the Evidence Gap View renders.
    """
    nodes = [
        EvidenceNode(
            node_id="NODE-E-P01",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            node_type=NodeType.ENTITY,
            label="Worker P01",
            provenance=_prov("identity", ["SEG-A-P01", "SEG-C-P01"]),
        ),
        EvidenceNode(
            node_id="NODE-E-R12",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            node_type=NodeType.ENTITY,
            label="Robot R12",
            provenance=_prov("identity", ["SEG-B-R12"]),
        ),
        EvidenceNode(
            node_id="NODE-V-ZONE1",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            node_type=NodeType.EVENT,
            label="P01 entered robot lane Z1",
            timestamp_s=12.8,
            source_ref="EVT-0004",
            confidence=0.90,
            provenance=_prov("events", ["EVT-0004"]),
        ),
        EvidenceNode(
            node_id="NODE-V-PROX",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            node_type=NodeType.EVENT,
            label="Separation 1.6 m and closing",
            timestamp_s=13.0,
            source_ref="EVT-0005",
            confidence=0.86,
            provenance=_prov("events", ["EVT-0005"]),
        ),
        EvidenceNode(
            node_id="NODE-V-ESTOP",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            node_type=NodeType.EVENT,
            label="R12 state changed to ESTOP",
            timestamp_s=ESTOP_S,
            source_ref="EVT-0006",
            confidence=1.0,
            provenance=_prov("events", ["EVT-0006"]),
        ),
        EvidenceNode(
            node_id="NODE-GAP-CAMC",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            node_type=NodeType.GAP,
            label="CAM_C occluded by forklift F01",
            interval_s=(GAP_START_S, GAP_END_S),
            confidence=0.88,
            provenance=_prov("reasoning", ["EVT-0003", "EVT-0007"]),
        ),
    ]

    edges = [
        EvidenceEdge(
            edge_id="EDGE-0001",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            from_node="NODE-E-P01",
            to_node="NODE-V-ZONE1",
            relation=Relation.OBSERVED_AS,
            weight=0.90,
            provenance=_prov("evidence"),
        ),
        EvidenceEdge(
            edge_id="EDGE-0002",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            from_node="NODE-V-ZONE1",
            to_node="NODE-V-PROX",
            relation=Relation.PRECEDES,
            weight=1.0,
            provenance=_prov("evidence"),
        ),
        EvidenceEdge(
            edge_id="EDGE-0003",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            from_node="NODE-V-PROX",
            to_node="NODE-V-ESTOP",
            relation=Relation.CANDIDATE_CAUSE_OF,
            weight=0.87,
            provenance=_prov("reasoning"),
        ),
        EvidenceEdge(
            edge_id="EDGE-0004",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            from_node="NODE-GAP-CAMC",
            to_node="NODE-V-PROX",
            relation=Relation.CONTRADICTS,
            weight=0.30,
            provenance=_prov("reasoning"),
        ),
    ]
    return nodes, edges


def build_hypotheses() -> list[Hypothesis]:
    """Build two ranked candidate causes, one of them weak.

    A single hypothesis presented alone reads as a verdict. Carrying a second,
    lower-scoring candidate with its own support is what makes the ranking legible
    as a ranking.
    """
    return [
        Hypothesis(
            hypothesis_id="HYP-0001",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            description="Worker P01 entering robot lane Z1 caused R12 to emergency stop",
            evidence_level=EvidenceLevel.STRONGLY_INFERRED,
            score=0.87,
            support_refs=["NODE-V-ZONE1", "NODE-V-PROX", "NODE-V-ESTOP"],
            contradiction_refs=["NODE-GAP-CAMC"],
            components={"temporal_precedence": 0.95, "proximity": 0.88, "evidence_strength": 0.78},
        ),
        Hypothesis(
            hypothesis_id="HYP-0002",
            run_id=RUN_ID,
            incident_id=INCIDENT_ID,
            description="Forklift F01 entering the intersection triggered the stop",
            evidence_level=EvidenceLevel.POSSIBLE,
            score=0.31,
            support_refs=["NODE-GAP-CAMC"],
            contradiction_refs=["NODE-V-ESTOP"],
            components={"temporal_precedence": 0.42, "proximity": 0.20, "evidence_strength": 0.31},
        ),
    ]


def build_report() -> Report:
    """Build the report, exercising three distinct evidence levels.

    The UNKNOWN claim is the one that matters. It gives the frontend a concrete
    example of a statement the system refuses to make, which is the visual state
    most easily forgotten when a UI is built against happy-path data only.
    """
    return Report(
        report_id="REP-0001",
        run_id=RUN_ID,
        incident_id=INCIDENT_ID,
        generator_version="deterministic-0.1.0",
        created_at=CREATED,
        summary=(
            "Robot R12 performed an emergency stop at 13.4 s. Worker P01 was observed "
            "entering the robot lane 0.6 s earlier."
        ),
        claims=[
            Claim(
                claim_id="CLM-0001",
                text="Observed: robot R12 changed state to ESTOP at 13.4 s",
                evidence_level=EvidenceLevel.CONFIRMED,
                evidence_refs=["EVT-0006", "NODE-V-ESTOP"],
            ),
            Claim(
                claim_id="CLM-0002",
                text="Observed: worker P01 entered robot lane Z1 at 12.8 s",
                evidence_level=EvidenceLevel.CONFIRMED,
                evidence_refs=["EVT-0004", "NODE-V-ZONE1"],
            ),
            Claim(
                claim_id="CLM-0003",
                text=(
                    "Likely contributed: worker P01 entering the robot lane while R12 "
                    "was approaching"
                ),
                evidence_level=EvidenceLevel.STRONGLY_INFERRED,
                evidence_refs=["HYP-0001", "NODE-V-PROX"],
            ),
            Claim(
                claim_id="CLM-0004",
                text=(
                    "Cannot determine whether physical contact occurred between 12.0 s and 14.4 s"
                ),
                evidence_level=EvidenceLevel.UNKNOWN,
                evidence_refs=[],
            ),
        ],
        ranked_hypotheses=["HYP-0001", "HYP-0002"],
        gaps=["NODE-GAP-CAMC"],
        limitations=(
            "CAM_C was occluded by forklift F01 between 12.0 s and 14.4 s. No camera "
            "establishes contact during that interval, so no contact is claimed."
        ),
    )


def main() -> int:
    """Write every golden fixture to disk and report what was produced."""
    OUT.mkdir(parents=True, exist_ok=True)

    observations = build_observations()
    segments = build_segments(observations)
    nodes, edges = build_graph()

    files: dict[str, object] = {
        "00_cameras.json": [c.model_dump(mode="json") for c in build_cameras()],
        "01_run.json": build_run().model_dump(mode="json"),
        "10_observations.json": [o.model_dump(mode="json") for o in observations],
        "20_track_segments.json": [s.model_dump(mode="json") for s in segments],
        "30_identity_links.json": [link.model_dump(mode="json") for link in build_identity_links()],
        "40_events.json": [e.model_dump(mode="json") for e in build_events()],
        "50_incident.json": build_incident().model_dump(mode="json"),
        "60_evidence_graph.json": {
            "nodes": [n.model_dump(mode="json") for n in nodes],
            "edges": [e.model_dump(mode="json") for e in edges],
        },
        "70_hypotheses.json": [h.model_dump(mode="json") for h in build_hypotheses()],
        "80_report.json": build_report().model_dump(mode="json"),
    }

    for name, payload in files.items():
        path = OUT / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        count = len(payload) if isinstance(payload, list) else 1
        log.info(f"  {name:26s} {count:3d} record(s)")

    log.info(f"\nwrote {len(files)} fixtures to {OUT}")
    return 0


if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
