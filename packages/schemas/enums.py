"""Closed vocabularies shared by every stage of the pipeline.

These are the words the system is allowed to use. A stage cannot invent a new
evidence level or event type without changing this file, which requires a
schema_version bump and an ADR — see CONTRIBUTING.md.
"""

from __future__ import annotations

from enum import StrEnum


class EvidenceLevel(StrEnum):
    """How strongly the evidence supports a claim.

    This is the spine of the whole system. Every claim in every report carries one
    of these, and the phrasing available to the report generator is derived from it
    rather than chosen freely.
    """

    CONFIRMED = "confirmed"
    STRONGLY_INFERRED = "strongly_inferred"
    POSSIBLE = "possible"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


#: The only phrasing each evidence level permits. Data, not prose — the report
#: generator reads this table rather than being told in a prompt to be careful.
ALLOWED_LANGUAGE: dict[EvidenceLevel, str] = {
    EvidenceLevel.CONFIRMED: "Observed",
    EvidenceLevel.STRONGLY_INFERRED: "Likely contributed",
    EvidenceLevel.POSSIBLE: "Possible",
    EvidenceLevel.CONFLICTING: "Conflicting evidence",
    EvidenceLevel.UNKNOWN: "Cannot determine",
}

#: Levels that require at least one supporting evidence reference. UNKNOWN is the
#: deliberate exception: "cannot determine" is a claim *about* absent evidence, so
#: demanding a supporting reference for it would be incoherent.
REQUIRES_SUPPORT: frozenset[EvidenceLevel] = frozenset(
    {
        EvidenceLevel.CONFIRMED,
        EvidenceLevel.STRONGLY_INFERRED,
        EvidenceLevel.POSSIBLE,
        EvidenceLevel.CONFLICTING,
    }
)


class EntityClass(StrEnum):
    """The four entity classes frozen in the charter. Not five."""

    PERSON = "person"
    ROBOT = "robot"
    FORKLIFT = "forklift"
    PALLET = "pallet"


class RobotState(StrEnum):
    """Robot state channel. Read from telemetry, never inferred from motion."""

    MOVING = "moving"
    ESTOP = "estop"
    IDLE = "idle"


class EventType(StrEnum):
    """Semantic events extracted from trajectories."""

    ZONE_ENTRY = "zone_entry"
    ZONE_EXIT = "zone_exit"
    STOP = "stop"
    DIRECTION_CHANGE = "direction_change"
    PROXIMITY = "proximity"
    OCCLUSION_START = "occlusion_start"
    OCCLUSION_END = "occlusion_end"
    STATE_CHANGE = "state_change"


class IncidentClass(StrEnum):
    """The two MVP incident classes. Adding a third requires a charter amendment."""

    ROBOT_ESTOP_HUMAN_INCURSION = "robot_estop_human_incursion"
    ZONE_BLOCKED_UNATTENDED_OBJECT = "zone_blocked_unattended_object"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    NEW = "new"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class LinkDecision(StrEnum):
    """The outcome of a cross-camera identity comparison.

    UNKNOWN is a first-class result, not a failure. Refusing to link two segments
    is frequently the correct answer, and a system that always links has simply
    moved its error rate somewhere less visible.
    """

    LINKED = "linked"
    UNKNOWN = "unknown"


class NodeType(StrEnum):
    """Evidence graph node kinds."""

    ENTITY = "entity"
    OBSERVATION = "observation"
    EVENT = "event"
    LOCATION = "location"
    INTERVAL = "interval"
    GAP = "gap"
    CONFLICT = "conflict"


class Relation(StrEnum):
    """Evidence graph edge kinds."""

    OBSERVED_AS = "observed_as"
    PRECEDES = "precedes"
    CO_OCCURS = "co_occurs"
    NEAR = "near"
    SAME_ENTITY_AS = "same_entity_as"
    OCCLUDES = "occludes"
    CANDIDATE_CAUSE_OF = "candidate_cause_of"
    CONTRADICTS = "contradicts"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
