"""Rev 1 §8 — the CapabilityRouter. The owner does not choose tools.

§3 of the prompt is the product requirement: the owner says "Van, research this"
and never picks between Stagehand, VEKL, NotebookLM or n8n. §8 is how that stays
honest — a deterministic preference order, policy as a hard filter, and the
decision persisted as evidence.

Two rules are worth stating because they are what keep this from becoming a
place where a model quietly acquires influence:

**Policy is a filter, not a score.** §8: *"No model score may override policy."*
Ineligible candidates are removed by `CapabilityRegistry.routability()` before
any arithmetic happens, so no weighting, however extreme, can promote something
the owner's envelope forbids. Scoring only ever ranks the already-permitted.

**The score is arithmetic over declared facts.** Every term comes from the
manifest — determinism, verification strength, latency, cost, privacy — none
from a model and none from the page or provider being routed to. The same
declaration set and the same constraints produce the same ranking, every time,
which is what makes the persisted decision reproducible rather than merely
recorded.

`AutomationMediumRouter` in `van_gateway.automation.router` is the other router
and a different job: once work is known to be automation, it picks the medium.
This one picks the capability.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from van_gateway.capability.models import (
    CapabilityClass,
    CapabilityDeclaration,
    CostClass,
    LatencyClass,
    PrivacyClass,
    Routability,
    RoutingConstraints,
    VerificationStrategy,
)
from van_gateway.capability.registry import CapabilityRegistry, CapabilityRegistryError
from van_gateway.storage.db import Store

ROUTING_POLICY_VERSION = "van-capability-routing-1"

#: §8's preference order, as weights over declared facts. Higher is preferred.
#: Verification quality dominates because §6's rule — no success without a
#: verifier receipt — is worth more than any amount of speed.
_VERIFICATION_WEIGHT = {
    VerificationStrategy.API_READBACK: 40,
    VerificationStrategy.LEDGER_EVENT: 40,
    VerificationStrategy.REPOSITORY_SHA: 38,
    VerificationStrategy.CI_RUN: 36,
    VerificationStrategy.PROVIDER_RECEIPT: 30,
    VerificationStrategy.SCREENSHOT: 18,
    VerificationStrategy.NONE: 0,
}
#: §8 prefers a deterministic local read over a semantic one; this encodes
#: "already verified context, then deterministic local, then retrieval, then
#: official API, then workflow, then semantic browser" as a class preference.
_CLASS_WEIGHT = {
    CapabilityClass.NATIVE_READ: 30,
    CapabilityClass.KNOWLEDGE_RETRIEVAL: 26,
    CapabilityClass.GOOGLE_WORKSPACE: 22,
    CapabilityClass.AUTOMATION: 18,
    CapabilityClass.WEB_RESEARCH: 14,
    CapabilityClass.NOTEBOOK: 12,
    CapabilityClass.REPOSITORY: 12,
    CapabilityClass.DEVELOPER: 10,
    CapabilityClass.TRADING_ANALYSIS: 10,
    CapabilityClass.BROWSER_INTERACTION: 6,
    CapabilityClass.COMPUTER_USE: 4,
    CapabilityClass.NOTIFICATION: 4,
    CapabilityClass.TRADING_EXECUTION: 0,
}
_LATENCY_WEIGHT = {
    LatencyClass.INTERACTIVE: 12, LatencyClass.SECONDS: 8,
    LatencyClass.MINUTES: 3, LatencyClass.LONG_RUNNING: 0,
}
_COST_WEIGHT = {
    CostClass.FREE: 10, CostClass.CHEAP: 7, CostClass.METERED: 3, CostClass.EXPENSIVE: 0,
}
#: Keeping owner data inside VAN is preferred, all else equal.
_PRIVACY_WEIGHT = {PrivacyClass.OWNER_PRIVATE: 10, PrivacyClass.EXTERNAL_DISCLOSING: 0}


@dataclass(frozen=True)
class ScoredCandidate:
    capability_id: str
    score: int
    breakdown: dict[str, int]

    def as_evidence(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "score": self.score,
            "breakdown": dict(self.breakdown),
        }


@dataclass(frozen=True)
class RouteDecision:
    """§8 — what was chosen, what was not, and why. Persisted as evidence."""

    decision_id: str
    goal_class: str
    selected: CapabilityDeclaration | None
    candidates: tuple[ScoredCandidate, ...] = ()
    rejected: tuple[Routability, ...] = ()
    fallback_chain: tuple[str, ...] = ()
    routing_policy_version: str = ROUTING_POLICY_VERSION
    manifest_digest: str = ""
    mission_id: str | None = None
    decided_at_ms: int = 0

    @property
    def routed(self) -> bool:
        return self.selected is not None

    @property
    def selected_capability_id(self) -> str | None:
        return self.selected.capability_id if self.selected else None


def score(declaration: CapabilityDeclaration) -> ScoredCandidate:
    """Pure arithmetic over declared facts. No I/O, no model, no caller input."""
    breakdown = {
        "verification": _VERIFICATION_WEIGHT.get(declaration.verification_strategy, 0),
        "class_preference": _CLASS_WEIGHT.get(declaration.capability_class, 0),
        "latency": _LATENCY_WEIGHT.get(declaration.latency_class, 0),
        "cost": _COST_WEIGHT.get(declaration.cost_class, 0),
        "privacy": _PRIVACY_WEIGHT.get(declaration.privacy_class, 0),
        # §8 counts determinism directly: a capability that can be checkpointed
        # and resumed loses less work when something fails mid-mission.
        "determinism": (5 if declaration.supports_resume else 0)
        + (5 if declaration.supports_checkpoint else 0)
        + (5 if not declaration.requires_network else 0),
        # An interruption the owner did not ask for is a cost, so a capability
        # that needs them present ranks below one that does not.
        "owner_interruption": -10 if declaration.requires_owner_presence else 0,
    }
    return ScoredCandidate(
        capability_id=declaration.capability_id,
        score=sum(breakdown.values()),
        breakdown=breakdown,
    )


class CapabilityRouter:
    """Picks the capability. Deterministic, policy-filtered, evidence-producing."""

    def __init__(self, store: Store, registry: CapabilityRegistry) -> None:
        self.store = store
        self.registry = registry

    async def route(
        self,
        *,
        goal_class: str,
        candidate_classes: list[CapabilityClass],
        constraints: RoutingConstraints | None = None,
        mission_id: str | None = None,
        persist: bool = True,
        now_ms: int | None = None,
    ) -> RouteDecision:
        """Select the best permitted capability, or none, and say why.

        `candidate_classes` is required, and that is the important part of this
        signature. Scoring ranks how *good* a capability is — how strongly it
        verifies, how fast, how private — but it has no idea what the goal was.
        Asked to route "LOOKUP" across everything declared, it will happily
        return the best-verified capability in the registry even if that is
        trading analysis, because nothing in the arithmetic knows better.

        Which classes can serve a goal is goal interpretation, and §2.1 gives
        that to Hermes. So the router refuses to guess rather than inventing a
        goal-to-class mapping of its own: Hermes narrows, the router chooses
        deterministically within the narrowing, and neither does the other's job.

        Returning a decision with `selected=None` rather than raising is
        deliberate: "nothing was routable, here is each candidate and the reason"
        is the useful answer, and it is what §8 wants persisted.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        constraints = constraints or RoutingConstraints()
        if not candidate_classes:
            raise CapabilityRegistryError(
                "ROUTE_CANDIDATE_CLASSES_REQUIRED",
                "the router does not interpret goals; name the classes that could serve it",
            )

        pool: list[CapabilityDeclaration] = []
        for capability_id in self.registry.capability_ids:
            declaration = self.registry.require(capability_id)
            if declaration.capability_class not in candidate_classes:
                continue
            pool.append(declaration)

        eligible: list[CapabilityDeclaration] = []
        rejected: list[Routability] = []
        for declaration in pool:
            verdict = await self.registry.routability(
                declaration.capability_id, constraints=constraints
            )
            if verdict.routable:
                eligible.append(declaration)
            else:
                rejected.append(verdict)

        # Scoring happens only over what policy already permitted.
        scored = sorted(
            (score(d) for d in eligible),
            # Ties break on capability_id so the ranking is total and stable —
            # a router that reorders equal candidates between runs is not
            # reproducible, and its persisted evidence would be misleading.
            key=lambda c: (-c.score, c.capability_id),
        )
        selected = self.registry.require(scored[0].capability_id) if scored else None

        decision = RouteDecision(
            decision_id=f"route_{uuid.uuid4().hex}",
            goal_class=goal_class,
            selected=selected,
            candidates=tuple(scored),
            rejected=tuple(rejected),
            fallback_chain=tuple(
                await self._fallback_chain(selected, constraints) if selected else ()
            ),
            manifest_digest=self.registry.manifest_digest,
            mission_id=mission_id,
            decided_at_ms=now,
        )
        if persist:
            await self._persist(decision)
        return decision

    async def _fallback_chain(
        self, declaration: CapabilityDeclaration, constraints: RoutingConstraints
    ) -> list[str]:
        """Declared fallbacks that are themselves currently routable.

        Following the chain transitively, with a visited set: a manifest cycle
        would otherwise hang the router, and the registry only rejects *self*
        reference at load time.
        """
        chain: list[str] = []
        seen = {declaration.capability_id}
        frontier = list(declaration.fallback_capabilities)
        while frontier:
            capability_id = frontier.pop(0)
            if capability_id in seen:
                continue
            seen.add(capability_id)
            verdict = await self.registry.routability(capability_id, constraints=constraints)
            if verdict.routable:
                chain.append(capability_id)
                nxt = self.registry.get(capability_id)
                if nxt is not None:
                    frontier.extend(nxt.fallback_capabilities)
        return chain

    async def _persist(self, decision: RouteDecision) -> None:
        await self.store.execute(
            """
            INSERT INTO capability_route_decisions(
              decision_id, mission_id, goal_class, selected_capability_id, candidates_json,
              rejected_json, fallback_chain_json, routing_policy_version, manifest_digest,
              decided_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id, decision.mission_id, decision.goal_class,
                decision.selected_capability_id,
                Store.dumps([c.as_evidence() for c in decision.candidates]),
                Store.dumps([
                    {
                        "capability_id": r.capability_id,
                        "reason": r.reason.value,
                        "detail": r.detail,
                    }
                    for r in decision.rejected
                ]),
                Store.dumps(list(decision.fallback_chain)),
                decision.routing_policy_version, decision.manifest_digest,
                decision.decided_at_ms,
            ),
        )

    async def decisions_for(self, mission_id: str) -> list[dict[str, Any]]:
        rows = await self.store.fetchall(
            "SELECT * FROM capability_route_decisions WHERE mission_id = ? "
            "ORDER BY decided_at_ms",
            (mission_id,),
        )
        return [dict(r) for r in rows]


__all__ = [
    "ROUTING_POLICY_VERSION",
    "CapabilityRouter",
    "RouteDecision",
    "ScoredCandidate",
    "score",
]
