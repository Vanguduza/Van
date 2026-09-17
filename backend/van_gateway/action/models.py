from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass, PrincipalType


class ExecutionStatus(str, Enum):
    RECEIVED = "RECEIVED"
    RESOLVING = "RESOLVING"
    CONTEXT_READY = "CONTEXT_READY"
    PLANNED = "PLANNED"
    AUTHORIZED = "AUTHORIZED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    EXECUTING = "EXECUTING"
    SUBMITTED = "SUBMITTED"
    VERIFYING = "VERIFYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    UNVERIFIABLE = "UNVERIFIABLE"
    CONTEXT_INSUFFICIENT = "CONTEXT_INSUFFICIENT"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    CONFLICTED_STATE = "CONFLICTED_STATE"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


_TERMINAL = {
    ExecutionStatus.VERIFIED_SUCCESS,
    ExecutionStatus.UNVERIFIABLE,
    ExecutionStatus.CONTEXT_INSUFFICIENT,
    ExecutionStatus.AUTHORIZATION_REQUIRED,
    ExecutionStatus.PRECONDITION_FAILED,
    ExecutionStatus.EXECUTION_FAILED,
    ExecutionStatus.VERIFICATION_FAILED,
    ExecutionStatus.PARTIAL_SUCCESS,
    ExecutionStatus.CONFLICTED_STATE,
    ExecutionStatus.DENIED,
    ExecutionStatus.EXPIRED,
    ExecutionStatus.REVOKED,
}


class VerifierType(str, Enum):
    NONE = "NONE"
    READ_BACK = "READ_BACK"
    RECEIPT = "RECEIPT"
    STATE_PREDICATE = "STATE_PREDICATE"
    DOMAIN_ATTESTATION = "DOMAIN_ATTESTATION"


class ActionDefinition(BaseModel):
    action_id: str
    action_class: ActionClass
    mutates_state: bool = False
    allowed_principals: set[PrincipalType] = Field(default_factory=lambda: {PrincipalType.OWNER_DEVICE})
    verifier_type: VerifierType = VerifierType.NONE
    no_stale_replay: bool = False
    max_age_seconds: int | None = None
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ActionExecution(BaseModel):
    execution_id: str
    command_id: str
    turn_id: str | None = None
    action_id: str
    action_class: ActionClass
    principal_type: PrincipalType
    requested_by: str
    status: ExecutionStatus
    idempotency_key: str
    snapshot_id: str | None = None
    parameters_digest: str
    submitted_at_ms: int | None = None
    verified_at_ms: int | None = None
    correlation: dict[str, Any] = Field(default_factory=dict)
    evidence_pointer: str | None = None
    error_code: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL


class VerificationObservation(BaseModel):
    execution_id: str
    success: bool
    correlation: dict[str, Any] = Field(default_factory=dict)
    observed_postcondition: dict[str, Any] = Field(default_factory=dict)
    evidence_pointer: str | None = None
    partial: bool = False


class ActionReceipt(BaseModel):
    receipt_id: str
    execution_id: str
    status: ExecutionStatus
    verifier_type: VerifierType
    correlation: dict[str, Any] = Field(default_factory=dict)
    observed_postcondition: dict[str, Any] = Field(default_factory=dict)
    evidence_pointer: str | None = None
    created_at_ms: int
