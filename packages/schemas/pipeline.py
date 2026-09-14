"""Perception-pipeline contracts: run -> observation -> track -> identity -> event."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import Contract
from .enums import (
    EntityClass,
    EventType,
    IncidentClass,
    IncidentStatus,
    LinkDecision,
    RunStatus,
    Severity,
)


class BBox(Contract):
    """Axis-aligned box in pixel coordinates, top-left origin."""

    x1: float
    y1: float
    x2: float
    y2: float

    @model_validator(mode="after")
    def _ordered(self) -> BBox:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError(f"degenerate bbox: ({self.x1},{self.y1})-({self.x2},{self.y2})")
        return self

    @property
    def area(self) -> float:
        """Return the box area in square pixels."""
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    @property
    def centroid(self) -> tuple[float, float]:
        """Return the box centre as ``(x, y)`` in pixel coordinates."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


class Camera(Contract):
    """A fixed camera, its intrinsics and its offset from the shared clock."""

    camera_id: str
    name: str
    source_uri: str
    timezone: str = "UTC"
    #: Clock offset applied at ingestion to reach the shared timebase. The scene spec
    #: injects known offsets precisely so this correction has something to correct.
    clock_offset_s: float = 0.0
    width: int
    height: int
    fps: float
    calibration_ref: str | None = None


class ProcessingRun(Contract):
    """One execution of the pipeline over one input set.

    The four version fields are what make a result reproducible. A benchmark number
    without a run behind it is an anecdote.
    """

    run_id: str
    input_hash: str = Field(description="Hash of the input media set")
    dataset_version: str
    model_versions: dict[str, str] = Field(default_factory=dict)
    config_version: str
    status: RunStatus = RunStatus.QUEUED
    device: str = Field(default="unknown", description="Accelerator used, e.g. mps / cpu")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    #: Camera id to the clip that camera's observations were read from, recorded by the
    #: pipeline from the clips it decoded, so a replay plays exactly the footage the
    #: evidence came from (ADR-0006). Empty until the run is processed.
    media_uris: dict[str, str] = Field(default_factory=dict)
    captured_at: datetime | None = Field(
        default=None,
        description="Wall-clock start of the run's shared timebase; None for rendered footage",
    )


class Observation(Contract):
    """One entity seen in one frame of one camera.

    Ground truth is emitted in this exact shape, which is what lets the evaluation
    harness compare predictions against truth without a translation layer.
    """

    observation_id: str
    run_id: str
    camera_id: str
    frame_index: int
    timestamp_s: float = Field(description="Seconds on the shared timebase")
    entity_class: EntityClass
    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)
    track_id: str | None = None
    entity_id: str | None = Field(default=None, description="Ground truth only")
    world_xyz: tuple[float, float, float] | None = None
    visibility: float = Field(default=1.0, ge=0.0, le=1.0)


class TrackSegment(Contract):
    """A contiguous run of observations of one entity in one camera."""

    segment_id: str
    run_id: str
    camera_id: str
    local_track_id: str
    entity_class: EntityClass
    start_time_s: float
    end_time_s: float
    observation_ids: list[str]
    mean_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> TrackSegment:
        if self.end_time_s < self.start_time_s:
            raise ValueError("segment ends before it starts")
        return self


class IdentityLink(Contract):
    """A cross-camera identity comparison and its outcome.

    A record is written whether or not a link was made. `UNKNOWN` with a low score
    is a real, useful result — it is what stops the evidence graph from inventing a
    trajectory across a coverage gap.
    """

    link_id: str
    run_id: str
    segment_a: str
    segment_b: str
    decision: LinkDecision
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(
        default_factory=dict,
        description="Per-signal contributions: temporal, appearance, geometric",
    )
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _decision_matches_score(self) -> IdentityLink:
        if self.decision is LinkDecision.LINKED and self.score < self.threshold:
            raise ValueError(
                f"linked at score {self.score} below threshold {self.threshold} — "
                "a link must be justified by its own score"
            )
        return self


class SemanticEvent(Contract):
    """A trajectory turned into something an investigator would recognise."""

    event_id: str
    run_id: str
    event_type: EventType
    timestamp_s: float
    camera_id: str | None = Field(default=None, description="None if cross-camera")
    entity_ids: list[str] = Field(default_factory=list)
    zone_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(
        default_factory=list, description="Observation or segment IDs supporting this"
    )
    payload: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _zone_events_name_a_zone(self) -> SemanticEvent:
        if self.event_type in (EventType.ZONE_ENTRY, EventType.ZONE_EXIT) and not self.zone_id:
            raise ValueError(f"{self.event_type} requires a zone_id")
        return self


class Incident(Contract):
    """A detected incident and the window opened to investigate it."""

    incident_id: str
    run_id: str
    incident_class: IncidentClass
    trigger_event_id: str
    detected_at_s: float
    window_start_s: float
    window_end_s: float
    severity: Severity
    status: IncidentStatus = IncidentStatus.NEW

    @model_validator(mode="after")
    def _window_contains_trigger(self) -> Incident:
        if not self.window_start_s <= self.detected_at_s <= self.window_end_s:
            raise ValueError("investigation window does not contain its own trigger")
        if self.window_end_s <= self.window_start_s:
            raise ValueError("investigation window has non-positive duration")
        return self
