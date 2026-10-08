"""Rev 1.3 §§219-222, 227, 402 — the Automation Fabric control surface.

Every route here is internal-control only. Hermes reaches the fabric through
these endpoints; it never touches the n8n management API (§38), never holds an
n8n credential (§14), and never receives a raw workflow ID as identity (§50).

The endpoints are thin. They resolve, delegate to the services that own each
rule, and translate refusals into structured HTTP — they do not re-decide policy,
because a second opinion is a second place for the rules to drift.
"""

from __future__ import annotations

import json
import time

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.automation.credentials import (
    CredentialAlias,
    CredentialClass,
    CredentialResolver,
)
from van_gateway.automation.events import (
    EventRejected,
    ExternalEventIngestor,
    Sensitivity,
    SourceTrust,
)
from van_gateway.automation.repair import (
    FailureClass,
    RepairService,
    decide as repair_decide,
)
from pydantic import BaseModel, Field

from van_gateway.automation.canonical import digest, new_id
from van_gateway.automation.cold import (
    ColdGenerationPlanner,
    GenerationOutcome,
    TemplateBackedProposer,
)
from van_gateway.automation.compiler import AutomationCompiler
from van_gateway.automation.provisioner import N8nProvisioner, ProvisioningError, graph_matches, verify_runtime_dependencies
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.automation.n8n_client import N8nClientError
from van_gateway.automation.source_credentials import SourceCredentialStore
from van_gateway.automation.standing_runner import StandingRunProducer, cron_due
from van_gateway.action.models import ActionDefinition, VerifierType
from van_gateway.action.service import ActionRuntime
from van_gateway.automation.dispatch import AutomationDispatcher, DispatchError
from van_gateway.automation.models import (
    AutomationWorkflowArtifact,
    IntentSignature,
    WorkflowCapability,
    WorkflowEngine,
    WorkflowLifecycle,
    WorkflowIR,
    LIFECYCLE_TRANSITIONS,
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
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store


class RepairOpenBody(BaseModel):
    """P2-DEAD-001 — what a failing capability needs to become a repair candidate."""

    capability_id: str = Field(min_length=1)
    failing_artifact_id: str = Field(min_length=1)
    failure_class: FailureClass
    failing_run_id: str | None = None
    error_code: str | None = None
    failing_node: str | None = None
    attempt: int = 1


class CredentialResolveBody(BaseModel):
    """P2-DEAD-001 — the alias a workflow asks for, and the class it claims."""

    alias: str = Field(min_length=1)
    credential_class: CredentialClass
    admitted: bool = False
    n8n_credential_id: str | None = None


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
    workflow_ir: WorkflowIR | None = None


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
    #: §5 — a mission-scoped run binds itself as an Activity, so the owner's
    #: Missions page reflects what actually executed.
    mission_id: str | None = None


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


class StandingRunBody(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


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
        binder: Any | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.registry = registry
        self.hot_index = hot_index
        self.standing = standing
        self.dispatcher = dispatcher
        self.binder = binder
        self.policy = policy or load_automation_policy()
        self.templates = TemplateLibrary()
        self.validator = WorkflowValidator(self.policy)
        self.source_credentials = SourceCredentialStore(getattr(settings, "automation_source_credentials_file", ""))
        self.compiler = AutomationCompiler(self.policy, self.source_credentials)
        self.runtime_bindings = RuntimeBindingStore(store)
        self.provisioner = N8nProvisioner(store, settings=settings, client=dispatcher.client,
            registry=registry, compiler=self.compiler) if dispatcher else None
        self.standing_runner = StandingRunProducer(store, standing=standing, registry=registry, dispatcher=dispatcher)
        self.planner = ColdGenerationPlanner(
            policy=self.policy, templates=self.templates, validator=self.validator
        )
        self.router_service = AutomationMediumRouter(
            registry=registry,
            hot_index=hot_index,
            templates=self.templates,
            temporal_available=(
                settings.temporal_enabled
                and bool(settings.temporal_bridge_url)
                and bool(settings.temporal_bridge_token)
            ),
        )
        # P2-DEAD-001 — three complete services that nothing imported. Each enforces a rule
        # the fabric is documented to enforce, so an unconstructed one is an unenforced rule.
        #
        # `events` carries §18: an external event may become evidence and may never become an
        # owner command. That is the rule, fully implemented, that had no ingress to guard.
        self.events = ExternalEventIngestor(
            store, ingress_enabled=settings.automation_ingress_enabled
        )
        # `credentials` refuses a payment-instrument credential in any class (owner decision
        # 2026-09-18). Unconstructed, the refusal never ran.
        self.credentials = CredentialResolver()
        # `repair` produces a candidate and never edits a live artifact, so a rollback is
        # always the previous artifact still sitting there.
        self.repair = RepairService(store, registry=registry)
        self.router = APIRouter(prefix="/v1/automation", tags=["automation"])
        self._install_routes()

    def _require_internal(self, token: str | None) -> None:
        # GAP-F-009: scope-aware, same authority as the middleware.
        require_scoped_internal(self.settings, token, ControlScope.AUTOMATION)

    def _require_enabled(self) -> None:
        if not self.settings.automation_enabled:
            raise HTTPException(status_code=503, detail="AUTOMATION_FABRIC_DISABLED")

    async def _ensure_credential_bindings(self) -> None:
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_credential_bindings(
            alias TEXT PRIMARY KEY, credential_class TEXT NOT NULL, admitted INTEGER NOT NULL,
            n8n_credential_id TEXT, gateway_capability TEXT)""")

    async def _load_credential_bindings(self) -> None:
        await self._ensure_credential_bindings()
        for row in await self.store.fetchall("SELECT * FROM automation_credential_bindings"):
            self.credentials.register(CredentialAlias(alias=row["alias"], credential_class=CredentialClass(row["credential_class"]),
                admitted=bool(row["admitted"]), n8n_credential_id=row["n8n_credential_id"], gateway_capability=row["gateway_capability"]))

    async def _persist_credential_binding(self, alias: CredentialAlias) -> None:
        await self._ensure_credential_bindings()
        await self.store.execute("""INSERT INTO automation_credential_bindings(alias,credential_class,admitted,n8n_credential_id,gateway_capability)
            VALUES (?,?,?,?,?) ON CONFLICT(alias) DO UPDATE SET credential_class=excluded.credential_class,
            admitted=excluded.admitted,n8n_credential_id=excluded.n8n_credential_id,gateway_capability=excluded.gateway_capability""",
            (alias.alias, alias.credential_class.value, int(alias.admitted), alias.n8n_credential_id, alias.gateway_capability))

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

            return await self.compile_candidate(body)

        @router.post("/workflows/{artifact_id}/provision")
        async def provision_workflow(artifact_id: str, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            return await self.provision_candidate(artifact_id)

        @router.post("/admit")
        async def admit(body: AdmitBody, x_van_internal_token: str | None = Header(default=None)):
            """§221 — one guarded transition. §154: no partial admission."""
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            return await self.transition_candidate(body)

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
                    mission_id=body.mission_id,
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
            # §5 — bind after dispatch, because the run_id only exists once the
            # dispatcher has minted it. A binding failure is reported rather than
            # raised: the run happened, and losing that fact to a bookkeeping
            # error would be worse than an unbound Activity.
            binding: dict[str, Any] | None = None
            if body.mission_id and self.binder is not None:
                try:
                    activity_id = await self.binder.bind_automation_run(
                        mission_id=body.mission_id, run_id=result.run_id
                    )
                    binding = {"mission_id": body.mission_id, "activity_id": activity_id}
                except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
                    binding = {
                        "mission_id": body.mission_id, "activity_id": None,
                        "error": type(exc).__name__, "detail": str(exc),
                    }

            return {
                "run_id": result.run_id,
                "mission_binding": binding,
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

        @router.post("/standing-authorities/{authority_id}/run")
        async def run_due_standing(authority_id: str, body: StandingRunBody,
                                   x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            source = await self.standing.get(authority_id)
            if source is None:
                raise HTTPException(status_code=404, detail="STANDING_AUTHORITY_NOT_FOUND")
            intent = await self.store.fetchone("SELECT trigger_json FROM automation_standing_intents WHERE intent_id=?", (source.standing_intent_id,))
            trigger = json.loads(intent["trigger_json"]) if intent else {}
            now = int(time.time() * 1000)
            try:
                if (str(trigger.get("kind", "")).upper() != "SCHEDULE" or trigger.get("timezone", "UTC") != "UTC"
                        or not cron_due(str(trigger.get("cron", "")), now)):
                    raise StandingAuthorityError("STANDING_TRIGGER_NOT_DUE")
                result = await self.standing_runner.run(authority_id, inputs=body.inputs,
                                                       trigger_key=f"schedule:{now // 60000}", now_ms=now)
            except (StandingAuthorityError, DispatchError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return result.model_dump(mode="json")

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

        @router.post("/events")
        async def ingest_external_event(
            request: Request,
            x_van_internal_token: str | None = Header(default=None),
            x_van_event_signature: str | None = Header(default=None),
            x_van_event_timestamp: str | None = Header(default=None),
        ):
            """§§15-18, 208-209 — the one door an external event comes through.

            P2-DEAD-001. `ExternalEventIngestor` implemented dedupe, a bounded replay window,
            HMAC verification, payload bounds and injection assessment, and no route reached
            it. The rule it exists to enforce — an external event may become evidence and may
            never become an owner command — was therefore unenforced at the only place it
            could be enforced.

            Owner trust is refused here rather than downgraded. An adapter that labels its own
            event OWNER_VERIFIED is trying to mint authority, and answering it with a quietly
            corrected trust level teaches it that the label is merely advisory.
            """
            self._require_internal(x_van_internal_token)
            body = await request.body()
            if len(body) > ExternalEventIngestor.MAX_PAYLOAD_BYTES:
                raise HTTPException(status_code=413, detail="EVENT_PAYLOAD_TOO_LARGE")
            try:
                parsed = json.loads(body or b"{}")
            except ValueError:
                raise HTTPException(status_code=400, detail="EVENT_BODY_NOT_JSON") from None
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="EVENT_BODY_NOT_AN_OBJECT")

            # A signature is verified when one is offered. An unsigned event is accepted only
            # as the lower trust it actually has; it is never promoted by omission.
            trust = SourceTrust.PROVIDER_UNSIGNED
            if x_van_event_signature is not None:
                secret = self.settings.automation_webhook_secret
                if not secret:
                    raise HTTPException(status_code=503, detail="WEBHOOK_SECRET_UNCONFIGURED")
                try:
                    ExternalEventIngestor.verify_provider_signature(
                        secret=secret, body=body, signature=x_van_event_signature,
                        timestamp_ms=int(x_van_event_timestamp or 0),
                        now_ms=int(time.time() * 1000),
                    )
                except (EventRejected, ValueError) as exc:
                    raise HTTPException(status_code=403, detail=str(exc)) from exc
                trust = SourceTrust.PROVIDER_SIGNED

            try:
                result = await self.events.ingest(
                    source_system=str(parsed.get("source_system", "")).strip() or "unknown",
                    event_type=str(parsed.get("event_type", "")).strip() or "unknown",
                    payload=parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {},
                    payload_schema_id=str(parsed.get("payload_schema_id", "")).strip() or "unknown",
                    source_trust=trust,
                    sensitivity=Sensitivity.INTERNAL,
                    provider_event_id=parsed.get("provider_event_id"),
                    source_account_alias=parsed.get("source_account_alias"),
                    observed_at_ms=parsed.get("observed_at_ms"),
                    correlation_refs=parsed.get("correlation_refs"),
                )
            except EventRejected as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {
                "event_id": result.event.event_id,
                "created": result.created,
                "source_trust": result.event.source_trust.value,
                "injection_assessment": ExternalEventIngestor.assess_injection(
                    result.event.payload
                ),
            }

        @router.post("/credentials/resolve")
        async def resolve_credential_alias(
            body: CredentialResolveBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            """§§45-46 — the alias a workflow may use, and the classes it may not.

            P2-DEAD-001. The rule that no credential class admits a payment instrument was
            written, tested and never called by anything, so a workflow could name any alias.
            """
            self._require_internal(x_van_internal_token)
            try:
                alias = self.credentials.register(
                    CredentialAlias(
                        alias=body.alias,
                        credential_class=body.credential_class,
                        admitted=body.admitted,
                        n8n_credential_id=body.n8n_credential_id,
                    )
                )
                await self._persist_credential_binding(alias)
            except PolicyError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"alias": alias.alias, "credential_class": alias.credential_class.value,
                    "admitted": alias.admitted}

        @router.post("/repair")
        async def open_repair(
            body: RepairOpenBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            """§§78, 243-245 — a failing workflow becomes a repair candidate, with lineage.

            P2-DEAD-001. `RepairService` was written, tested and imported by nothing, so a
            failing capability had no path to repair at all.

            A repair never edits a live artifact: it produces a candidate that goes through
            the ordinary admission path, which is what keeps rollback equal to "the previous
            artifact, still sitting there".
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                packet = await self.repair.build_packet(
                    capability_id=body.capability_id,
                    failing_artifact_id=body.failing_artifact_id,
                    failure_class=body.failure_class,
                    failing_run_id=body.failing_run_id,
                    error_code=body.error_code,
                    failing_node=body.failing_node,
                )
            except RegistryError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            decision = repair_decide(packet, attempt=body.attempt)
            return {
                "capability_id": packet.capability_id,
                "failing_artifact_id": packet.failing_artifact_id,
                "failure_class": packet.failure_class.value,
                "decision": decision.value,
                "attempt": body.attempt,
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

    async def provision_candidate(self, artifact_id: str):
        self._require_enabled()
        endpoint = getattr(self.settings, "automation_worker_endpoint", "")
        if self.provisioner is None or not endpoint:
            raise HTTPException(status_code=503, detail="AUTOMATION_WORKER_PROVISIONING_UNCONFIGURED")
        try:
            binding = await self.provisioner.provision(artifact_id, endpoint)
        except (ProvisioningError, N8nClientError, PolicyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"artifact_id": artifact_id, "binding_state": binding["binding_state"],
                "n8n_workflow_id": binding["n8n_workflow_id"], "full_digest": binding["full_digest"]}

    async def transition_candidate(self, body: AdmitBody):
        self._require_enabled()
        try:
            if body.target not in LIFECYCLE_TRANSITIONS[body.expected]:
                raise RegistryError(f"illegal_transition:{body.expected.value}->{body.target.value}")
            binding = await self.runtime_bindings.get(body.artifact_id)
            if body.n8n_workflow_id and (binding is None or binding["binding_state"] != "DEPLOYED" or body.n8n_workflow_id != binding["n8n_workflow_id"]):
                raise RegistryError("WORKFLOW_RUNTIME_BINDING_MISMATCH")
            if body.target in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}:
                if binding is None or binding["binding_state"] != "DEPLOYED" or binding["readiness_errors"]:
                    raise RegistryError("WORKFLOW_RUNTIME_NOT_DEPLOYED")
                if body.n8n_workflow_id and body.n8n_workflow_id != binding["n8n_workflow_id"]:
                    raise RegistryError("WORKFLOW_RUNTIME_BINDING_MISMATCH")
                if self.dispatcher is None:
                    raise RegistryError("AUTOMATION_DISPATCH_UNCONFIGURED")
                current = await self.registry.get_artifact(body.artifact_id)
                if current is None or current.lifecycle_state != body.expected:
                    raise RegistryError("transition_precondition_failed")
                ir = WorkflowIR.model_validate(binding["ir"])
                if (digest(ir.semantic_payload()) != current.workflow_ir_digest or
                        digest(binding["semantic_graph"]) != current.compiled_semantic_digest or
                        RuntimeBindingStore.compute_full_digest(binding["runtime_graph"], binding["dependencies"]) != current.compiled_full_digest or
                        binding["n8n_workflow_id"] != current.n8n_workflow_id):
                    raise RegistryError("WORKFLOW_RUNTIME_MANIFEST_MISMATCH")
                running = await self.store.fetchone("SELECT run_id FROM automation_runs WHERE capability_id=? AND status IN ('PENDING','DISPATCHED','SUBMITTED') LIMIT 1",
                                                     (current.capability_id,))
                if running:
                    raise RegistryError("WORKFLOW_REPLACEMENT_HAS_ACTIVE_RUNS")
                if body.target is WorkflowLifecycle.ADMITTED:
                    await verify_runtime_dependencies(self.dispatcher.client, binding)
                    await self.dispatcher.client.activate(binding["n8n_workflow_id"])
                else:
                    await verify_runtime_dependencies(self.dispatcher.client, binding)
                observed = await self.dispatcher.client.get_workflow(binding["n8n_workflow_id"])
                if observed.get("active") is not True or not graph_matches(binding["runtime_graph"], observed):
                    raise RegistryError("WORKFLOW_ACTIVATION_READBACK_MISMATCH")
            artifact = await self.registry.transition(
                body.artifact_id, expected=body.expected, target=body.target,
                n8n_workflow_id=binding["n8n_workflow_id"] if body.target is WorkflowLifecycle.ADMITTED else body.n8n_workflow_id,
                runtime_ir=ir if body.target is WorkflowLifecycle.ADMITTED else None,
            )
        except (RegistryError, N8nClientError, ProvisioningError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "artifact_id": artifact.artifact_id,
            "capability_id": artifact.capability_id,
            "version": artifact.version,
            "lifecycle_state": artifact.lifecycle_state.value,
            "admitted_at_ms": artifact.admitted_at_ms,
        }

    async def compile_candidate(self, body: CompileBody):
        """Persist a validated immutable proposal; this grants no execution authority."""
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
            await self._load_credential_bindings()
            required = [step.credential_alias for step in ir.steps if step.credential_alias]
            admitted_credentials = (self.source_credentials.admitted_handles(required) if self.source_credentials.configured
                                    else self.credentials.resolve_for_compilation(required))
            if body.credential_ids and body.credential_ids != admitted_credentials:
                raise PolicyError("caller_credential_binding_mismatch")
            compiled = self.compiler.compile(ir, credential_ids=admitted_credentials)
        except PolicyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        now = int(time.time() * 1000)
        capability_id = body.capability_id or new_id("capability")
        version = await self.registry.next_version(capability_id)
        active = await self.registry.get_capability(capability_id)
        if active and active.lifecycle_state in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT} and active.semantic_name != body.semantic_name:
            raise HTTPException(status_code=409, detail="CAPABILITY_SEMANTIC_IDENTITY_CONFLICT")
        proposed = (
            WorkflowCapability(
                capability_id=capability_id,
                semantic_name=body.semantic_name,
                engine=WorkflowEngine.N8N,
                action_class=ir.action_class,
                mutates_state=any(step.mutates for step in ir.steps),
                input_schema=ir.inputs_schema,
                output_schema=ir.outputs_schema,
                allowed_principals=["OWNER_DEVICE", "AUTOMATION"],
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
        if active is None or active.lifecycle_state not in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}:
            await self.registry.upsert_capability(proposed)
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
        await self.runtime_bindings.record(artifact_id=artifact.artifact_id, ir=ir.model_dump(mode="json"),
            semantic_graph=compiled.semantic_graph, runtime_graph=compiled.n8n_graph if compiled.deployable else None,
            readiness_errors=list(compiled.readiness_errors))
        actions = self.dispatcher.actions if self.dispatcher else ActionRuntime(self.store)
        if active is None or active.lifecycle_state not in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}:
            await actions.register(ActionDefinition(action_id=f"automation.workflow.{capability_id}",
                action_class=ir.action_class, mutates_state=any(step.mutates for step in ir.steps),
                allowed_principals={PrincipalType.OWNER_DEVICE, PrincipalType.AUTOMATION},
                verifier_type=VerifierType.READ_BACK, parameter_schema=ir.inputs_schema,
                no_stale_replay=ir.action_class is ActionClass.A4, max_age_seconds=5 if ir.action_class is ActionClass.A4 else 300))
        return {
            "capability_id": capability_id,
            "artifact_id": artifact.artifact_id,
            "version": version,
            "action_class": ir.action_class.value,
            "lifecycle_state": WorkflowLifecycle.PROPOSED.value,
            "semantic_digest": compiled.semantic_digest,
            "validation_report_digest": report.report_digest,
            "auto_admissible": compiled.deployable and self.policy.may_auto_admit(ir.action_class.value),
            "deployable": compiled.deployable,
            "runtime_readiness_errors": list(compiled.readiness_errors),
            "action_id": f"automation.workflow.{capability_id}",
        }

    def _build_ir(self, body: CompileBody):
        if body.workflow_ir is not None:
            if body.template_id is not None or body.bindings:
                raise TemplateError("compile_ir_and_template_are_exclusive")
            return body.workflow_ir
        if body.template_id is None:
            raise TemplateError("compile_requires_template_id")
        return self.templates.specialise(
            body.template_id, bindings=body.bindings,
            policy_version=self.policy.policy_version,
        )


__all__ = ["AutomationApi"]
