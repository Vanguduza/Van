"""Rev 1.3 §§219-222, 227, 402 — the Automation Fabric control surface.

Every route here is internal-control only. Hermes reaches the fabric through
these endpoints; it never touches the n8n management API (§38), never holds an
n8n credential (§14), and never receives a raw workflow ID as identity (§50).

The endpoints are thin. They resolve, delegate to the services that own each
rule, and translate refusals into structured HTTP — they do not re-decide policy,
because a second opinion is a second place for the rules to drift.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.automation.canonical import digest, new_id
from van_gateway.automation.cold import (
    ColdGenerationPlanner,
    GenerationOutcome,
    TemplateBackedProposer,
)
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.dispatch import AutomationDispatcher, DispatchError
from van_gateway.automation.models import (
    AutomationWorkflowArtifact,
    IntentSignature,
    WorkflowCapability,
    WorkflowEngine,
    WorkflowLifecycle,
)
from van_gateway.automation.payments import PaymentBoundaryError
from van_gateway.automation.policy import AutomationPolicy, PolicyError, load_automation_policy
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex, RegistryError
from van_gateway.automation.router import AutomationMediumRouter, RouteRequest
from van_gateway.automation.templates import TemplateError, TemplateLibrary
from van_gateway.automation.verifier import PostconditionSpec
from van_gateway.automation.validator import WorkflowValidator
from van_gateway.command.standing import (
    StandingAuthorityError,
    StandingAutomationAuthorityService,
)
from van_gateway.config import Settings
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store


class RouteBody(BaseModel):
    goal: str
    signature: IntentSignature
    native_capability_id: str | None = None
    web_only: bool = False
    known_browser_capsule_id: str | None = None
    critical_durable: bool = False
    wants_reuse: bool = False


class CompileBody(BaseModel):
    """§220 — compile a capability from a template (WARM) or an IR (COLD result)."""

    semantic_name: str
    signature: IntentSignature
    template_id: str | None = None
    bindings: dict[str, Any] = Field(default_factory=dict)
    #: Resolved by the caller through CredentialResolver; aliases map to n8n ids.
    credential_ids: dict[str, str] = Field(default_factory=dict)
    capability_id: str | None = None


class AdmitBody(BaseModel):
    """§221 — walk an artifact through the lifecycle, one guarded step at a time."""

    artifact_id: str
    target: WorkflowLifecycle
    expected: WorkflowLifecycle
    n8n_workflow_id: str | None = None


class GenerateBody(BaseModel):
    """§22 — COLD generation. The gateway ships only the deterministic proposer."""

    goal: str
    signature: IntentSignature
    credential_aliases: list[str] = Field(default_factory=list)


class ExecuteBody(BaseModel):
    """§222 — execute an admitted capability under an existing command authority.

    There is no field here for an action class or an approval: both come from
    the sealed command record, which is why this endpoint cannot be used to
    escalate one. A standing run passes `standing_authority_id` instead of an
    owner command of its own.
    """

    capability_id: str
    action_id: str
    command_id: str
    snapshot_id: str
    requested_by: str
    #: Stated, not defaulted: it is compared against the sealed command record,
    #: and a default that silently mismatched would look like a policy refusal.
    principal_type: PrincipalType
    inputs: dict[str, Any] = Field(default_factory=dict)
    turn_id: str | None = None
    standing_authority_id: str | None = None


class PublishHotBody(BaseModel):
    capability_id: str
    signature: IntentSignature


class StandingIntentBody(BaseModel):
    """§227 — creating a persistent trigger is itself a mutation."""

    intent_id: str
    owner_goal: str
    source_command_id: str
    capability_id: str
    artifact_id: str
    workflow_version: int
    action_class_ceiling: ActionClass
    trigger: dict[str, Any]
    parameter_constraints: dict[str, Any] = Field(default_factory=dict)
    allowed_effects: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    owner_authority_evidence_ref: str
    expires_at_ms: int | None = None


class AutomationApi:
    """`/v1/automation/*` — compile, admit, publish, route, and standing intents."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        registry: AutomationRegistry,
        hot_index: HotWorkflowIndex,
        standing: StandingAutomationAuthorityService,
        policy: AutomationPolicy | None = None,
        dispatcher: AutomationDispatcher | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.registry = registry
        self.hot_index = hot_index
        self.standing = standing
        self.dispatcher = dispatcher
        self.policy = policy or load_automation_policy()
        self.templates = TemplateLibrary()
        self.validator = WorkflowValidator(self.policy)
        self.compiler = AutomationCompiler(self.policy)
        self.planner = ColdGenerationPlanner(
            policy=self.policy, templates=self.templates, validator=self.validator
        )
        self.router_service = AutomationMediumRouter(
            registry=registry, hot_index=hot_index, templates=self.templates
        )
        self.router = APIRouter(prefix="/v1/automation", tags=["automation"])
        self._install_routes()

    def _require_internal(self, token: str | None) -> None:
        try:
            verify_internal_control(self.settings.internal_control_token, token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

    def _require_enabled(self) -> None:
        if not self.settings.automation_enabled:
            raise HTTPException(status_code=503, detail="AUTOMATION_FABRIC_DISABLED")

    # ------------------------------------------------------------- routes

    def _install_routes(self) -> None:
        router = self.router

        @router.post("/route")
        async def route_goal(body: RouteBody, x_van_internal_token: str | None = Header(default=None)):
            """§5 — deterministic medium selection. Safe to call with the fabric off."""
            self._require_internal(x_van_internal_token)
            decision = await self.router_service.route(
                RouteRequest(
                    goal=body.goal, signature=body.signature,
                    native_capability_id=body.native_capability_id, web_only=body.web_only,
                    known_browser_capsule_id=body.known_browser_capsule_id,
                    critical_durable=body.critical_durable, wants_reuse=body.wants_reuse,
                )
            )
            return {
                "medium": decision.medium.value,
                "reason": decision.reason.value,
                "capability_id": decision.capability_id,
                "workflow_version": decision.workflow_version,
                "template_id": decision.template_id,
                "immediate_native_capability_id": decision.immediate_native_capability_id,
                "compile_in_background": decision.compile_in_background,
                "detail": decision.detail,
            }

        @router.post("/compile")
        async def compile_capability(
            body: CompileBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§220 — IR → validate → compile → persist as PROPOSED.

            Nothing is deployed and nothing is admitted here; the result is a
            candidate with a validation report attached (§51).
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()

            try:
                ir = self._build_ir(body)
            except (TemplateError, PolicyError, PaymentBoundaryError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            report = self.validator.validate(ir)
            if not report.ok:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "WORKFLOW_VALIDATION_FAILED", "errors": sorted(report.errors)},
                )

            try:
                compiled = self.compiler.compile(ir, credential_ids=body.credential_ids)
            except PolicyError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            now = int(time.time() * 1000)
            capability_id = body.capability_id or new_id("capability")
            version = await self.registry.next_version(capability_id)

            await self.registry.upsert_capability(
                WorkflowCapability(
                    capability_id=capability_id,
                    semantic_name=body.semantic_name,
                    engine=WorkflowEngine.N8N,
                    action_class=ir.action_class,
                    mutates_state=any(step.mutates for step in ir.steps),
                    input_schema=ir.inputs_schema,
                    output_schema=ir.outputs_schema,
                    allowed_principals=["OWNER_DEVICE", "HERMES_AGENT", "AUTOMATION"],
                    allowed_origin_channels=["VOICE", "TEXT", "UI", "AUTOMATION"],
                    latency_class=ir.latency_class,
                    duration_class="SECONDS",
                    required_context=[],
                    required_credentials=list(ir.credential_requirements),
                    verifier_type=str(ir.verifier.get("kind", "NONE")),
                    idempotency_policy="IDEMPOTENT_WITH_KEY",
                    evidence_policy="SEAL",
                    lifecycle_state=WorkflowLifecycle.PROPOSED,
                    workflow_ir_digest=digest(ir.semantic_payload()),
                    policy_version=self.policy.policy_version,
                    compiler_version=compiled.compiler_version,
                    created_at_ms=now, updated_at_ms=now,
                )
            )
            artifact = await self.registry.record_artifact(
                AutomationWorkflowArtifact(
                    artifact_id=new_id("artifact"),
                    capability_id=capability_id,
                    version=version,
                    workflow_ir_digest=digest(ir.semantic_payload()),
                    compiled_semantic_digest=compiled.semantic_digest,
                    compiled_full_digest=compiled.full_digest,
                    n8n_workflow_id=None,
                    compiler_version=compiled.compiler_version,
                    node_catalog_version=compiled.node_catalog_version,
                    policy_version=self.policy.policy_version,
                    source_refs=list(ir.generated_from),
                    validation_report_digest=report.report_digest,
                    lifecycle_state=WorkflowLifecycle.PROPOSED,
                    created_at_ms=now,
                )
            )
            return {
                "capability_id": capability_id,
                "artifact_id": artifact.artifact_id,
                "version": version,
                "action_class": ir.action_class.value,
                "lifecycle_state": WorkflowLifecycle.PROPOSED.value,
                "semantic_digest": compiled.semantic_digest,
                "validation_report_digest": report.report_digest,
                "auto_admissible": self.policy.may_auto_admit(ir.action_class.value),
            }

        @router.post("/admit")
        async def admit(body: AdmitBody, x_van_internal_token: str | None = Header(default=None)):
            """§221 — one guarded transition. §154: no partial admission."""
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                artifact = await self.registry.transition(
                    body.artifact_id, expected=body.expected, target=body.target,
                    n8n_workflow_id=body.n8n_workflow_id,
                )
            except RegistryError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {
                "artifact_id": artifact.artifact_id,
                "capability_id": artifact.capability_id,
                "version": artifact.version,
                "lifecycle_state": artifact.lifecycle_state.value,
                "admitted_at_ms": artifact.admitted_at_ms,
            }

        @router.post("/generate")
        async def generate(
            body: GenerateBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§§22, 29-31 — the COLD path, run with a deterministic proposer.

            §20 forbids a model emitting n8n JSON, and nothing here imports a model
            client: the gateway's proposer specialises a template when one fits and
            otherwise returns NO_PROPOSAL, at which point Hermes may propose a
            `WorkflowIR` of its own through `/compile`. Either way the IR meets the
            same validator.
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            planner = ColdGenerationPlanner(
                policy=self.policy, templates=self.templates, validator=self.validator,
                credential_aliases=list(body.credential_aliases),
            )
            result = await planner.generate(
                goal=body.goal, signature=body.signature,
                proposer=TemplateBackedProposer(self.templates),
            )
            payload: dict[str, Any] = {
                "outcome": result.outcome.value,
                "ok": result.ok,
                "detail": result.detail,
                "errors": result.errors,
                "elapsed_ms": result.elapsed_ms,
                "action_class": result.ir.action_class.value if result.ir else None,
                "requires_owner_approval": (
                    result.outcome is GenerationOutcome.REQUIRES_OWNER_APPROVAL
                ),
            }
            if result.ir is not None and result.ok:
                payload["ir"] = result.ir.model_dump(mode="json")
                payload["ir_digest"] = digest(result.ir.semantic_payload())
            if result.retrieval is not None:
                payload["prompt_contract"] = result.retrieval.as_prompt_contract()
            return payload

        @router.post("/execute")
        async def execute(
            body: ExecuteBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§222 — run an admitted capability, verified independently (§80).

            Everything that decides whether this is permitted lives behind the
            dispatcher: the Action Runtime re-derives the canonical rules and the
            command authority record supplies the class and any owner approval.
            The endpoint contributes no judgement of its own.
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            if self.dispatcher is None:
                raise HTTPException(status_code=503, detail="AUTOMATION_DISPATCH_UNCONFIGURED")

            # §165 — the postcondition comes from what the capability declared at
            # compile time, never from the caller. A run cannot ask to be verified
            # more weakly than the workflow it is running.
            capability = await self.registry.get_capability(body.capability_id)
            if capability is None:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "CAPABILITY_UNKNOWN", "detail": body.capability_id},
                )
            postcondition = (
                PostconditionSpec(kind=capability.verifier_type)
                if capability.verifier_type not in ("", "NONE")
                else None
            )
            try:
                result = await self.dispatcher.dispatch(
                    capability_id=body.capability_id, action_id=body.action_id,
                    command_id=body.command_id, principal_type=body.principal_type,
                    requested_by=body.requested_by, snapshot_id=body.snapshot_id,
                    inputs=body.inputs, turn_id=body.turn_id,
                    postcondition=postcondition,
                    standing_authority_id=body.standing_authority_id,
                )
            except DispatchError as exc:
                status = {
                    "AUTOMATION_FABRIC_DISABLED": 503,
                    "AUTOMATION_GRANTS_UNCONFIGURED": 503,
                    "CAPABILITY_NOT_ADMITTED": 409,
                    "CAPABILITY_UNKNOWN": 404,
                    "UNKNOWN_ACTION": 404,
                    "AUTHORITY_DENIED": 403,
                }.get(exc.code, 400)
                raise HTTPException(
                    status_code=status, detail={"error": exc.code, "detail": exc.detail}
                ) from exc
            return {
                "run_id": result.run_id,
                "capability_id": result.capability_id,
                "artifact_id": result.artifact_id,
                "status": result.status.value,
                # §17 — engine success is not owner success, so the distinction is
                # carried in the response rather than collapsed into `status`.
                "owner_success": result.owner_success,
                "verification_outcome": (
                    result.verification_outcome.value if result.verification_outcome else None
                ),
                "evidence_pointer": result.evidence_pointer,
                "error_code": result.error_code,
                "detail": result.detail,
            }

        @router.post("/hot/publish")
        async def publish_hot(
            body: PublishHotBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§25 — only an admitted artifact may enter the HOT index."""
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            artifact = await self.registry.admitted_artifact(body.capability_id)
            if artifact is None:
                raise HTTPException(status_code=409, detail="CAPABILITY_NOT_ADMITTED")
            self.hot_index.publish(
                body.signature, body.capability_id, artifact.version,
                artifact.n8n_workflow_id or "",
            )
            return {
                "capability_id": body.capability_id,
                "version": artifact.version,
                "hot_index_size": self.hot_index.size,
                "revision": self.hot_index.revision,
            }

        @router.post("/hot/withdraw/{capability_id}")
        async def withdraw_hot(
            capability_id: str, x_van_internal_token: str | None = Header(default=None)
        ):
            """§77 — a degraded capability stops being routed to immediately."""
            self._require_internal(x_van_internal_token)
            self.hot_index.withdraw(capability_id)
            return {"capability_id": capability_id, "hot_index_size": self.hot_index.size}

        @router.post("/standing-intents")
        async def create_standing_intent(
            body: StandingIntentBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§227 — creating a persistent trigger is itself a mutation.

            The standing authority is sealed from the owner's signed command, so a
            recurring automation can never carry more than that command permitted.
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()

            now = int(time.time() * 1000)
            await self.store.execute(
                """
                INSERT INTO automation_standing_intents(
                  intent_id, owner_goal, trigger_json, scope_json, allowed_effects_json,
                  expires_at_ms, capability_id, workflow_version, action_class,
                  owner_approval_ref, enabled, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(intent_id) DO UPDATE SET
                  owner_goal=excluded.owner_goal, trigger_json=excluded.trigger_json,
                  updated_at_ms=excluded.updated_at_ms
                """,
                (
                    body.intent_id, body.owner_goal, Store.dumps(body.trigger),
                    Store.dumps({"domains": body.allowed_domains}),
                    Store.dumps(sorted(body.allowed_effects)), body.expires_at_ms,
                    body.capability_id, body.workflow_version, body.action_class_ceiling.value,
                    body.owner_authority_evidence_ref, now, now,
                ),
            )
            try:
                authority = await self.standing.seal(
                    standing_intent_id=body.intent_id,
                    source_command_id=body.source_command_id,
                    capability_id=body.capability_id,
                    artifact_id=body.artifact_id,
                    workflow_version=body.workflow_version,
                    action_class_ceiling=body.action_class_ceiling,
                    trigger=body.trigger,
                    parameter_constraints=body.parameter_constraints,
                    allowed_effects=body.allowed_effects,
                    allowed_domains=body.allowed_domains,
                    owner_authority_evidence_ref=body.owner_authority_evidence_ref,
                    policy_version=self.policy.policy_version,
                    expires_at_ms=body.expires_at_ms,
                )
            except StandingAuthorityError as exc:
                # The intent row stays, disabled, so the refusal is visible rather
                # than leaving a dangling enabled intent with no authority.
                await self.store.execute(
                    "UPDATE automation_standing_intents SET enabled = 0 WHERE intent_id = ?",
                    (body.intent_id,),
                )
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            return {
                "intent_id": body.intent_id,
                "authority_id": authority.authority_id,
                "action_class_ceiling": authority.action_class_ceiling.value,
                "trigger_digest": authority.trigger_digest,
                "expires_at_ms": authority.expires_at_ms,
                "source_device_is_revocation_root": True,
            }

        @router.post("/standing-intents/{intent_id}/disable")
        async def disable_standing_intent(
            intent_id: str, x_van_internal_token: str | None = Header(default=None)
        ):
            self._require_internal(x_van_internal_token)
            now = int(time.time() * 1000)
            await self.store.execute(
                "UPDATE automation_standing_intents SET enabled = 0, updated_at_ms = ? "
                "WHERE intent_id = ?",
                (now, intent_id),
            )
            rows = await self.store.fetchall(
                "SELECT authority_id FROM standing_automation_authorities "
                "WHERE standing_intent_id = ? AND revoked_at_ms IS NULL",
                (intent_id,),
            )
            for row in rows:
                await self.standing.revoke(str(row["authority_id"]), now_ms=now)
            return {"intent_id": intent_id, "revoked_authorities": len(rows)}

        @router.get("/capabilities/{capability_id}")
        async def get_capability(
            capability_id: str, x_van_internal_token: str | None = Header(default=None)
        ):
            self._require_internal(x_van_internal_token)
            capability = await self.registry.get_capability(capability_id)
            if capability is None:
                raise HTTPException(status_code=404, detail="UNKNOWN_CAPABILITY")
            artifact = await self.registry.admitted_artifact(capability_id)
            return {
                "capability": capability.model_dump(mode="json"),
                "admitted_artifact": artifact.model_dump(mode="json") if artifact else None,
            }

        @router.get("/templates")
        async def list_templates(x_van_internal_token: str | None = Header(default=None)):
            """§30 — the WARM library is resident, so Hermes can see it cheaply."""
            self._require_internal(x_van_internal_token)
            return {
                "templates": [
                    {
                        "template_id": template.template_id,
                        "macro": template.macro,
                        "summary": template.summary,
                        "holes": [
                            {
                                "name": hole.name, "description": hole.description,
                                "required": hole.required,
                                "enum": list(hole.enum) if hole.enum else None,
                            }
                            for hole in template.holes
                        ],
                    }
                    for template in (
                        self.templates.get(tid) for tid in self.templates.template_ids
                    )
                ]
            }

    # ------------------------------------------------------------ helpers

    def _build_ir(self, body: CompileBody):
        if body.template_id is None:
            raise TemplateError("compile_requires_template_id")
        return self.templates.specialise(
            body.template_id, bindings=body.bindings,
            policy_version=self.policy.policy_version,
        )


__all__ = ["AutomationApi"]
