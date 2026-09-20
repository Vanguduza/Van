from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from vati.validation.certificates import passing_certificate

from conftest import mandate_dict
from test_intelligence import mk_bars, noisy_trend
from vati.__main__ import main as cli_main
from vati.app import DecisionCycle, SessionConfig, SessionRunner
from vati.arbiter import OpportunityEngine
from vati.backtest import BacktestEngine, compute_metrics, deflated_sharpe, pbo_cscv, walk_forward_splits
from vati.core import EventKind, Ledger
from vati.execution import OwnerTicketAdapter, PaperAdapter
from vati.execution.reconciliation import LedgerPosition
from vati.intelligence.events import EventMatrix
from vati.market_data import FX_CALENDAR
from vati.market_data.calendars import zse_calendar
from vati.risk import Decision, KillSwitchTrigger, LossModel, SymbolContract, TradingMandate
from vati.strategies import STRATEGY_IMPLEMENTATIONS, CapsuleRegistry, StrategyContext, ZseSnapshot
from vati.zse.currency import CurrencyRegime

REG = Path(__file__).resolve().parents[1] / "strategies" / "registry"


def synthetic_bars(n_cycles=4):
    """Several trend legs with pullbacks and a reversal, so the pullback strategy gets chances."""
    closes = noisy_trend(140)
    for k in range(n_cycles):
        last = closes[-1]
        closes += [last - 0.0015 * (i + 1) for i in range(5)]                 # pullback
        base = closes[-1]
        closes += [base + 0.0006 * i + 0.0018 * ((i % 6) - 2.5) / 2.5 for i in range(40)]  # resume trend
    return mk_bars(closes, start=1_757_980_800_000, step=3_600_000)


def fx_cfg(eurusd, **mandate_over):
    m = mandate_dict(venue="paper", mode="DEMO_TRADER", allowed_strategies=["FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"], **mandate_over)
    return SessionConfig(symbol="EURUSD", base="EUR", quote="USD", venue="paper", account_alias="fx_primary", contract=SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), mandate_dict=m, session_id="bt-1")


def fx_engine(cfg):
    reg = CapsuleRegistry.load_dir(REG)
    impl = {sid: STRATEGY_IMPLEMENTATIONS[sid.rsplit("-", 1)[0]](strategy_id=sid) for sid in ("FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01")}
    return OpportunityEngine(reg, impl, TradingMandate.from_mapping(cfg.mandate_dict))


def test_backtest_runs_trades_and_replays(eurusd, tmp_path):
    cfg = fx_cfg(eurusd)
    bt = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.0003"), calendar=FX_CALENDAR, events=EventMatrix(), ledger_path=str(tmp_path / "bt.sqlite"))
    res = bt.run(synthetic_bars())
    assert res.trades >= 1, res.summary()
    assert res.ledger_ok and res.decision_replay_identical
    assert res.metrics.trades == res.trades and res.equity_curve[-1][1] != Decimal("10000") or res.trades == 0
    assert any(c.decision in ("APPROVED", "REDUCED") for c in res.cycles)
    led = Ledger(tmp_path / "bt.sqlite")
    assert led.count(EventKind.RISK_DECISION) >= 1 and led.count(EventKind.TRADE_REVIEW) == res.trades and led.count(EventKind.TCA_RECORD) >= 1
    # determinism: same bars → same ledger head
    res2 = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.0003"), calendar=FX_CALENDAR, events=EventMatrix()).run(synthetic_bars())
    assert res2.summary()["metrics"] == res.summary()["metrics"]


def test_leakage_switch_changes_results(eurusd):
    cfg = fx_cfg(eurusd)
    bars = synthetic_bars()
    honest = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.0003"), calendar=FX_CALENDAR, events=EventMatrix()).run(bars)
    peek = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.0003"), calendar=FX_CALENDAR, events=EventMatrix()).run(bars, peek=True)
    assert honest.summary()["metrics"] != peek.summary()["metrics"] or [c.state_hash for c in honest.cycles] != [c.state_hash for c in peek.cycles]


def test_cost_gate_blocks_everything_when_cost_is_high(eurusd):
    cfg = fx_cfg(eurusd)
    res = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.05"), calendar=FX_CALENDAR, events=EventMatrix()).run(synthetic_bars())
    assert res.trades == 0 and all(c.decision in ("NO_TRADE", "WAIT") for c in res.cycles)


def test_metrics_dsr_pbo_walkforward():
    pnls = [Decimal(x) for x in ("10", "-5", "12", "-4", "8", "-6", "15", "-5")]
    rs = [Decimal(x) for x in ("1", "-0.5", "1.2", "-0.4", "0.8", "-0.6", "1.5", "-0.5")]
    m = compute_metrics(pnls, rs, Decimal("1000"))
    assert m.trades == 8 and m.wins == 4 and m.profit_factor > 1 and m.max_drawdown == 6.0 and m.net_pnl == 25.0
    assert deflated_sharpe(0.6, n_obs=200, skew=0.0, kurtosis=3.0, n_trials=1, sr_variance_across_trials=0.0) > 0.99
    lucky = deflated_sharpe(0.15, n_obs=60, skew=-0.5, kurtosis=5.0, n_trials=500, sr_variance_across_trials=0.05)
    assert lucky < 0.95
    good = [[0.01 * ((i % 3) - 0.5) + 0.004 for i in range(80)]]
    rnd = [[((i * (k + 3)) % 7 - 3) / 100 for i in range(80)] for k in range(8)]
    assert pbo_cscv(good + rnd) <= 1.0 and pbo_cscv(rnd) >= 0.0
    assert walk_forward_splits(100, train=40, test=20) == [(range(0, 40), range(40, 60)), (range(20, 60), range(60, 80)), (range(40, 80), range(80, 100))]
    with pytest.raises(ValueError):
        pbo_cscv(rnd, partitions=3)


def test_runner_startup_blocks_on_orphan_and_owner_halt(eurusd):
    cfg = fx_cfg(eurusd)
    paper = PaperAdapter(venue="paper", account_alias="fx_primary")
    cyc = DecisionCycle(cfg=cfg, adapter=paper, ledger=Ledger(), engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.0003"), calendar=FX_CALENDAR, events=EventMatrix())
    run = SessionRunner(cyc)
    rep = run.startup(now_ms=1, ledger_positions=[LedgerPosition("ghost", "EURUSD", Decimal("0.1"), Decimal("1.09"))])
    assert not rep.permit_new_orders and not run.permit_new_orders and KillSwitchTrigger.RECONCILIATION_FAILURE in cyc.kill.active
    bars = synthetic_bars()
    assert run.on_bar(bars[:80], now_ms=bars[79].end_ms, last_quote_ms=bars[79].end_ms).decision == "NEW_TRADES_BLOCKED"
    clean = SessionRunner(DecisionCycle(cfg=cfg, adapter=PaperAdapter(venue="paper", account_alias="fx_primary"), ledger=Ledger(), engine=fx_engine(cfg), cost_fn=lambda st: Decimal("0.0003"), calendar=FX_CALENDAR, events=EventMatrix()))
    assert clean.startup(now_ms=1).permit_new_orders and clean.permit_new_orders
    from conftest_owner_authority import OwnerAuthorityHarness

    owner = OwnerAuthorityHarness()
    clean.authority = owner.verifier
    # P0-TRADE-001 — both of these used to be accepted; the second was the happy path.
    for refused in ("", "sig:owner"):
        with pytest.raises(PermissionError):
            clean.owner_halt(now_ms=2, owner_signature_ref=refused)
        assert clean.permit_new_orders, "trading stopped on an unverifiable halt"
    clean.owner_halt(
        now_ms=2,
        owner_signature_ref=owner.token(act="owner-halt", subject=cfg.session_id, issued_at_unix=1),
    )
    assert clean.on_bar(bars[:80], now_ms=bars[79].end_ms, last_quote_ms=bars[79].end_ms).decision == "NEW_TRADES_BLOCKED"


def test_zse_session_produces_owner_ticket():
    contract = SymbolContract(symbol="DELTA", venue="zse", base_currency="DELTA", quote_currency="ZiG", account_currency="ZiG", contract_size=Decimal("1"), tick_size=Decimal("0.01"), tick_value=Decimal("0.01"),
                              volume_min=Decimal("100"), volume_step=Decimal("100"), volume_max=Decimal("10000000"), min_stop_distance=Decimal("0"), trade_mode="LONG_ONLY", loss_model=LossModel.ILLIQUID_EQUITY,
                              board_lot=Decimal("100"), adv_20d=Decimal("120000"), liquidity_haircut=Decimal("0.03"), round_trip_cost_pct=Decimal("0.044"))
    m = mandate_dict(venue="zse", instruments=["DELTA"], allowed_strategies=["ZSE-VALUE-ROTATION-01"], mode="LIMITED_LIVE", weekend_hold_allowed=True, max_open_stop_risk="0.02", max_risk_per_trade="0.01", account_alias="zse_primary")
    cfg = SessionConfig(symbol="DELTA", base="DELTA", quote="ZiG", venue="zse", account_alias="zse_primary", contract=contract, mandate_dict=m, session_id="zse-1", software_stops=True, time_in_force="GTC30")
    from conftest_owner_authority import OwnerAuthorityHarness

    owner = OwnerAuthorityHarness()
    reg = CapsuleRegistry.load_dir(REG, authority=owner.verifier)
    StrategyState = __import__("vati.risk", fromlist=["StrategyState"]).StrategyState
    # Each step up the ladder needs its own owner authority, named for the state it grants.
    for st in ("BACKTEST", "VALIDATION", "DEMO", "SHADOW", "LIMITED_LIVE"):
        # TRD-ENH-021 — from DEMO onwards the promotion carries sealed semantic
        # evidence bound to the capsule revision being promoted.
        cert = passing_certificate(
            strategy_id="ZSE-VALUE-ROTATION-01",
            capsule_hash=reg.get("ZSE-VALUE-ROTATION-01").capsule_hash,
        )
        reg.promote(
            "ZSE-VALUE-ROTATION-01", StrategyState(st),
            approval_signature_ref=owner.token(
                act="capsule-promote", subject=f"ZSE-VALUE-ROTATION-01:{st}", issued_at_unix=1
            ),
            evidence_refs=["bt", "shadow"], approved_at_unix=1, certificate=cert,
        )
    engine = OpportunityEngine(reg, {"ZSE-VALUE-ROTATION-01": STRATEGY_IMPLEMENTATIONS["ZSE-VALUE-ROTATION"](strategy_id="ZSE-VALUE-ROTATION-01")}, TradingMandate.from_mapping(m))
    snap = ZseSnapshot("DELTA", "ZSE", Decimal("25.00"), Decimal("120000"), 18, Decimal("0.02"), Decimal("0.8"), 40, None, CurrencyRegime.ELEVATED, Decimal("0.044"), Decimal("0.03"))
    adapter = OwnerTicketAdapter(equity=Decimal("1000000"), csd_verified=True)
    cyc = DecisionCycle(cfg=cfg, adapter=adapter, ledger=Ledger(), engine=engine, cost_fn=lambda st: Decimal("0.044"), calendar=zse_calendar(None, None, verified=False), events=EventMatrix(),
                        ctx_fn=lambda st, cost: StrategyContext(round_trip_cost_pct=cost, zse=snap))
    run = SessionRunner(cyc)
    assert run.startup(now_ms=1).permit_new_orders
    bars = mk_bars([25.0 + 0.05 * ((i % 5) - 2) for i in range(80)], symbol="DELTA", step=86_400_000, spread=Decimal("0.5"))
    res = run.on_bar(bars, now_ms=bars[-1].end_ms, last_quote_ms=bars[-1].end_ms)
    assert res.decision in ("APPROVED", "REDUCED"), res
    assert adapter.tickets and cyc.ledger.count(EventKind.OWNER_TICKET) == 1
    t = next(iter(adapter.tickets.values()))
    assert t.quantity_shares % 100 == 0 and t.quantity_shares <= 12000 and t.software_stop is not None


def test_cli_backtest_and_replay(eurusd, tmp_path):
    bars = synthetic_bars()
    p = tmp_path / "bars.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["symbol", "start_ms", "end_ms", "open", "high", "low", "close", "volume", "ticks", "avg_spread"])
        for b in bars:
            w.writerow([b.symbol, b.start_ms, b.end_ms, b.open, b.high, b.low, b.close, b.volume, b.ticks, b.avg_spread])
    from vati.risk.serde import contract_to_dict
    cfg = {"symbol": "EURUSD", "base": "EUR", "quote": "USD", "venue": "paper", "account_alias": "fx_primary", "contract": contract_to_dict(SymbolContract(**{**eurusd.__dict__, "venue": "paper"})),
           "mandate": mandate_dict(venue="paper", mode="DEMO_TRADER", allowed_strategies=["FX-TREND-PULLBACK-01"]), "capsules": ["FX-TREND-PULLBACK-01"], "round_trip_cost_pct": "0.0003"}
    (tmp_path / "cfg.json").write_text(json.dumps(cfg))
    ledger = tmp_path / "l.sqlite"
    assert cli_main(["backtest", "--bars", str(p), "--config", str(tmp_path / "cfg.json"), "--ledger", str(ledger), "--out", str(tmp_path / "out.json")]) == 0
    out = json.loads((tmp_path / "out.json").read_text())
    assert out["ledger_ok"] and out["decision_replay_identical"]
    assert cli_main(["replay-verify", "--ledger", str(ledger)]) == 0
    assert cli_main(["ledger-status", "--ledger", str(ledger)]) == 0
    assert cli_main(["stack-lock"]) == 0 and cli_main(["zse-facts"]) == 0
