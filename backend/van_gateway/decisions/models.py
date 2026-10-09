"""Typed owner judgments. An answer records a choice; it never grants an effect."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class DecisionStatus(str, Enum):
    OPEN = "OPEN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ANSWERED = "ANSWERED"
    EXPIRED = "EXPIRED"


class DecisionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class DecisionEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(min_length=1, max_length=512)
    label: str = Field(default="", max_length=200)
    kind: Literal["REFERENCE", "MISSION_EVENT"] = "REFERENCE"
    observed_at_unix: int | None = Field(default=None, ge=0)


class DecisionEvidence(DecisionEvidenceInput):
    verification: Literal["REFERENCE_ONLY", "RECORDED_EVENT"] = "REFERENCE_ONLY"


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=12000)
    source: str = Field(default="hermes", min_length=1, max_length=100)
    hermes_ref: str | None = Field(default=None, max_length=512)
    blocking: StrictBool = True
    choices: list[DecisionChoice] = Field(default_factory=list, max_length=16)
    evidence: list[DecisionEvidenceInput] = Field(default_factory=list, max_length=32)
    mission_id: str | None = Field(default=None, min_length=1, max_length=128)
    expires_at_unix: StrictInt | None = Field(default=None, ge=1)
    request_id: str | None = Field(default=None, min_length=8, max_length=128,
                                  pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

    @model_validator(mode="after")
    def distinct_choices(self):
        if self.choices and len(self.choices) < 2:
            raise ValueError("a choice decision requires at least two options")
        if len({item.id for item in self.choices}) != len(self.choices):
            raise ValueError("decision choice IDs must be distinct")
        if len({item.ref for item in self.evidence}) != len(self.evidence):
            raise ValueError("decision evidence references must be distinct")
        return self


class DecisionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice_id: str = Field(min_length=1, max_length=64,
                           pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    expected_revision: StrictInt = Field(ge=1, le=2**31-1)
    request_id: str = Field(min_length=8, max_length=128,
                            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    note: str = Field(default="", max_length=2000)


class DecisionRecord(BaseModel):
    id: str
    title: str
    body: str
    status: DecisionStatus
    source: str
    hermes_ref: str | None = None
    created_at_unix: int
    updated_at_unix: int
    blocking: bool = True
    choices: list[DecisionChoice] = Field(default_factory=list)
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    mission_id: str | None = None
    expires_at_unix: int | None = None
    revision: int = 1
    selected_choice_id: str | None = None
    answer_note: str | None = None
    answered_at_unix: int | None = None
    resolution_request_id: str | None = None
    grants_action_authority: Literal[False] = False


def binary_choices() -> list[DecisionChoice]:
    return [DecisionChoice(id="approve", label="Approve proposal",
                           description="Record agreement. Any action still requires its own authority."),
            DecisionChoice(id="reject", label="Reject proposal",
                           description="Record disagreement. No action is authorized.")]
