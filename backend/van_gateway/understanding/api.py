"""Rev 1 §§33, 43 — the Understanding surface and the honest scoreboard.

§33 requires the owner be able to inspect what VAN believes about how they work,
and to confirm, correct, reject, or scope it. §63.6 calls that owner agency and
§63.5 makes it mandatory that inferred understanding be reversible.

So every mutation here is the owner's, and none of them is internal-control:
Hermes may *observe*, but only the owner confirms. That asymmetry is the whole
point — a system that could confirm its own guesses about the owner would have
no owner model at all, just a memory of its own opinions.

`/v1/eval` is deliberately on this surface rather than an admin one. §41 says do
not self-award, and the most effective way to keep that honest is for the person
being claimed about to be able to read the scoreboard, including every dimension
VAN cannot measure and why.
"""

from __future__ import annotations

import json


from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.attention.scoring import AttentionScorer
from van_gateway.learning.feed import LearningFeed
from van_gateway.capability.permissions import PermissionRegistry
from van_gateway.config import Settings
from van_gateway.evolution.radar import AIEvolutionRadar, StrategyLearning
from van_gateway.evolution.vaneval import VanEval
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.proactive.autonomy import DomainTrustService, ProactivePolicyService
from van_gateway.reasoning.kernel import CriticalReasoningKernel
from van_gateway.storage.db import Store
from van_gateway.reasoning.calibration import RelationshipCalibrationEngine
from van_gateway.understanding.memory import (
    CognitiveComplementMap,
    SharedVocabularyRegistry,
    SymbioticGrowthLedger,
)
from van_gateway.understanding.owner_model import (
    OwnerCognitiveModel,
    OwnerModelError,
    OwnerModelField,
)


class ObserveBody(BaseModel):
    owner_principal_id: str
    field: OwnerModelField
    value: str
    episode_ref: str
    evidence_refs: list[str] = Field(default_factory=list)
    project_id: str | None = None


class CorrectBody(BaseModel):
    new_value: str


class UnderstandingApi:
    """`/v1/understanding`, `/v1/technology-radar`, `/v1/eval`, `/v1/autonomy`."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        # P1-LEARN-001 — the owner-facing surface is where corrections arrive, so this is
        # the instance that has to feed the growth ledger.
        self.owner_model = OwnerCognitiveModel(store, learning=LearningFeed(store))
        self.vocabulary = SharedVocabularyRegistry(store)
        self.complement = CognitiveComplementMap(store)
        self.growth = SymbioticGrowthLedger(store)
        self.kernel = CriticalReasoningKernel(store)
        # P2-DEAD-001 — §75. The engine decides how VAN says a thing and how hard it pushes,
        # never what it is willing to call true. It was complete, tested and imported by
        # nothing, so every answer came out at one fixed register regardless of how
        # consequential it was or how often VAN had recently been wrong.
        self.calibration = RelationshipCalibrationEngine(store)
        self.attention = AttentionScorer(store)
        self.trust = DomainTrustService(store)
        self.policies = ProactivePolicyService(store, self.trust)
        self.radar = AIEvolutionRadar(store)
        self.eval = VanEval(store)
        self.permissions = PermissionRegistry(store)
        self.router = APIRouter(prefix="/v1", tags=["understanding"])
        self._install_routes()

    def _require_internal(self, token: str | None) -> None:
        try:
            verify_internal_control(self.settings.internal_control_token, token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

    def _install_routes(self) -> None:
        router = self.router

        @router.get("/understanding")
        async def understanding(owner_principal_id: str = "owner"):
            """§33 — what VAN believes, how firmly, and what it has adapted."""
            return {
                **await self.owner_model.understanding(owner_principal_id),
                "shared_vocabulary": [
                    v.model_dump(mode="json") for v in await self.vocabulary.all_terms()
                ],
                "cognitive_complement": await self.complement.all(),
                "recent_adaptation": await self.growth.effective(),
                "adaptation_awaiting_you": await self.growth.awaiting_owner(),
            }

        @router.post("/understanding/{assertion_id}/confirm")
        async def confirm(assertion_id: str):
            try:
                assertion = await self.owner_model.confirm(assertion_id)
            except OwnerModelError as exc:
                raise HTTPException(status_code=404, detail=exc.code) from exc
            return assertion.model_dump(mode="json")

        @router.post("/understanding/{assertion_id}/correct")
        async def correct(assertion_id: str, body: CorrectBody):
            try:
                assertion = await self.owner_model.correct(
                    assertion_id, new_value=body.new_value
                )
            except OwnerModelError as exc:
                raise HTTPException(status_code=404, detail=exc.code) from exc
            return assertion.model_dump(mode="json")

        @router.post("/understanding/{assertion_id}/reject")
        async def reject(assertion_id: str):
            try:
                assertion = await self.owner_model.reject(assertion_id)
            except OwnerModelError as exc:
                raise HTTPException(status_code=404, detail=exc.code) from exc
            return assertion.model_dump(mode="json")

        @router.post("/understanding/adaptation/{change_id}/confirm")
        async def confirm_adaptation(change_id: str):
            await self.growth.confirm(change_id)
            return {"change_id": change_id, "confirmed": True}

        @router.post("/understanding/adaptation/{change_id}/revert")
        async def revert_adaptation(change_id: str):
            """§63.5 — inferred understanding must be reversible, in practice."""
            reverted = await self.growth.revert(change_id)
            if not reverted:
                raise HTTPException(status_code=409, detail="ADAPTATION_NOT_REVERSIBLE")
            return {"change_id": change_id, "reverted": True}

        @router.post("/understanding/observe")
        async def observe(
            body: ObserveBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """Hermes observes. It never confirms — that asymmetry is the point."""
            self._require_internal(x_van_internal_token)
            assertion = await self.owner_model.observe(
                owner_principal_id=body.owner_principal_id, field=body.field,
                value=body.value, episode_ref=body.episode_ref,
                evidence_refs=body.evidence_refs, project_id=body.project_id,
            )
            return assertion.model_dump(mode="json")

        @router.get("/permissions")
        async def permissions():
            """§36 — every standing grant, where it came from, when last used."""
            return await self.permissions.owner_view()

        @router.post("/permissions/{grant_id}/revoke")
        async def revoke_permission(grant_id: str):
            if not await self.permissions.revoke(grant_id):
                raise HTTPException(status_code=409, detail="PERMISSION_ALREADY_REVOKED")
            return {"grant_id": grant_id, "revoked": True}

        @router.get("/technology-radar")
        async def technology_radar():
            return {
                "technologies": await self.radar.radar(),
                "deprecations": await self.radar.deprecations(),
            }

        @router.get("/autonomy")
        async def autonomy():
            """§§30-31 — what VAN may do unprompted, per domain, and why."""
            rows = await self.store.fetchall("SELECT domain FROM domain_trust ORDER BY domain")
            domains = []
            for row in rows:
                trust = await self.trust.get(str(row["domain"]))
                domains.append({
                    "domain": trust.domain,
                    "earned_ceiling": trust.earned_ceiling.value,
                    "owner_granted_ceiling": (
                        trust.owner_granted_ceiling.value
                        if trust.owner_granted_ceiling else None
                    ),
                    "effective_ceiling": trust.effective_ceiling.value,
                    "verified_successes": trust.verified_successes,
                    "false_successes": trust.false_successes,
                    "suspended_for_false_success": trust.has_unrecovered_false_success,
                })
            return {"domains": domains, "policies": await self.policies.policies()}

        @router.get("/strategies")
        async def strategies():
            """§25 / §41 — what VAN has learned about how to do each kind of work.

            P1-LEARN-003 — every row here comes from a mission that actually ran: the
            capability sequence is read back from its activities, and only a
            VERIFIED_SUCCESS counts as a success. A strategy with no runs is not shown as
            an approach VAN prefers, because it is not one.

            `max_action_class` is the ceiling the sequence was exercised under, and
            P1-LEARN-002 is why it is on the wire: a strategy is only ever offered to a
            mission whose envelope already reaches that far, so nothing here can widen
            what VAN is permitted to do.
            """
            rows = await self.store.fetchall(
                "SELECT * FROM execution_strategies ORDER BY mission_class, updated_at_ms DESC"
            )
            out = []
            for row in rows:
                runs = int(row["success_count"]) + int(row["failure_count"])
                out.append({
                    "strategy_id": str(row["strategy_id"]),
                    "mission_class": str(row["mission_class"]),
                    "capability_sequence": json.loads(str(row["capability_sequence_json"])),
                    "promotion_state": str(row["promotion_state"]),
                    "max_action_class": str(row["max_action_class"]),
                    "runs": runs,
                    "verified_successes": int(row["success_count"]),
                    # None, not 0.0: a strategy nothing has exercised has no success rate,
                    # and reporting zero would read as one that keeps failing.
                    "success_rate": (
                        round(int(row["success_count"]) / runs, 3) if runs else None
                    ),
                    "eval_run_id": row["eval_run_id"],
                })
            return {
                "strategies": out,
                "promotion_rule": {
                    "preferred_min_runs": StrategyLearning.PREFERRED_MIN_RUNS,
                    "preferred_min_rate": StrategyLearning.PREFERRED_MIN_RATE,
                    "promotion_requires_eval_evidence": True,
                    "demotion_is_automatic": True,
                },
            }

        @router.get("/eval")
        async def run_eval():
            """§41 — the scoreboard, including everything it cannot score."""
            report = await self.eval.run()
            report["anti_sycophancy"] = await self.kernel.sycophancy_metrics()
            report["attention"] = await self.attention.metrics()
            return report


__all__ = ["UnderstandingApi"]
