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
from van_gateway.evolution.radar import (
    AIEvolutionRadar,
    BenchmarkHarness,
    ExternalRealityModel,
    StrategyLearning,
)
from van_gateway.evolution.vaneval import VanEval
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.proactive.autonomy import DomainTrustService, ProactivePolicyService
from van_gateway.reasoning.kernel import CriticalReasoningKernel
from van_gateway.storage.db import Store
from van_gateway.reasoning.calibration import RelationshipCalibrationEngine
from van_gateway.understanding.memory import (
    CognitiveComplementMap,
    DecisionFingerprints,
    IntentContinuityGraph,
    SharedVocabularyRegistry,
    StrategicEntryType,
    StrategicMemory,
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


class StrategicMemoryBody(BaseModel):
    entry_type: StrategicEntryType
    statement: str
    rationale: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


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
        # P2-EVO-001 — §§22, 24, 79. Both had correct invariants and no surface: the
        # external-reality store had no producer and the benchmark harness no corpus,
        # and neither absence was reported anywhere.
        self.reality = ExternalRealityModel(store)
        self.benchmarks = BenchmarkHarness(store)
        self.eval = VanEval(store)
        self.permissions = PermissionRegistry(store)
        # P2-MEM-001 — §§65, 77, 78. Three stores with no route and no producer. The
        # producer is `LearningFeed`, on the mission path; these are the surfaces that
        # make what they hold the owner's to see and, for strategic memory, to write.
        self.intents = IntentContinuityGraph(store)
        self.fingerprints = DecisionFingerprints(store)
        self.strategic = StrategicMemory(store)
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

        @router.get("/understanding/intents")
        async def standing_intents():
            """§77 — the owner's long-lived goals, and what each is in tension with.

            P2-MEM-001 — the graph had no producer, so this was a concept VAN could
            describe and had never seen an instance of. Every node here came from a
            mission the owner actually opened.
            """
            rows = await self.store.fetchall(
                "SELECT intent_id FROM intent_nodes ORDER BY latest_observed_ms DESC"
            )
            out = []
            for row in rows:
                node = await self.intents.get(str(row["intent_id"]))
                if node is None:
                    continue
                conflicts = await self.intents.conflicts_for(node.intent_id)
                out.append({
                    **node.model_dump(mode="json"),
                    # The point of the graph: a newer instruction that contradicts an
                    # older standing goal is visible rather than silently winning because
                    # it arrived more recently.
                    "conflicts_with": [
                        {"intent_id": c.intent_id, "owner_goal": c.owner_goal}
                        for c in conflicts
                    ],
                })
            return {
                "intents": out,
                # P2-MEM-003 — separated, because they are different things. A standing
                # goal is what the owner is trying to do; an ephemeral one is a request
                # they made once. Presenting them in one list made every calendar lookup
                # look like a long-term commitment, and gave §77's conflict detection
                # transient commands to contradict genuine goals with.
                "standing": [
                    row for row in out if row["horizon"] in ("STANDING", "PROJECT")
                ],
                "one_off_requests": [row for row in out if row["horizon"] == "EPHEMERAL"],
                "promotion_rule": {
                    "observations_for_standing": self.intents.STANDING_AFTER_OBSERVATIONS,
                    "owner_declaration_is_sufficient": True,
                    "van_never_infers_a_standing_goal_from_one_request": True,
                },
                "stale_after_days": self.intents.STALE_AFTER_MS // (24 * 60 * 60 * 1000),
                # STALE is not abandoned, and the surface says so rather than leaving the
                # word to be read as a verdict.
                "stale_means": (
                    "unmentioned for long enough that VAN will ask before assuming it "
                    "still matters; only you abandon a goal"
                ),
            }

        @router.get("/understanding/decisions")
        async def decision_fingerprints():
            """§65 — what you decided and how it turned out.

            §12 forbids treating an inferred pattern as an unquestionable rule and
            requires outcomes to be able to falsify one. VAN does not currently infer why
            the owner decided anything, so every fingerprint here has a null inferred
            reason and `falsified` is empty. That is reported explicitly: an owner reading
            "no falsified patterns" from a silent surface would reasonably take it to mean
            VAN's model of them is accurate, when it means VAN has not made a claim.
            """
            rows = await self.store.fetchall(
                "SELECT decision_id, mission_id, owner_choice, owner_stated_reason, "
                "inferred_reason, outcome, created_at_ms FROM decision_fingerprints "
                "ORDER BY created_at_ms DESC LIMIT 200"
            )
            return {
                "decisions": [dict(r) for r in rows],
                "falsified": await self.fingerprints.falsified(),
                "pattern_inference": {
                    "active": False,
                    "why": (
                        "VAN records what you decided and how it turned out. It does not "
                        "infer why, so there is nothing here for an outcome to falsify."
                    ),
                },
            }

        @router.get("/projects/{project_id}/strategic-memory")
        async def strategic_memory(project_id: str):
            """§78 — why this project exists and what was already tried and rejected."""
            return {
                "project_id": project_id,
                "entries": await self.strategic.for_project(project_id),
                # §21 — kept apart from Project Truth on purpose, and said on the wire so
                # a rationale is not read back as a fact about the code.
                "not_project_truth": (
                    "Project Truth is what the repository is; this is why it became that"
                ),
            }

        @router.post("/projects/{project_id}/strategic-memory")
        async def record_strategic_memory(project_id: str, body: StrategicMemoryBody):
            """The owner is the author of project rationale, so this is an owner route.

            Recording something already rejected is answered with the rejection rather
            than a second entry: `already_rejected` is the question worth asking before
            proposing anything, and the one place it can be asked today is here.
            """
            if await self.strategic.already_rejected(project_id, body.statement):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STRATEGY_ALREADY_REJECTED",
                        "project_id": project_id,
                        "statement": body.statement,
                    },
                )
            entry_id = await self.strategic.record(
                project_id=project_id,
                entry_type=body.entry_type,
                statement=body.statement,
                rationale=body.rationale,
                evidence_refs=body.evidence_refs,
            )
            return {"entry_id": entry_id, "project_id": project_id}

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
                    "failures": int(row["failure_count"]),
                    # P1-LEARN-005 — runs that say nothing about the approach: refused,
                    # cancelled, expired, or finished without anything able to check them.
                    # Reported rather than hidden, because a strategy that keeps being
                    # cancelled is worth seeing and is not one that keeps failing. It is
                    # excluded from `runs` and from `success_rate` on purpose: including it
                    # either way would make VAN's blind spots look like evidence.
                    "inconclusive": int(row["inconclusive_count"]),
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
                    "inconclusive_runs_count_toward_neither": True,
                },
            }

        @router.get("/external-reality")
        async def external_reality(subject: str | None = None):
            """§§22, 79 — what available evidence says, kept apart from what you believe.

            §22 calls that separation mandatory, to prevent personalization becoming an
            echo chamber. P2-EVO-001 — the store had no producer, so the separation was
            protecting nothing. Every observation here comes from a research result with a
            citable source; the model refuses to record one without.

            `contradicts_owner_belief` is never set, because nothing compares a search
            result with the owner model. That is reported rather than left to be inferred:
            an empty contradiction list from a silent surface reads as the world agreeing
            with the owner, when it means no comparison was made.
            """
            observations = (
                await self.reality.current(subject) if subject
                else [
                    dict(r) for r in await self.store.fetchall(
                        "SELECT * FROM external_reality WHERE superseded_by IS NULL "
                        "ORDER BY observed_at_ms DESC LIMIT 200"
                    )
                ]
            )
            return {
                "subject": subject,
                "observations": observations,
                "contradictions": await self.reality.contradictions(),
                "contradiction_detection": {
                    "active": False,
                    "why": (
                        "nothing compares an external observation with the owner model, so "
                        "no observation is marked as contradicting one"
                    ),
                },
            }

        @router.get("/eval")
        async def run_eval():
            """§41 — the scoreboard, including everything it cannot score."""
            report = await self.eval.run()
            report["anti_sycophancy"] = await self.kernel.sycophancy_metrics()
            report["attention"] = await self.attention.metrics()
            # §24 — the benchmark vocabulary exists and no suite has a task corpus, which
            # is why no technology can reach ADMITTED. Reported here so that fail-closed
            # state is read from the scoreboard rather than discovered when an adoption is
            # refused.
            report["benchmarks"] = await self.benchmarks.coverage()
            return report


__all__ = ["UnderstandingApi"]
