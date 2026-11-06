"""Bounded owner read contracts; runtime credentials and raw payloads have no fields."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OwnerDto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectionError(OwnerDto):
    section: str
    code: str = "LOCAL_STATE_UNAVAILABLE"


class OwnerReadView(OwnerDto):
    schema_version: Literal[1] = 1
    observed_at_ms: int
    # Availability of this local read, distinct from provider readiness.
    status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"] = "AVAILABLE"
    errors: list[ProjectionError] = Field(default_factory=list)


class OwnerCommandControl(OwnerDto):
    control_id: str
    label: str
    action_id: str
    command_template: str
    required_fields: list[str] = Field(default_factory=list)
    submission_path: Literal["/v1/commands"] = "/v1/commands"
    available: bool
    unavailable_reason: str | None = None
    action_class: str | None = None
    approval_policy: Literal["SIGNED_OWNER_COMMAND_AND_CONTROLLER_POLICY"] = (
        "SIGNED_OWNER_COMMAND_AND_CONTROLLER_POLICY"
    )


class ProviderReadiness(OwnerDto):
    provider: str
    state: str
    credential_locus: str
    evidence_pointer: str | None = None
    verified_at_ms: int | None = None


class KnowledgeCitation(OwnerDto):
    evidence_id: str
    provider: str
    query_id: str
    source_ref: str | None = None
    title: str | None = None
    source_trust: str
    epistemic_state: str
    scope: str
    retrieved_at_ms: int
    content_digest: str
    snippet: str


class KnowledgeOperation(OwnerDto):
    operation_id: str
    provider: str
    operation: str
    status: str
    resource_id: str | None = None
    evidence_pointer: str | None = None
    error_code: str | None = None
    updated_at_ms: int


class OwnerKnowledgeView(OwnerReadView):
    providers: list[ProviderReadiness] = Field(default_factory=list)
    evidence: list[KnowledgeCitation] = Field(default_factory=list)
    operations: list[KnowledgeOperation] = Field(default_factory=list)
    controls: list[OwnerCommandControl] = Field(default_factory=list)
    canonical_truth_writes_exposed: Literal[False] = False
    provider_certification_required_for_ready: Literal[True] = True


class ResearchCitation(OwnerDto):
    evidence_id: str
    research_id: str
    source_url: str | None = None
    title: str | None = None
    source_trust: str
    published_at: str | None = None
    retrieved_at_ms: int
    content_digest: str
    highlights: list[str] = Field(default_factory=list)


class OwnerResearchView(OwnerReadView):
    provider: ProviderReadiness | None = None
    egress_enabled: bool = False
    evidence: list[ResearchCitation] = Field(default_factory=list)
    controls: list[OwnerCommandControl] = Field(default_factory=list)
    cached_evidence_is_current_provider_readiness: Literal[False] = False


class RuntimeReadiness(OwnerDto):
    capability: str
    state: str
    configured: bool
    egress_enabled: bool
    runtime_version: str | None = None
    expected_version: str | None = None
    evidence_pointer: str | None = None
    verified_at_ms: int | None = None
    degraded_code: str | None = None


class AutomationCapability(OwnerDto):
    capability_id: str
    semantic_name: str
    engine: str
    action_class: str
    mutates_state: bool
    lifecycle_state: str
    verifier_type: str
    updated_at_ms: int


class AutomationRun(OwnerDto):
    run_id: str
    capability_id: str
    artifact_id: str
    command_id: str | None = None
    execution_id: str | None = None
    status: str
    verifier_status: str | None = None
    evidence_pointer: str | None = None
    error_code: str | None = None
    owner_success: bool
    started_at_ms: int
    completed_at_ms: int | None = None


class StandingIntent(OwnerDto):
    intent_id: str
    owner_goal: str
    capability_id: str
    workflow_version: int
    action_class: str
    enabled: bool
    expires_at_ms: int | None = None
    expired: bool
    active_authorities: int
    current_device_authorities: int
    current_device_authority_roots: int
    executable_authority_present: bool
    disable_control: OwnerCommandControl


class AutomationDeadLetter(OwnerDto):
    dead_letter_id: str
    run_id: str | None = None
    capability_id: str | None = None
    failure_class: str
    error_code: str | None = None
    attempt_count: int
    next_action: str
    evidence_refs: list[str] = Field(default_factory=list)
    created_at_ms: int


class OwnerAutomationView(OwnerReadView):
    runtime: RuntimeReadiness | None = None
    governance: dict[str, Any] = Field(default_factory=dict)
    ingress_enabled: bool = False
    egress_enabled: bool = False
    capabilities: list[AutomationCapability] = Field(default_factory=list)
    runs: list[AutomationRun] = Field(default_factory=list)
    standing_intents: list[StandingIntent] = Field(default_factory=list)
    dead_letters: list[AutomationDeadLetter] = Field(default_factory=list)
    workflow_health: dict[str, int] = Field(default_factory=dict)
    workflows_needing_attention: list[dict[str, Any]] = Field(default_factory=list)
    ladder: dict[str, int | float] = Field(default_factory=dict)
    engine_success_is_owner_success: Literal[False] = False


class OwnerDiagnosticsView(OwnerReadView):
    services: list[RuntimeReadiness] = Field(default_factory=list)
    computer_use: dict[str, Any] = Field(default_factory=dict)
    scheduler: dict[str, Any] = Field(default_factory=dict)
    pki: dict[str, Any] = Field(default_factory=dict)
    device_pki: dict[str, Any] = Field(default_factory=dict)
    backup: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)
    temporal: dict[str, Any] = Field(default_factory=dict)
    interactive_browser: dict[str, Any] = Field(default_factory=dict)
    live_provider_probe_performed: Literal[False] = False


class BrowserEvidenceSummary(OwnerDto):
    evidence_id: str
    kind: str
    source_trust: str
    injection_assessment: str
    created_at_ms: int
    content_digests: dict[str, str] = Field(default_factory=dict)


class MissionOutcome(OwnerDto):
    mission_id: str
    state: str
    verification_state: str
    owner_success: bool
    evidence_refs: list[str] = Field(default_factory=list)
    verified_at_ms: int | None = None
    verification_scope: Literal["MISSION"] = "MISSION"


class OwnerBrowserOutcomeView(OwnerReadView):
    task_id: str
    task_status: str
    execution_completed: bool
    # The historical task row does not persist the worker's final proposal.
    worker_goal_reported: bool | None = None
    owner_success: Literal[False] = False
    verification_state: Literal["UNVERIFIED"] = "UNVERIFIED"
    verification_scope: Literal["STANDALONE_TASK"] = "STANDALONE_TASK"
    evidence: list[BrowserEvidenceSummary] = Field(default_factory=list)
    mission_outcomes: list[MissionOutcome] = Field(default_factory=list)
    missing_postconditions: list[str] = Field(default_factory=lambda: [
        "An independent observer matched to the task goal is not registered."
    ])
    next_action: str = "Review task evidence and request a command with an explicit verifiable result."
