"""Rev 1 §§3, 5 — the Mission, the single owner-visible unit of work.

Blueprint §3.1 makes Mission the one thing the owner sees across chat, voice,
browser, research, development, Google actions, automations and trading
analysis. Everything else in the unified architecture binds to a `mission_id`,
which is why this is the first thing built and why the rest of the mission
depends on its gates.

Two decisions are recorded here because §57 requires the conservative choice to
be written down rather than merely taken:

**The state vocabulary is deliberately the one already in the repository.**
`BrowserTaskStatus` already carries WAITING_FOR_OWNER, RESUME_AUTHORIZED,
VERIFYING, BLOCKED_POLICY, BLOCKED_UNSAFE and EXPIRED, with exactly the meanings
the blueprint gives them. Inventing a parallel vocabulary one level up would
give VAN two ways to say the same thing and guarantee they drift. Missions and
browser tasks therefore share a vocabulary, not a table.

**VERIFIED_SUCCESS is unreachable without evidence, structurally.** §6 says no
success without verifier evidence and §55 forbids claiming success without a
postcondition. That is enforced in `MissionService.transition()` rather than
documented here: the transition is refused when the verification record is
missing, so "the worker returned OK" cannot become owner success by any path.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass, OriginChannel, PrincipalType


class MissionState(str, Enum):
    """§3.2 — deterministic. Anything not in LEGAL_TRANSITIONS fails closed."""

    CAPTURED = "CAPTURED"
    UNDERSTOOD = "UNDERSTOOD"
    PLANNED = "PLANNED"
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    WAITING_FOR_OWNER = "WAITING_FOR_OWNER"
    RESUME_AUTHORIZED = "RESUME_AUTHORIZED"
    VERIFYING = "VERIFYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    BLOCKED_UNSAFE = "BLOCKED_UNSAFE"
    UNVERIFIABLE = "UNVERIFIABLE"


#: §3.2 — "WAITING_FOR_OWNER is non-terminal". Stated as data so the property is
#: checkable rather than a claim in prose.
TERMINAL_STATES = frozenset({
    MissionState.VERIFIED_SUCCESS,
    MissionState.PARTIAL_SUCCESS,
    MissionState.FAILED,
    MissionState.CANCELLED,
    MissionState.EXPIRED,
    MissionState.BLOCKED_POLICY,
    MissionState.BLOCKED_UNSAFE,
    MissionState.UNVERIFIABLE,
})

#: States a mission may reach only by passing through verification.
VERIFICATION_OUTCOMES = frozenset({
    MissionState.VERIFIED_SUCCESS,
    MissionState.PARTIAL_SUCCESS,
    MissionState.UNVERIFIABLE,
})

_S = MissionState
LEGAL_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    _S.CAPTURED: frozenset({_S.UNDERSTOOD, _S.CANCELLED, _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE,
                            _S.EXPIRED}),
    _S.UNDERSTOOD: frozenset({_S.PLANNED, _S.CANCELLED, _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE,
                              _S.EXPIRED}),
    _S.PLANNED: frozenset({_S.AUTHORIZED, _S.WAITING_FOR_OWNER, _S.CANCELLED,
                           _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE, _S.EXPIRED}),
    _S.AUTHORIZED: frozenset({_S.RUNNING, _S.CANCELLED, _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE,
                              _S.EXPIRED}),
    _S.RUNNING: frozenset({_S.WAITING_EXTERNAL, _S.WAITING_FOR_OWNER, _S.VERIFYING, _S.FAILED,
                           _S.CANCELLED, _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE, _S.EXPIRED}),
    _S.WAITING_EXTERNAL: frozenset({_S.RUNNING, _S.WAITING_FOR_OWNER, _S.FAILED, _S.CANCELLED,
                                    _S.EXPIRED, _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE}),
    # Non-terminal by construction: every edge here leads somewhere.
    _S.WAITING_FOR_OWNER: frozenset({_S.RESUME_AUTHORIZED, _S.CANCELLED, _S.EXPIRED,
                                     _S.BLOCKED_POLICY, _S.BLOCKED_UNSAFE}),
    _S.RESUME_AUTHORIZED: frozenset({_S.RUNNING, _S.CANCELLED, _S.EXPIRED, _S.BLOCKED_POLICY,
                                     _S.BLOCKED_UNSAFE}),
    # The only road to a success outcome runs through VERIFYING.
    _S.VERIFYING: frozenset({_S.VERIFIED_SUCCESS, _S.PARTIAL_SUCCESS, _S.UNVERIFIABLE, _S.FAILED,
                             _S.CANCELLED, _S.EXPIRED}),
    _S.VERIFIED_SUCCESS: frozenset(),
    _S.PARTIAL_SUCCESS: frozenset(),
    _S.FAILED: frozenset(),
    _S.CANCELLED: frozenset(),
    _S.EXPIRED: frozenset(),
    _S.BLOCKED_POLICY: frozenset(),
    _S.BLOCKED_UNSAFE: frozenset(),
    _S.UNVERIFIABLE: frozenset(),
}


class MissionOrigin(str, Enum):
    OWNER_VOICE = "OWNER_VOICE"
    OWNER_TEXT = "OWNER_TEXT"
    OWNER_UI = "OWNER_UI"
    PROACTIVE = "PROACTIVE"
    AUTOMATION_EVENT = "AUTOMATION_EVENT"
    SCHEDULED = "SCHEDULED"


class Sensitivity(str, Enum):
    ROUTINE = "ROUTINE"
    PERSONAL = "PERSONAL"
    FINANCIAL = "FINANCIAL"
    SECURITY = "SECURITY"


class VerificationStatus(str, Enum):
    """§6 — a verifier says one of exactly three things."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNVERIFIABLE = "UNVERIFIABLE"


class ActivityState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AuthorityEnvelope(BaseModel):
    """What a mission is permitted to do, decided once and carried throughout.

    §2.2 keeps the Gateway authoritative, so this is a *record* of authority
    granted elsewhere, never a grant in its own right. A mission cannot widen it;
    only a new owner decision can, and that produces a new envelope.
    """

    max_action_class: ActionClass = ActionClass.A2
    allowed_capability_classes: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    requires_owner_presence: bool = False
    source_command_id: str | None = None
    standing_authority_id: str | None = None

    @property
    def permits_mutation(self) -> bool:
        return self.max_action_class not in (ActionClass.A1,)


class SuccessContract(BaseModel):
    """§6 — machine-readable, so "done" is checkable rather than asserted.

    `postconditions` are the claims a verifier must observe. An empty contract is
    legal (not every mission is consequential) but it can never yield
    VERIFIED_SUCCESS — `MissionService` routes it to UNVERIFIABLE instead, since
    a mission with nothing to check has not been verified, only finished.
    """

    postconditions: dict[str, Any] = Field(default_factory=dict)
    verifier_class: str | None = None
    evidence_required: bool = True

    @property
    def is_checkable(self) -> bool:
        return bool(self.postconditions) and self.verifier_class is not None


class VerificationRecord(BaseModel):
    """§6 — the receipt that makes a success claim inspectable."""

    status: VerificationStatus
    observed_postconditions: dict[str, Any] = Field(default_factory=dict)
    missing_postconditions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    verifier_version: str
    verified_at_ms: int

    @property
    def supports_success(self) -> bool:
        """§55 — evidence, not a status string, is what makes success claimable."""
        return (
            self.status is VerificationStatus.VERIFIED
            and bool(self.evidence_refs)
            and not self.missing_postconditions
        )


class Mission(BaseModel):
    mission_id: str
    owner_principal_id: str
    project_id: str | None = None
    origin: MissionOrigin
    origin_channel: OriginChannel
    title: str
    goal: str
    success_contract: SuccessContract = Field(default_factory=SuccessContract)
    constraints: list[str] = Field(default_factory=list)
    authority_envelope: AuthorityEnvelope = Field(default_factory=AuthorityEnvelope)
    sensitivity: Sensitivity = Sensitivity.ROUTINE
    context_snapshot_id: str | None = None
    state: MissionState = MissionState.CAPTURED
    priority: int = 50
    created_at_ms: int
    updated_at_ms: int
    deadline_ms: int | None = None
    attention_policy: str = "NORMAL"
    plan_revision: int = 0
    current_phase: str | None = None
    parent_mission_id: str | None = None
    final_outcome: str | None = None
    verification_state: VerificationStatus = VerificationStatus.PENDING
    learning_record_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def needs_owner(self) -> bool:
        return self.state is MissionState.WAITING_FOR_OWNER


class Activity(BaseModel):
    """§5 — modular execution under one mission.

    A browser task, an automation run, a Google action and a research step are
    all Activities. The specialist subsystems keep their own tables; an Activity
    references them by `executor_ref` rather than absorbing them, because §5
    warns against deleting mature subsystem state prematurely.
    """

    activity_id: str
    mission_id: str
    activity_type: str
    capability_id: str
    executor: str
    executor_ref: str | None = None
    input_contract: dict[str, Any] = Field(default_factory=dict)
    authority_ref: str | None = None
    state: ActivityState = ActivityState.PENDING
    attempt: int = 1
    started_at_ms: int
    ended_at_ms: int | None = None
    dependency_activity_ids: list[str] = Field(default_factory=list)
    checkpoint_ref: str | None = None
    error_class: str | None = None
    retry_policy: str = "NONE"
    verification_contract: dict[str, Any] = Field(default_factory=dict)


class MissionEventType(str, Enum):
    """§44 — versioned event vocabulary."""

    MISSION_CREATED = "mission.created"
    MISSION_UNDERSTOOD = "mission.understood"
    MISSION_PLANNED = "mission.planned"
    MISSION_STARTED = "mission.started"
    MISSION_WAITING_OWNER = "mission.waiting_owner"
    MISSION_RESUMED = "mission.resumed"
    MISSION_VERIFYING = "mission.verifying"
    MISSION_COMPLETED = "mission.completed"
    MISSION_FAILED = "mission.failed"
    ACTIVITY_STARTED = "activity.started"
    ACTIVITY_CHECKPOINTED = "activity.checkpointed"
    ACTIVITY_COMPLETED = "activity.completed"
    ACTIVITY_FAILED = "activity.failed"


#: Which state arrival announces itself as which event.
EVENT_FOR_STATE = {
    MissionState.UNDERSTOOD: MissionEventType.MISSION_UNDERSTOOD,
    MissionState.PLANNED: MissionEventType.MISSION_PLANNED,
    MissionState.RUNNING: MissionEventType.MISSION_STARTED,
    MissionState.WAITING_FOR_OWNER: MissionEventType.MISSION_WAITING_OWNER,
    MissionState.RESUME_AUTHORIZED: MissionEventType.MISSION_RESUMED,
    MissionState.VERIFYING: MissionEventType.MISSION_VERIFYING,
    MissionState.VERIFIED_SUCCESS: MissionEventType.MISSION_COMPLETED,
    MissionState.PARTIAL_SUCCESS: MissionEventType.MISSION_COMPLETED,
    MissionState.FAILED: MissionEventType.MISSION_FAILED,
}


class MissionEvent(BaseModel):
    """§34 — the owner-visible timeline entry."""

    event_id: str
    mission_id: str
    activity_id: str | None = None
    event_type: MissionEventType
    actor: PrincipalType
    occurred_at_ms: int
    severity: str = "INFO"
    owner_visibility: bool = True
    summary: str = ""
    evidence_ref: str | None = None


__all__ = [
    "EVENT_FOR_STATE",
    "LEGAL_TRANSITIONS",
    "TERMINAL_STATES",
    "VERIFICATION_OUTCOMES",
    "Activity",
    "ActivityState",
    "AuthorityEnvelope",
    "Mission",
    "MissionEvent",
    "MissionEventType",
    "MissionOrigin",
    "MissionState",
    "Sensitivity",
    "SuccessContract",
    "VerificationRecord",
    "VerificationStatus",
]
