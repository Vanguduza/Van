from __future__ import annotations

from enum import Enum
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
from van_gateway.authority.descriptor import Reversibility, describe_action
from van_gateway.context.service import ContextAdmissionError, OwnerContextService
from van_gateway.epistemics.models import SemanticClass
from van_gateway.reasoning.kernel import (
    AssumptionStatus,
    CriticalReasoningKernel,
    Importance,
    ReasoningError,
)
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.knowledge.models import (
    NotebookConsumerAskRequest,
    ObsidianIndexRequest,
    ObsidianQueryRequest,
    VeklQueryRequest,
)
from van_gateway.knowledge.notebook import NotebookProviderError
from van_gateway.knowledge.obsidian import ObsidianProviderError
from van_gateway.knowledge.service import KnowledgeRuntime
from van_gateway.knowledge.vekl import VeklProviderError
from van_gateway.models import PrincipalType
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.research.exa import ExaResearchService, ResearchPolicyError
from van_gateway.research.models import ResearchSearchRequest
from van_gateway.storage.db import Store


class ContextReadinessBody(BaseModel):
    command_id: str
    requirements: list[ContextRequirement]


class ContextSnapshotBody(ContextReadinessBody):
    graph_evidence_refs: list[str] = Field(default_factory=list)
    lexical_evidence_refs: list[str] = Field(default_factory=list)
    knowledge_evidence_refs: list[str] = Field(default_factory=list)
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


class AssumptionRecordBody(BaseModel):
    """What the planner is taking for granted, recorded where the gate can see it.

    `mission_id` rather than `command_id` because an assumption belongs to the work, and
    the same command can only ever have opened one mission.
    """

    mission_id: str = Field(min_length=1, max_length=256)
    claim: str = Field(min_length=1, max_length=2000)
    source: str = Field(min_length=1, max_length=256)
    importance: Importance = Importance.MEDIUM
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    testability: str = Field(default="UNKNOWN", max_length=64)
    verification_plan: str | None = Field(default=None, max_length=2000)


class PremiseAssessmentBody(BaseModel):
    """What the owner asserted, what VAN concluded, and what it cited.

    `agreed_without_evidence` is deliberately absent: the kernel derives it, so a caller
    cannot mark its own agreement well-founded. That derivation is what makes §17's
    unsupported-agreement rate a measurement rather than a self-report.
    """

    owner_premise: str = Field(min_length=1, max_length=4000)
    van_position: str = Field(min_length=1, max_length=4000)
    semantic_class: SemanticClass
    evidence_refs: list[str] = Field(default_factory=list)
    corrected: bool = False
    mission_id: str | None = Field(default=None, max_length=256)


class AssumptionResolveBody(BaseModel):
    status: AssumptionStatus
    evidence_refs: list[str] = Field(default_factory=list)
    superseded_by: str | None = Field(default=None, max_length=256)


class KnowledgeActionExecuteBody(BaseModel):
    execution_id: str = Field(min_length=1, max_length=256)
    parameters: dict[str, Any] = Field(default_factory=dict)


class HermesMissionResultStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_FOR_OWNER = "WAITING_FOR_OWNER"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"


class HermesMissionResultBody(BaseModel):
    hermes_run_id: str = Field(min_length=1, max_length=256)
    status: HermesMissionResultStatus
    summary: str = Field(default="", max_length=4000)


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
        self.resolver = TypedCommandResolver(
            default_notebook_id=getattr(settings, "notebook_default_id", ""),
        )
        self.kernel = CriticalReasoningKernel(store)
        self.knowledge = KnowledgeRuntime(store, settings)
        self.research = ExaResearchService(
            store,
            api_key=settings.exa_api_key,
            base_url=settings.exa_base_url,
            egress_enabled=settings.exa_egress_enabled,
            timeout_seconds=settings.exa_timeout_seconds,
        )
        self.missions: MissionService | None = None
        self.router = APIRouter(prefix="/v1/runtime", tags=["owner-runtime"])
        self._install_routes()

    def bind_missions(self, missions: MissionService) -> None:
        self.missions = missions

    async def _refuse_irreversible_work_on_unsettled_assumptions(
        self, definition: Any, command_id: str
    ) -> None:
        """§15's gate, applied where irreversible work is actually requested.

        Two decisions worth stating.

        **The descriptor decides what is irreversible**, not a list kept here. That is the
        point of `ACTION_REVERSIBILITY`: one place says whether the owner can undo a thing.
        UNDECLARED is treated as irreversible, matching the descriptor's own reasoning —
        an action whose reversibility nobody has decided is not assumed reversible, because
        that is the assumption that costs something.

        **A command with no mission is not exempt.** It is refused. A mission is how work
        is tracked, and an irreversible action arriving without one is either a bug or a
        path around the ledger; either way it is not the thing to wave through.
        """
        descriptor = describe_action(definition)
        if descriptor.reversibility not in (
            Reversibility.IRREVERSIBLE,
            Reversibility.UNDECLARED,
        ):
            return
        row = await self.store.fetchone(
            "SELECT mission_id FROM missions "
            "WHERE json_extract(authority_envelope_json, '$.source_command_id') = ?",
            (command_id,),
        )
        if row is None:
            raise HTTPException(
                status_code=409,
                detail="irreversible_action_without_a_mission",
            )
        try:
            await self.kernel.assert_safe_for_irreversible_work(str(row["mission_id"]))
        except ReasoningError as exc:
            raise HTTPException(status_code=409, detail=exc.code) from exc

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
        await self.knowledge.startup()
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
            "knowledge": await self.knowledge.status(),
        }

    def _install_routes(self) -> None:
        router = self.router

        @router.get("/status")
        async def runtime_status(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.status()

        @router.post("/missions/result")
        async def report_mission_result(
            body: HermesMissionResultBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            if self.missions is None:
                raise HTTPException(status_code=503, detail="mission_runtime_unbound")
            try:
                mission = await self.missions.apply_hermes_result(
                    hermes_run_id=body.hermes_run_id,
                    outcome=body.status.value,
                    summary=body.summary,
                )
            except MissionError as exc:
                code = 404 if exc.code == "HERMES_RUN_UNBOUND" else 409
                raise HTTPException(status_code=code, detail=exc.code) from exc
            return {
                "hermes_run_id": body.hermes_run_id,
                "mission_id": mission.mission_id,
                "state": mission.state.value,
                "verification_state": mission.verification_state.value,
                "final_outcome": mission.final_outcome,
            }

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
                    lexical_evidence_refs=body.lexical_evidence_refs,
                    knowledge_evidence_refs=body.knowledge_evidence_refs,
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

        @router.get("/knowledge/status")
        async def knowledge_status(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.knowledge.status()

        @router.post("/knowledge/vekl/query")
        async def knowledge_vekl_query(body: VeklQueryRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.query_vekl(body)
            except VeklProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/vekl/certify-canary")
        async def knowledge_vekl_certify(body: VeklQueryRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.certify_vekl(body)
            except VeklProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/obsidian/query")
        async def knowledge_obsidian_query(body: ObsidianQueryRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.query_obsidian(body)
            except ObsidianProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/obsidian/index")
        async def knowledge_obsidian_index(body: ObsidianIndexRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.index_obsidian(force=body.force)
            except ObsidianProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/obsidian/certify")
        async def knowledge_obsidian_certify(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.certify_obsidian()
            except ObsidianProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.get("/knowledge/notebook/enterprise/recent")
        async def knowledge_notebook_recent(page_size: int = 100, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return {"notebooks": await self.knowledge.notebook_enterprise_recent(page_size)}
            except NotebookProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.get("/knowledge/notebook/enterprise/{notebook_id}")
        async def knowledge_notebook_get(notebook_id: str, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.notebook_enterprise_get(notebook_id)
            except NotebookProviderError as exc:
                code = 404 if str(exc) == "notebook_enterprise_not_found" else 503
                raise HTTPException(status_code=code, detail=str(exc)) from exc

        @router.post("/knowledge/notebook/enterprise/certify")
        async def knowledge_notebook_enterprise_certify(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.certify_notebook_enterprise()
            except NotebookProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/notebook/consumer/ask")
        async def knowledge_notebook_consumer_ask(body: NotebookConsumerAskRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.ask_consumer_notebook(body)
            except NotebookProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/notebook/consumer/certify")
        async def knowledge_notebook_consumer_certify(body: NotebookConsumerAskRequest, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.certify_consumer_notebook(body)
            except NotebookProviderError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

        @router.post("/knowledge/actions/execute")
        async def knowledge_action_execute(body: KnowledgeActionExecuteBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                return await self.knowledge.execute_authorized_action(
                    self.actions, execution_id=body.execution_id, parameters=body.parameters,
                )
            except ActionPolicyError as exc:
                code = 404 if str(exc) == "unknown_execution" else 409
                raise HTTPException(status_code=code, detail=str(exc)) from exc

        # ------------------------------------------------------------- §15 reasoning
        #
        # The assumption ledger had neither a producer nor a consumer. `record_assumption`
        # was called by nothing, `assert_safe_for_irreversible_work` was called by nothing,
        # and there was no route through which the only system that does the reasoning —
        # Hermes — could have supplied one. A gate with no ingress is not a gate that is
        # switched off; it is a gate with no door.
        #
        # These are internal-control routes because an assumption is a statement about a
        # plan, which is the runtime's to make. It is emphatically not a statement about
        # the owner: P0-COG-001 keeps that on the owner's side of the boundary and nothing
        # here touches it.

        @router.post("/reasoning/assumptions")
        async def record_assumption(
            body: AssumptionRecordBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """Recording an assumption can only ever restrict, never permit.

            Which is why it needs no evidence to record and evidence to clear. The
            asymmetry is the whole design.
            """
            self._require_internal(x_van_internal_token)
            mission = await self.store.fetchone(
                "SELECT mission_id FROM missions WHERE mission_id = ?", (body.mission_id,)
            )
            if mission is None:
                raise HTTPException(status_code=404, detail="unknown_mission")
            assumption = await self.kernel.record_assumption(
                mission_id=body.mission_id,
                claim=body.claim,
                source=body.source,
                importance=body.importance,
                confidence=body.confidence,
                testability=body.testability,
                verification_plan=body.verification_plan,
            )
            return assumption.model_dump(mode="json")

        @router.get("/reasoning/assumptions/{mission_id}")
        async def list_blocking_assumptions(
            mission_id: str, x_van_internal_token: str | None = Header(default=None)
        ):
            """What is currently blocking irreversible work on this mission, and why.

            Readable so a planner can find out *before* it is refused, rather than
            discovering the gate by hitting it.
            """
            self._require_internal(x_van_internal_token)
            blocking = await self.kernel.blocking_assumptions(mission_id)
            return {
                "mission_id": mission_id,
                "blocking": [a.model_dump(mode="json") for a in blocking],
            }

        @router.post("/reasoning/assumptions/{assumption_id}/resolve")
        async def resolve_assumption(
            assumption_id: str,
            body: AssumptionResolveBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            try:
                await self.kernel.resolve_assumption(
                    assumption_id,
                    status=body.status,
                    evidence_refs=body.evidence_refs,
                    superseded_by=body.superseded_by,
                )
            except ReasoningError as exc:
                raise HTTPException(status_code=409, detail=exc.code) from exc
            return {"assumption_id": assumption_id, "status": body.status.value}

        @router.post("/reasoning/premises")
        async def record_premise_assessment(
            body: PremiseAssessmentBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            """§71 — every time VAN agreed or disagreed with a factual premise.

            The producer `sycophancy_metrics` never had. The metric reported
            `unmeasured` honestly, which was the right answer to give and still meant
            nobody could tell whether VAN was agreeing with the owner fluently — the
            specific failure §71 names as what makes personalisation dangerous.

            Nothing here can lower a gate. Recording an agreement only ever adds to the
            denominator of a rate VAN is judged by, which is why it needs no approval and
            why a caller cannot supply the flag that makes its own agreement look
            well-founded.
            """
            self._require_internal(x_van_internal_token)
            premise_id = await self.kernel.assess_premise(
                owner_premise=body.owner_premise,
                van_position=body.van_position,
                semantic_class=body.semantic_class,
                evidence_refs=body.evidence_refs,
                corrected=body.corrected,
                mission_id=body.mission_id,
            )
            return {"premise_id": premise_id}

        @router.post("/actions/begin")
        async def begin_action(body: ActionBeginBody, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            try:
                definition = await self.actions.get_definition(body.action_id)
                if definition is None:
                    raise ActionPolicyError("unknown_action")
                # §15 — irreversible work waits on the mission's unsettled high-impact
                # assumptions. Enforced here rather than at authorization because
                # assumptions are recorded during planning, which happens after the
                # orchestrator has handed the mission over; a check at authorize time would
                # always find an empty ledger and always pass.
                await self._refuse_irreversible_work_on_unsettled_assumptions(
                    definition, body.command_id
                )
                authority, command_age = await self.authority.authorize_action(
                    command_id=body.command_id,
                    action=definition,
                    principal_type=body.principal_type,
                    requested_by=body.requested_by,
                    snapshot_id=body.snapshot_id,
                    turn_id=body.turn_id,
                    parameters=body.parameters,
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