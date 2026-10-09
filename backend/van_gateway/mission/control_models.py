"""Owner controls and worker checkpoint reports are separate typed contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class MissionControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    expected_generation: StrictInt = Field(ge=0, le=2**31 - 1)
    reason: str = Field(default="", max_length=2000)


class MissionDirectionBody(MissionControlBody):
    message: str = Field(min_length=1, max_length=16000)


class MissionControlPollBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mission_id: str = Field(min_length=1, max_length=256)
    hermes_run_id: str = Field(min_length=1, max_length=256)


class MissionControlAckBody(MissionControlPollBody):
    control_id: str = Field(min_length=1, max_length=256)
    generation: StrictInt = Field(ge=0, le=2**31 - 1)
    payload_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    checkpoint_ref: str = Field(min_length=1, max_length=2048)


class MissionControlReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["CONTROL_RECORDED"]
    control_id: str
    mission_id: str
    request_id: str
    operation: Literal["PAUSE", "RESUME", "DIRECTION"]
    expected_generation: int
    generation: int
    payload_digest: str
    desired_execution: Literal["RUNNING", "PAUSED"]
    hermes_run_id: str | None
    requested_by: str
    reason: str = ""
    created_at_ms: int
    direction: str | None = None


class MissionControlInstruction(MissionControlReceipt):
    pass


class MissionControlAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["CHECKPOINT_RECORDED", "DIRECTION_ADOPTION_RECORDED"]
    control_id: str
    mission_id: str
    hermes_run_id: str
    generation: int
    original_control_generation: int
    payload_digest: str
    checkpoint_ref: str
    acknowledged_at_ms: int
    process_stopped_verified: Literal[False]
    authority_granted: Literal[False]


class MissionControlState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mission_id: str
    mission_state: str
    generation: int
    desired_execution: Literal["RUNNING", "PAUSED"]
    dispatch_allowed: bool
    hermes_run_id: str | None
    latest_control: MissionControlInstruction | None
    latest_fence_control: MissionControlInstruction | None
    latest_worker_report: MissionControlAcknowledgement | None
    pending_directions: list[MissionControlInstruction]
