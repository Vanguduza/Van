from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ThreadKind(str, Enum):
    MAIN = "MAIN"
    SIDE = "SIDE"


class ThreadStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class FollowUpStatus(str, Enum):
    QUEUED = "QUEUED"
    PROMOTED = "PROMOTED"
    DISMISSED = "DISMISSED"


class ConversationMessage(BaseModel):
    message_id: str
    thread_id: str
    role: str
    body: str
    command_id: str | None = None
    mission_id: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    terminal: bool = False
    created_at_ms: int


class ConversationFollowUp(BaseModel):
    followup_id: str
    thread_id: str
    prompt: str
    status: FollowUpStatus
    command_id: str | None = None
    created_at_ms: int
    updated_at_ms: int


class ConversationThread(BaseModel):
    thread_id: str
    title: str
    kind: ThreadKind
    status: ThreadStatus
    project_id: str | None = None
    created_at_ms: int
    updated_at_ms: int
    archived_at_ms: int | None = None
    draft_text: str = ""
    messages: list[ConversationMessage] = Field(default_factory=list)
    message_count: int = 0
    messages_has_more: bool = False
    messages_next_before_id: str | None = None
    followups: list[ConversationFollowUp] = Field(default_factory=list)


class ConversationMessagePage(BaseModel):
    thread_id: str
    messages: list[ConversationMessage]
    total_count: int
    has_more: bool
    next_before_message_id: str | None = None


class FollowUpDecisionResult(ConversationFollowUp):
    fresh_owner_prompt: str | None = None
