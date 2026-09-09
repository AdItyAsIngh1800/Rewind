"""SQLAlchemy models mirroring the frozen contracts in packages.schemas.

Relational where relationships need integrity, JSONB where the shape is genuinely
open (score components, event payloads, provenance). Anything JSONB here has a
Pydantic contract governing it — JSONB is a storage decision, never a licence to
store an unvalidated blob.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    source_uri: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    clock_offset_s: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[float] = mapped_column(Float)
    calibration_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(128), index=True)
    dataset_version: Mapped[str] = mapped_column(String(64))
    model_versions: Mapped[dict] = mapped_column(JSONB, default=dict)
    config_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    device: Mapped[str] = mapped_column(String(32), default="unknown")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Observation(Base):
    __tablename__ = "observations"

    observation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.run_id"), index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id"))
    frame_index: Mapped[int] = mapped_column(Integer)
    timestamp_s: Mapped[float] = mapped_column(Float)
    entity_class: Mapped[str] = mapped_column(String(32), index=True)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    track_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    world_xyz: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[float] = mapped_column(Float, default=1.0)

    __table_args__ = (
        # The access pattern every downstream stage uses: "what did camera X see
        # between t0 and t1 in this run". Sub-500 ms locally depends on this index.
        Index("ix_obs_run_camera_time", "run_id", "camera_id", "timestamp_s"),
    )


class TrackSegment(Base):
    __tablename__ = "track_segments"

    segment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.run_id"), index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.camera_id"))
    local_track_id: Mapped[str] = mapped_column(String(64))
    entity_class: Mapped[str] = mapped_column(String(32))
    start_time_s: Mapped[float] = mapped_column(Float)
    end_time_s: Mapped[float] = mapped_column(Float)
    observation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    mean_confidence: Mapped[float] = mapped_column(Float)


class IdentityLink(Base):
    __tablename__ = "identity_links"

    link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.run_id"), index=True)
    segment_a: Mapped[str] = mapped_column(ForeignKey("track_segments.segment_id"))
    segment_b: Mapped[str] = mapped_column(ForeignKey("track_segments.segment_id"))
    # Refusals are persisted alongside links. A row saying "these were compared and
    # deliberately not linked" is evidence; discarding it would hide the decision.
    decision: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)


class SemanticEvent(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.run_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    timestamp_s: Mapped[float] = mapped_column(Float, index=True)
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_ids: Mapped[list] = mapped_column(JSONB, default=list)
    zone_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (Index("ix_event_run_time", "run_id", "timestamp_s"),)


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.run_id"), index=True)
    incident_class: Mapped[str] = mapped_column(String(64), index=True)
    trigger_event_id: Mapped[str] = mapped_column(ForeignKey("events.event_id"))
    detected_at_s: Mapped[float] = mapped_column(Float)
    window_start_s: Mapped[float] = mapped_column(Float)
    window_end_s: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)


class EvidenceNode(Base):
    __tablename__ = "evidence_nodes"

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    node_type: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(Text)
    timestamp_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    provenance: Mapped[dict] = mapped_column(JSONB)


class EvidenceEdge(Base):
    __tablename__ = "evidence_edges"

    edge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    from_node: Mapped[str] = mapped_column(ForeignKey("evidence_nodes.node_id"))
    to_node: Mapped[str] = mapped_column(ForeignKey("evidence_nodes.node_id"))
    relation: Mapped[str] = mapped_column(String(32), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    provenance: Mapped[dict] = mapped_column(JSONB)


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    hypothesis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float, index=True)
    support_refs: Mapped[list] = mapped_column(JSONB, default=list)
    contradiction_refs: Mapped[list] = mapped_column(JSONB, default=list)
    components: Mapped[dict] = mapped_column(JSONB, default=dict)


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), index=True)
    generator_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str] = mapped_column(Text)
    # Claims are stored as JSONB, validated by the Claim contract on the way in and
    # on the way out. A claim that cannot be validated cannot be persisted.
    claims: Mapped[list] = mapped_column(JSONB, default=list)
    ranked_hypotheses: Mapped[list] = mapped_column(JSONB, default=list)
    gaps: Mapped[list] = mapped_column(JSONB, default=list)
    limitations: Mapped[str] = mapped_column(Text)
    # Reports referenced by an audit trail must remain readable exactly as issued.
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)


class EvidenceAccessLog(Base):
    """Who looked at what evidence, and when.

    Specification §M requires access to sensitive evidence to be logged. This is an
    append-only audit table: rows are written, never updated or deleted. It is
    deliberately separate from application logging, because an audit trail that can
    be rotated away with the application logs is not an audit trail.
    """

    __tablename__ = "evidence_access_log"

    access_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    actor_role: Mapped[str] = mapped_column(String(32))
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_ref: Mapped[str] = mapped_column(String(256))
    action: Mapped[str] = mapped_column(String(32))
    request_context: Mapped[dict] = mapped_column(JSONB, default=dict)
