from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class SuggestionStatus(str,Enum):
    NEW="NEW"
    ACCEPTED="ACCEPTED"
    EDITED="EDITED"
    DISMISSED="DISMISSED"


class Suggestion(BaseModel):
    suggestion_id:str
    title:str
    rationale:str
    proposed_prompt:str
    edited_prompt:str|None=None
    source_refs:list[str]=Field(default_factory=list)
    status:SuggestionStatus
    attention_id:str|None=None
    project_id:str|None=None
    created_at_ms:int
    updated_at_ms:int
    decided_at_ms:int|None=None


class SuggestionCreate(BaseModel):
    title:str=Field(min_length=1,max_length=300)
    rationale:str=Field(min_length=1,max_length=4000)
    proposed_prompt:str=Field(min_length=1,max_length=8000)
    source_refs:list[str]=Field(default_factory=list,max_length=100)
    project_id:str|None=None


class SuggestionDecision(BaseModel):
    action:str=Field(pattern="^(accept|edit|dismiss)$")
    edited_prompt:str|None=Field(default=None,max_length=8000)
