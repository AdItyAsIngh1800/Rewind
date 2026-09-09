"""The internal event envelope.

Every message crossing a service boundary is wrapped in this. It carries enough
identity and versioning that a stage could be lifted onto a message bus later
without changing its payload contract — which is the escape hatch ADR-0001 relies
on when it defers Kafka.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import Contract


class EventEnvelope(Contract):
    """Wrapper placed around every message that crosses a service boundary.

    Carrying producer identity and version here, rather than inside each payload,
    is what would let a stage move onto a message bus later without its contract
    changing.
    """

    event_id: str
    event_type: str
    event_time: datetime
    run_id: str
    producer_service: str
    producer_version: str
    entity_ids: list[str] = Field(default_factory=list)
    source_camera: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
