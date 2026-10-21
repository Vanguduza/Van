"""P1-TRADE-RISK-005 — risk lockouts that bound loss but cannot strand an autonomous account.

Found by the 17 October 2026 backtest research: after 4 straight losses the strategy
never traded again (the counter reset only on a win, which could not happen), and at a
4% drawdown only CERTIFIED_LIVE strategies could trade, so a demo account with none
stopped for good. Both reset silently on a process restart.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

import time

from conftest import intent as make_intent, mandate_dict, snapshot
from vati.core import EventKind, Ledger
from vati.risk import Decision, RiskAuthority, StrategyState, TradingMandate
from vati.risk.lockouts import (
    ACCOUNT_SCOPE, COOLDOWN_EVENT, DRAWDOWN_RESUME_EVENT, HOUR_MS, MANUAL_STRATEGY_ID, LockoutPolicy, LossStreakGovernor, relative_top_state,
    restore_equity_baselines,
)

D = Decimal
def now_ms() -> int:
    return int(time.time() * 1000)   # owner tokens are signed against the real clock, so read it when used
LOSS, WIN = D("-10"), D("12")
POLICY = LockoutPolicy(max_consecutive_losses=4)


def _lose(g, sid, n, t0=0):
    out = []
    for k in range(n):
        out += g.on_close(sid, LOSS, t0 + k)
    return out


# ------------------------------------------------------------------ governor
def test_four_losses_start_a_cooldown_not_a_permanent_stop():
    g = LossStreakGovernor(POLICY)
    events = _lose(g, "A", 4)
    assert any(e["event"] == COOLDOWN_EVENT and e["scope"] == "A" for e in events)
    assert g.verdict("A", 10).lock
    assert g.verdict("A", 24 * HOUR_MS + 10).lock == "", "the cooldown must end on its own"


def test_after_the_cooldown_the_strategy_trades_on_probation_until_it_wins():
    g = LossStreakGovernor(POLICY)
    _lose(g, "A", 4)
    later = 24 * HOUR_MS + 10
    assert g.verdict("A", later).risk_multiplier == D("0.5")
    g.on_close("A", WIN, later + 1)
    assert g.verdict("A", later + 2).risk_multiplier == D("1")


def test_one_strategy_s_streak_does_not_stop_another():
    g = LossStreakGovernor(LockoutPolicy(max_consecutive_losses=4))
    _lose(g, "A", 3)
    assert g.verdict("B", 5).lock == ""


def test_an_account_wide_streak_across_strategies_cools_the_account():
    g = LossStreakGovernor(POLICY)
    for k, sid in enumerate(("A", "B", "C", "D")):
        g.on_close(sid, LOSS, k)
    assert ACCOUNT_SCOPE in g.verdict("E", 10).lock


def test_repeated_cooldowns_in_a_week_escalate_to_the_owner():
    g = LossStreakGovernor(POLICY)
    t = 0
    for _ in range(3):
        _lose(g, "A", 4, t)
        t += 24 * HOUR_MS + 100
    v = g.verdict("A", t + 10 * 24 * HOUR_MS)
    assert "suspended" in v.lock and "owner" in v.lock, "a suspension never lifts by time alone"
    g.reset("A"); g.reset(ACCOUNT_SCOPE)
    assert g.verdict("A", t).lock == ""


def test_a_manual_streak_pauses_manual_entries_only():
    g = LossStreakGovernor(POLICY)
    _lose(g, MANUAL_STRATEGY_ID, 4)
    assert g.verdict(MANUAL_STRATEGY_ID, 10).lock, "four manual losses in a row pause manual entries"
    assert g.verdict("A", 10).lock == "", "the owner's losses never stop an autonomous strategy"
    assert g.verdict(MANUAL_STRATEGY_ID, 24 * HOUR_MS + 10).risk_multiplier == D("0.5")


def test_an_autonomous_account_cooldown_never_blocks_the_owner():
    g = LossStreakGovernor(POLICY)
    for k, sid in enumerate(("A", "B", "C", "D")):
        g.on_close(sid, LOSS, k)
    assert g.verdict("E", 10).lock and g.verdict(MANUAL_STRATEGY_ID, 10).lock == ""


def test_the_state_is_a_fold_over_the_ledger_so_a_restart_cannot_reset_it():
    from vati.core.events import make_event
    led = Ledger()
    for k in range(4):
        led.append(make_event(EventKind.TRADE_REVIEW, "t", {"strategy_id": "A", "pnl": "-10"}, event_time_ms=k, received_time_ms=k))
    rebuilt = LossStreakGovernor.rebuild(POLICY, led.iter())
    assert rebuilt.verdict("A", 10).lock, "a fresh process must see the same cooldown"


# ------------------------------------------------------------------ authority
@pytest.fixture
def fx_intent():
    return make_intent()


def _intent(fx_intent, state):
    from dataclasses import replace
    return replace(fx_intent, strategy_state=state)


def test_a_lock_is_refused_and_probation_reduces_size(eurusd, fx_intent):
    def a():
        return RiskAuthority(TradingMandate.from_mapping(mandate_dict()))   # fresh: the authority refuses a repeated intent
    locked = a().evaluate_safe(fx_intent, snapshot(eurusd, loss_streak_lock="A cooling down"))
    assert locked.decision is Decision.REJECTED and locked.reason_code == "CONSECUTIVE_LOSSES"
    full = a().evaluate_safe(fx_intent, snapshot(eurusd))
    half = a().evaluate_safe(fx_intent, snapshot(eurusd, loss_streak_multiplier=D("0.5")))
    assert half.approved_size < full.approved_size and "LOSS_STREAK_PROBATION" in half.constraints


def test_at_the_restricted_tier_the_best_strategies_present_keep_trading(eurusd, fx_intent):
    def a():
        return RiskAuthority(TradingMandate.from_mapping(mandate_dict(mode="DEMO_TRADER", venue="mt5")))
    dd = dict(peak_equity=D("10000"), equity=D("9550"), day_start_equity=D("9550"), week_start_equity=D("9550"))   # 4.5%
    demo = _intent(fx_intent, StrategyState.DEMO)
    legacy = a().evaluate_safe(demo, snapshot(eurusd, **dd))
    assert legacy.reason_code == "DRAWDOWN_TOP_TIER_ONLY", "without a top state the legacy floor still applies"
    allowed = a().evaluate_safe(demo, snapshot(eurusd, drawdown_top_state=StrategyState.DEMO, **dd))
    assert allowed.decision in (Decision.APPROVED, Decision.REDUCED), allowed
    refused = a().evaluate_safe(demo, snapshot(eurusd, drawdown_top_state=StrategyState.LIMITED_LIVE, **dd))
    assert refused.reason_code == "DRAWDOWN_TOP_TIER_ONLY", "below the best present tier still waits"


def test_the_suspending_tier_still_stops_everything(eurusd, fx_intent):
    a = RiskAuthority(TradingMandate.from_mapping(mandate_dict()))
    dd = dict(peak_equity=D("10000"), equity=D("9350"), day_start_equity=D("9350"), week_start_equity=D("9350"))   # 6.5%
    d = a.evaluate_safe(_intent(fx_intent, StrategyState.CERTIFIED_LIVE), snapshot(eurusd, drawdown_top_state=StrategyState.DEMO, **dd))
    assert d.reason_code == "DRAWDOWN_SUSPENDED"


def test_relative_top_state():
    assert relative_top_state([StrategyState.DEMO, StrategyState.RESEARCH]) is StrategyState.DEMO
    assert relative_top_state([StrategyState.RETIRED]) is None


# ------------------------------------------------------------------ cycle and restart
def _cycle(eurusd, led):
    from test_backtest_runner_cli import fx_cfg, fx_engine
    from vati.app import DecisionCycle
    from vati.execution import PaperAdapter
    from vati.intelligence.events import EventMatrix
    from vati.market_data import FX_CALENDAR
    cfg = fx_cfg(eurusd)
    return DecisionCycle(cfg=cfg, adapter=PaperAdapter(venue="paper", account_alias="fx_primary"), ledger=led, engine=fx_engine(cfg),
                         cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix())


def test_a_restart_keeps_the_cooldown_and_the_high_water_mark(eurusd):
    led = Ledger()
    cyc = _cycle(eurusd, led)
    for k in range(4):
        cyc._entries[f"t{k}"] = {"entry": D("1.1"), "stop": D("1.09"), "direction": cyc.cfg.contract and __import__("vati.risk.contracts", fromlist=["Direction"]).Direction.LONG,
                                  "strategy_id": "FX-TREND-PULLBACK-01", "cost_pct": D("0")}
        cyc.adapter.closed.append({"intent": f"t{k}", "pnl": D("-10")})
        cyc._on_close(f"t{k}", D("1.09"), "VENUE_STOP", 1_000 + k)
    snap = cyc.snapshot(now_ms=2_000, quote_age_ms=0, strategy_id="FX-TREND-PULLBACK-01")
    assert snap.loss_streak_lock
    cyc.peak_equity = D("12345")
    from vati.core.events import make_event
    led.append(make_event(EventKind.RISK_DECISION, "t", {"inputs": {"snapshot": {"peak_equity": "12345", "day_start_equity": "12000", "week_start_equity": "12000"}}},
                          event_time_ms=2_000, received_time_ms=2_000))
    again = _cycle(eurusd, led)
    assert again.snapshot(now_ms=3_000, quote_age_ms=0, strategy_id="FX-TREND-PULLBACK-01").loss_streak_lock, "restart reset the cooldown"
    assert again.peak_equity == D("12345"), "restart re-baselined the high-water mark"


def test_day_and_week_baselines_survive_a_restart_only_within_their_period():
    from vati.core.events import make_event
    led = Ledger()
    led.append(make_event(EventKind.RISK_DECISION, "t", {"inputs": {"snapshot": {"peak_equity": "10000", "day_start_equity": "9900", "week_start_equity": "9800"}}},
                          event_time_ms=1_000, received_time_ms=1_000))
    assert restore_equity_baselines(led.iter(), 2_000) == (D("10000"), D("9900"), D("9800"))
    peak, day, week = restore_equity_baselines(led.iter(), 1_000 + 8 * 86_400_000)
    assert peak == D("10000") and day is None and week is None


def test_resuming_after_suspension_needs_the_owner_s_signature(eurusd):
    from conftest import owner_authority
    owner = owner_authority()
    led = Ledger()
    cyc = _cycle(eurusd, led)
    cyc.peak_equity = D("20000")
    for bad in ("", owner.token(act="kill-switch-clear", subject="fx_primary"), owner.token(act="drawdown-resume", subject="other"),
                owner.stranger_token(act="drawdown-resume", subject="fx_primary")):
        with pytest.raises(PermissionError):
            cyc.resume_after_drawdown(owner_signature_ref=bad, authority=owner.verifier, now_ms=now_ms())
        assert cyc.peak_equity == D("20000")
    cyc.resume_after_drawdown(owner_signature_ref=owner.token(act="drawdown-resume", subject="fx_primary"), authority=owner.verifier, now_ms=now_ms())
    assert cyc.peak_equity == cyc.adapter.sync_account().equity
    assert any(e.payload.get("event") == DRAWDOWN_RESUME_EVENT for e in led.iter(EventKind.SESSION))
    assert _cycle(eurusd, led).peak_equity == cyc.peak_equity, "the owner's re-baseline survives a restart"


def test_a_loss_streak_suspension_reset_needs_the_owner_s_signature(eurusd):
    from conftest import owner_authority
    owner = owner_authority()
    cyc = _cycle(eurusd, Ledger())
    with pytest.raises(PermissionError):
        cyc.reset_loss_streak("FX-TREND-PULLBACK-01", owner_signature_ref=owner.token(act="loss-streak-reset", subject="fx_primary:OTHER"),
                              authority=owner.verifier, now_ms=now_ms())
    cyc.reset_loss_streak("FX-TREND-PULLBACK-01", owner_signature_ref=owner.token(act="loss-streak-reset", subject="fx_primary:FX-TREND-PULLBACK-01"),
                          authority=owner.verifier, now_ms=now_ms())


def test_the_defaults_are_the_owner_accepted_values():
    """OD-39: the owner accepted these values; changing one is a new owner decision."""
    p = LockoutPolicy(max_consecutive_losses=4)
    assert (p.cooldown_ms, p.probation_risk_multiplier, p.max_cooldowns_per_week) == (24 * HOUR_MS, D("0.5"), 2)
