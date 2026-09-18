"""Rev 1.3 §§143-147, 155-156 — WorkflowCapability, WorkflowIR and lifecycle contracts.

The IR is deliberately platform-neutral (§20). Hermes proposes intent; the
Gateway compiles a validated IR into an n8n graph. Nothing about n8n's node
schema leaks into this module, which is what makes static analysis, diffing,
replay and engine substitution possible (§21).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass

RANK: dict[str, int] = {"A1": 1, "A2": 2, "A3": 3, "A4": 4, "A5": 5}


class WorkflowEngine(str, Enum):
    N8N = "N8N"
    TEMPORAL = "TEMPORAL"
    NATIVE = "NATIVE"


class WorkflowLifecycle(str, Enum):
    """§§51, 155. GENERATED is the pre-persistence state; PROPOSED is the first stored one."""

    GENERATED = "GENERATED"
    PROPOSED = "PROPOSED"
    QUARANTINED = "QUARANTINED"
    VALIDATED = "VALIDATED"
    ADMITTED = "ADMITTED"
    HOT = "HOT"
    DEGRADED = "DEGRADED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


#: §155 — the only permitted lifecycle transitions. Anything else is rejected by
#: the admission service so a workflow cannot skip validation on its way to HOT.
LIFECYCLE_TRANSITIONS: dict[WorkflowLifecycle, frozenset[WorkflowLifecycle]] = {
    WorkflowLifecycle.GENERATED: frozenset({WorkflowLifecycle.PROPOSED, WorkflowLifecycle.REVOKED}),
    WorkflowLifecycle.PROPOSED: frozenset({WorkflowLifecycle.QUARANTINED, WorkflowLifecycle.REVOKED}),
    WorkflowLifecycle.QUARANTINED: frozenset(
        {WorkflowLifecycle.VALIDATED, WorkflowLifecycle.REPAIR_REQUIRED, WorkflowLifecycle.REVOKED}
    ),
    WorkflowLifecycle.VALIDATED: frozenset(
        {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.REPAIR_REQUIRED, WorkflowLifecycle.REVOKED}
    ),
    WorkflowLifecycle.ADMITTED: frozenset(
        {
            WorkflowLifecycle.HOT,
            WorkflowLifecycle.DEGRADED,
            WorkflowLifecycle.REPAIR_REQUIRED,
            WorkflowLifecycle.SUPERSEDED,
            WorkflowLifecycle.REVOKED,
        }
    ),
    WorkflowLifecycle.HOT: frozenset(
        {
            WorkflowLifecycle.DEGRADED,
            WorkflowLifecycle.REPAIR_REQUIRED,
            WorkflowLifecycle.SUPERSEDED,
            WorkflowLifecycle.REVOKED,
        }
    ),
    WorkflowLifecycle.DEGRADED: frozenset(
        {WorkflowLifecycle.HOT, WorkflowLifecycle.REPAIR_REQUIRED, WorkflowLifecycle.REVOKED}
    ),
    WorkflowLifecycle.REPAIR_REQUIRED: frozenset(
        {WorkflowLifecycle.QUARANTINED, WorkflowLifecycle.SUPERSEDED, WorkflowLifecycle.REVOKED}
    ),
    WorkflowLifecycle.SUPERSEDED: frozenset({WorkflowLifecycle.REVOKED}),
    WorkflowLifecycle.REVOKED: frozenset(),
}


class WorkflowStepEffect(str, Enum):
    READ = "READ"
    NETWORK_READ = "NETWORK_READ"
    WRITE = "WRITE"
    DELETE = "DELETE"
    NOTIFY = "NOTIFY"
    SECURITY = "SECURITY"
    FINANCIAL = "FINANCIAL"
    AUTHORITY = "AUTHORITY"
    #: Owner decision 2026-09-18. Moving money is its own effect precisely so it
    #: can never be smuggled in as an ordinary WRITE.
    PAYMENT = "PAYMENT"
    #: Persisting a card, bank detail, wallet or payment-provider token. Named so
    #: the analyser can refuse it outright rather than relying on a credential check.
    PAYMENT_INSTRUMENT_STORAGE = "PAYMENT_INSTRUMENT_STORAGE"


#: §145 / config/automation/policy.yaml `prohibited_effects`, plus the owner's
#: 2026-09-18 payment prohibition — never compilable into an automation.
#: `docs/SECURITY_POLICY.md` §Payments: payment execution cannot be automated, and
#: a payment instrument is never stored. Both are therefore uncompilable, not
#: merely ungranted: no admission state and no owner approval makes a *workflow*
#: able to pay. A payment happens as an A4 native action under a fresh approval.
PROHIBITED_EFFECTS = frozenset(
    {
        WorkflowStepEffect.FINANCIAL,
        WorkflowStepEffect.AUTHORITY,
        WorkflowStepEffect.PAYMENT,
        WorkflowStepEffect.PAYMENT_INSTRUMENT_STORAGE,
    }
)

#: Effects that make a step a mutation, so it must declare a postcondition verifier.
MUTATING_EFFECTS = frozenset(
    {WorkflowStepEffect.WRITE, WorkflowStepEffect.DELETE, WorkflowStepEffect.NOTIFY}
)

#: Effects that constitute moving money or retaining the means to.
PAYMENT_EFFECTS = frozenset(
    {WorkflowStepEffect.PAYMENT, WorkflowStepEffect.PAYMENT_INSTRUMENT_STORAGE}
)


class RetryClass(str, Enum):
    IDEMPOTENT = "IDEMPOTENT"
    IDEMPOTENT_WITH_KEY = "IDEMPOTENT_WITH_KEY"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    NEVER_RETRY = "NEVER_RETRY"


class Primitive(str, Enum):
    """§147 — the stable compiler contract. n8n node versions are backends."""

    HTTP_GET = "HTTP_GET"
    HTTP_REQUEST = "HTTP_REQUEST"
    EVENT_TRIGGER = "EVENT_TRIGGER"
    SCHEDULE_TRIGGER = "SCHEDULE_TRIGGER"
    WEBHOOK_TRIGGER = "WEBHOOK_TRIGGER"
    FILTER = "FILTER"
    SWITCH = "SWITCH"
    MAP_FIELDS = "MAP_FIELDS"
    MERGE = "MERGE"
    DEDUPE = "DEDUPE"
    HASH = "HASH"
    WAIT = "WAIT"
    EXECUTE_SUBWORKFLOW = "EXECUTE_SUBWORKFLOW"
    VAN_CAPABILITY = "VAN_CAPABILITY"
    VAN_EVENT = "VAN_EVENT"
    VAN_EVIDENCE = "VAN_EVIDENCE"
    STORE_TRANSIENT_FILE = "STORE_TRANSIENT_FILE"
    DELETE_TRANSIENT_FILE = "DELETE_TRANSIENT_FILE"


TRIGGER_PRIMITIVES = frozenset(
    {Primitive.EVENT_TRIGGER, Primitive.SCHEDULE_TRIGGER, Primitive.WEBHOOK_TRIGGER}
)

#: §147 — named so a rejection message can be explicit rather than "unknown primitive".
DISALLOWED_PRIMITIVE_NAMES = frozenset(
    {
        "EXECUTE_SHELL",
        "ARBITRARY_JS",
        "ARBITRARY_PYTHON",
        "RAW_SQL_WRITE",
        "RAW_FILESYSTEM",
        "RAW_SSH",
        "BROKER_ORDER",
    }
)


class WorkflowIRStep(BaseModel):
    step_id: str
    primitive: Primitive
    operation: str

    input_bindings: dict[str, Any] = Field(default_factory=dict)
    output_name: str | None = None

    external_domain: str | None = None
    credential_alias: str | None = None

    effects: list[WorkflowStepEffect]
    action_class: ActionClass

    timeout_ms: int = Field(gt=0, le=300_000)
    retry_class: RetryClass
    max_attempts: int = Field(ge=1, le=5)

    idempotency_key_expr: str | None = None

    precondition: dict[str, Any] | None = None
    postcondition: dict[str, Any] | None = None

    @property
    def mutates(self) -> bool:
        return any(effect in MUTATING_EFFECTS for effect in self.effects)


class WorkflowIREdge(BaseModel):
    from_step: str
    to_step: str
    branch: str | None = None


class WorkflowIR(BaseModel):
    ir_id: str
    family: str
    semantic_goal: str
    version: int = Field(ge=1)

    trigger: dict[str, Any]
    inputs_schema: dict[str, Any] = Field(default_factory=dict)
    outputs_schema: dict[str, Any] = Field(default_factory=dict)

    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowIRStep]
    edges: list[WorkflowIREdge] = Field(default_factory=list)

    credential_requirements: list[str] = Field(default_factory=list)
    external_domains: list[str] = Field(default_factory=list)

    evidence_requirements: list[str] = Field(default_factory=list)
    verifier: dict[str, Any] = Field(default_factory=dict)

    action_class: ActionClass
    latency_class: str = "T3"
    engine_hint: WorkflowEngine = WorkflowEngine.N8N

    generated_from: list[str] = Field(default_factory=list)
    policy_version: str
    compiler_version: str

    def semantic_payload(self) -> dict[str, Any]:
        """The part of the IR that determines behavior.

        Excludes ``ir_id`` and provenance so two IRs that mean the same thing
        compile to the same semantic digest — this is what §263's determinism
        test and §50's lineage rely on.
        """
        return {
            "family": self.family,
            "semantic_goal": self.semantic_goal,
            "version": self.version,
            "trigger": self.trigger,
            "inputs_schema": self.inputs_schema,
            "outputs_schema": self.outputs_schema,
            "variables": self.variables,
            "steps": [step.model_dump(mode="json") for step in self.steps],
            "edges": [edge.model_dump(mode="json") for edge in self.edges],
            "credential_requirements": sorted(self.credential_requirements),
            "external_domains": sorted(self.external_domains),
            "evidence_requirements": sorted(self.evidence_requirements),
            "verifier": self.verifier,
            "action_class": self.action_class.value,
            "latency_class": self.latency_class,
            "engine_hint": self.engine_hint.value,
        }


class WorkflowCapability(BaseModel):
    capability_id: str
    semantic_name: str
    engine: WorkflowEngine
    runtime_workflow_ref: str | None = None

    action_class: ActionClass
    mutates_state: bool

    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    allowed_principals: list[str] = Field(default_factory=list)
    allowed_origin_channels: list[str] = Field(default_factory=list)

    latency_class: str
    duration_class: str

    required_context: list[str] = Field(default_factory=list)
    required_credentials: list[str] = Field(default_factory=list)

    verifier_type: str
    idempotency_policy: str
    evidence_policy: str

    lifecycle_state: WorkflowLifecycle
    workflow_ir_digest: str
    policy_version: str
    compiler_version: str

    created_at_ms: int
    updated_at_ms: int


class AutomationWorkflowArtifact(BaseModel):
    """§50 — VAN-owned lineage, independent of n8n workflow IDs."""

    artifact_id: str
    capability_id: str
    version: int
    workflow_ir_digest: str
    compiled_semantic_digest: str
    compiled_full_digest: str
    n8n_workflow_id: str | None = None
    compiler_version: str
    node_catalog_version: str
    policy_version: str
    source_refs: list[str] = Field(default_factory=list)
    validation_report_digest: str | None = None
    lifecycle_state: WorkflowLifecycle
    created_at_ms: int
    validated_at_ms: int | None = None
    admitted_at_ms: int | None = None


class RunStatus(str, Enum):
    """§156 — runtime execution state machine."""

    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    SUBMITTED = "SUBMITTED"
    VERIFYING = "VERIFYING"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    UNVERIFIABLE = "UNVERIFIABLE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD_LETTER = "DEAD_LETTER"


class IntentSignature(BaseModel):
    """§26 — semantic index key, so natural phrasing maps to one capability."""

    goal_class: str
    source_class: str
    destination_class: str
    mutation_class: ActionClass

    def canonical(self) -> dict[str, str]:
        """§170 — canonicalized so wording never affects the signature."""
        return {
            "goal_class": self.goal_class.strip().upper().replace(" ", "_"),
            "source_class": self.source_class.strip().upper().replace(" ", "_"),
            "destination_class": self.destination_class.strip().upper().replace(" ", "_"),
            "mutation_class": self.mutation_class.value,
        }


def strongest_class(steps: list[WorkflowIRStep]) -> ActionClass:
    """§146 — a workflow inherits the strongest consequence of any step.

    The compiler therefore cannot hide a consequential action inside a nominally
    read-only workflow.
    """
    if not steps:
        return ActionClass.A1
    return max((step.action_class for step in steps), key=lambda c: RANK[c.value])


__all__ = [
    "AutomationWorkflowArtifact",
    "DISALLOWED_PRIMITIVE_NAMES",
    "IntentSignature",
    "LIFECYCLE_TRANSITIONS",
    "MUTATING_EFFECTS",
    "PROHIBITED_EFFECTS",
    "Primitive",
    "RANK",
    "RetryClass",
    "RunStatus",
    "TRIGGER_PRIMITIVES",
    "WorkflowCapability",
    "WorkflowEngine",
    "WorkflowIR",
    "WorkflowIREdge",
    "WorkflowIRStep",
    "WorkflowLifecycle",
    "WorkflowStepEffect",
    "strongest_class",
]
