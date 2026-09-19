from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from van_gateway.observability.correlation import for_command as correlation_for_command


class ActionClass(str, Enum):
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    A4 = "A4"
    A5 = "A5"


class PrincipalType(str, Enum):
    OWNER_DEVICE = "OWNER_DEVICE"
    HERMES_AGENT = "HERMES_AGENT"
    AUTOMATION = "AUTOMATION"
    SYSTEM = "SYSTEM"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"


class OriginChannel(str, Enum):
    VOICE = "VOICE"
    TEXT = "TEXT"
    UI = "UI"
    NOTIFICATION_EVENT = "NOTIFICATION_EVENT"
    SHARE_INTENT = "SHARE_INTENT"
    AUTOMATION = "AUTOMATION"
    HERMES_EVENT = "HERMES_EVENT"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class AttentionSeverity(str, Enum):
    INFO = "INFO"
    FOLLOW_UP = "FOLLOW_UP"
    BLOCKER = "BLOCKER"
    URGENT = "URGENT"


class AttentionState(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    SNOOZED = "SNOOZED"
    WAITING_ON_OTHERS = "WAITING_ON_OTHERS"
    HANDLED = "HANDLED"
    STALE = "STALE"
    AUTO_RESOLVED = "AUTO_RESOLVED"


class DegradedCode(str, Enum):
    HERMES_OFFLINE = "HERMES_OFFLINE"
    GEMINI_UNAVAILABLE = "GEMINI_UNAVAILABLE"
    GOOGLE_TOKEN_EXPIRED = "GOOGLE_TOKEN_EXPIRED"
    GOOGLE_PARTIAL = "GOOGLE_PARTIAL"
    GOOGLE_PRINCIPAL_UNVERIFIED = "GOOGLE_PRINCIPAL_UNVERIFIED"
    GOOGLE_CAPABILITY_UNAVAILABLE = "GOOGLE_CAPABILITY_UNAVAILABLE"
    ANTIGRAVITY_CAPACITY_LIMITED = "ANTIGRAVITY_CAPACITY_LIMITED"
    GOOGLE_OAUTH_CLIENT_UNCONFIGURED = "GOOGLE_OAUTH_CLIENT_UNCONFIGURED"
    GOOGLE_ACCOUNT_ENTITLEMENT_UNVERIFIED = "GOOGLE_ACCOUNT_ENTITLEMENT_UNVERIFIED"
    NOTIFICATION_PERMISSION_REVOKED = "NOTIFICATION_PERMISSION_REVOKED"
    STALE_PROJECT_TRUTH = "STALE_PROJECT_TRUTH"
    REPO_UNAVAILABLE = "REPO_UNAVAILABLE"
    GROUP_ROOM_UNSUPPORTED = "GROUP_ROOM_UNSUPPORTED"
    WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
    EVENT_CURSOR_RESET = "EVENT_CURSOR_RESET"
    AUDIT_PROBLEM = "AUDIT_PROBLEM"
    STORAGE_PROBLEM = "STORAGE_PROBLEM"
    PHONE_OFFLINE = "PHONE_OFFLINE"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    TRADING_LEDGER_UNAVAILABLE = "TRADING_LEDGER_UNAVAILABLE"
    OWNER_CONTEXT_UNAVAILABLE = "OWNER_CONTEXT_UNAVAILABLE"
    OWNER_CONTEXT_CONFLICTED = "OWNER_CONTEXT_CONFLICTED"
    RESEARCH_UNAVAILABLE = "RESEARCH_UNAVAILABLE"
    RESEARCH_EGRESS_DENIED = "RESEARCH_EGRESS_DENIED"
    DEVICE_OR_GRANT_REVOKED = "DEVICE_OR_GRANT_REVOKED"
    # Rev 1.3 §100 / §421 — Automation & Browser Fabric degradation.
    AUTOMATION_FABRIC_UNAVAILABLE = "AUTOMATION_FABRIC_UNAVAILABLE"
    AUTOMATION_WORKFLOW_DEGRADED = "AUTOMATION_WORKFLOW_DEGRADED"
    AUTOMATION_CREDENTIAL_EXPIRED = "AUTOMATION_CREDENTIAL_EXPIRED"
    AUTOMATION_COMPILER_UNAVAILABLE = "AUTOMATION_COMPILER_UNAVAILABLE"
    AUTOMATION_SECURITY_AUDIT_FAILED = "AUTOMATION_SECURITY_AUDIT_FAILED"
    AUTOMATION_INGRESS_DISABLED = "AUTOMATION_INGRESS_DISABLED"
    BROWSER_HARNESS_UNAVAILABLE = "BROWSER_HARNESS_UNAVAILABLE"
    COMPUTER_USE_NO_SURFACE_WORKER = "COMPUTER_USE_NO_SURFACE_WORKER"
    BROWSER_SEMANTIC_UNAVAILABLE = "BROWSER_SEMANTIC_UNAVAILABLE"
    BROWSER_PROFILE_AUTH_REQUIRED = "BROWSER_PROFILE_AUTH_REQUIRED"


class ContentTrust(str, Enum):
    OWNER_SIGNED = "OWNER_SIGNED"
    PROJECT_TRUTH = "PROJECT_TRUTH"
    CAPABILITY_GRANT = "CAPABILITY_GRANT"
    DETERMINISTIC_STATE = "DETERMINISTIC_STATE"
    HERMES_MEMORY = "HERMES_MEMORY"
    CONVERSATION = "CONVERSATION"
    UNTRUSTED = "UNTRUSTED"


class OwnerApprovalProof(BaseModel):
    challenge_id: str
    # Optional echo only. The authoritative source command ID is embedded server-side
    # in the signed one-time challenge and is never trusted from the client.
    source_command_id: str | None = None
    signature_b64: str
    algorithm: str = "ECDSA_P256_SHA256"


class CommandRequest(BaseModel):
    command_id: str
    idempotency_key: str
    device_id: str
    issued_at_unix: int
    signature: str
    text: str
    action_class: ActionClass = ActionClass.A1
    project_id: str | None = None
    # Deprecated compatibility field. A non-empty string confers no authority.
    approval_token: str | None = None
    approval_proof: OwnerApprovalProof | None = None
    client_context: dict[str, Any] = Field(default_factory=dict)
    context_trust: ContentTrust = ContentTrust.CONVERSATION
    signature_version: int = 1
    turn_id: str | None = None
    origin_channel: OriginChannel = OriginChannel.UI
    principal_type: PrincipalType = PrincipalType.OWNER_DEVICE
    requested_by: str = "owner_device"
    expires_at_unix: int | None = None
    nonce: str | None = None
    context_capsule_revision: int | None = None
    context_capsule_hash: str | None = None
    speech_evidence_ref: str | None = None
    no_stale_replay: bool = False


class CommandResult(BaseModel):
    status: str
    command_id: str
    idempotency_key: str
    message: str
    hermes_run_id: str | None = None
    degraded: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    approval_challenge_id: str | None = None
    approval_challenge: str | None = None
    approval_expires_at_unix: int | None = None
    resolved_action_id: str | None = None
    effective_action_class: ActionClass | None = None
    no_stale_replay: bool | None = None
    max_age_seconds: int | None = None
    evidence_id: str | None = None
    execution_id: str | None = None
    context_snapshot_id: str | None = None
    #: P0-EXEC-001 — the durable work record this command opened. Present on every result
    #: from the point the command is established as owner intent, including the degraded
    #: ones, so the device can show a mission that was authorised and never started.
    mission_id: str | None = None
    #: P2-OBS-001 — the one identifier that joins this command to its mission, its
    #: Hermes run, its execution and its verification. Derived from `command_id`, so it
    #: is present on every result including the refusals, and an owner reporting a
    #: problem can quote it before anything downstream has run at all.
    correlation_id: str | None = None

    @model_validator(mode="after")
    def _derive_correlation_id(self) -> "CommandResult":
        """Fill the correlation id from the command id rather than asking 21 call
        sites to remember.

        The orchestrator builds a `CommandResult` in twenty-one places — every
        refusal, every degraded path, the replayed idempotent result. Adding an
        argument to each would have been twenty-one chances to miss one, and the
        one that got missed would be a refusal, which is the case an operator most
        needs to trace. Deriving it here makes "present on every result" a property
        of the type instead of a convention.
        """
        if not self.correlation_id and self.command_id:
            object.__setattr__(self, "correlation_id", correlation_for_command(self.command_id))
        return self


class AttentionItem(BaseModel):
    id: str
    title: str
    severity: AttentionSeverity
    state: AttentionState
    source: str
    project_id: str | None = None
    created_at_unix: int
    updated_at_unix: int
    dedupe_key: str
    snooze_until_unix: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BriefingCategory(str, Enum):
    NEEDS_YOU_NOW = "Needs you now"
    TODAY = "Today"
    WAITING_ON_OTHERS = "Waiting on others"
    PROJECTS_AT_RISK = "Projects at risk"
    MESSAGES_REQUIRING_REPLY = "Messages requiring reply"
    RECENT_COMPLETIONS = "Recent completions"
    HANDLED_AUTOMATICALLY = "Handled automatically"
    LOWER_PRIORITY = "Lower priority"


class BriefingSection(BaseModel):
    category: BriefingCategory
    items: list[dict[str, Any]] = Field(default_factory=list)


class Briefing(BaseModel):
    generated_at_unix: int
    sections: list[BriefingSection]
    invented_data: bool = False
    degraded: list[str] = Field(default_factory=list)


class DegradedCapability(BaseModel):
    code: DegradedCode
    broken: str
    still_works: str
    will_not_do: str
    restore_action: str


class ReminderCreate(BaseModel):
    text: str
    due_at_unix: int
    idempotency_key: str
    project_id: str | None = None
    chain_follow_up_text: str | None = None
    chain_follow_up_offset_seconds: int | None = None


class GoogleConnectionStatus(BaseModel):
    connected: bool
    scopes: list[str] = Field(default_factory=list)
    services: dict[str, str] = Field(default_factory=dict)
    degraded: list[str] = Field(default_factory=list)