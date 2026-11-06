"""Owner inspection schemas, including provenance and constrained destructive scope."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel


class MemoryRecordField(BaseModel):
    name: str
    value: Any


class MemoryRecordView(BaseModel):
    store: str
    record_id: str
    revision_sha256: str
    kind: str
    title: str
    source_class: Literal["OWNER_DECLARED", "OBSERVED", "INFERRED", "MIXED", "UNCLASSIFIED"]
    fields: list[MemoryRecordField]
    provenance: dict[str, Any]
    erasure: dict[str, Any]
    content_screened: bool
    execution_grant: Literal[False]
    content_bounds: dict[str, int]
    export_scope: str


class MemoryRecordPage(BaseModel):
    store: str
    records: list[MemoryRecordView]
    total: int
    next_cursor: int | None
    truncated: bool
    snapshot_consistent: bool
    pagination_consistency: str


class MemoryRecordErasurePlan(BaseModel):
    store: str
    record_id: str
    revision_sha256: str
    command_text: str
    action_class: Literal["A4"]
    affected_stores: list[str]
    affected_records: list[dict[str, Any]]
    kept_deliberately: dict[str, str]
    scope: str


class LearningProducerView(BaseModel):
    id: Literal["decision-patterns", "external-contradictions"]
    active: bool
    status: Literal["READY", "NO_DATA", "PARTIAL", "DEGRADED"]
    observations: int | None
    comparisons: int | None
    unmeasured: int | None
    truncated: bool = False
    evidence_refs: list[str]
    snapshot_sha256: str | None
    observed_at_ms: int
    why: str
    execution_grant: bool = False


class LearningProducersView(BaseModel):
    observed_at_ms: int
    producers: list[LearningProducerView]
    execution_grant: Literal[False]
