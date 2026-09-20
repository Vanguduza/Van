"""AccountDecisionCoordinator: one authority per account alias (§12, TRD-ENH-034).

The problem this exists for: portfolio heat is a *whole-account* constraint
evaluated at a *single-instrument* decision point. Whichever bar closes first
consumes capacity, so a marginal EURUSD setup takes heat a materially better
GBPUSD setup then cannot have. Allocation is arrival-ordered, and nothing ever
compares the two.

The coordinator owns the account: mandate, Risk Authority, router, kill switch,
lease. Evaluators own symbols. Between them sits the pool and the allocator.

The shared-heat procedure is the load-bearing part:

    rank fresh candidates
        -> candidate #1 -> fresh portfolio snapshot -> Risk Authority
        -> execute / reject -> refresh portfolio truth -> candidate #2

Ranking happens once per pass; **admission is re-evaluated per candidate against
live state**. A candidate that ranked second may be rejected outright once the
first one's risk is in the book — that is correct, and it is the Risk
Authority's decision rather than the allocator's. The allocator never reserves
heat, never pre-approves, and never sets a size.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Iterable, Optional, Protocol, Sequence

from vati.app.account_lease import AccountRuntimeLease, LeaseOutcome, LeaseResult
from vati.app.candidate_pool import CandidatePool, CandidateState
from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.intent_factory import IntentFactory
from vati.app.instrument_evaluator import InstrumentEvaluator
from vati.core.canonical import canonical_hash
from vati.market_data.bars import Bar


class Allocator(Protocol):
    def rank(self, candidates: Sequence[CandidateOpportunity], *, now_ms: int) -> Sequence: ...


@dataclass
class CoordinatorConfig:
    account_alias: str
    #: Most passes admit one new position; the sequence still re-checks each.
    max_new_intents_per_pass: int = 1


@dataclass(frozen=True)
class AdmissionOutcome:
    candidate_id: str
    symbol: str
    rank: int
    decision: str
    reason: str = ""
    snapshot_hash: str = ""
    risk_decision: object | None = None

    def as_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "symbol": self.symbol, "rank": self.rank,
                "decision": self.decision, "reason": self.reason, "snapshot_hash": self.snapshot_hash}


@dataclass(frozen=True)
class CoordinatorPass:
    account_alias: str
    as_of_ms: int
    lease_outcome: str
    symbols_evaluated: tuple[str, ...]
    candidates_admitted: tuple[str, ...]
    expired: tuple[str, ...]
    ranking: tuple[str, ...]
    outcomes: tuple[AdmissionOutcome, ...]
    allocation_epoch_id: str = ""
    pass_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "account_alias": self.account_alias, "as_of_ms": self.as_of_ms,
            "lease_outcome": self.lease_outcome,
            "symbols_evaluated": list(self.symbols_evaluated),
            "candidates_admitted": list(self.candidates_admitted),
            "expired": list(self.expired), "ranking": list(self.ranking),
            "outcomes": [o.as_dict() for o in self.outcomes],
            "allocation_epoch_id": self.allocation_epoch_id,
        }

    def sealed(self) -> "CoordinatorPass":
        return CoordinatorPass(**{**self.__dict__, "pass_hash": canonical_hash(self.as_dict())})


class AccountDecisionCoordinator:
    """The live account entry point. Exactly one per alias."""

    def __init__(
        self,
        cfg: CoordinatorConfig,
        *,
        evaluators: Sequence[InstrumentEvaluator],
        allocator: Allocator,
        lease: Optional[AccountRuntimeLease] = None,
        intent_factory: Optional[IntentFactory] = None,
        #: Fresh account/position truth. Called again after every execution.
        snapshot_fn: Callable[[], object] = lambda: None,
        #: The deterministic sizer. Never bypassed, never pre-empted.
        risk_fn: Optional[Callable[[object, object], object]] = None,
        #: Sends an approved intent. The third argument is the strategy's
        #: explicit target tuple; the fourth is the currently held lease epoch.
        execute_fn: Optional[Callable[[object, object, tuple[Decimal, ...], Optional[int]], object]] = None,
        #: Recomputed after every fresh portfolio snapshot. Ranking may use a
        #: dependency estimate, but live admission must not reuse one after the
        #: previous candidate changed the book.
        dependency_fn: Optional[Callable[[CandidateOpportunity, object], object]] = None,
        #: Per-strategy budget lookup (TRD-ENH-060). Pass a TradingMandate as
        #: `mandate` and this resolves each candidate's own signed ceiling.
        risk_pct_fn: Optional[Callable[[CandidateOpportunity], Decimal]] = None,
        mandate=None,
    ) -> None:
        self.cfg = cfg
        self.evaluators = {e.symbol: e for e in evaluators}
        self.allocator = allocator
        self.lease = lease
        self.intent_factory = intent_factory or IntentFactory()
        self.pool = CandidatePool(account_alias=cfg.account_alias)
        self.snapshot_fn = snapshot_fn
        self.risk_fn = risk_fn
        self.execute_fn = execute_fn
        self.dependency_fn = dependency_fn
        self.mandate = mandate
        self.risk_pct_fn = risk_pct_fn or self._mandate_risk_pct
        self.snapshot_calls = 0

    def _mandate_risk_pct(self, candidate: CandidateOpportunity) -> Decimal:
        """A strategy's own owner-signed budget, or the mandate ceiling.

        `risk_budget_for` already takes the minimum against
        `max_risk_per_trade`, so a budget can only ever narrow.
        """
        capsule_ceiling = candidate.capsule_risk_ceiling
        if capsule_ceiling <= 0:
            return Decimal("0")
        if self.mandate is None:
            return capsule_ceiling
        return min(capsule_ceiling, self.mandate.risk_budget_for(candidate.strategy_id))

    # -- helpers -----------------------------------------------------------

    def _snapshot(self):
        """Portfolio truth, re-read every time. The count is asserted by test."""
        self.snapshot_calls += 1
        return self.snapshot_fn()

    def _snapshot_hash(self, snapshot) -> str:
        if snapshot is None:
            return ""
        as_dict = getattr(snapshot, "as_dict", None)
        try:
            return canonical_hash(as_dict() if callable(as_dict) else {"repr": repr(snapshot)})
        except Exception:                                  # noqa: BLE001 — hashing must not fail a pass
            return canonical_hash({"repr": repr(snapshot)})

    # -- the pass ----------------------------------------------------------

    def step(self, *, now_ms: int, bars_by_symbol: dict[str, Sequence[Bar]]) -> CoordinatorPass:
        lease_outcome = LeaseOutcome.GRANTED.value
        if self.lease is not None:
            result: LeaseResult = self.lease.renew(now_ms=now_ms)
            lease_outcome = result.outcome.value
            if not result.permits_orders:
                # Fail closed. STORE_UNREACHABLE and REFUSED_HELD_BY_OTHER both
                # stop here, and the pass records which one it was.
                return CoordinatorPass(
                    account_alias=self.cfg.account_alias, as_of_ms=now_ms,
                    lease_outcome=lease_outcome, symbols_evaluated=(),
                    candidates_admitted=(), expired=(), ranking=(), outcomes=(),
                ).sealed()

        # 1. every configured symbol evaluates, independently.
        evaluated: list[str] = []
        admitted: list[str] = []
        for symbol in sorted(self.evaluators):
            ev = self.evaluators[symbol]
            cands = ev.evaluate(bars_by_symbol.get(symbol, ()), now_ms=now_ms)
            evaluated.append(symbol)
            for c in cands:
                self.pool.admit(c, now_ms=now_ms)
                admitted.append(c.candidate_id)

        expired = self.pool.expire_stale(now_ms=now_ms)

        # 2. rank once, over the candidates that are fresh right now.
        active = self.pool.active(now_ms=now_ms)
        decisions = list(self.allocator.rank(active, now_ms=now_ms))
        ranking = tuple(d.candidate_id for d in decisions)
        epoch_id = canonical_hash({"alias": self.cfg.account_alias, "as_of": now_ms,
                                   "candidates": list(ranking)})[:24]

        by_id = {c.candidate_id: c for c in active}
        outcomes: list[AdmissionOutcome] = []
        admitted_count = 0

        # 3. admit sequentially against refreshed truth.
        for d in decisions:
            cand = by_id.get(d.candidate_id)
            if cand is None:
                continue
            if admitted_count >= self.cfg.max_new_intents_per_pass:
                self.pool.mark(cand.candidate_id, CandidateState.DEFERRED,
                               reason="pass intent budget reached", now_ms=now_ms)
                outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank, "DEFERRED",
                                                 "pass intent budget reached"))
                continue
            if getattr(d, "decision", "SELECTED") != "SELECTED":
                self.pool.mark(cand.candidate_id, CandidateState.NOT_SELECTED,
                               reason=getattr(d, "reason", "not selected"), now_ms=now_ms)
                outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank,
                                                 "NOT_SELECTED", getattr(d, "reason", "")))
                continue
            # Freshly re-read: the previous candidate may have changed the book.
            snapshot = self._snapshot()
            snap_hash = self._snapshot_hash(snapshot)
            if not cand.fresh_at(now_ms):
                self.pool.mark(cand.candidate_id, CandidateState.EXPIRED,
                               reason="expired before admission", now_ms=now_ms)
                outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank,
                                                 "EXPIRED", "expired before admission", snap_hash))
                continue

            correlation = getattr(d, "correlation_multiplier", Decimal("1"))
            if self.dependency_fn is not None:
                fresh_dependency = self.dependency_fn(cand, snapshot)
                correlation = getattr(fresh_dependency, "correlation_multiplier", correlation)

            intent = self.intent_factory.from_selected_candidate(
                cand, requested_risk_pct=self.risk_pct_fn(cand),
                idempotency_seed=f"{self.cfg.account_alias}:{cand.symbol}:{cand.generated_at_ms}",
                allocation_decision_hash=getattr(d, "decision_hash", ""),
                correlation_multiplier=correlation,
                now_ms=now_ms,
            )

            if self.risk_fn is None:
                self.pool.mark(cand.candidate_id, CandidateState.RISK_REJECTED,
                               reason="risk_authority_unbound", now_ms=now_ms)
                outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank,
                                                 "RISK_REJECTED", "risk_authority_unbound", snap_hash))
                continue

            decision = self.risk_fn(intent, snapshot)
            approved = getattr(decision, "decision", None)
            if approved in ("APPROVED", "REDUCED"):
                if self.execute_fn is None:
                    self.pool.mark(cand.candidate_id, CandidateState.RISK_REJECTED,
                                   reason="execution_path_unbound", now_ms=now_ms)
                    outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank,
                                                     "EXECUTION_REFUSED", "execution_path_unbound",
                                                     snap_hash, decision))
                    continue
                lease_epoch = self.lease.epoch if self.lease is not None else None
                self.execute_fn(intent, decision, tuple(cand.targets), lease_epoch)
                self.pool.mark(cand.candidate_id, CandidateState.SELECTED,
                               reason=str(approved), now_ms=now_ms)
                outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank,
                                                 str(approved), "", snap_hash, decision))
                admitted_count += 1
            else:
                # The Risk Authority's refusal, not the allocator's.
                self.pool.mark(cand.candidate_id, CandidateState.RISK_REJECTED,
                               reason=str(getattr(decision, "reason_code", approved)), now_ms=now_ms)
                outcomes.append(AdmissionOutcome(cand.candidate_id, cand.symbol, d.rank,
                                                 "RISK_REJECTED",
                                                 str(getattr(decision, "reason_code", approved)),
                                                 snap_hash, decision))

        return CoordinatorPass(
            account_alias=self.cfg.account_alias, as_of_ms=now_ms,
            lease_outcome=lease_outcome, symbols_evaluated=tuple(evaluated),
            candidates_admitted=tuple(admitted), expired=expired, ranking=ranking,
            outcomes=tuple(outcomes), allocation_epoch_id=epoch_id,
        ).sealed()


__all__ = ["AccountDecisionCoordinator", "AdmissionOutcome", "Allocator",
           "CoordinatorConfig", "CoordinatorPass"]
