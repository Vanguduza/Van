from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ArtifactKind(str, Enum):
    REPORT = "REPORT"
    PLAN = "PLAN"
    COMPARISON = "COMPARISON"
    DOCUMENT = "DOCUMENT"
    PDF = "PDF"
    BROWSER_SNAPSHOT = "BROWSER_SNAPSHOT"
    CHART = "CHART"
    TABLE = "TABLE"
    FILE = "FILE"
    RECEIPT = "RECEIPT"
    FINANCE_SUMMARY = "FINANCE_SUMMARY"
    OTHER = "OTHER"


class ArtifactSensitivity(str, Enum):
    PUBLIC = "PUBLIC"
    OWNER_PRIVATE = "OWNER_PRIVATE"
    SECRET_REF_ONLY = "SECRET_REF_ONLY"


class OwnerArtifact(BaseModel):
    artifact_id: str
    owner_id: str = "owner"
    project_id: str | None = None
    command_id: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
    kind: ArtifactKind
    title: str
    summary: str = ""
    mime_type: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    canonical_source_type: str
    canonical_source_id: str
    canonical_source_digest: str = Field(min_length=64, max_length=64)
    content_ref: str | None = None
    preview_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    created_at_ms: int
    expires_at_ms: int | None = None
    sensitivity: ArtifactSensitivity = ArtifactSensitivity.OWNER_PRIVATE
