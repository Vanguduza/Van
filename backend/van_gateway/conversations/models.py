from __future__ import annotations

from enum import Enum
from pydantic import BaseModel,Field


class ThreadKind(str,Enum):
    MAIN="MAIN"
    SIDE="SIDE"


class ThreadStatus(str,Enum):
    ACTIVE="ACTIVE"
    ARCHIVED="ARCHIVED"


class ConversationMessage(BaseModel):
    message_id:str
    thread_id:str
    role:str
    body:str
    command_id:str|None=None
    mission_id:str|None=None
    artifact_refs:list[str]=Field(default_factory=list)
    terminal:bool=False
    created_at_ms:int


class ConversationThread(BaseModel):
    thread_id:str
    title:str
    kind:ThreadKind
    status:ThreadStatus
    project_id:str|None=None
    created_at_ms:int
    updated_at_ms:int
    archived_at_ms:int|None=None
    draft_text:str=""
    messages:list[ConversationMessage]=Field(default_factory=list)
