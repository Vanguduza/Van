from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Message(Closed):
    id: Identifier
    role: Literal["user", "assistant"]
    text: str = Field(max_length=32000)
    streaming: bool = False
    truncated: bool = False


class Prompt(Closed):
    id: Identifier
    revision: int = Field(ge=1)
    action_fingerprint: Digest
    element_ref: Identifier
    description: str = Field(min_length=1, max_length=16000)
    allowed_actions: list[Literal["ALLOW_ONCE", "DENY"]] = Field(min_length=1, max_length=2)
    # Any unclassified provider permission requires fresh owner step-up to allow.
    action_class: Literal["A1", "A2", "A3", "A4", "A5", "UNCLASSIFIED"] = "UNCLASSIFIED"
    expires_at_epoch_ms: int = Field(gt=0)


class Session(Closed):
    session_id: Identifier
    thread_id: Identifier
    task_id: Identifier
    project_id: Identifier | None = None
    scope_binding_sha256: Digest
    control_generation: int = Field(ge=1)
    revision: int = Field(ge=1)
    title: str = Field(max_length=240)
    state: str = Field(max_length=64)
    current_job_only: bool
    can_send: bool = False
    messages_truncated: bool = False
    messages: list[Message] = Field(default_factory=list, max_length=200)
    approvals: list[Prompt] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        for rows in (self.messages, self.approvals):
            ids = [row.id for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate_source_identity")
        return self

    def binding(self) -> dict[str, Any]:
        return self.model_dump(include={"session_id", "thread_id", "task_id", "project_id", "scope_binding_sha256"})


class Snapshot(Closed):
    schema_version: Literal[1] = 1
    producer_id: Identifier
    sequence: int = Field(ge=1)
    observed_at_ms: int = Field(gt=0)
    health: Literal["GREEN", "DEGRADED", "UNOBSERVED"]
    watchdog: Literal["GREEN", "DEGRADED", "UNOBSERVED"]
    complete: bool
    sessions: list[Session] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_sessions(self):
        ids = [s.session_id for s in self.sessions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_session_identity")
        return self


class Action(Closed):
    action: Literal["SEND_MESSAGE", "DECIDE_APPROVAL"]
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    session_id: Identifier
    thread_id: Identifier
    task_id: Identifier
    project_id: Identifier | None = None
    scope_binding_sha256: Digest
    control_generation: int = Field(ge=1)
    expected_revision: int = Field(ge=1)
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    approval_id: Identifier | None = None
    action_fingerprint: Digest | None = None
    choice: Literal["ALLOW_ONCE", "DENY"] | None = None
    challenge_id: str | None = Field(default=None, max_length=160)
    signature_b64: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def exact_shape(self):
        if self.action == "SEND_MESSAGE":
            if not self.text or not self.text.strip() or any(x is not None for x in (self.approval_id, self.choice, self.action_fingerprint)):
                raise ValueError("message_shape_invalid")
        elif self.text is not None or not all((self.approval_id, self.choice, self.action_fingerprint)):
            raise ValueError("approval_shape_invalid")
        if bool(self.challenge_id) != bool(self.signature_b64):
            raise ValueError("incomplete_step_up_proof")
        return self

    def intent(self) -> dict[str, Any]:
        return self.model_dump(exclude={"challenge_id", "signature_b64"}, exclude_none=True)


class Outcome(Closed):
    command_id: Identifier
    command_digest: Digest
    state: Literal["CONFIRMED", "REJECTED", "UNKNOWN"]
    observed_at_ms: int = Field(gt=0)
    evidence_digest: Digest
    reason: str = Field(max_length=160, pattern=r"^[A-Za-z0-9_.: -]*$")


class MuseError(ValueError):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status
