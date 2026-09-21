"""Persistent Rev 5.1 shadow cognition runtime.

This is the production join for packets 091-103 and 132.  It wakes after the
existing deterministic RiskAuthority decision, so first-pass cognition cannot
create, enlarge or reroute a trade.  With no provider invoker configured it
records a sealed MODEL_UNAVAILABLE abstention instead of pretending cognition
ran successfully.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from vati.cognition.budget import CognitiveBudget
from vati.cognition.context import (
    ContextContaminated, ContextIncomplete, compile_decision_context,
)
from vati.cognition.contracts import (
    AssessmentRejected, CognitiveAssessment, ModelRole, Verdict, abstention, normalise,
)
from vati.cognition.handoff import (
    ContinuityState, HandoffReason, HandoffRecorder,
)
from vati.cognition.performance_ledger import CognitivePerformanceLedger
from vati.cognition.providers import (
    ProviderLease, QuotaScheduler, default_registry,
)
from vati.cognition.shadow_book import (
    DeterministicOutcome, EntryStatus, ShadowBook, ShadowEntry,
)
from vati.cognition.translator import ActionTranslator, Mode
from vati.cognition.world_model import TradingWorldModel
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.research.director import FableResearchDirector, ResearchTrigger
from vati.research.missions import MissionLedger
from vati.risk.serde import snapshot_to_dict

InvokeFn = Callable[[ProviderLease, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class CognitionWakeResult:
    assessment: CognitiveAssessment
    shadow_entry: ShadowEntry
    context_hash: str
    provider_attempts: int
    model_available: bool


class ShadowCognitionRuntime:
    """Long-lived shadow-only cognition coordinator.

    The deterministic decision is final before this method runs.  The
    ActionTranslator is permanently constructed in SHADOW mode, and its output
    is not returned to the trading caller.
    """

    def __init__(self, *, ledger, invoker: Optional[InvokeFn] = None,
                 budget: Optional[CognitiveBudget] = None) -> None:
        self.ledger = ledger
        self.invoker = invoker
        self.scheduler = QuotaScheduler(default_registry())
        self.budget = budget or CognitiveBudget(
            micros_per_window=5_000_000,
            invocations_per_window=240,
            ledger=ledger,
        )
        self.world = TradingWorldModel()
        self.shadow = ShadowBook(ledger=ledger)
        self.performance = CognitivePerformanceLedger(ledger=ledger)
        self.translator = ActionTranslator(mode=Mode.SHADOW, ledger=ledger)
        self.handoffs = HandoffRecorder(ledger=ledger)
        self.missions = MissionLedger(ledger=ledger)
        self.director = FableResearchDirector(self.missions)
        self._seen_event_hashes: set[str] = set()

    def _sync_world(self) -> None:
        for event in self.ledger.iter():
            if event.hash in self._seen_event_hashes:
                continue
            self.world.apply(event)
            self._seen_event_hashes.add(event.hash)

    def _compile_context(self, *, intent, decision, snapshot, now_ms: int):
        self._sync_world()
        decision_point = {
            "trade_intent_id": intent.trade_intent_id,
            "symbol": intent.symbol,
            "strategy_id": intent.strategy_id,
            "market_snapshot_hash": intent.market_snapshot_hash,
            "deterministic_decision": decision.decision.value,
            "reason_code": decision.reason_code,
            "risk_decision_hash": decision.decision_hash,
        }
        risk_state = snapshot_to_dict(snapshot)
        context = compile_decision_context(
            decision_point=decision_point,
            risk_state=risk_state,
            world=self.world,
            now_ms=now_ms,
        )
        self.ledger.append(make_event(
            EventKind.COGNITIVE_CONTEXT,
            "vati-shadow-cognition-runtime",
            context.body() | {"context_hash": context.context_hash},
            event_time_ms=now_ms,
            received_time_ms=now_ms,
            correlation_id=intent.trade_intent_id,
        ))
        return context

    def _invoke(self, *, context, now_ms: int) -> tuple[CognitiveAssessment, int, bool]:
        budget_decision = self.budget.check(
            now_ms=now_ms, context_hash=context.context_hash,
            is_high_impact=True,
        )
        if not budget_decision.allowed:
            return (
                abstention(
                    context_hash=context.context_hash,
                    model_id="budget",
                    role=ModelRole.PRIMARY,
                    reason="BUDGET_EXHAUSTED",
                    now_ms=now_ms,
                    narrative=budget_decision.reason,
                ),
                0,
                False,
            )
        if self.invoker is None:
            return (
                abstention(
                    context_hash=context.context_hash,
                    model_id="unavailable",
                    role=ModelRole.PRIMARY,
                    reason="MODEL_UNAVAILABLE",
                    now_ms=now_ms,
                    narrative="no model invoker is configured on this runtime",
                ),
                0,
                False,
            )

        excluded: list[str] = []
        previous: Optional[ProviderLease] = None
        continuity = ContinuityState(context_hash=context.context_hash)
        pending_reason = HandoffReason.TRANSPORT_ERROR
        attempts = 0
        while True:
            lease = self.scheduler.acquire(
                now_ms=now_ms, exclude_model_ids=tuple(excluded))
            if lease is None:
                role = previous.role if previous is not None else ModelRole.PRIMARY
                model_id = previous.model_id if previous is not None else "unavailable"
                return (
                    abstention(
                        context_hash=context.context_hash,
                        model_id=model_id,
                        role=role,
                        reason="MODEL_UNAVAILABLE",
                        now_ms=now_ms,
                        narrative="all Rev 5.1 providers were unavailable or refused",
                    ),
                    attempts,
                    False,
                )
            attempts += 1
            if previous is not None:
                self.handoffs.record(
                    previous=previous,
                    nxt=lease,
                    reason=pending_reason,
                    continuity=continuity,
                    now_ms=now_ms,
                )
            try:
                raw = self.invoker(
                    lease,
                    context.body() | {"context_hash": context.context_hash},
                )
                assessment = normalise(
                    raw,
                    model_id=lease.model_id,
                    role=lease.role,
                    context_hash=context.context_hash,
                    now_ms=now_ms,
                )
                provider = self.scheduler.registry.by_model_id(lease.model_id)
                spent = 0 if provider is None else provider.cost_per_request_micros
                self.budget.spend(
                    micros=spent, now_ms=now_ms, context_hash=context.context_hash)
                self.scheduler.release(lease, ok=True, now_ms=now_ms)
                return assessment, attempts, True
            except AssessmentRejected:
                self.performance.record_refusal(lease.model_id)
                self.scheduler.release(lease, ok=False, now_ms=now_ms)
                excluded.append(lease.model_id)
                previous = lease
                pending_reason = HandoffReason.RESULT_REFUSED
            except Exception:
                self.scheduler.release(lease, ok=False, now_ms=now_ms)
                excluded.append(lease.model_id)
                previous = lease
                pending_reason = HandoffReason.TRANSPORT_ERROR

    def wake(self, *, intent, decision, snapshot, now_ms: int) -> CognitionWakeResult:
        """Measure cognition against one already-completed deterministic decision."""
        try:
            context = self._compile_context(
                intent=intent, decision=decision, snapshot=snapshot, now_ms=now_ms)
            assessment, attempts, available = self._invoke(
                context=context, now_ms=now_ms)
            context_hash = context.context_hash
        except (ContextIncomplete, ContextContaminated) as exc:
            context_hash = canonical_hash({
                "trade_intent_id": intent.trade_intent_id,
                "risk_decision_hash": decision.decision_hash,
                "context_error": type(exc).__name__,
            })
            assessment = abstention(
                context_hash=context_hash,
                model_id="context",
                role=ModelRole.PRIMARY,
                reason="CONTEXT_INCOMPLETE",
                now_ms=now_ms,
                narrative=str(exc)[:500],
            )
            attempts = 0
            available = False

        # SHADOW translator records the typed assessment but returns the original
        # intent unchanged. The production caller does not consume that return value.
        self.translator.translate(assessment, intent, now_ms=now_ms)
        actual = DeterministicOutcome(
            decision=decision.decision.value,
            reason_code=decision.reason_code,
            approved_size=decision.approved_size,
            approved_risk_pct=decision.approved_risk_pct,
            risk_decision_hash=decision.decision_hash,
        )
        entry = self.shadow.record(
            decision_point_id=intent.trade_intent_id,
            context_hash=context_hash,
            symbol=intent.symbol,
            strategy_id=intent.strategy_id,
            account_alias=intent.account_alias,
            actual=actual,
            assessment=assessment,
            now_ms=now_ms,
            horizon_ms=max(assessment.horizon_ms, 86_400_000),
        )

        if assessment.verdict is Verdict.PROPOSE_RESEARCH:
            self.director.open(
                ResearchTrigger(
                    trigger_id=f"cognition:{assessment.assessment_id}",
                    question=assessment.narrative or (
                        f"Investigate {intent.strategy_id} decision "
                        f"{intent.trade_intent_id}"),
                    evidence_ids=(assessment.seal, context_hash),
                    data_domains=("external_web", "repository"),
                    specialist_roles=("evidence", "contradiction"),
                ),
                now_ms=now_ms,
            )

        return CognitionWakeResult(
            assessment=assessment,
            shadow_entry=entry,
            context_hash=context_hash,
            provider_attempts=attempts,
            model_available=available,
        )

    def resolve_trade(self, trade_intent_id: str, *, actual_r, now_ms: int) -> Optional[ShadowEntry]:
        entry = self.shadow.for_decision_point(trade_intent_id)
        if entry is None or entry.status is not EntryStatus.OPEN:
            return entry
        resolved = self.shadow.resolve(
            entry.entry_id, actual_r=actual_r, now_ms=now_ms)
        self.performance.compile_all(self.shadow.entries(), now_ms=now_ms)
        return resolved

    def shadow_entry_for(self, trade_intent_id: str) -> Optional[ShadowEntry]:
        return self.shadow.for_decision_point(trade_intent_id)
