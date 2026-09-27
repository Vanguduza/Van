from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    IMPORTED = "IMPORTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


class DocumentFieldKind(str, Enum):
    TEXT = "TEXT"
    CHECKBOX = "CHECKBOX"


class DocumentField(BaseModel):
    name: str
    kind: DocumentFieldKind
    value: str | bool | None = None
    required: bool = False
    on_value: str | None = None


class DocumentRecord(BaseModel):
    document_id: str
    filename: str
    mime_type: str = "application/pdf"
    project_id: str | None = None
    command_id: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
    source_artifact_id: str
    output_artifact_id: str | None = None
    source_sha256: str
    output_sha256: str | None = None
    page_count: int
    form_kind: str
    fields: list[DocumentField] = Field(default_factory=list)
    status: DocumentStatus
    error_code: str | None = None
    created_at_ms: int
    updated_at_ms: int


class FillDocumentRequest(BaseModel):
    values: dict[str, Any]
    project_id: str | None = None
    command_id: str | None = None
    mission_id: str | None = None
    execution_id: str | None = None
