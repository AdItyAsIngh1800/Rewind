"""Evidence graph, hypotheses and report contracts.

This module carries the project's central claim: that a conclusion cannot be stated
more confidently than the evidence behind it permits. That is enforced here, in
validators, rather than requested politely at generation time.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .base import Contract, Provenance
from .enums import (
    ALLOWED_LANGUAGE,
    REQUIRES_SUPPORT,
    EvidenceLevel,
    NodeType,
    Relation,
)


class EvidenceNode(Contract):
    """A single node in an incident's evidence graph.

    A ``GAP`` node represents an interval no camera could see. It is evidence in its
    own right — the thing that lets a report say "cannot determine" rather than
    quietly omitting the interval.
    """

    node_id: str
    run_id: str
    incident_id: str
    node_type: NodeType
    label: str
    timestamp_s: float | None = None
    interval_s: tuple[float, float] | None = None
    source_ref: str | None = Field(
        default=None, description="Observation / event / segment this node stands for"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Provenance

    @model_validator(mode="after")
    def _gaps_have_intervals(self) -> EvidenceNode:
        if self.node_type is NodeType.GAP and self.interval_s is None:
            raise ValueError("a GAP node must name the interval it spans")
        return self


class EvidenceEdge(Contract):
    """A directed relationship between two evidence nodes, with its provenance."""

    edge_id: str
    run_id: str
    incident_id: str
    from_node: str
    to_node: str
    relation: Relation
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Provenance


class Hypothesis(Contract):
    """A candidate contributing cause, with what argues for and against it."""

    hypothesis_id: str
    run_id: str
    incident_id: str
    description: str
    evidence_level: EvidenceLevel
    score: float = Field(ge=0.0, le=1.0)
    support_refs: list[str] = Field(default_factory=list)
    contradiction_refs: list[str] = Field(default_factory=list)
    components: dict[str, float] = Field(
        default_factory=dict,
        description="Score breakdown: temporal precedence, proximity, evidence strength",
    )

    @model_validator(mode="after")
    def _supported(self) -> Hypothesis:
        if self.evidence_level in REQUIRES_SUPPORT and not self.support_refs:
            raise ValueError(
                f"hypothesis at level {self.evidence_level} has no support_refs — "
                "only UNKNOWN may stand without supporting evidence"
            )
        return self


class Claim(Contract):
    """One material statement in a report.

    The two validators here are the anti-hallucination mechanism. They make an
    unsupported claim structurally impossible to construct rather than merely
    discouraged: the object cannot be instantiated, so it cannot reach a report.
    """

    claim_id: str
    text: str
    evidence_level: EvidenceLevel
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _must_cite_unless_unknown(self) -> Claim:
        if self.evidence_level in REQUIRES_SUPPORT and not self.evidence_refs:
            raise ValueError(
                f"claim {self.claim_id!r} is stated at level {self.evidence_level} "
                "with no evidence_refs. Cite evidence or lower the level to UNKNOWN."
            )
        return self

    @model_validator(mode="after")
    def _phrasing_matches_level(self) -> Claim:
        required = ALLOWED_LANGUAGE[self.evidence_level]
        if required.lower() not in self.text.lower():
            raise ValueError(
                f"claim {self.claim_id!r} is at level {self.evidence_level}, which "
                f"requires the phrase {required!r}, but its text does not contain it. "
                "The vocabulary is fixed by the evidence level, not chosen freely."
            )
        return self


class Report(Contract):
    """A generated investigation report.

    ``limitations`` is required and must not be empty: there is always something a
    three-camera reconstruction cannot establish, and a report that claims otherwise
    is misrepresenting its own evidence.
    """

    report_id: str
    run_id: str
    incident_id: str
    generator_version: str
    created_at: datetime
    summary: str
    claims: list[Claim]
    ranked_hypotheses: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(
        default_factory=list, description="GAP node IDs — intervals nothing could see"
    )
    limitations: str = Field(
        description="What this report cannot establish. Never empty; there is always something."
    )

    @property
    def evidence_coverage(self) -> float:
        """Fraction of material claims carrying at least one evidence reference.

        UNKNOWN claims count as covered: 'cannot determine' is a supported statement
        about absent evidence, and penalising honesty would invert the incentive.
        """
        if not self.claims:
            return 1.0
        covered = sum(
            1 for c in self.claims if c.evidence_refs or c.evidence_level is EvidenceLevel.UNKNOWN
        )
        return covered / len(self.claims)
