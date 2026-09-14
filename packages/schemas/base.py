"""Shared base model and the schema version every contract carries."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: Bumped whenever any contract in this package changes shape.
#: A bump requires an ADR and regenerated golden fixtures. See CONTRIBUTING.md.
#: 1.1.0: `ProcessingRun` records `media_uris` and `captured_at` (ADR-0006), additive.
SCHEMA_VERSION = "1.2.0"


class Contract(BaseModel):
    """Base for every cross-stage contract.

    Frozen and extra-forbidding on purpose. A stage that quietly adds a field is
    the exact drift the gate reviews exist to catch, and forbidding extras turns
    that from a Week 14 surprise into an immediate validation error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)

    schema_version: str = Field(default=SCHEMA_VERSION)


class Provenance(Contract):
    """Where a piece of derived data came from.

    Attached to every evidence node and edge. Without this the graph is a set of
    assertions; with it, the graph is auditable.
    """

    producer_service: str = Field(description="Which service emitted this")
    producer_version: str = Field(description="Version of that service or model")
    run_id: str
    derived_from: list[str] = Field(
        default_factory=list, description="IDs of the records this was computed from"
    )
    created_at: datetime
