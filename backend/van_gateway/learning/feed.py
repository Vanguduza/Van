"""The production events that reach the learning stores.

P1-LEARN-001: StrategyLearning, SymbioticGrowthLedger, AIEvolutionRadar, BenchmarkHarness
and DomainTrust all had correct invariants and no caller that recorded a real outcome. The
stores were written, tested and empty. VanEval's scores were threshold constants over row
counts, so a system that had done nothing scored the same as one that had done everything
right.

This is the feed. It is small on purpose: the events VAN actually has, rather than a
taxonomy of events it might one day produce.

  * a mission reached a terminal state — what was asked for, and how it ended;
  * the owner corrected something — the strongest signal there is, and the only one that
    outranks accumulation.

What it deliberately does not do is *conclude* anything. Recording that VAN changed its
behaviour, when VAN has not changed its behaviour, would be the same defect one layer up.
So the growth ledger is written only where an adaptation genuinely occurred — an owner
correction that superseded an assertion — and mission outcomes are recorded as outcomes,
which is what they are.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from van_gateway.evolution.radar import PromotionState, StrategyLearning, StrategyOutcome
from van_gateway.mission.models import Mission, MissionState
from van_gateway.storage.db import Store
from van_gateway.understanding.memory import (
    DecisionFingerprints,
    IntentContinuityGraph,
    SymbioticGrowthLedger,
)

#: Terminal states worth learning from, and what each one means about the work.
OUTCOME_KIND: dict[MissionState, str] = {
    MissionState.VERIFIED_SUCCESS: "verified_success",
    MissionState.PARTIAL_SUCCESS: "partial_success",
    MissionState.UNVERIFIABLE: "unverifiable",
    MissionState.FAILED: "failed",
    MissionState.BLOCKED_POLICY: "refused_policy",
    MissionState.BLOCKED_UNSAFE: "refused_unsafe",
    MissionState.CANCELLED: "cancelled",
    MissionState.EXPIRED: "expired",
}


class LearningFeed:
    """Records what actually happened, for the stores that had nothing to read."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.growth = SymbioticGrowthLedger(store)
        self.strategies = StrategyLearning(store)
        # P2-MEM-001 — §§65, 77. Both stores were complete and neither had a producer, so
        # the owner's standing goals and their decisions were concepts the system could
        # describe and had never seen an instance of.
        self.intents = IntentContinuityGraph(store)
        self.fingerprints = DecisionFingerprints(store)

    async def record_mission_outcome(
        self,
        *,
        mission_id: str,
        state: MissionState,
        goal: str,
        verification_status: str | None = None,
        evidence_refs: list[str] | None = None,
        now_ms: int | None = None,
    ) -> str | None:
        """One row per terminal mission. A non-terminal state is not an outcome."""
        kind = OUTCOME_KIND.get(state)
        if kind is None:
            return None
        stamp = int(time.time() * 1000) if now_ms is None else now_ms
        outcome_id = f"out_{mission_id}"
        await self.store.execute(
            """
            INSERT INTO learning_outcomes(
              outcome_id, mission_id, outcome_kind, goal, verification_status,
              evidence_refs_json, recorded_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(outcome_id) DO UPDATE SET
              outcome_kind = excluded.outcome_kind,
              verification_status = excluded.verification_status,
              evidence_refs_json = excluded.evidence_refs_json,
              recorded_at_ms = excluded.recorded_at_ms
            """,
            (
                outcome_id, mission_id, kind, goal[:500], verification_status,
                Store.dumps(sorted(set(evidence_refs or []))), stamp,
            ),
        )
        return outcome_id

    async def record_mission_opened(
        self, mission: Mission, *, now_ms: int | None = None
    ) -> dict[str, str | None]:
        """P2-MEM-001 — §§65, 77. What the owner asked for, and what they decided.

        A mission is a stated owner goal, which is what `IntentContinuityGraph` is a graph
        of. Observing it here means the graph is built from instructions VAN actually
        received rather than from a separate act of curation nobody performs. The node is
        keyed on the goal text, so asking for the same thing again refreshes a standing
        intent instead of creating a second one — which is what makes STALE mean
        "unmentioned for ninety days" rather than "recorded once".

        A decision fingerprint is recorded only where there was a decision: a mission
        whose authority envelope required the owner's presence is one they could have
        declined and did not. A command that needed no approval is not a choice, and
        recording one would fill §65's store with the owner's ordinary use of VAN.
        """
        intent = await self.intents.observe(
            owner_goal=mission.goal,
            project_id=mission.project_id,
            constraints=mission.constraints,
            now_ms=now_ms,
        )
        await self.intents.link_mission(intent.intent_id, mission.mission_id, now_ms=now_ms)

        decision_id = None
        if mission.authority_envelope.requires_owner_presence:
            decision_id = await self.fingerprints.record(
                owner_choice=f"approved: {mission.goal[:200]}",
                mission_id=mission.mission_id,
                context={
                    "mission_class": mission.mission_class,
                    "action_class": mission.authority_envelope.max_action_class.value,
                    "origin_channel": mission.origin_channel.value,
                    "sensitivity": mission.sensitivity.value,
                },
                options_considered=["approve", "decline"],
                # §12 — deliberately absent. VAN does not infer why the owner approved,
                # and writing a plausible reason here is how a fingerprint store becomes
                # a machine for justifying whatever the owner did last. `falsified()`
                # therefore returns nothing, and the understanding surface says that this
                # is because nothing was inferred rather than because nothing was wrong.
                inferred_reason=None,
                now_ms=now_ms,
            )
        return {"intent_id": intent.intent_id, "decision_id": decision_id}

    async def record_decision_outcome(
        self, mission: Mission, *, state: MissionState, now_ms: int | None = None
    ) -> None:
        """§12 — the outcome is what lets an inferred reason be wrong.

        Recorded against the mission rather than the fingerprint id so the caller does not
        have to carry one, and written only where a fingerprint exists: a mission nobody
        had to approve has no decision to have an outcome.
        """
        kind = OUTCOME_KIND.get(state)
        if kind is None:
            return
        rows = await self.store.fetchall(
            "SELECT decision_id FROM decision_fingerprints WHERE mission_id = ?",
            (mission.mission_id,),
        )
        for row in rows:
            await self.fingerprints.record_outcome(
                str(row["decision_id"]), outcome=kind, now_ms=now_ms,
            )

    #: P1-LEARN-005 — what each terminal state says about the *approach*, which is a
    #: different question from what it says about the mission.
    #:
    #: Only two states are evidence about a strategy. VERIFIED_SUCCESS means an
    #: independent observation confirmed the work; FAILED means it was attempted and did
    #: not do what it was supposed to. Everything else is a statement about authority, the
    #: owner, or VAN's own blind spots:
    #:
    #:   PARTIAL_SUCCESS   some postconditions held and some did not — real information
    #:                     about the world, but not a clean verdict on the approach
    #:   UNVERIFIABLE      explicitly "VAN does not know"
    #:   CANCELLED         the owner changed their mind
    #:   BLOCKED_POLICY    a statement about authority
    #:   BLOCKED_UNSAFE    a statement about safety
    #:   EXPIRED           nothing came back, which is as likely to be the runtime as the
    #:                     approach
    STRATEGY_OUTCOME: dict[MissionState, StrategyOutcome] = {
        MissionState.VERIFIED_SUCCESS: StrategyOutcome.SUCCESS,
        MissionState.FAILED: StrategyOutcome.FAILURE,
        MissionState.PARTIAL_SUCCESS: StrategyOutcome.INCONCLUSIVE,
        MissionState.UNVERIFIABLE: StrategyOutcome.INCONCLUSIVE,
        MissionState.CANCELLED: StrategyOutcome.INCONCLUSIVE,
        MissionState.BLOCKED_POLICY: StrategyOutcome.INCONCLUSIVE,
        MissionState.BLOCKED_UNSAFE: StrategyOutcome.INCONCLUSIVE,
        MissionState.EXPIRED: StrategyOutcome.INCONCLUSIVE,
    }

    async def record_strategy_outcome(
        self, mission: Mission, *, state: MissionState, now_ms: int | None = None
    ) -> str | None:
        """P1-LEARN-003 — what VAN actually did for this kind of work, and how it went.

        A strategy is the ordered capability sequence the mission really executed, read
        back from its activities rather than from a plan. That distinction is the whole
        point: a plan is what VAN intended, and learning from intentions is how a system
        concludes that an approach works when it never ran.

        A mission with no activities produces nothing. That is the common case today —
        the gateway delegates to Hermes and Hermes creates the specialist work — and
        recording an empty sequence would make every free-form command look like the same
        successful strategy.
        """
        outcome = self.STRATEGY_OUTCOME.get(state)
        if outcome is None:
            # Not a terminal state, so there is no outcome to record. Defaulting to any of
            # the three would be inventing evidence.
            return None
        rows = await self.store.fetchall(
            "SELECT capability_id FROM mission_activities WHERE mission_id = ? "
            "ORDER BY started_at_ms, activity_id",
            (mission.mission_id,),
        )
        sequence = [str(r["capability_id"]) for r in rows]
        if not sequence:
            return None
        strategy_id = await self.strategies.find_or_register(
            mission_class=mission.mission_class,
            capability_sequence=sequence,
            # P1-LEARN-002 — the envelope this sequence was actually exercised under, so
            # a strategy can never be offered to a mission the owner authorised for less.
            max_action_class=mission.authority_envelope.max_action_class,
            now_ms=now_ms,
        )
        await self.strategies.record_outcome(strategy_id, outcome=outcome, now_ms=now_ms)
        return strategy_id

    #: GAP-F-008 — promotion states that mean a strategy has cleared VanEval, not merely
    #: accumulated runs. `permitted_for`/`preferred_for` answer "what does VAN prefer",
    #: which includes EXPERIMENTAL and SHADOW sequences nobody has reviewed evidence for;
    #: a caller placing this in `canonical_context` for Hermes to read is asking a
    #: narrower question — "what has VAN actually been allowed to keep doing" — so only
    #: the two states `StrategyLearning.promote` reaches with eval evidence behind them
    #: are offered here. Never CANDIDATE, EXPERIMENTAL, or SHADOW.
    READ_BACK_STATES = (PromotionState.ADMITTED.value, PromotionState.PREFERRED.value)

    async def strategies_for(
        self,
        *,
        intent_id: str | None,
        project_id: str | None = None,
        text: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """GAP-F-008 read-back — what VAN has actually learned works for this intent.

        `strategies_for` → `permitted_for` (evolution/radar.py) had no caller: every
        mission outcome fed the learning stores and nothing downstream ever read them
        back, so promotion existed and never changed what happened next. This is the
        caller — attached to `canonical_context` so a promoted strategy can inform the
        next same-intent command instead of being knowledge VAN has and never uses.

        `intent_id` is the typed resolver's intent (`CommandResolution.intent_id`, which
        is exactly what `Mission.mission_class` is populated from — see
        `mission/models.py`'s docstring on that field), so this matches directly on the
        column `record_strategy_outcome` writes strategies under. A missing intent (free
        text VAN could not classify, or no resolution yet) has nothing to match and
        returns nothing rather than guessing.

        `project_id` and `text` are accepted for symmetry with `context_requirements`'s
        call shape and so a future project- or fingerprint-scoped match can be added
        without changing every caller; `execution_strategies` rows are not project- or
        text-scoped today, so neither parameter narrows the match yet, and that is
        reported here rather than left to look like unused arguments.

        Bounded and read-only in every direction that matters for §27's discipline:
        results are capped at `limit`, nothing here is written, and a strategy's own
        `max_action_class` travels with it as `evidence_rate`/`outcome_counts` context —
        never as a grant. Offering a sequence proven under a wider envelope in `context`
        does not authorise it: `ActionRuntime.begin` re-checks principal, class and
        approval independently of anything in `canonical_context`, so nothing read back
        here can widen what a mission is actually permitted to execute.
        """
        if not intent_id:
            return []
        placeholders = ",".join("?" for _ in self.READ_BACK_STATES)
        rows = await self.store.fetchall(
            f"SELECT * FROM execution_strategies WHERE mission_class = ? "  # noqa: S608
            f"AND promotion_state IN ({placeholders}) ORDER BY updated_at_ms DESC",
            (intent_id, *self.READ_BACK_STATES),
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            success = int(row["success_count"])
            failure = int(row["failure_count"])
            inconclusive = int(row["inconclusive_count"])
            runs = success + failure
            if runs == 0:
                # ADMITTED needs an eval run, not a production run — §25 promotion is
                # separate from §41 "measurable improvement". A strategy the owner's
                # eval approved but that has never actually executed for this owner is
                # not yet evidence of what works *here*, so it is left out rather than
                # offered on the strength of a benchmark alone.
                continue
            sequence = json.loads(str(row["capability_sequence_json"]))
            fingerprint = hashlib.sha256(
                str(row["capability_sequence_json"]).encode("utf-8")
            ).hexdigest()[:16]
            out.append({
                "strategy_id": str(row["strategy_id"]),
                "fingerprint": fingerprint,
                "summary": f"{intent_id}: " + " -> ".join(sequence[:8]),
                "evidence_rate": round(success / runs, 3),
                "outcome_counts": {
                    "success": success, "failure": failure, "inconclusive": inconclusive,
                },
                # Always true: only PROMOTED strategies with real outcome evidence reach
                # this list, never a candidate. The field names that filter explicitly so
                # a consumer reading one row out of context still sees the guarantee.
                "permitted": True,
            })
            if len(out) >= max(0, limit):
                break
        return out

    async def record_owner_correction(
        self,
        *,
        assertion_id: str,
        field: str,
        previous_value: str,
        new_value: str,
        now_ms: int | None = None,
    ) -> str:
        """An owner correction is an adaptation, so it belongs in the growth ledger.

        It is also the one case where recording an adaptation is honest: the owner said
        something different, VAN superseded what it believed, and that changed what VAN
        will do. Nothing is inferred.
        """
        return await self.growth.record(
            observed_pattern=f"owner corrected {field}",
            previous_behavior=f"{field} = {previous_value}",
            new_behavior=f"{field} = {new_value}",
            reason="owner correction",
            evidence_refs=[f"assertion:{assertion_id}"],
            # Already the owner's own instruction; asking them to confirm their own
            # correction would be VAN not listening the first time.
            owner_confirmation_required=False,
            reversible=True,
            now_ms=now_ms,
        )

    async def outcome_counts(self) -> dict[str, int]:
        """What the learning stores actually hold, by outcome kind."""
        rows = await self.store.fetchall(
            "SELECT outcome_kind, COUNT(*) AS n FROM learning_outcomes GROUP BY outcome_kind", ()
        )
        return {str(r["outcome_kind"]): int(r["n"]) for r in rows}

    async def evidence_rate(self) -> dict[str, Any]:
        """How often a finished mission produced something checkable.

        This is the measure VanEval wanted and could not compute: a score over row counts
        cannot tell a system that verified its work from one that never tried.
        """
        counts = await self.outcome_counts()
        finished = sum(counts.values())
        verified = counts.get("verified_success", 0)
        unverifiable = counts.get("unverifiable", 0)
        return {
            "finished": finished,
            "verified": verified,
            "unverifiable": unverifiable,
            # None rather than 0.0 when nothing has finished: a system that has done
            # nothing has no success rate, and reporting zero would read as failure.
            "verified_rate": round(verified / finished, 3) if finished else None,
            "by_kind": counts,
        }


__all__ = ["OUTCOME_KIND", "LearningFeed"]
