"""Command Center read models on a real session-service ledger (paper account, synthetic lake)."""
from __future__ import annotations

import json
from decimal import Decimal

from conftest import mandate_dict
from test_backtest_runner_cli import synthetic_bars
from vati.accounts import Account, AccountRegistry
from vati.app import account_states, lake_bars, market_state, portfolio, risk_view, trade_detail
from vati.app.service import ServiceConfig, SessionService, lake_bar_source
from vati.core import EventKind, Ledger
from vati.market_data.feeds import BarLake
from vati.risk.serde import contract_to_dict

D = Decimal


def run_session(tmp_path, eurusd, steps=None):
    reg = AccountRegistry(tmp_path / "accounts.json"); reg.add(Account(alias="paper_lab", broker="PAPER", mode="DEMO_TRADER", currency="USD", label="Paper Lab"))
    lake = BarLake(tmp_path / "lake"); bars = synthetic_bars(); lake.write(bars, symbol="EURUSD", timeframe="H1", source="t", provenance="SYNTHETIC")
    cfg = ServiceConfig(account_alias="paper_lab", symbol="EURUSD", base="EUR", quote="USD", timeframe="H1", contract=contract_to_dict(eurusd), mandate=mandate_dict(venue="paper", mode="DEMO_TRADER", account_alias="paper_lab", allowed_strategies=["FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"]),
                        capsules=["FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"], registry_path=str(tmp_path / "accounts.json"), ledger=str(tmp_path / "l.sqlite"), lake_root=str(tmp_path / "lake"), heartbeat_path=str(tmp_path / "hb.json"))
    clock = {"now": bars[100].end_ms}
    svc = SessionService(cfg, lake_bar_source(lake, "EURUSD", "H1"), clock=lambda: clock["now"]).build(); svc.start()
    for i in range(101, 101 + (steps or len(bars) - 101)):
        clock["now"] = bars[i].end_ms + 1000; svc.step_once()
    return Ledger(tmp_path / "l.sqlite"), reg, lake, bars


def test_portfolio_accounts_risk_and_market_state(tmp_path, eurusd):
    led, reg, lake, bars = run_session(tmp_path, eurusd)
    acc = account_states(led, reg.public())
    assert len(acc) == 1 and acc[0]["alias"] == "paper_lab" and acc[0]["connection_state"] == "LIVE" and acc[0]["safety_identity"] == "PAPER" and D(acc[0]["equity"]) > 0
    assert acc[0]["drawdown_pct"] is not None and D(acc[0]["drawdown_pct"]) >= 0 and acc[0]["session_event"] == "STARTED"
    pf = portfolio(led, reg.public())
    assert pf["totals"]["accounts_in_reporting_currency"] == 1 and D(pf["totals"]["equity"]) == D(acc[0]["equity"]) and pf["totals"]["accounts_in_other_currencies"] == []
    assert pf["data_state"]["EURUSD"]["state"] == "LIVE" and isinstance(pf["potential_trades"], list) and len(pf["recent_trades"]) <= 5
    assert pf["risk"]["kill_switch_active"] == [] and pf["risk"]["open_trades"] == len(pf["open_positions"])
    ms = market_state(led)["symbols"]
    assert len(ms) == 1 and ms[0]["symbol"] == "EURUSD" and ms[0]["regime"]["trend"] in ("BULL", "BEAR", "RANGE") and ms[0]["session"] and ms[0]["van_summary"].startswith("EURUSD:")
    assert ms[0]["last_decision"]["decision"] in ("TRADE", "REDUCE_SIZE", "WAIT", "SKIP", "NO_TRADE") and market_state(led, "xauusd")["symbols"] == []
    rk = risk_view(led)
    assert rk["portfolio_heat"] is not None and rk["limits"]["max_daily_loss"] and rk["equity"] and set(rk["concentration"]) == {"by_symbol", "by_currency", "by_direction"}
    if rk["positions"]:
        assert rk["concentration"]["by_currency"].keys() >= {"EUR", "USD"}
    # unknown-alias snapshots still surface (ledger truth beats a stale registry)
    assert account_states(led, [])[0]["broker"] == "UNKNOWN"


def test_trade_detail_timeline_levels_and_chart(tmp_path, eurusd):
    led, reg, lake, bars = run_session(tmp_path, eurusd)
    reviewed = [e.correlation_id for e in led.iter(EventKind.TRADE_REVIEW)]
    assert reviewed, "the synthetic session must close at least one trade"
    d = trade_detail(led, reviewed[0], lake=lake)
    kinds = [t["kind"] for t in d["timeline"]]
    first = {k: kinds.index(k) for k in ("RISK_DECISION", "ORDER_SENT", "EXECUTION", "REVIEW")}
    assert kinds[0] == "RISK_DECISION" and first["RISK_DECISION"] < first["ORDER_SENT"] < first["EXECUTION"] < first["REVIEW"]      # causal order, even inside one millisecond
    assert [t["at_ms"] for t in d["timeline"]] == sorted(t["at_ms"] for t in d["timeline"]) and all(len(t["hash"]) == 64 for t in d["timeline"])
    assert d["state"] == "CLOSED" and d["levels"]["entry"] and d["levels"]["stop"] and d["levels"]["exit"] and d["levels"]["target"]
    assert d["account_alias"] == "paper_lab" and set(d["multipliers"]) >= {"regime_multiplier", "confidence_multiplier"} and d["review"]["outcome"]
    assert d["chart"]["timeframe"] == "H1" and d["chart"]["bars"] and d["chart"]["markers"][0]["kind"] == "ENTRY" and any(m["kind"] == "EXIT" for m in d["chart"]["markers"])
    assert any("Confidence" in s for s in d["van_interpretation"]) and any("Review:" in s for s in d["van_interpretation"])
    assert trade_detail(led, "no-such-intent") is None
    rejected = [e.correlation_id for e in led.iter(EventKind.RISK_DECISION) if e.payload["decision"]["decision"] == "REJECTED"]
    if rejected:
        r = trade_detail(led, rejected[0])
        assert r["state"] == "REJECTED" and any("refused" in s for s in r["van_interpretation"]) and "chart" not in r
    b = lake_bars(lake, "eurusd", "H1", limit=50, ledger=led)
    assert b["count"] == 50 and b["provenance"] == ["SYNTHETIC"] and b["data_state"]["state"] == "LIVE" and b["bars"][-1]["t"] == bars[-1].start_ms
    assert lake_bars(lake, "EURUSD", "H1", limit=5, end_ms=bars[10].end_ms)["bars"][-1]["t"] == bars[10].start_ms   # end_ms is exclusive on bar start
