from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from van_gateway.context.models import EpistemicState, SourceTrust


class KnowledgeProvider(str, Enum):
    VEKL = "VEKL"
    OBSIDIAN = "OBSIDIAN"
    NOTEBOOK_ENTERPRISE = "NOTEBOOK_ENTERPRISE"
    NOTEBOOK_CONSUMER = "NOTEBOOK_CONSUMER"


class ProviderState(str, Enum):
    DISABLED = "DISABLED"
    UNCONFIGURED = "UNCONFIGURED"
    CONFIGURED = "CONFIGURED"
    READY = "READY"
    DEGRADED = "DEGRADED"


class KnowledgeOperationStatus(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    SUBMITTED = "SUBMITTED"
    VERIFYING = "VERIFYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    CONFLICTED_STATE = "CONFLICTED_STATE"


class KnowledgeEvidence(BaseModel):
    evidence_id: str
    provider: KnowledgeProvider
    query_id: str
    source_ref: str
    title: str | None = None
    source_trust: SourceTrust
    epistemic_state: EpistemicState = EpistemicState.EXTERNAL_EVIDENCE
    scope: str = "global"
    retrieved_at_ms: int
    content_digest: str
    snippet: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderStatus(BaseModel):
    provider: KnowledgeProvider
    state: ProviderState
    credential_locus: str
    evidence_pointer: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class VeklQueryRequest(BaseModel):
    mission_id: str
    query: str = ""
    max_results: int = Field(default=16, ge=1, le=64)
    scope: str = Field(default="engineering", min_length=1, max_length=128)

    @field_validator("mission_id")
    @classmethod
    def _mission_uuid(cls, value: str) -> str:
        return str(UUID(value.strip()))

    @field_validator("query")
    @classmethod
    def _query_bound(cls, value: str) -> str:
        value = value.strip()
        if len(value) > 512:
            raise ValueError("query exceeds 512 characters")
        return value


class VeklQueryResult(BaseModel):
    query_id: str
    mission_id: str
    query: str
    evidence: list[KnowledgeEvidence]
    evidence_pointer: str
    truncated: bool = False


class ObsidianIndexRequest(BaseModel):
    force: bool = False


class ObsidianIndexResult(BaseModel):
    scanned: int
    indexed: int
    unchanged: int
    blocked: int
    deleted: int
    fts_enabled: bool
    evidence_pointer: str


class ObsidianQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    max_results: int = Field(default=16, ge=1, le=64)
    scope: str = Field(default="owner-knowledge", min_length=1, max_length=128)
    refresh: bool = True

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class ObsidianQueryResult(BaseModel):
    query_id: str
    query: str
    evidence: list[KnowledgeEvidence]
    evidence_pointer: str
    index_refreshed: bool
    fts_used: bool


class NotebookEnterpriseCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=256)

    @field_validator("title")
    @classmethod
    def _title_trim(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class NotebookSourceKind(str, Enum):
    TEXT = "TEXT"
    WEB = "WEB"
    GOOGLE_DRIVE = "GOOGLE_DRIVE"
    YOUTUBE = "YOUTUBE"
    FILE = "FILE"


class NotebookSourceInput(BaseModel):
    kind: NotebookSourceKind
    source_name: str = Field(min_length=1, max_length=512)
    content: str | None = None
    url: str | None = None
    document_id: str | None = None
    mime_type: str | None = None
    file_path: str | None = None

    @model_validator(mode="after")
    def _kind_payload(self) -> "NotebookSourceInput":
        if self.kind == NotebookSourceKind.TEXT and not (self.content or "").strip():
            raise ValueError("TEXT source requires content")
        if self.kind in {NotebookSourceKind.WEB, NotebookSourceKind.YOUTUBE} and not (self.url or "").strip():
            raise ValueError(f"{self.kind.value} source requires url")
        if self.kind == NotebookSourceKind.GOOGLE_DRIVE:
            if not (self.document_id or "").strip() or not (self.mime_type or "").strip():
                raise ValueError("GOOGLE_DRIVE source requires document_id and mime_type")
        if self.kind == NotebookSourceKind.FILE:
            if not (self.file_path or "").strip() or not (self.mime_type or "").strip():
                raise ValueError("FILE source requires file_path and mime_type")
        return self


class NotebookEnterpriseAddSourcesRequest(BaseModel):
    notebook_id: str = Field(min_length=1, max_length=256)
    sources: list[NotebookSourceInput] = Field(min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=256)


class NotebookEnterpriseDeleteRequest(BaseModel):
    notebook_id: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=8, max_length=256)


class NotebookEnterpriseDeleteSourcesRequest(BaseModel):
    notebook_id: str = Field(min_length=1, max_length=256)
    source_names: list[str] = Field(min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=256)


class NotebookConsumerNoteCreateRequest(BaseModel):
    notebook_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=200_000)
    idempotency_key: str = Field(min_length=8, max_length=256)

    @field_validator("title", "notebook_id")
    @classmethod
    def _trim_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class NotebookOperationResult(BaseModel):
    operation_id: str
    provider: KnowledgeProvider
    operation: str
    status: KnowledgeOperationStatus
    idempotency_key: str
    resource_id: str | None = None
    correlation: dict[str, Any] = Field(default_factory=dict)
    evidence_pointer: str | None = None
    error_code: str | None = None
    observed_postcondition: dict[str, Any] = Field(default_factory=dict)


class NotebookConsumerAskRequest(BaseModel):
    notebook_id: str = Field(min_length=1, max_length=512)
    question: str = Field(min_length=1, max_length=20_000)
    scope: str = Field(default="google-notebook", min_length=1, max_length=128)

    @field_validator("notebook_id", "question")
    @classmethod
    def _trim_ask(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class NotebookGroundedAnswer(BaseModel):
    query_id: str
    notebook_id: str
    question: str
    answer: str
    evidence_pointer: str
    provider: KnowledgeProvider = KnowledgeProvider.NOTEBOOK_CONSUMER
    source_grounded: bool = True