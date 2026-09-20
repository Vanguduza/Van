"""Phase 5/6: account-scoped competition, sequential heat, lease fencing."""

from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import dataclass
from decimal import Decimal

import pytest

from vati.app.account_coordinator import AccountDecisionCoordinator, CoordinatorConfig
from vati.app.account_lease import (
    AccountRuntimeLease,
    InMemoryLeaseStore,
    LeaseOutcome,
    LeaseStoreUnavailable,
)
from vati.app.candidate_pool import CandidatePool, CandidateState
from vati.app.instrument_evaluator import InstrumentEvaluator, InstrumentEvaluatorConfig
from vati.arbiter.candidate import CandidateOpportunity
from vati.arbiter.portfolio_allocator import (
    V0_FORBIDDEN_INPUTS,
    OpportunityPortfolioAllocator,
)
from vati.risk.contracts import Direction

ALIAS = "fx_primary"


def cand(cid, symbol, *, cost="3", gen=1_000, ttl=60_000, confidence="0.5",
         regime="1", entry="1.1000", capsule_risk="0.005") -> CandidateOpportunity:
    return CandidateOpportunity(
        candidate_id=cid, account_alias=ALIAS, venue="deriv", symbol=symbol,
        strategy_id=f"S-{symbol}", strategy_version="1.0.0", capsule_hash="cap",
        strategy_state="DEMO", generated_at_ms=gen, valid_from_ms=gen, valid_until_ms=gen + ttl,
        mtf_state_hash=f"mtf-{symbol}", source_state_hashes=("s",), feature_contract_hash="fc",
        direction=Direction.LONG, entry=Decimal(entry), stop=Decimal("1.0950"),
        targets=(Decimal("1.1150"),), horizon="SWING",
        cost_multiple=Decimal(cost), capsule_risk_ceiling=Decimal(capsule_risk),
        confidence_score=Decimal(confidence),
        regime_multiplier=Decimal(regime),
    ).sealed()


# ---------------------------------------------------------------- lease

def test_second_host_is_refused_by_arbitration_on_a_reachable_store():
    """B2: this is the test that proves fencing, not connectivity."""
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a")
    b = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-b")
    assert a.acquire(now_ms=0).outcome is LeaseOutcome.GRANTED
    r = b.acquire(now_ms=1)
    assert r.outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert r.holder_instance_id == "vm-a"
    assert not r.permits_orders


def test_unreachable_store_is_a_different_outcome_from_being_fenced():
    """Both block orders; only one proves the control ran."""
    store = InMemoryLeaseStore()
    store.reachable = False
    r = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-c").acquire(now_ms=0)
    assert r.outcome is LeaseOutcome.STORE_UNREACHABLE
    assert r.outcome is not LeaseOutcome.REFUSED_HELD_BY_OTHER
    assert not r.permits_orders


def test_expired_lease_can_be_taken_over_with_a_new_epoch():
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a", ttl_ms=1_000)
    b = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-b", ttl_ms=1_000)
    assert a.acquire(now_ms=0).outcome is LeaseOutcome.GRANTED
    r = b.acquire(now_ms=2_000)
    assert r.outcome is LeaseOutcome.GRANTED
    assert r.lease.lease_epoch == 2


def test_epoch_fence_rejects_a_stale_epoch():
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a", ttl_ms=1_000)
    a.acquire(now_ms=0)
    stale = a.epoch
    AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-b", ttl_ms=1_000).acquire(now_ms=5_000)
    a._held = None
    a.acquire(now_ms=6_000)
    assert not a.fence(stale), "an old epoch must not pass the fence"
    assert a.fence(a.epoch)


def test_renewal_after_takeover_is_refused():
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a", ttl_ms=1_000)
    a.acquire(now_ms=0)
    AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-b", ttl_ms=1_000).acquire(now_ms=9_000)
    assert a.renew(now_ms=9_500).outcome is LeaseOutcome.REFUSED_HELD_BY_OTHER


def test_submission_fence_rechecks_shared_store_after_takeover():
    """The old holder's cached epoch is not sufficient once another host owns the row."""
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a", ttl_ms=1_000)
    b = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-b", ttl_ms=10_000)
    assert a.acquire(now_ms=0).permits_orders
    stale = a.epoch
    assert b.acquire(now_ms=2_000).permits_orders
    # Deliberately do not renew/clear A: this is the stale-process counterexample.
    assert not a.fence(stale, now_ms=2_001, min_validity_ms=0)


def test_submission_fence_fails_closed_when_store_is_lost():
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a", ttl_ms=10_000)
    assert a.acquire(now_ms=0).permits_orders
    store.reachable = False
    assert not a.fence(a.epoch, now_ms=1_000, min_validity_ms=0)


def test_submission_fence_requires_a_validity_margin():
    store = InMemoryLeaseStore()
    a = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a", ttl_ms=5_000)
    assert a.acquire(now_ms=0).permits_orders
    assert a.fence(a.epoch, now_ms=1_000, min_validity_ms=2_000)
    assert not a.fence(a.epoch, now_ms=3_500, min_validity_ms=2_000)


# ---------------------------------------------------------------- pool

def test_two_symbols_coexist_in_one_pool():
    p = CandidatePool(account_alias=ALIAS)
    p.admit_all([cand("a", "EURUSD"), cand("b", "GBPUSD")], now_ms=1_000)
    assert p.symbols(now_ms=1_000) == ("EURUSD", "GBPUSD")


def test_replaying_the_same_candidate_cannot_reactivate_a_terminal_row():
    p = CandidatePool(account_alias=ALIAS)
    original = cand("same", "EURUSD")
    p.admit(original, now_ms=1_000)
    p.mark("same", CandidateState.SELECTED, reason="filled", now_ms=1_001)
    replay = p.admit(original, now_ms=2_000)
    assert replay.state is CandidateState.SELECTED
    assert p.active(now_ms=2_000) == ()


def test_newer_candidate_for_the_same_setup_supersedes_the_older():
    p = CandidatePool(account_alias=ALIAS)
    p.admit(cand("a", "EURUSD", gen=1_000), now_ms=1_000)
    p.admit(cand("a2", "EURUSD", gen=2_000), now_ms=2_000)
    assert p.row("a").state is CandidateState.SUPERSEDED
    assert len(p.active(now_ms=2_000)) == 1


def test_pool_refuses_a_candidate_for_another_account():
    p = CandidatePool(account_alias="other")
    with pytest.raises(ValueError, match="offered to"):
        p.admit(cand("a", "EURUSD"), now_ms=1_000)


def test_expired_candidate_leaves_the_active_set():
    p = CandidatePool(account_alias=ALIAS)
    p.admit(cand("a", "EURUSD", ttl=10), now_ms=1_000)
    assert p.expire_stale(now_ms=2_000) == ("a",)
    assert p.active(now_ms=2_000) == ()


def test_terminal_states_distinguish_why_a_candidate_did_not_trade():
    """"We chose otherwise", "risk refused it" and "it went stale" are different facts."""
    assert {CandidateState.NOT_SELECTED, CandidateState.RISK_REJECTED,
            CandidateState.EXPIRED, CandidateState.ROUTER_REFUSED} <= set(CandidateState)


# ---------------------------------------------------------------- allocator

def test_allocator_does_not_rank_on_confidence():
    """B3: an uncalibrated score must not decide which trade happens."""
    a = OpportunityPortfolioAllocator()
    low = cand("low", "EURUSD", cost="5", confidence="0.01")
    high = cand("high", "GBPUSD", cost="2", confidence="0.99")
    ranked = a.rank([high, low], now_ms=1_000)
    assert ranked[0].candidate_id == "low", "cost multiple decided, not confidence"


def test_allocator_utility_is_invariant_to_confidence_score():
    a = OpportunityPortfolioAllocator()
    x = a.rank([cand("x", "EURUSD", confidence="0.01")], now_ms=1_000)[0]
    y = a.rank([cand("x", "EURUSD", confidence="0.99")], now_ms=1_000)[0]
    assert x.allocation_utility == y.allocation_utility


def test_allocator_reads_no_forbidden_input():
    src = textwrap.dedent(inspect.getsource(OpportunityPortfolioAllocator._utility))
    attrs = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)}
    assert not (attrs & set(V0_FORBIDDEN_INPUTS))


def test_allocator_has_no_sizing_api():
    for name in ("reserve_heat", "allocate_size", "preapprove", "approve", "execute"):
        assert not hasattr(OpportunityPortfolioAllocator, name)


def test_ranking_is_deterministic_under_ties():
    a = OpportunityPortfolioAllocator()
    one = a.rank([cand("b", "GBPUSD"), cand("a", "EURUSD")], now_ms=1_000)
    two = a.rank([cand("a", "EURUSD"), cand("b", "GBPUSD")], now_ms=1_000)
    assert [d.candidate_id for d in one] == [d.candidate_id for d in two]


def test_staleness_lowers_utility():
    a = OpportunityPortfolioAllocator()
    fresh = a.rank([cand("x", "EURUSD")], now_ms=1_000)[0]
    stale = a.rank([cand("x", "EURUSD")], now_ms=55_000)[0]
    assert stale.allocation_utility < fresh.allocation_utility


# ---------------------------------------------------------------- coordinator

@dataclass
class _Decision:
    decision: str
    reason_code: str = ""
    approved_size: Decimal = Decimal("1")


class _Book:
    """Portfolio truth that changes when a trade is executed."""

    def __init__(self, capacity: int = 1):
        self.open = 0
        self.capacity = capacity
        self.reads = 0
        self.executions = []
        self.risk_correlations = []

    def snapshot(self, candidate=None):
        self.reads += 1
        return {"open": self.open, "capacity": self.capacity}

    def risk(self, intent, snapshot):
        self.risk_correlations.append(intent.correlation_multiplier)
        if snapshot["open"] >= snapshot["capacity"]:
            return _Decision("REJECTED", "PORTFOLIO_HEAT_EXCEEDED")
        return _Decision("APPROVED")

    def execute(self, candidate, intent, decision, targets, lease_epoch):
        self.open += 1
        self.executions.append((intent, decision, targets, lease_epoch))
        return {"filled": True}


class _StubEvaluator(InstrumentEvaluator):
    def __init__(self, symbol, candidates):
        self.cfg = InstrumentEvaluatorConfig(symbol=symbol, base=symbol[:3], quote=symbol[3:],
                                             venue="deriv", account_alias=ALIAS)
        self._candidates = candidates
        self.last_candidates = ()
        self.last_state = None

    def evaluate(self, bars, *, now_ms, mtf_state_hash=""):
        self.last_candidates = self._candidates
        return self._candidates


def _coordinator(book, evaluators, *, lease=None, max_new=1):
    return AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=ALIAS, max_new_intents_per_pass=max_new),
        evaluators=evaluators, allocator=OpportunityPortfolioAllocator(), lease=lease,
        snapshot_fn=book.snapshot, risk_fn=book.risk, execute_fn=book.execute,
        risk_pct_fn=lambda c: Decimal("0.005"),
    )


def test_two_symbols_are_evaluated_and_compete_in_one_pass():
    book = _Book(capacity=5)
    c = _coordinator(book, [
        _StubEvaluator("EURUSD", (cand("eur", "EURUSD", cost="2"),)),
        _StubEvaluator("GBPUSD", (cand("gbp", "GBPUSD", cost="9"),)),
    ], max_new=2)
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1], "GBPUSD": [1]})
    assert result.symbols_evaluated == ("EURUSD", "GBPUSD")
    assert set(result.candidates_admitted) == {"eur", "gbp"}
    assert len(result.ranking) == 2


def test_merit_can_beat_arrival_order():
    """The finding this whole phase exists for."""
    book = _Book(capacity=1)
    # EURUSD arrives first (evaluated first, alphabetically) but is marginal.
    c = _coordinator(book, [
        _StubEvaluator("EURUSD", (cand("eur", "EURUSD", cost="2"),)),
        _StubEvaluator("GBPUSD", (cand("gbp", "GBPUSD", cost="9"),)),
    ])
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1], "GBPUSD": [1]})
    assert result.ranking[0] == "gbp", "the better opportunity ranked first"
    winner = [o for o in result.outcomes if o.decision == "APPROVED"]
    assert len(winner) == 1 and winner[0].candidate_id == "gbp"


def test_fresh_snapshot_is_read_for_every_admitted_candidate():
    """§I4: ranking once, admission re-evaluated against live state."""
    book = _Book(capacity=5)
    c = _coordinator(book, [
        _StubEvaluator("EURUSD", (cand("eur", "EURUSD", cost="9"),)),
        _StubEvaluator("GBPUSD", (cand("gbp", "GBPUSD", cost="8"),)),
    ], max_new=2)
    c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1], "GBPUSD": [1]})
    assert book.reads == 2, "one snapshot per candidate, not one per pass"


def test_first_execution_changes_the_second_candidates_risk_decision():
    """Two candidates cannot both be approved against one stale snapshot."""
    book = _Book(capacity=1)
    c = _coordinator(book, [
        _StubEvaluator("EURUSD", (cand("eur", "EURUSD", cost="9"),)),
        _StubEvaluator("GBPUSD", (cand("gbp", "GBPUSD", cost="8"),)),
    ], max_new=2)
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1], "GBPUSD": [1]})
    decisions = {o.candidate_id: o.decision for o in result.outcomes}
    assert decisions["eur"] == "APPROVED"
    assert decisions["gbp"] == "RISK_REJECTED"
    assert book.open == 1


def test_risk_rejection_is_recorded_as_such_not_as_allocator_choice():
    book = _Book(capacity=0)
    c = _coordinator(book, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))])
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert result.outcomes[0].decision == "RISK_REJECTED"
    assert c.pool.row("eur").state is CandidateState.RISK_REJECTED


def test_a_fenced_coordinator_admits_nothing():
    store = InMemoryLeaseStore()
    AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a").acquire(now_ms=0)
    loser = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-b")
    book = _Book(capacity=5)
    c = _coordinator(book, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))], lease=loser)
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert result.lease_outcome == LeaseOutcome.REFUSED_HELD_BY_OTHER.value
    assert result.outcomes == () and book.open == 0


def test_unreachable_store_also_admits_nothing_but_says_why():
    store = InMemoryLeaseStore()
    lease = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a")
    lease.acquire(now_ms=0)
    store.reachable = False
    book = _Book(capacity=5)
    c = _coordinator(book, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))], lease=lease)
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert result.lease_outcome == LeaseOutcome.STORE_UNREACHABLE.value
    assert book.open == 0


def test_expired_candidate_cannot_be_admitted():
    book = _Book(capacity=5)
    c = _coordinator(book, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD", gen=0, ttl=10),))])
    result = c.step(now_ms=100_000, bars_by_symbol={"EURUSD": [1]})
    assert "eur" in result.expired and book.open == 0


def test_coordinator_pass_is_hashed_and_replayable():
    book = _Book(capacity=5)
    evs = [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))]
    a = _coordinator(book, evs).step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    book2 = _Book(capacity=5)
    b = _coordinator(book2, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))]).step(
        now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert a.pass_hash == b.pass_hash and a.pass_hash


def test_instrument_evaluator_cannot_execute():
    for name in ("execute", "send", "route", "size", "approve"):
        assert not hasattr(InstrumentEvaluator, name)


def test_capsule_risk_ceiling_survives_the_coordinator_path():
    class _Mandate:
        def risk_budget_for(self, strategy_id):
            return Decimal("0.01")

    book = _Book(capacity=1)
    c = AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=ALIAS),
        evaluators=[_StubEvaluator("EURUSD", (cand("eur", "EURUSD", capsule_risk="0.005"),))],
        allocator=OpportunityPortfolioAllocator(),
        snapshot_fn=book.snapshot, risk_fn=book.risk, execute_fn=book.execute,
        mandate=_Mandate(),
    )
    c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert book.executions[0][0].requested_risk_pct == Decimal("0.005")


def test_strategy_targets_reach_the_execution_join_unchanged():
    book = _Book(capacity=1)
    target = Decimal("1.1150")
    c = _coordinator(book, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))])
    c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert book.executions[0][2] == (target,)


def test_dependency_is_recomputed_after_the_first_execution_changes_the_book():
    class _Dep:
        def __init__(self, value):
            self.correlation_multiplier = Decimal(value)

    book = _Book(capacity=5)
    c = AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=ALIAS, max_new_intents_per_pass=2),
        evaluators=[
            _StubEvaluator("EURUSD", (cand("eur", "EURUSD", cost="9"),)),
            _StubEvaluator("GBPUSD", (cand("gbp", "GBPUSD", cost="8"),)),
        ],
        allocator=OpportunityPortfolioAllocator(),
        snapshot_fn=book.snapshot, risk_fn=book.risk, execute_fn=book.execute,
        risk_pct_fn=lambda candidate: Decimal("0.005"),
        dependency_fn=lambda candidate, snapshot: _Dep("1" if snapshot["open"] == 0 else "0.25"),
    )
    c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1], "GBPUSD": [1]})
    assert book.risk_correlations == [Decimal("1"), Decimal("0.25")]


def test_missing_risk_authority_is_a_refusal_not_a_selection():
    book = _Book(capacity=1)
    c = AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=ALIAS),
        evaluators=[_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))],
        allocator=OpportunityPortfolioAllocator(),
        snapshot_fn=book.snapshot, risk_fn=None, execute_fn=book.execute,
        risk_pct_fn=lambda candidate: Decimal("0.005"),
    )
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert result.outcomes[0].decision == "RISK_REJECTED"
    assert result.outcomes[0].reason == "risk_authority_unbound"
    assert book.open == 0


def test_missing_execution_path_is_a_refusal_not_a_success():
    book = _Book(capacity=1)
    c = AccountDecisionCoordinator(
        CoordinatorConfig(account_alias=ALIAS),
        evaluators=[_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))],
        allocator=OpportunityPortfolioAllocator(),
        snapshot_fn=book.snapshot, risk_fn=book.risk, execute_fn=None,
        risk_pct_fn=lambda candidate: Decimal("0.005"),
    )
    result = c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert result.outcomes[0].decision == "EXECUTION_REFUSED"
    assert result.outcomes[0].reason == "execution_path_unbound"
    assert book.open == 0


def test_lease_epoch_is_passed_to_the_execution_join():
    store = InMemoryLeaseStore()
    lease = AccountRuntimeLease(store, account_alias=ALIAS, instance_id="vm-a")
    assert lease.acquire(now_ms=0).permits_orders
    book = _Book(capacity=1)
    c = _coordinator(book, [_StubEvaluator("EURUSD", (cand("eur", "EURUSD"),))], lease=lease)
    c.step(now_ms=1_000, bars_by_symbol={"EURUSD": [1]})
    assert book.executions[0][3] == lease.epoch
