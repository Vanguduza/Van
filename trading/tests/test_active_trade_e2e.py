"""GAP-F-003 end to end: one trade, from sealed claim to lesson learned.

Every other file in this change tests one component against its own contract.
This one exists because the defect GAP-F-003 recorded was never in a component
— each piece was present and reachable *from a test* — it was in the joins. So
this walks a single position along the real path, on the real adapter, through
the real authority, and then reads the result back out of the gateway's read
models from the same ledger:

    open on PaperAdapter through ExecutionRouter
      -> thesis sealed as a ledger event
      -> an adverse, relevant T1 headline is ingested
      -> the PROTECT stage assesses the claim as RISKIER
      -> the candidate event-risk multiplier falls below 1
      -> a REDUCE proposal goes through RiskAuthority.evaluate
      -> the position closes
      -> decision quadrant + lesson are written
      -> capsule health is driven by decision quality, downwards only
      -> gateway positions()/events()/history()/assessment() surface all of it

If any join is missing, this test fails — which is the only kind of evidence
that is worth anything about a join.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from conftest import mandate_dict, snapshot
from test_intelligence import mk_bars, trending
from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.arbiter import OpportunityEngine
from vati.cognition.attribution import Quadrant
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.events.news_ingress import (
    Concern, Headline, NewsIngress, NewsSource, SourceTrust,
)
from vati.execution.paper import PaperAdapter
from vati.execution.protection import ProtectionManager
from vati.execution.router import ExecutionRouter
from vati.intelligence import DEFAULT_EVENT_MATRIX, RegimeEngine, build_market_state
from vati.learning.episodes import Environment
from vati.learning.hooks import LearningHooks
from vati.lifecycle.scale_policy import (
    Adjustment, DEFENSIVE, PositionAdjustmentProposal,
)
from vati.lifecycle.thesis import ThesisState
from vati.market_data import FX_CALENDAR
from vati.readmodels import active
from vati.risk import (
    Decision, KillSwitch, MarketIntegrityState, OpenPosition, RiskAuthority,
    TradingMandate,
)
from vati.risk.contracts import (
    Direction, StrategyState, SymbolContract, TradeIntent,
)
from vati.strategies import CapsuleRegistry

REG = Path(__file__).resolve().parents[1] / "strategies" / "registry"
STRATEGY = "FX-TREND-PULLBACK-01"
SYMBOL = "EURUSD"
ENTRY = Decimal("1.10000")
STOP = Decimal("1.09500")


def _contract() -> SymbolContract:
    return SymbolContract(
        symbol=SYMBOL, venue="paper", base_currency="EUR", quote_currency="USD",
        account_currency="USD", contract_size=Decimal("100000"),
        tick_size=Decimal("0.00001"), tick_value=Decimal("1.00"),
        volume_min=Decimal("0.01"), volume_step=Decimal("0.01"),
        volume_max=Decimal("100"), min_stop_distance=Decimal("0.00030"),
    )


def _market_state(now_ms: int):
    """A real MarketState from real bars — the thesis reads regime and features."""
    bars = mk_bars(trending(240))
    return build_market_state(
        symbol=SYMBOL, base="EUR", quote="USD", bars=bars,
        regime_engine=RegimeEngine(), calendar=FX_CALENDAR,
        events=DEFAULT_EVENT_MATRIX, integrity=MarketIntegrityState.NORMAL,
        now_ms=now_ms, last_quote_ms=now_ms - 100, activation_id="vtil-act-test",
        timeframe="H1")


class World:
    """The live join under test: one account, one symbol, one position."""

    def __init__(self, tmp_path: Path) -> None:
        self.ledger = Ledger(tmp_path / "vati.sqlite")
        self.adapter = PaperAdapter(
            venue="paper", account_alias="fx_primary", equity=Decimal("10000"))
        self.kill = KillSwitch()
        self.protection = ProtectionManager()
        self.router = ExecutionRouter(
            ledger=self.ledger, adapters={"paper": self.adapter},
            kill_switch=self.kill, protection=self.protection)
        # Two positions per instrument, because a delta intent for a reduction
        # is a second intent on the same symbol: with a ceiling of one, every
        # remainder question is rejected and every REDUCE escalates to a close.
        # That escalation is the deliberate fail-safe (see `_execute_adjustment`)
        # and it is exercised below; this mandate lets the partial path run too.
        self.mandate = TradingMandate.from_mapping(mandate_dict(
            venue="paper", allowed_strategies=[STRATEGY],
            max_positions_per_instrument=2))
        self.authority = RiskAuthority(self.mandate)
        self.contract = _contract()
        self.registry = CapsuleRegistry.load_dir(REG)
        self.engine = OpportunityEngine(self.registry, {}, self.mandate)
        self.learning = LearningHooks(environment=Environment.LIMITED_LIVE, broker="paper")
        self.news = NewsIngress(
            ledger=self.ledger,
            sources=[NewsSource(source_id="reuters", trust=SourceTrust.T1_PRIMARY,
                                label="Reuters")],
            relevance_window_ms=6 * 3_600_000)
        self.lifecycle = AccountTradeLifecycle(
            ledger=self.ledger,
            adapter=self.adapter,
            router=self.router,
            protection=self.protection,
            contracts={SYMBOL: self.contract},
            engines_by_symbol={SYMBOL: self.engine},
            modelled_costs={SYMBOL: Decimal("0.0002")},
            learning=self.learning,
            authority=self.authority,
            mandate=self.mandate,
            news=self.news,
            market_state_fn=lambda symbol: self.state,
            snapshot_fn=self._snapshot_for,
        )
        # Per-capsule policy. An unregistered capsule stays HOLD_OR_EXIT, which
        # is why this has to be said out loud for the capsule under test.
        self.lifecycle.adjustment_policies.register(STRATEGY, DEFENSIVE)
        self.state = None

    # The authority must see the book as it actually is, including the position
    # already open — otherwise a "can the book carry the remainder" question is
    # being asked about a book that does not exist.
    def _snapshot_for(self, symbol: str):
        open_positions = tuple(
            OpenPosition(
                p.symbol, p.direction, p.quantity,
                abs(p.entry_price - (p.stop_price or STOP)),
                self.contract.value_per_price_unit_per_lot, "EUR", "USD",
                STRATEGY, p.stop_price is not None)
            for p in self.adapter.positions())
        return snapshot(self.contract, open_positions=open_positions,
                        equity=self.adapter.sync_account().equity,
                        balance=self.adapter.sync_account().balance)


def _intent(now_ms: int) -> TradeIntent:
    return TradeIntent(
        trade_intent_id="ti-e2e-1", idempotency_key="idem-e2e-1",
        account_alias="fx_primary", venue="paper", symbol=SYMBOL,
        direction=Direction.LONG, strategy_id=STRATEGY, strategy_version="1.0.0",
        strategy_state=StrategyState.CERTIFIED_LIVE,
        entry=ENTRY, stop=STOP, requested_risk_pct=Decimal("0.0040"),
        decision_hash="dh-e2e", market_snapshot_hash="msh-e2e",
        expected_gross_move_pct=Decimal("0.01"))


@pytest.fixture
def world(tmp_path) -> World:
    return World(tmp_path)


def test_one_trade_from_sealed_claim_to_lesson_learned(world: World):
    now = 1_800_000_000_000
    world.state = _market_state(now)

    # --- 1. open, through the authority and the router --------------------
    intent = _intent(now)
    snap = world._snapshot_for(SYMBOL)
    decision = world.authority.evaluate(intent, snap)
    assert decision.decision in (Decision.APPROVED, Decision.REDUCED)

    receipt = world.router.execute(
        intent, decision, world.mandate, now_ms=now, targets=(Decimal("1.11000"),))
    assert receipt.status == "FILLED" and receipt.filled_qty > Decimal("0")

    world.lifecycle.record_entry(
        intent=intent, receipt=receipt, state=world.state,
        modelled_cost_pct=Decimal("0.0002"), software_stop=False,
        decision=decision, targets=(Decimal("1.11000"),),
        expected_horizon_ms=4 * 3_600_000)

    # --- 2. the claim is sealed as a ledger event -------------------------
    sealed = list(world.ledger.iter(EventKind.TRADE_THESIS))
    assert len(sealed) == 1
    thesis_payload = sealed[0].payload
    assert thesis_payload["trade_intent_id"] == intent.trade_intent_id
    assert thesis_payload["statement"] and thesis_payload["invalidation"]
    assert Decimal(thesis_payload["original_approved_risk_pct"]) == \
        decision.approved_risk_pct

    # --- 3. an adverse, relevant T1 headline arrives ----------------------
    headline_ms = now + 60_000
    world.news.ingest(Headline(
        source_id="reuters", trust=SourceTrust.T1_PRIMARY,
        published_ms=headline_ms, observed_ms=headline_ms,
        title="ECB signals emergency review of euro liquidity operations",
        currencies=("EUR", "USD"), symbols=(SYMBOL,),
        severity=Decimal("0.9"), concern=Concern.ADVERSE_TO_LONG,
        url="https://example.invalid/ecb"), now_ms=headline_ms)
    assert world.ledger.count(EventKind.NEWS_HEADLINE) == 1

    # The candidate-facing half of the same news: a multiplier that can only
    # shrink the next trade, never enlarge it.
    multiplier, materiality, refs = world.news.candidate_risk(
        SYMBOL, now_ms=headline_ms + 1_000)
    assert Decimal("0") < multiplier < Decimal("1")
    assert materiality >= Decimal("0.5") and refs
    world.engine.m.news_event_risk[SYMBOL] = multiplier

    # --- 4. the PROTECT stage reads the claim as RISKIER ------------------
    mark_ms = headline_ms + 120_000
    world.state = _market_state(mark_ms)
    world.lifecycle.mark(SYMBOL, Decimal("1.10005"), Decimal("1.10015"),
                         now_ms=mark_ms)

    assessments = list(world.ledger.iter(EventKind.THESIS_ASSESSMENT))
    assert assessments, "the PROTECT stage never assessed the sealed thesis"
    latest = assessments[-1].payload
    assert latest["state"] in (ThesisState.RISKIER.value, ThesisState.WEAKER.value)
    assert Decimal(latest["event_materiality"]) >= Decimal("0.5")
    assert "EVENT_IMPACT" in latest["reasons"]
    assert latest["argues_for_less"] is True

    impacts = list(world.ledger.iter(EventKind.EVENT_IMPACT))
    assert any(e.payload.get("subject_id") == intent.trade_intent_id
               for e in impacts), "the impact was never linked to the position"

    # --- 5. the reduction went through RiskAuthority.evaluate -------------
    proposals = list(world.ledger.iter(EventKind.POSITION_ADJUSTMENT))
    assert proposals
    reduce_proposals = [p for p in proposals
                        if p.payload["action"] in ("REDUCE", "PARTIAL_TAKE")]
    assert reduce_proposals, [p.payload["action"] for p in proposals]
    assert reduce_proposals[-1].payload["requires_authority"] is True

    delta_decisions = [
        e for e in world.ledger.iter(EventKind.RISK_DECISION)
        if e.payload.get("parent_trade_intent_id") == intent.trade_intent_id]
    assert delta_decisions, "the size change never reached the authority"
    delta = delta_decisions[-1]
    assert delta.payload["adjustment"]["action"] in ("REDUCE", "PARTIAL_TAKE")
    assert delta.payload["decision"]["decision_hash"]

    # The reduction actually reduced: the venue holds less than it did.
    remaining = {p.trade_intent_id: p.quantity for p in world.adapter.positions()}
    assert remaining.get(intent.trade_intent_id, Decimal("0")) < receipt.filled_qty

    # --- 6. close, and the two axes that outlive the trade ----------------
    # Price runs back through the protective stop. Nothing in the test closes
    # the position: the lifecycle does, on the same path a live stop takes.
    close_ms = mark_ms + 60_000
    world.state = _market_state(close_ms)
    world.lifecycle.mark(SYMBOL, Decimal("1.09400"), Decimal("1.09410"),
                         now_ms=close_ms)
    assert intent.trade_intent_id not in world.lifecycle.entries
    assert not world.adapter.positions()

    reviews = list(world.ledger.iter(EventKind.TRADE_REVIEW))
    assert reviews

    quadrants = list(world.ledger.iter(EventKind.DECISION_QUADRANT))
    assert quadrants, "no decision-quality verdict was written"
    verdict = quadrants[-1].payload
    assert verdict["quadrant"] in {q.value for q in Quadrant}
    assert verdict["decision_quality"] and verdict["outcome_quality"]
    assert verdict["trade_intent_id"] == intent.trade_intent_id

    lessons = list(world.ledger.iter(EventKind.TRADE_LESSON))
    assert lessons, "the closed trade taught nothing"
    assert lessons[-1].payload["strategy_id"] == STRATEGY
    assert lessons[-1].payload["quadrant"] == verdict["quadrant"]

    # --- 7. the decision axis is bounded and reduce-only ------------------
    quality = world.lifecycle.decision_quality.health_multiplier(STRATEGY)
    assert quality <= Decimal("1")
    assert world.lifecycle.decision_quality.get(intent.trade_intent_id) is not None
    # One trade is below the learning boundary's evidence minimum, so no live
    # capsule-health adjustment exists yet and nothing was written. That the
    # axis *drives* capsule health once there is evidence is proven in
    # `test_capsule_health_is_driven_by_the_decision_axis_downwards_only`.
    assert STRATEGY not in world.engine.m.capsule_health

    # --- 8. the gateway read models see all of it, from this ledger -------
    positions_view = active.positions(world.ledger)
    assert positions_view["ledger_available"] is True
    assert positions_view["count"] == 0   # the position is closed

    events_view = active.events(world.ledger, limit=50)
    assert events_view["ledger_available"] is True
    assert any(h["headline_id"] for h in events_view["events"])
    assert events_view["impacts"]

    history_view = active.history(world.ledger, limit=50)
    assert history_view["count"] >= 1
    row = history_view["history"][0]
    assert row["trade_intent_id"] == intent.trade_intent_id
    assert row["quadrant"]["quadrant"] == verdict["quadrant"]
    assert row["lessons"], "the lesson is not joined to the closed trade"
    assert row["lessons"][0]["quadrant"] == verdict["quadrant"]
    assert history_view["by_quadrant"].get(verdict["quadrant"]) == 1
    # The history route owns the owner-facing closed-trade curve; Android renders this
    # authoritative series rather than inventing one from list rows.
    assert "equity_curve_r" in history_view
    assert "equity_curve_pnl" in history_view
    if row["r_multiple"] is not None:
        assert history_view["equity_curve_r"][-1]["value"] == pytest.approx(float(row["r_multiple"]))
    if row["pnl"] is not None:
        assert history_view["equity_curve_pnl"][-1]["value"] == pytest.approx(float(row["pnl"]))

    assessment_view = active.assessment(world.ledger)
    assert assessment_view["ledger_available"] is True
    assert assessment_view["cognition"]["state"] == "MODEL_INVOKER_UNCONFIGURED"


def test_the_same_path_refuses_to_add_when_the_authority_says_no(world: World):
    """The mirror image: an ADD is only ever as real as the authority's answer.

    The proposal here is well formed — it asks for half the risk originally
    approved for this position, with protection already at break-even, so it
    satisfies every rule the proposal layer enforces. It is still refused,
    because the *book* cannot carry it: `RiskAuthority.evaluate` measures the
    delta intent against portfolio heat and the mandate, and on a rejection
    `_execute_adjustment` submits nothing. The proposal layer bounds the
    request; the authority is what refuses it (INV-AUTH-001).
    """
    now = 1_800_000_000_000
    world.state = _market_state(now)
    intent = _intent(now)
    decision = world.authority.evaluate(intent, world._snapshot_for(SYMBOL))
    receipt = world.router.execute(intent, decision, world.mandate, now_ms=now)
    world.lifecycle.record_entry(
        intent=intent, receipt=receipt, state=world.state,
        modelled_cost_pct=Decimal("0.0002"), software_stop=False,
        decision=decision, expected_horizon_ms=4 * 3_600_000)

    row = world.lifecycle.entries[intent.trade_intent_id]
    thesis = world.lifecycle.thesis.thesis_for(intent.trade_intent_id)
    assert thesis is not None

    half = (decision.approved_risk_pct / Decimal("2")).quantize(Decimal("0.00001"))
    add = PositionAdjustmentProposal(
        trade_intent_id=intent.trade_intent_id, symbol=SYMBOL,
        strategy_id=STRATEGY, action=Adjustment.ADD,
        reasons=("THESIS_STRONGER",),
        rationale="the claim strengthened and protection is at break-even",
        thesis_state=ThesisState.STRONGER.value, thesis_seal=thesis.seal,
        delta_risk_pct=half,
        original_approved_risk_pct=decision.approved_risk_pct,
        risk_after_action_pct=half,
        proposed_ms=now + 60_000)
    assert add.risk_after_action_pct <= add.original_approved_risk_pct

    # The book the authority is asked about already carries the account's whole
    # open stop-risk allowance.
    heavy_book = (
        OpenPosition(SYMBOL, Direction.LONG, Decimal("3.0"), Decimal("0.00500"),
                     world.contract.value_per_price_unit_per_lot, "EUR", "USD",
                     STRATEGY, True),
    )
    world.lifecycle.snapshot_fn = lambda symbol: snapshot(
        world.contract, open_positions=heavy_book)

    before = len(world.adapter.positions())
    delta_decision = world.lifecycle._authorise_delta(
        proposal=add, row=row, intent_id=intent.trade_intent_id,
        thesis=thesis, mark=Decimal("1.10600"), now_ms=now + 60_000)
    assert delta_decision is not None
    assert delta_decision.decision is Decision.REJECTED
    assert delta_decision.approved_size == Decimal("0")

    executed = []
    world.lifecycle.execute_add_fn = lambda i, d: executed.append((i, d))
    world.lifecycle._execute_adjustment(
        proposal=add, row=row, intent_id=intent.trade_intent_id,
        thesis=thesis, family=None, mark=Decimal("1.10600"), now_ms=now + 60_000)
    assert executed == []
    assert len(world.adapter.positions()) == before


def test_capsule_health_is_driven_by_the_decision_axis_downwards_only(world: World):
    """The join item 5 exists for: process quality, not luck, moves capsule health.

    `_learn` used to pass `review.process_ok` — a constant — so only R moved the
    number. It now passes the decision-quality verdict and combines the axis
    multiplier with `min`, which is what makes the result reduce-only: whatever
    the axis says, it can only take health down.

    The learning boundary needs 30 environment-weighted samples before any live
    capsule-health adjustment exists at all, so this runs that many real round
    trips on the paper venue rather than asserting the join from one trade.
    """
    now = 1_800_000_000_000
    world.state = _market_state(now)
    # A fixed account view: this test is about the learning join, not about the
    # drawdown governor, and a shrinking equity would eventually (correctly)
    # have the authority refuse to open anything at all.
    world.lifecycle.snapshot_fn = lambda symbol: snapshot(world.contract)

    trades = 32
    for i in range(trades):
        opened = now + i * 3_600_000
        intent = TradeIntent(
            trade_intent_id=f"ti-loop-{i}", idempotency_key=f"idem-loop-{i}",
            account_alias="fx_primary", venue="paper", symbol=SYMBOL,
            direction=Direction.LONG, strategy_id=STRATEGY,
            strategy_version="1.0.0", strategy_state=StrategyState.CERTIFIED_LIVE,
            entry=ENTRY, stop=STOP, requested_risk_pct=Decimal("0.0040"),
            decision_hash=f"dh-loop-{i}", market_snapshot_hash="msh-loop",
            expected_gross_move_pct=Decimal("0.01"))
        decision = world.authority.evaluate(intent, snapshot(world.contract))
        assert decision.decision in (Decision.APPROVED, Decision.REDUCED)
        receipt = world.router.execute(
            intent, decision, world.mandate, now_ms=opened)
        assert receipt.status == "FILLED"
        world.lifecycle.record_entry(
            intent=intent, receipt=receipt, state=world.state,
            modelled_cost_pct=Decimal("0.0002"), software_stop=False,
            decision=decision, expected_horizon_ms=4 * 3_600_000)
        # Through the protective stop: the venue closes it, the lifecycle sees
        # the close, and the review/quadrant/lesson chain runs for real.
        world.lifecycle.mark(SYMBOL, Decimal("1.09400"), Decimal("1.09410"),
                             now_ms=opened + 1_800_000)
        assert intent.trade_intent_id not in world.lifecycle.entries

    assert len(list(world.ledger.iter(EventKind.DECISION_QUADRANT))) == trades
    assert len(list(world.ledger.iter(EventKind.TRADE_LESSON))) == trades

    adjustment = world.learning.health.live_adjustment(STRATEGY)
    assert adjustment is not None, "the learning boundary never produced an adjustment"
    quality = world.lifecycle.decision_quality.health_multiplier(STRATEGY)

    health = world.engine.m.capsule_health.get(STRATEGY)
    assert health is not None, "capsule health was never updated from the closes"
    assert health == min(adjustment.multiplier, quality)
    assert health <= Decimal("1")
    assert health <= quality   # the decision axis can only take it down

    # And the owner surface reports the same quadrants from the same ledger.
    history_view = active.history(world.ledger, limit=200)
    assert history_view["count"] == trades
    assert sum(history_view["by_quadrant"].values()) == trades
