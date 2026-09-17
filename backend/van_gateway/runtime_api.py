from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.action.models import VerificationObservation
from van_gateway.action.registry import install_builtin_actions
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.config import Settings
from van_gateway.context.models import ContextEdgeCandidate, ContextRequirement, OwnerFactCandidate
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

    This is deliberately not an agent loop. Hermes profile ``van`` remains the
    sole planner/reasoner. The gateway owns canonical context, action policy,
    verification ledgers and provider credentials.
    """

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.context = OwnerContextService(store)
        self.actions = ActionRuntime(store)
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

    async def startup(self) -> None:
        await install_builtin_actions(self.actions)

    async def status(self) -> dict[str, Any]:
        action_count_row = await self.store.fetchone("SELECT COUNT(*) AS n FROM action_definitions WHERE enabled=1")
        return {
            "hermes_is_sole_agent_runtime": True,
            "context_kernel_revision": await self.context.kernel_revision(),
            "enabled_actions": int(action_count_row["n"]) if action_count_row is not None else 0,
            "research": await self.research.status(),
        }

    def _install_routes(self) -> None:
        router = self.router

        @router.get("/status")
        async def runtime_status(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.status()

        @router.post("/context/facts")
        async def admit_fact(body: OwnerFactCandidate, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.context.admit_fact(body)
            except ContextAdmissionError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @router.post("/context/edges")
        async def admit_edge(body: ContextEdgeCandidate, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                revision = await self.context.admit_edge(body)
                return {"edge_id": body.edge_id, "revision": revision}
            except ContextAdmissionError as exc:
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
            return {"scope": scope, "deleted_facts": await self.context.erase_scope(scope)}

        @router.post("/actions/begin")
        async def begin_action(body: ActionBeginBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.actions.begin(
                    execution_id=body.execution_id,
                    command_id=body.command_id,
                    turn_id=body.turn_id,
                    action_id=body.action_id,
                    principal_type=body.principal_type,
                    requested_by=body.requested_by,
                    idempotency_key=body.idempotency_key,
                    parameters=body.parameters,
                    snapshot_id=body.snapshot_id,
                    owner_approved=body.owner_approved,
                    command_age_seconds=body.command_age_seconds,
                )
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
