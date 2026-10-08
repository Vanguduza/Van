from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GoalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class GoalMilestone(BaseModel):
    milestone_id: str
    title: str
    done: bool = False
    due_at_ms: int | None = None
    sort_order: int = 0


class Goal(BaseModel):
    goal_id: str
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.ACTIVE
    priority: int = Field(default=50, ge=0, le=100)
    project_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    milestones: list[GoalMilestone] = Field(default_factory=list)
    mission_ids: list[str] = Field(default_factory=list)
    created_at_ms: int
    updated_at_ms: int
    completed_at_ms: int | None = None


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)
    priority: int = Field(default=50, ge=0, le=100)
    project_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list, max_length=100)


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    priority: int | None = Field(default=None, ge=0, le=100)
    status: GoalStatus | None = None


class WatchSourceKind(str, Enum):
    BROWSER = "BROWSER"
    PROVIDER = "PROVIDER"
    AUTOMATION = "AUTOMATION"
    MANUAL_FEED = "MANUAL_FEED"


class WatchConditionKind(str, Enum):
    CHANGED = "CHANGED"
    NUMERIC_ABOVE = "NUMERIC_ABOVE"
    NUMERIC_BELOW = "NUMERIC_BELOW"
    TEXT_CONTAINS = "TEXT_CONTAINS"
    BOOLEAN_TRUE = "BOOLEAN_TRUE"


class WatchStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class Watch(BaseModel):
    watch_id: str
    goal_id: str | None = None
    title: str
    source_kind: WatchSourceKind
    target: str
    condition: dict[str, Any]
    interval_seconds: int
    status: WatchStatus
    consecutive_failures: int
    failure_streak: int
    next_run_at_ms: int
    last_success_at_ms: int | None = None
    last_observation: Any = None
    created_at_ms: int
    updated_at_ms: int


class WatchCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source_kind: WatchSourceKind
    target: str = Field(min_length=1, max_length=2000)
    condition: dict[str, Any]
    interval_seconds: int = Field(default=3600, ge=60, le=31 * 24 * 3600)
    goal_id: str | None = None


class WatchObservation(BaseModel):
    observation: Any = None
    success: bool = True
    error_code: str | None = Field(default=None, max_length=200)
