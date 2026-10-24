"""P1-TRADE-EXEC-002/003 — execution bounds must work at every instrument's price scale.

Found by the 17 October 2026 backtest research (docs/design/van-next/research/
strategy_backtest_20261017): with 0.2 pip of slippage, 11,379 approved USDJPY orders
produced zero fills, because the template slippage cap was an absolute 0.0001 price
units; and approved stops were refused as STOP_WIDER_THAN_APPROVED after tick rounding.
"""
from __future__ import annotations

from decimal import Decimal

from conftest import historical_mandate_dict, mandate_dict
from test_intelligence import mk_bars, noisy_trend
from vati.app import SessionConfig
from vati.arbiter import OpportunityEngine
from vati.backtest import BacktestEngine
from vati.core import EventKind, Ledger
from vati.execution.mt5_pull import deviation_points
from vati.execution.policy_templates import DEFAULT_TEMPLATES, LIMIT_AT_TOUCH, slippage_bound_in_price
from vati.intelligence.events import EventMatrix
from vati.market_data import FX_CALENDAR
from vati.risk import SymbolContract, TradingMandate  # noqa: F401
from vati.strategies import STRATEGY_IMPLEMENTATIONS, CapsuleRegistry

from pathlib import Path

D = Decimal
REG = Path(__file__).resolve().parents[1] / "strategies" / "registry"
SID = "FX-TREND-PULLBACK-01"


def usdjpy() -> SymbolContract:
    return SymbolContract(symbol="USDJPY", venue="paper", base_currency="USD", quote_currency="JPY", account_currency="USD",
                          contract_size=D("100000"), tick_size=D("0.001"), tick_value=D("0.667"), volume_min=D("0.01"),
                          volume_step=D("0.01"), volume_max=D("100"), min_stop_distance=D("0.030"))


def jpy_bars():
    """The trend-with-pullbacks shape the EURUSD backtest tests use, at a JPY price scale."""
    closes = [c * 100 for c in noisy_trend(140)]
    for _ in range(4):
        last = closes[-1]
        closes += [last - 0.15 * (i + 1) for i in range(5)]
        base = closes[-1]
        closes += [base + 0.06 * i + 0.18 * ((i % 6) - 2.5) / 2.5 for i in range(40)]
    bars = mk_bars(closes, symbol="USDJPY", spread=D("0.008"))
    # mk_bars uses a fixed ±0.0005 range, which is a FX-scale wick; widen it for JPY.
    from dataclasses import replace
    return [replace(b, high=b.close + D("0.05"), low=b.close - D("0.05")) for b in bars]


def run_jpy(tmp_path, slippage: Decimal):
    m = historical_mandate_dict(venue="paper", mode="DEMO_TRADER", instruments=["USDJPY"], allowed_strategies=[SID])
    cfg = SessionConfig(symbol="USDJPY", base="USD", quote="JPY", venue="paper", account_alias="fx_primary", contract=usdjpy(), mandate_dict=m, session_id="jpy-1")
    reg = CapsuleRegistry.load_dir(REG)
    engine = OpportunityEngine(reg, {SID: STRATEGY_IMPLEMENTATIONS[SID.rsplit("-", 1)[0]](strategy_id=SID)}, TradingMandate.from_mapping(m))
    bt = BacktestEngine(cfg=cfg, engine=engine, cost_fn=lambda st: D("0.00008"), calendar=FX_CALENDAR, events=EventMatrix(),
                        spread=D("0.008"), slippage=slippage, ledger_path=str(tmp_path / "jpy.sqlite"))
    return bt.run(jpy_bars()), Ledger(tmp_path / "jpy.sqlite")


def test_template_bounds_are_fractions_of_price():
    t = DEFAULT_TEMPLATES[LIMIT_AT_TOUCH]
    assert t.version == "1.1.0"
    assert slippage_bound_in_price(t.max_slippage, D("1.10")) == D("0.000110")     # ~1.1 pip on EURUSD
    assert slippage_bound_in_price(t.max_slippage, D("150.000")) == D("0.0150000")  # 1.5 pips on USDJPY


def test_usdjpy_orders_with_normal_slippage_now_fill(tmp_path):
    res, led = run_jpy(tmp_path, slippage=D("0.002"))   # 0.2 pip
    receipts = [e.payload for e in led.iter(EventKind.EXECUTION_RECEIPT)]
    refused = [r for r in receipts if r.get("reject_reason") == "max_slippage"]
    assert receipts and not refused, f"{len(refused)} of {len(receipts)} JPY orders refused for slippage"
    assert res.trades >= 1


def test_the_command_bound_scales_with_the_entry_price(tmp_path):
    _res, led = run_jpy(tmp_path, slippage=D("0.002"))
    cmds = [e.payload for e in led.iter(EventKind.ORDER_COMMAND)]
    assert cmds
    for c in cmds:
        entry, bound = D(c["entry_price"]), D(c["max_slippage"])
        assert bound == entry * DEFAULT_TEMPLATES[LIMIT_AT_TOUCH].max_slippage, c


def test_slippage_beyond_the_bound_is_still_refused(tmp_path):
    """The cap must still bite: 3 pips of slippage on USDJPY exceeds the 1 bp bound."""
    _res, led = run_jpy(tmp_path, slippage=D("0.030"))
    receipts = [e.payload for e in led.iter(EventKind.EXECUTION_RECEIPT)]
    assert receipts and all(r.get("reject_reason") == "max_slippage" for r in receipts)


def test_mt5_deviation_is_in_points_of_the_symbol():
    assert deviation_points("EURUSD", D("0.00011")) == 11          # 5-digit: 1.1 pip = 11 points
    assert deviation_points("USDJPY", D("0.0150")) == 15           # 3-digit: 1.5 pip = 15 points
    assert deviation_points("XAUUSD", D("0.20")) == 200
    assert deviation_points("EURUSD", D("0.00011"), {"EURUSD": "0.0001"}) == 1   # 4-digit broker
    assert deviation_points("EURUSD", None) == 20


# ---------------------------------------------------------------- P1-TRADE-EXEC-003
def _eurusd():
    return SymbolContract(symbol="EURUSD", venue="paper", base_currency="EUR", quote_currency="USD", account_currency="USD",
                          contract_size=D("100000"), tick_size=D("0.00001"), tick_value=D("1.00"), volume_min=D("0.01"),
                          volume_step=D("0.01"), volume_max=D("100"), min_stop_distance=D("0.00030"))


def _quantise(entry, stop, direction):
    from vati.execution.route_registry import RouteRegistry
    reg = RouteRegistry()
    reg.refresh(account_alias="fx_primary", adapter_id="paper", contracts={"EURUSD": _eurusd()}, now_ms=1)
    route = reg.resolve("fx_primary", "EURUSD", now_ms=1, direction=direction)
    return reg.quantise(route, quantity=D("0.10"), entry=entry, stop=stop, direction=direction)


def test_the_research_case_no_longer_widens_the_stop():
    """London breakout entry off the tick: entry rounded up, stop on the tick below."""
    from vati.risk.contracts import Direction
    entry, stop = D("1.0123460"), D("1.00709")   # approved distance 0.005256
    q = _quantise(entry, stop, Direction.LONG)
    assert abs(q.entry_price - q.stop_price) <= abs(entry - stop), (q.entry_price, q.stop_price)


def test_rounding_never_widens_any_stop_in_either_direction():
    from vati.risk.contracts import Direction
    import random
    rnd = random.Random(17)
    for _ in range(2000):
        e = D(str(round(rnd.uniform(1.0, 1.5), 7)))
        dist = D(str(round(rnd.uniform(0.0004, 0.01), 7)))
        for d, s in ((Direction.LONG, e - dist), (Direction.SHORT, e + dist)):
            q = _quantise(e, s, d)
            assert abs(q.entry_price - q.stop_price) <= abs(e - s), (d, e, s, q)
            # still on the stop side of the entry, and on the tick grid
            assert (q.stop_price < q.entry_price) if d is Direction.LONG else (q.stop_price > q.entry_price)
            assert (q.stop_price / D("0.00001")) % 1 == 0


# ---------------------------------------------------------------- P1-TRADE-EXEC-004
def _cmd(entry_type, direction, entry, stop, *, expires_at_ms=None):
    from vati.execution.base import OrderCommand, StopMode
    from vati.risk.contracts import LossModel
    return OrderCommand("ti-x", "d" * 64, "k-x", "paper_primary", "paper", "EURUSD", direction, entry_type, D("0.10"), entry, stop,
                        StopMode.VENUE, LossModel.STOP_DISTANCE, max_slippage=D("0.0003"), expires_at_ms=expires_at_ms).sealed()


def test_a_stop_entry_rests_until_price_trades_through_it():
    from vati.execution import PaperAdapter
    from vati.risk.contracts import Direction
    pa = PaperAdapter(spread=D("0.0001"), slippage=D("0"))
    pa.mark("EURUSD", D("1.09995"), D("1.10005"), now_ms=0)          # mid 1.1000
    rec = pa.submit(_cmd("STOP", Direction.LONG, D("1.10200"), D("1.09900")), now_ms=1)
    assert rec.status == "ACCEPTED" and pa.positions() == [], "a buy stop above the market must not fill yet"
    assert pa.mark("EURUSD", D("1.10100"), D("1.10110"), now_ms=2) == []   # still below the level
    fills = pa.mark("EURUSD", D("1.10195"), D("1.10205"), now_ms=3)      # ask crosses 1.10200
    assert fills and fills[0].reject_reason == "PENDING_FILLED"
    assert fills[0].average_fill >= D("1.10200"), "a stop fills at or beyond its level, never before"


def test_a_limit_away_from_the_market_fills_only_when_reached():
    from vati.execution import PaperAdapter
    from vati.risk.contracts import Direction
    pa = PaperAdapter(spread=D("0.0001"), slippage=D("0.00002"))
    pa.mark("EURUSD", D("1.09995"), D("1.10005"), now_ms=0)
    rec = pa.submit(_cmd("LIMIT", Direction.LONG, D("1.09800"), D("1.09500")), now_ms=1)
    assert rec.status == "ACCEPTED" and not pa.positions()
    fills = pa.mark("EURUSD", D("1.09790"), D("1.09800"), now_ms=2)
    assert fills and fills[0].average_fill == D("1.09800")


def test_an_at_touch_limit_still_fills_immediately():
    from vati.execution import PaperAdapter
    from vati.risk.contracts import Direction
    pa = PaperAdapter(spread=D("0.0001"), slippage=D("0.00002"))
    pa.mark("EURUSD", D("1.09995"), D("1.10005"), now_ms=0)
    rec = pa.submit(_cmd("LIMIT", Direction.LONG, D("1.10000"), D("1.09700")), now_ms=1)
    assert rec.status == "FILLED"


def test_a_resting_entry_expires():
    from vati.execution import PaperAdapter
    from vati.risk.contracts import Direction
    pa = PaperAdapter()
    pa.mark("EURUSD", D("1.09995"), D("1.10005"), now_ms=0)
    pa.submit(_cmd("STOP", Direction.LONG, D("1.10500"), D("1.09900"), expires_at_ms=100), now_ms=1)
    out = pa.mark("EURUSD", D("1.09995"), D("1.10005"), now_ms=100)
    assert out and out[0].status == "EXPIRED" and not pa.pending


def test_the_policy_picks_a_template_that_can_execute_the_requested_type():
    from vati.execution.policy import ExecutionBucket, ExecutionPolicyEngine
    from vati.execution.policy_templates import PASSIVE, STOP_ENTRY
    eng = ExecutionPolicyEngine()
    b = ExecutionBucket("paper", "fx_primary", "EURUSD", "LONDON", "NORMAL", "NONE", "LONG")
    assert eng.select(candidate_id="c", bucket=b, entry_type="STOP").template_id == STOP_ENTRY
    assert eng.select(candidate_id="c", bucket=b, entry_type="PASSIVE_LIMIT").template_id == PASSIVE
    assert eng.select(candidate_id="c", bucket=b).template_id == LIMIT_AT_TOUCH


def test_the_router_refuses_to_turn_a_stop_into_a_limit(mandate, eurusd):
    import pytest
    from test_execution import approved, router
    from vati.execution import PaperAdapter
    from vati.execution.policy import ExecutionBucket, ExecutionPolicyEngine
    from vati.execution.router import RouterError
    from vati.risk import StrategyState
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    r, _led = router(PaperAdapter())
    limit_policy = ExecutionPolicyEngine().select(candidate_id=i.trade_intent_id, bucket=ExecutionBucket("paper", "fx_primary", "EURUSD", "LONDON", "NORMAL", "NONE", "LONG"))
    with pytest.raises(RouterError, match="ENTRY_TYPE_NOT_PERMITTED"):
        r.execute(i, d, m, now_ms=1_800_000_000_000, entry_type="STOP", execution_policy_decision=limit_policy)


def test_a_venue_that_cannot_place_stop_entries_refuses_them(mandate, eurusd):
    import pytest
    from test_execution import approved, router
    from vati.execution import PaperAdapter
    from vati.execution.router import RouterError
    from vati.risk import StrategyState

    class LimitOnlyVenue(PaperAdapter):
        supported_entry_types = ("MARKET", "LIMIT")

    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    r, _led = router(LimitOnlyVenue())
    with pytest.raises(RouterError, match="ENTRY_TYPE_NOT_SUPPORTED"):
        r.execute(i, d, m, now_ms=1_800_000_000_000, entry_type="STOP")


def test_a_market_only_venue_substitutes_an_at_touch_limit_and_says_so(mandate, eurusd):
    from test_execution import approved, router
    from vati.execution import PaperAdapter
    from vati.risk import StrategyState

    class MarketOnlyVenue(PaperAdapter):
        supported_entry_types = ("MARKET",)

    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    r, led = router(MarketOnlyVenue())
    r.execute(i, d, m, now_ms=1_800_000_000_000, entry_type="LIMIT")
    cmd = next(led.iter(EventKind.ORDER_COMMAND)).payload
    assert cmd["entry_type"] == "MARKET" and cmd["requested_entry_type"] == "LIMIT" and cmd["entry_type_substituted"] is True


def test_the_cycle_sends_the_strategy_s_own_entry_type(eurusd, tmp_path):
    """London breakout asks for STOP; the order command must say STOP, not LIMIT."""
    from test_backtest_runner_cli import fx_cfg, fx_engine, synthetic_bars
    from vati.app import DecisionCycle
    from vati.execution import PaperAdapter
    cfg = fx_cfg(eurusd)
    led = Ledger()
    cyc = DecisionCycle(cfg=cfg, adapter=PaperAdapter(venue="paper", account_alias="fx_primary"), ledger=led, engine=fx_engine(cfg),
                        cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix())
    bars = synthetic_bars()
    for i in range(60, len(bars)):
        for px in (bars[i].open, bars[i].low, bars[i].high, bars[i].close):
            cyc.mark(px - D("0.00005"), px + D("0.00005"), now_ms=bars[i].end_ms)
        cyc.step(bars[: i + 1], now_ms=bars[i].end_ms, last_quote_ms=bars[i].end_ms)
    cmds = [e.payload for e in led.iter(EventKind.ORDER_COMMAND)]
    london = [c for c in cmds if c["strategy_id"] == "FX-LONDON-BREAKOUT-01"]
    pullback = [c for c in cmds if c["strategy_id"] == "FX-TREND-PULLBACK-01"]
    assert london and all(c["entry_type"] == "STOP" for c in london)
    assert all(c["entry_type"] in ("LIMIT", "PASSIVE_LIMIT", "MARKET") for c in pullback)


def test_an_entry_filled_from_rest_gets_its_thesis_and_tca(eurusd):
    """A resting STOP that later fills is a position like any other: claim sealed, cost measured."""
    from test_backtest_runner_cli import fx_cfg, fx_engine, synthetic_bars
    from vati.app import DecisionCycle
    from vati.execution import PaperAdapter
    cfg = fx_cfg(eurusd)
    led = Ledger()
    cyc = DecisionCycle(cfg=cfg, adapter=PaperAdapter(venue="paper", account_alias="fx_primary"), ledger=led, engine=fx_engine(cfg),
                        cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix())
    bars = synthetic_bars()
    for i in range(60, len(bars)):
        for px in (bars[i].open, bars[i].low, bars[i].high, bars[i].close):
            cyc.mark(px - D("0.00005"), px + D("0.00005"), now_ms=bars[i].end_ms)
        cyc.step(bars[: i + 1], now_ms=bars[i].end_ms, last_quote_ms=bars[i].end_ms)
    filled = {e.correlation_id for e in led.iter(EventKind.SESSION) if e.payload.get("event") == "ENTRY_FILLED_FROM_REST"}
    assert filled, "the scenario must contain an entry that rested and then filled"
    tca = {e.correlation_id for e in led.iter(EventKind.TCA_RECORD)}
    assert filled <= tca, "a fill from rest must record its execution cost"
    sealed = {e.correlation_id: e.payload for e in led.iter(EventKind.TRADE_THESIS)}
    assert filled <= set(sealed), "a fill from rest must seal its thesis"
    fills = {e.correlation_id: D(e.payload["fill"]) for e in led.iter(EventKind.SESSION) if e.payload.get("event") == "ENTRY_FILLED_FROM_REST"}
    assert all(D(str(sealed[i]["entry"])) == fills[i] for i in filled), "the thesis entry is the actual fill, not the trigger"


def test_the_account_service_path_carries_the_entry_type():
    """The live path must hand the strategy's own type to policy and router, not the LIMIT default."""
    from vati.arbiter.candidate import CandidateOpportunity
    assert CandidateOpportunity.__dataclass_fields__["entry_type"].default == "LIMIT"
    src = (Path(__file__).resolve().parents[1] / "vati" / "app" / "account_service.py").read_text()
    body = src[src.index("    def _execute(self, candidate"):]
    body = body[: body.index("\n    def ", 10)]
    assert "entry_type=candidate.entry_type" in body.split("self.router.execute(")[0], "policy.select must get the entry type"
    assert "entry_type=candidate.entry_type" in body.split("self.router.execute(")[1], "router.execute must get the entry type"
    eng_src = (Path(__file__).resolve().parents[1] / "vati" / "arbiter" / "opportunity.py").read_text()
    assert eng_src.count("entry_type=sig.entry_type") >= 2, "candidates must carry the signal's entry type"
