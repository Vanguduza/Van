from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EpistemicState(str, Enum):
    CANONICAL_OWNER = "CANONICAL_OWNER"
    PROJECT_TRUTH = "PROJECT_TRUTH"
    VERIFIED_LIVE_STATE = "VERIFIED_LIVE_STATE"
    VERIFIED_HISTORY = "VERIFIED_HISTORY"
    CONFIRMED_LEARNED = "CONFIRMED_LEARNED"
    EXTERNAL_EVIDENCE = "EXTERNAL_EVIDENCE"
    INFERRED = "INFERRED"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"


class SourceTrust(str, Enum):
    OWNER_EXPLICIT = "OWNER_EXPLICIT"
    LOCKED_AUTHORITY = "LOCKED_AUTHORITY"
    VERIFIED_SYSTEM = "VERIFIED_SYSTEM"
    TRUSTED_OWNER_FILE = "TRUSTED_OWNER_FILE"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"
    MODEL_DERIVED = "MODEL_DERIVED"


class SensitivityClass(str, Enum):
    PUBLIC = "PUBLIC"
    OWNER_PRIVATE = "OWNER_PRIVATE"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"


class ReadinessState(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    MISSING = "MISSING"
    CONFLICTED = "CONFLICTED"
    UNKNOWN = "UNKNOWN"


class GraphDirection(str, Enum):
    OUT = "OUT"
    IN = "IN"
    BOTH = "BOTH"


class OwnerFactCandidate(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    value: Any
    authority: EpistemicState
    source_trust: SourceTrust
    source_ref: str
    confidence_permille: int = 1000
    confidence_profile_version: int = 1
    scope: str = "global"
    valid_from_ms: int
    valid_until_ms: int | None = None
    observed_at_ms: int
    last_verified_at_ms: int | None = None
    sensitivity: SensitivityClass = SensitivityClass.OWNER_PRIVATE
    supersedes_fact_id: str | None = None

    @field_validator("confidence_permille")
    @classmethod
    def _confidence_range(cls, value: int) -> int:
        if not 0 <= value <= 1000:
            raise ValueError("confidence_permille must be in 0..1000")
        return value


class OwnerFactRecord(OwnerFactCandidate):
    revision: int
    content_digest: str


class ContextRequirement(BaseModel):
    subject: str
    predicate: str
    scope: str = "global"
    max_age_ms: int | None = None
    allow_inferred: bool = False


class RequirementResolution(BaseModel):
    requirement: ContextRequirement
    state: ReadinessState
    fact: OwnerFactRecord | None = None
    conflicting_fact_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class ContextReadiness(BaseModel):
    command_id: str
    state: ReadinessState
    requirements: list[RequirementResolution]


class ContextSnapshot(BaseModel):
    snapshot_id: str
    command_id: str
    kernel_revision: int
    fact_ids: list[str]
    graph_evidence_refs: list[str] = Field(default_factory=list)
    lexical_evidence_refs: list[str] = Field(default_factory=list)
    live_state_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    compiled_at_ms: int
    digest: str


class ContextEdgeCandidate(BaseModel):
    edge_id: str
    from_node: str
    predicate: str
    to_node: str
    scope: str = "global"
    authority: EpistemicState
    source_trust: SourceTrust
    source_ref: str
    confidence_permille: int = 1000
    confidence_profile_version: int = 1
    valid_from_ms: int
    valid_until_ms: int | None = None
    observed_at_ms: int
    sensitivity: SensitivityClass = SensitivityClass.OWNER_PRIVATE
    supersedes_edge_id: str | None = None

    @field_validator("confidence_permille")
    @classmethod
    def _edge_confidence_range(cls, value: int) -> int:
        if not 0 <= value <= 1000:
            raise ValueError("confidence_permille must be in 0..1000")
        return value


class ContextEdgeRecord(ContextEdgeCandidate):
    revision: int


class ContextGraphQuery(BaseModel):
    seed_nodes: list[str]
    scope: str = "global"
    direction: GraphDirection = GraphDirection.BOTH
    predicates: list[str] = Field(default_factory=list)
    max_depth: int = 1
    max_edges: int = 64
    allow_inferred: bool = False
    min_confidence_permille: int = 0

    @field_validator("seed_nodes")
    @classmethod
    def _seeds_required(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in value if item.strip()})
        if not normalized:
            raise ValueError("seed_nodes must contain at least one node")
        if len(normalized) > 32:
            raise ValueError("seed_nodes may contain at most 32 nodes")
        return normalized

    @field_validator("max_depth")
    @classmethod
    def _depth_bound(cls, value: int) -> int:
        if not 1 <= value <= 3:
            raise ValueError("max_depth must be in 1..3")
        return value

    @field_validator("max_edges")
    @classmethod
    def _edge_bound(cls, value: int) -> int:
        if not 1 <= value <= 256:
            raise ValueError("max_edges must be in 1..256")
        return value

    @field_validator("min_confidence_permille")
    @classmethod
    def _min_confidence_bound(cls, value: int) -> int:
        if not 0 <= value <= 1000:
            raise ValueError("min_confidence_permille must be in 0..1000")
        return value


class ContextGraphResult(BaseModel):
    scope: str
    seed_nodes: list[str]
    visited_nodes: list[str]
    edges: list[ContextEdgeRecord]
    evidence_refs: list[str]
    max_depth: int
    truncated: bool
    compiled_at_ms: int
