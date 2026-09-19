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

import time
from typing import Any

from van_gateway.mission.models import MissionState
from van_gateway.storage.db import Store
from van_gateway.understanding.memory import SymbioticGrowthLedger

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
