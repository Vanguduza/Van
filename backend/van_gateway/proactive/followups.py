"""Rev 1 §§11, 20, 29 — GAP-F-028: VAN's one form of proactive initiative.

The symbiotic audit's finding was structural, not missing code: `ProactivePolicyService
.may_create()` existed, `AttentionEngine` existed, `IntentContinuityGraph.mark_stale`
existed and was scheduled — and nothing ever connected "a thing has gone quiet" to "the
owner should hear about it" without the owner or an external event asking first. VAN was
reactive by construction, not by design choice.

This job is deliberately the narrowest thing that closes that gap. It has exactly one
effect: it opens `FOLLOW_UP` attention items, through the same `AttentionEngine.upsert`
every other producer in the gateway uses, for four conditions that are already true in
the database and that nothing was surfacing:

  * a mission has been `WAITING_FOR_OWNER` longer than `waiting_owner_after_ms`;
  * a mission reached `EXPIRED` (VAN handed off and never heard back) recently enough
    that it is still worth mentioning;
  * a Hermes escalation (`DecisionService`) has sat `OPEN` longer than the same
    owner-attention threshold — `DecisionRecord` has no `expiry` field of its own, so the
    waiting-on-owner threshold is what "past due" means for a decision too;
  * an intent the scheduled `understanding.mark_stale_intents` job already marked
    `STALE` (`IntentContinuityGraph.mark_stale`) — this job reads that state rather than
    recomputing the ninety-day rule itself, so the definition of "stale" lives in exactly
    one place.

What it never does, by construction rather than by convention: it does not open a
mission, it does not call `ActionRuntime`, it does not resolve a decision, and it does
not change an intent's status. Every write it makes is `AttentionEngine.upsert`, which is
itself read-only with respect to everything but the `attention` table. An owner who never
looks at Needs You is exactly as unaffected as one who does — this job cannot make VAN
act on any of it.

It is idempotent by the same mechanism `AttentionEngine` already gives every other
producer: `dedupe_key` is stable per condition per row (`followup:<kind>:<id>`), so a
second run against an unchanged condition updates the same attention row rather than
creating a second one, and `AttentionEngine`'s own budget and quiet-hours handling apply
to what this job produces exactly as they apply to everything else. It respects
`ProactivePolicyService.follow_ups_enabled` per coarse domain (`"missions"`,
`"decisions"`, `"intents"`) before doing anything for that category, so an owner who
wants VAN to stop mentioning open decisions can say so once rather than snoozing them
forever.
"""

from __future__ import annotations

import time
from typing import Any

from van_gateway.attention.engine import AttentionEngine
from van_gateway.decisions.service import DecisionService
from van_gateway.mission.models import MissionState
from van_gateway.mission.service import MissionService
from van_gateway.models import AttentionSeverity
from van_gateway.proactive.autonomy import ProactivePolicyService
from van_gateway.storage.db import Store

#: DECISION (recorded): six hours. Long enough that a mission genuinely waiting on the
#: owner's ordinary attention is not chased before they have had a reasonable chance to
#: see it; short enough that "waiting on you" does not silently age into "VAN gave up
#: mentioning it".
DEFAULT_WAITING_OWNER_AFTER_MS = 6 * 60 * 60 * 1000

#: DECISION (recorded): seven days, matched to `AttentionEngine.list_open`'s own STALE
#: window for an unhandled item. Also used as the recency cutoff for surfacing an EXPIRED
#: mission at all: an expiry from months ago is history, not a follow-up.
DEFAULT_STALE_INTENT_AFTER_MS = 7 * 24 * 60 * 60 * 1000


class ProactiveFollowUpJob:
    """GAP-F-028 — the bounded proactive job. See the module docstring for what it is
    not allowed to do.

    Constructor kwargs, for the `OpsScheduler` job the manager registers this behind:

      * `store` — read-only here, for the one query (`intent_nodes`) that has no
        dedicated repository method.
      * `attention` — the `AttentionEngine` every FOLLOW_UP item is written through.
      * `missions` — a `MissionService`, read via `list_missions`.
      * `decisions` — a `DecisionService`, read via `list_open`.
      * `proactive_policy` — a `ProactivePolicyService`, consulted per domain before
        that domain's category runs at all.
      * `waiting_owner_after_ms` (default 6h) — how long `WAITING_FOR_OWNER` and an
        open decision may sit before this job mentions them.
      * `stale_intent_after_ms` (default 7d) — the recency cutoff for surfacing an
        `EXPIRED` mission.
    """

    def __init__(
        self,
        store: Store,
        attention: AttentionEngine,
        missions: MissionService,
        decisions: DecisionService,
        proactive_policy: ProactivePolicyService,
        *,
        waiting_owner_after_ms: int = DEFAULT_WAITING_OWNER_AFTER_MS,
        stale_intent_after_ms: int = DEFAULT_STALE_INTENT_AFTER_MS,
    ) -> None:
        self.store = store
        self.attention = attention
        self.missions = missions
        self.decisions = decisions
        self.proactive_policy = proactive_policy
        self.waiting_owner_after_ms = waiting_owner_after_ms
        self.stale_intent_after_ms = stale_intent_after_ms

    async def run(self, now_ms: int | None = None) -> dict[str, Any]:
        """One sweep. Returns counts, the same shape every scheduled job in app.py
        reports through `ScheduledJob`/`scheduler_runs`."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        produced = {
            "missions_waiting": await self._missions_waiting(now),
            "missions_expired": await self._missions_expired(now),
            "decisions_open": await self._decisions_open(now),
            "intents_stale": await self._intents_stale(now),
        }
        return {"produced": produced, "total": sum(produced.values())}

    async def _missions_waiting(self, now_ms: int) -> int:
        if not await self.proactive_policy.follow_ups_enabled("missions"):
            return 0
        count = 0
        for mission in await self.missions.list_missions(
            states=[MissionState.WAITING_FOR_OWNER], limit=200
        ):
            waited_ms = now_ms - mission.updated_at_ms
            if waited_ms < self.waiting_owner_after_ms:
                continue
            await self.attention.upsert(
                title=f"Still waiting on you: {mission.title}"[:200],
                severity=AttentionSeverity.FOLLOW_UP,
                source="proactive",
                dedupe_key=f"followup:mission_waiting:{mission.mission_id}",
                project_id=mission.project_id,
                payload={
                    "mission_id": mission.mission_id,
                    "goal": mission.goal[:500],
                    "waiting_hours": waited_ms // (60 * 60 * 1000),
                },
            )
            count += 1
        return count

    async def _missions_expired(self, now_ms: int) -> int:
        if not await self.proactive_policy.follow_ups_enabled("missions"):
            return 0
        count = 0
        for mission in await self.missions.list_missions(
            states=[MissionState.EXPIRED], limit=200
        ):
            # An expiry older than the recency window is not a follow-up any more; the
            # owner either already saw it or it is old enough that mentioning it now
            # would be VAN dredging up history rather than following up.
            if now_ms - mission.updated_at_ms > self.stale_intent_after_ms:
                continue
            await self.attention.upsert(
                title=f"VAN never heard back: {mission.title}"[:200],
                severity=AttentionSeverity.FOLLOW_UP,
                source="proactive",
                dedupe_key=f"followup:mission_expired:{mission.mission_id}",
                project_id=mission.project_id,
                payload={"mission_id": mission.mission_id, "goal": mission.goal[:500]},
            )
            count += 1
        return count

    async def _decisions_open(self, now_ms: int) -> int:
        if not await self.proactive_policy.follow_ups_enabled("decisions"):
            return 0
        count = 0
        for decision in await self.decisions.list_open():
            age_ms = now_ms - decision.created_at_unix * 1000
            if age_ms < self.waiting_owner_after_ms:
                continue
            await self.attention.upsert(
                title=f"Still open: {decision.title}"[:200],
                severity=AttentionSeverity.FOLLOW_UP,
                source="proactive",
                dedupe_key=f"followup:decision:{decision.id}",
                payload={
                    "decision_id": decision.id, "escalation_source": decision.source,
                    "open_hours": age_ms // (60 * 60 * 1000),
                },
            )
            count += 1
        return count

    async def _intents_stale(self, now_ms: int) -> int:
        if not await self.proactive_policy.follow_ups_enabled("intents"):
            return 0
        # Reads state `understanding.mark_stale_intents` already wrote; the ninety-day
        # rule itself lives only in `IntentContinuityGraph.mark_stale`.
        rows = await self.store.fetchall(
            "SELECT intent_id, owner_goal FROM intent_nodes WHERE status = 'STALE' "
            "ORDER BY latest_observed_ms DESC LIMIT 200"
        )
        count = 0
        for row in rows:
            await self.attention.upsert(
                title=f"Still a goal? {row['owner_goal']}"[:200],
                severity=AttentionSeverity.FOLLOW_UP,
                source="proactive",
                dedupe_key=f"followup:intent_stale:{row['intent_id']}",
                payload={
                    "intent_id": str(row["intent_id"]),
                    "owner_goal": str(row["owner_goal"])[:500],
                },
            )
            count += 1
        return count


__all__ = [
    "DEFAULT_STALE_INTENT_AFTER_MS",
    "DEFAULT_WAITING_OWNER_AFTER_MS",
    "ProactiveFollowUpJob",
]
