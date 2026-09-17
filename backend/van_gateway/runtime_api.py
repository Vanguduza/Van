from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.action.models import VerificationObservation
from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.command.authority import CommandAuthorityError, CommandAuthorityService
from van_gateway.command.resolver import TypedCommandResolver
from van_gateway.config import Settings
from van_gateway.context.models import (
    ContextEdgeCandidate,
    ContextGraphQuery,
    ContextRequirement,
    EpistemicState,
    OwnerFactCandidate,
    SourceTrust,
)
from van_gateway.context.retrieval import (
    ContextLexicalQuery,
    ContextRetrievalError,
    ContextRetrievalService,
    HotContextCapsuleRequest,
)
from van_gateway.context.service import ContextAdmissionError, OwnerContextService
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.models import PrincipalType
from van_gateway.research.exa import ExaResearchService, ResearchPolicyError
from van_gateway.research.models import ResearchSearchRequest
from van_gateway.storage.db import Store


class ContextReadinessBody(BaseModel):
    command_id: str
    requirements: list[ContextRequirement]


class ContextSnapshotBody(ContextReadinessBody):
    graph_evidence_refs: list[str] = Field(default_factory=list)
    live_state_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)


class CommandResolveBody(BaseModel):
    text: str


class ActionBeginBody(BaseModel):
    execution_id: str
    command_id: str
    turn_id: str | None = None
    action_id: str
    principal_type: PrincipalType
    requested_by: str
    idempotency_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    snapshot_id: str | None = None
    owner_approved: bool = False
    command_age_seconds: int = 0


class ActionSubmittedBody(BaseModel):
    correlation: dict[str, Any] = Field(default_factory=dict)
    evidence_pointer: str | None = None


class OwnerRuntimeApi:
    """Deterministic Rev 3.1 services exposed only to Hermes internal control.

    Hermes profile ``van`` is the sole planner/reasoner, but it is not a truth
    authority. Runtime memory writes from this surface are forced to
    MODEL_DERIVED + INFERRED; trusted/canonical admission must occur through a
    non-model owner/gateway authority path.
    """

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.context = OwnerContextService(store)
        self.retrieval = ContextRetrievalService(store, self.context)
        self.actions = ActionRuntime(store)
        self.authority = CommandAuthorityService(store)
        self.resolver = TypedCommandResolver()
        self.research = ExaResearchService(
            store,
            api_key=settings.exa_api_key,
            base_url=settings.exa_base_url,
            egress_enabled=settings.exa_egress_enabled,
            timeout_seconds=settings.exa_timeout_seconds,
        )
        self.router = APIRouter(prefix="/v1/runtime", tags=["owner-runtime"])
        self._install_routes()

    def _require_internal(self, token: str | None) -> None:
        try:
            verify_internal_control(self.settings.internal_control_token, token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

    @staticmethod
    def _require_hermes_memory_candidate(authority: EpistemicState, source_trust: SourceTrust) -> None:
        if authority != EpistemicState.INFERRED or source_trust != SourceTrust.MODEL_DERIVED:
            raise HTTPException(status_code=403, detail="hermes_context_admission_must_be_inferred_model_derived")

    async def startup(self) -> None:
        await install_builtin_actions(self.actions)

    async def status(self) -> dict[str, Any]:
        action_count_row = await self.store.fetchone("SELECT COUNT(*) AS n FROM action_definitions WHERE enabled=1")
        return {
            "hermes_is_sole_agent_runtime": True,
            "hermes_is_truth_authority": False,
            "context_kernel_revision": await self.context.kernel_revision(),
            "context_retrieval": {
                "exact": True,
                "temporal_graph": True,
                "deterministic_lexical": True,
                "hot_capsule": True,
                "semantic_on_critical_path": False,
            },
            "enabled_actions": int(action_count_row["n"]) if action_count_row is not None else 0,
            "resolver_version": "rev3.1.1",
            "signed_command_authority_required": True,
            "research": await self.research.status(),
        }

    def _install_routes(self) -> None:
        router = self.router

        @router.get("/status")
        async def runtime_status(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.status()

        @router.post("/resolve")
        async def resolve_command(body: CommandResolveBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return self.resolver.resolve(body.text)

        @router.post("/context/facts")
        async def admit_fact(body: OwnerFactCandidate, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            self._require_hermes_memory_candidate(body.authority, body.source_trust)
            try:
                return await self.context.admit_fact(body)
            except ContextAdmissionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @router.post("/context/edges")
        async def admit_edge(body: ContextEdgeCandidate, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            self._require_hermes_memory_candidate(body.authority, body.source_trust)
            try:
                revision = await self.context.admit_edge(body)
                return {"edge_id": body.edge_id, "revision": revision}
            except ContextAdmissionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @router.post("/context/graph/query")
        async def query_graph(body: ContextGraphQuery, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.context.traverse_graph(body)

        @router.post("/context/lexical/query")
        async def query_lexical(body: ContextLexicalQuery, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.retrieval.lexical_query(body)

        @router.post("/context/hot-capsules")
        async def compile_hot_capsule(
            body: HotContextCapsuleRequest,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                return await self.retrieval.compile_hot_capsule(body)
            except ContextRetrievalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @router.post("/context/readiness")
        async def readiness(body: ContextReadinessBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.context.readiness(body.command_id, body.requirements)

        @router.post("/context/snapshots")
        async def compile_snapshot(body: ContextSnapshotBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.context.compile_snapshot(
                    body.command_id,
                    body.requirements,
                    graph_evidence_refs=body.graph_evidence_refs,
                    live_state_refs=body.live_state_refs,
                    policy_refs=body.policy_refs,
                )
            except ContextAdmissionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @router.get("/context/export/{scope}")
        async def export_scope(scope: str, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.context.export_scope(scope)

        @router.delete("/context/scope/{scope}")
        async def erase_scope(scope: str, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return {"scope": scope, "deleted_items": await self.context.erase_scope(scope)}

        @router.post("/actions/begin")
        async def begin_action(body: ActionBeginBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                definition = await self.actions.get_definition(body.action_id)
                if definition is None:
                    raise ActionPolicyError("unknown_action")
                authority, command_age = await self.authority.authorize_action(
                    command_id=body.command_id,
                    action=definition,
                    principal_type=body.principal_type,
                    requested_by=body.requested_by,
                    snapshot_id=body.snapshot_id,
                    turn_id=body.turn_id,
                )
                return await self.actions.begin(
                    execution_id=body.execution_id,
                    command_id=body.command_id,
                    turn_id=authority.turn_id,
                    action_id=body.action_id,
                    principal_type=authority.principal_type,
                    requested_by=authority.requested_by,
                    idempotency_key=body.idempotency_key,
                    parameters=body.parameters,
                    snapshot_id=authority.snapshot_id,
                    owner_approved=authority.owner_approved,
                    command_age_seconds=command_age,
                )
            except CommandAuthorityError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except ActionPolicyError as exc:
                code = 403 if str(exc) == "principal_not_allowed" else 409
                raise HTTPException(status_code=code, detail=str(exc)) from exc

        @router.post("/actions/{execution_id}/submitted")
        async def mark_submitted(
            execution_id: str,
            body: ActionSubmittedBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                return await self.actions.mark_submitted(
                    execution_id,
                    correlation=body.correlation,
                    evidence_pointer=body.evidence_pointer,
                )
            except ActionPolicyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @router.post("/actions/verify")
        async def verify_action(
            body: VerificationObservation,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                return await self.actions.verify(body)
            except ActionPolicyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        @router.get("/actions/{execution_id}")
        async def get_action(execution_id: str, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            execution = await self.actions.get_execution(execution_id)
            if execution is None:
                raise HTTPException(status_code=404, detail="unknown_execution")
            return execution

        @router.get("/research/status")
        async def research_status(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.research.status()

        @router.post("/research/search")
        async def research_search(body: ResearchSearchRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.research.search(body)
            except ResearchPolicyError as exc:
                code = 503 if str(exc) in {"research_egress_disabled", "exa_api_key_unconfigured"} else 403
                raise HTTPException(status_code=code, detail=str(exc)) from exc

        @router.post("/research/certify-canary")
        async def research_canary(body: ResearchSearchRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.research.certify_canary(body)
            except ResearchPolicyError as exc:
                code = 503 if str(exc) in {"research_egress_disabled", "exa_api_key_unconfigured"} else 403
                raise HTTPException(status_code=code, detail=str(exc)) from exc
