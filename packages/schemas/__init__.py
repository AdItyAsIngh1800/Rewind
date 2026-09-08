"""Frozen cross-stage contracts for REWIND.

Everything in this package is a contract. Changing the shape of anything exported
here requires a SCHEMA_VERSION bump, an ADR, and regenerated golden fixtures.
See CONTRIBUTING.md.
"""

from .base import SCHEMA_VERSION, Contract, Provenance
from .enums import (
    ALLOWED_LANGUAGE,
    REQUIRES_SUPPORT,
    EntityClass,
    EventType,
    EvidenceLevel,
    IncidentClass,
    IncidentStatus,
    LinkDecision,
    NodeType,
    Relation,
    RobotState,
    RunStatus,
    Severity,
)
from .envelope import EventEnvelope
from .evidence import Claim, EvidenceEdge, EvidenceNode, Hypothesis, Report
from .pipeline import (
    BBox,
    Camera,
    IdentityLink,
    Incident,
    Observation,
    ProcessingRun,
    SemanticEvent,
    TrackSegment,
)

__all__ = [
    "ALLOWED_LANGUAGE",
    "REQUIRES_SUPPORT",
    "SCHEMA_VERSION",
    "BBox",
    "Camera",
    "Claim",
    "Contract",
    "EntityClass",
    "EventEnvelope",
    "EventType",
    "EvidenceEdge",
    "EvidenceLevel",
    "EvidenceNode",
    "Hypothesis",
    "IdentityLink",
    "Incident",
    "IncidentClass",
    "IncidentStatus",
    "LinkDecision",
    "NodeType",
    "Observation",
    "ProcessingRun",
    "Provenance",
    "Relation",
    "Report",
    "RobotState",
    "RunStatus",
    "SemanticEvent",
    "Severity",
    "TrackSegment",
]
