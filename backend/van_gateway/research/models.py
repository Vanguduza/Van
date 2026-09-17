from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchMode(str, Enum):
    INTERACTIVE = "INTERACTIVE"
    QUICK = "QUICK"
    NORMAL = "NORMAL"
    DEEP = "DEEP"
    DEEP_REASONING = "DEEP_REASONING"

    @property
    def exa_type(self) -> str:
        return {
            ResearchMode.INTERACTIVE: "instant",
            ResearchMode.QUICK: "fast",
            ResearchMode.NORMAL: "auto",
            ResearchMode.DEEP: "deep",
            ResearchMode.DEEP_REASONING: "deep-reasoning",
        }[self]


class ResearchEgressClass(str, Enum):
    PUBLIC_QUERY = "PUBLIC_QUERY"
    OWNER_CONTEXT_BOUNDED = "OWNER_CONTEXT_BOUNDED"
    SENSITIVE_CONTEXT = "SENSITIVE_CONTEXT"
    PROHIBITED_EGRESS = "PROHIBITED_EGRESS"


class ResearchSearchRequest(BaseModel):
    query: str
    mode: ResearchMode = ResearchMode.NORMAL
    egress_class: ResearchEgressClass = ResearchEgressClass.PUBLIC_QUERY
    max_results: int = 8
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    category: str | None = None
    owner_approved_sensitive_egress: bool = False

    @field_validator("query")
    @classmethod
    def _query_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        if len(value) > 4000:
            raise ValueError("query exceeds 4000 characters")
        return value

    @field_validator("max_results")
    @classmethod
    def _result_bounds(cls, value: int) -> int:
        if not 1 <= value <= 20:
            raise ValueError("max_results must be in 1..20")
        return value


class ResearchSource(BaseModel):
    title: str | None = None
    url: str
    published_at: str | None = None
    author: str | None = None
    highlights: list[str] = Field(default_factory=list)
    source_id: str | None = None
    content_digest: str


class ResearchSearchResult(BaseModel):
    research_id: str
    provider: str = "exa"
    request_id: str | None = None
    resolved_search_type: str | None = None
    query_hash: str
    sources: list[ResearchSource]
    cost_dollars: dict[str, Any] | None = None
    evidence_pointer: str
