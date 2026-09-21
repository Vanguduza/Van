"""Continuous learning (Rev 4 Part L): learning produces evidence and bounded
reduce-only adjustments; it never sizes, sends, promotes or widens."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from test_backtest_runner_cli import fx_cfg, fx_engine, synthetic_bars
from test_intelligence import mk_bars
from vati.backtest import BacktestEngine
from vati.core import EventKind, Ledger
from vati.core.events import make_event
from vati.intelligence.events import EventMatrix
from vati.learning import (
    CURRICULUM, ENVIRONMENT_WEIGHT, BrokerLearner, BrokerState, CounterfactualVariant, Environment, ExperienceEpisode, HealthObservation,
    HermesMemoryBridge, LearningBoundary, LearningBoundaryError, LiveAdjustment, MemoryBridgeError, ResearchPriorityEngine, StrategyHealthTracker,
    cluster_failures, curriculum_gate, daily_report, episode_from_ledger, evaluate_missed_opportunity, monthly_report, propose_candidate, run_counterfactuals, weekly_report,
)
from vati.learning.boundary import FORBIDDEN_TARGETS, LiveTarget
from vati.learning.hooks import LearningHooks
from vati.learning.replay import restore_learning_runtime
from vati.market_data import FX_CALENDAR
from vati.risk.contracts import Direction
from vati.strategies import CapsuleRegistry

REG = Path(__file__).resolve().parents[1] / "strategies" / "registry"
D = Decimal
EV = ("a" * 64,)


# ------------------------------------------------------------------ boundary
def test_boundary_accepts_only_reduce_only_adjustments_on_three_targets():
    ok = LiveAdjustment(LiveTarget.CAPSULE_HEALTH, "FX-TREND-PULLBACK-01", D("0.8"), "DEGRADED", EV, D("40"))
    assert LearningBoundary.check(ok) is ok
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, "x", D("1.2"), None, EV, D("40")))   # widening
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(LiveAdjustment(LiveTarget.REGIME_PROBABILITY, "BULL", D("0.5"), "SHADOW", EV, D("40")))   # only health demotes
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, "x", D("0.5"), "LIMITED_LIVE", EV, D("40")))   # promotion is never an output
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, "x", D("0.5"), None, EV, D("5")))   # too few weighted samples
    with pytest.raises(LearningBoundaryError):
        LearningBoundary.check(LiveAdjustment(LiveTarget.CAPSULE_HEALTH, "x", D("0.5"), None, (), D("40")))   # no evidence
    for tgt in sorted(FORBIDDEN_TARGETS):
        with pytest.raises(LearningBoundaryError):
            LearningBoundary.attempt(tgt)
        with pytest.raises(LearningBoundaryError):
            LearningBoundary.check(LiveAdjustment(tgt, "x", D("0.5"), None, EV, D("40")))   # type: ignore[arg-type]


# -------------------------------------------------------------------- health
def obs(sid, r, env=Environment.LIVE, process_ok=True, cost=D("1"), fit=True, i=0):
    return HealthObservation(sid, env, D(str(r)), process_ok, cost, fit, f"ev-{sid}-{i}")


def test_health_demotes_only_after_sustained_breach_and_never_promotes():
    t = StrategyHealthTracker(certified_expectancy_r={"S": D("0.3")}, sustain=5)
    v = None
    for i in range(30):
        v = t.observe(obs("S", 0.4, i=i))
    assert v.health >= D("0.9") and v.state_recommendation is None and v.weighted_samples == D("30")
    adj = t.live_adjustment("S")
    assert adj is not None and adj.multiplier <= 1 and adj.demote_to is None
    # a run of process breaches with heavy cost drift outside eligible regimes
    recs = []
    for i in range(30, 60):
        recs.append(t.observe(obs("S", -1.0, process_ok=False, cost=D("2.5"), fit=False, i=i)).state_recommendation)
    assert recs[0] is None                          # hysteresis: one bad day does not demote
    assert recs[-1] == "SHADOW"                     # sustained → demotion
    adj = t.live_adjustment("S")
    assert adj.demote_to == "SHADOW" and adj.multiplier < D("0.4")
    # backtest-only evidence weighs less: 30 BACKTEST observations are 9 weighted samples → no live adjustment
    t2 = StrategyHealthTracker()
    for i in range(30):
        t2.observe(obs("B", 0.5, env=Environment.BACKTEST, i=i))
    assert t2.verdict("B").weighted_samples == D("9.0") and t2.live_adjustment("B") is None


def test_health_verdict_reasons_are_explanatory():
    t = StrategyHealthTracker(certified_expectancy_r={"S": D("0.5")}, sustain=1)
    for i in range(10):
        v = t.observe(obs("S", -0.2, cost=D("1.9"), fit=False, i=i))
    assert any("expectancy" in r for r in v.reasons) and "cost drift" in v.reasons and any("eligible regimes" in r for r in v.reasons)


# -------------------------------------------------------------------- broker
def test_broker_learning_ignores_simulated_execution_facts_and_degrades_on_real_ones():
    bl = BrokerLearner()
    for _ in range(50):
        p = bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.BACKTEST, cost_ratio=D("5"), slippage_pips=D("9"), rejected=True, in_event_window=False)
    assert p.state() is BrokerState.CERTIFIED and p._w() == 0 and bl.live_adjustment("mt5-a", "EURUSD", "LONDON") is None
    for _ in range(40):
        p = bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"), rejected=False, in_event_window=False)
    assert p.state() is BrokerState.DEGRADED and p.liquidity_multiplier() == D("0.7")
    adj = bl.live_adjustment("mt5-a", "EURUSD", "LONDON")
    assert adj.target is LiveTarget.BROKER_PROFILE and adj.multiplier == D("0.7")
    for _ in range(10):
        p = bl.observe(broker="mt5-a", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"), rejected=True, in_event_window=False)
    assert p.state() is BrokerState.SUSPENDED and p.liquidity_multiplier() == 0
    ev = BrokerLearner()
    for _ in range(12):
        ev.observe(broker="b", symbol="XAUUSD", session="NY", environment=Environment.LIVE, cost_ratio=D("1.0"), slippage_pips=D("1"), rejected=False, in_event_window=False)
    for _ in range(4):
        q = ev.observe(broker="b", symbol="XAUUSD", session="NY", environment=Environment.LIVE, cost_ratio=D("3.0"), slippage_pips=D("2"), rejected=False, in_event_window=True)
    assert q.state() is BrokerState.EVENT_LIMITED


def test_restart_replays_capsule_health_before_new_decisions(eurusd, tmp_path):
    """A process restart cannot erase a reduce-only health gate or demotion."""
    cfg = fx_cfg(eurusd)
    engine = fx_engine(cfg)
    sid = "FX-TREND-PULLBACK-01"
    assert engine.registry.get(sid).state.value == "DEMO"

    ledger = Ledger(tmp_path / "learning-replay.sqlite")
    for i in range(30):
        artifact_hash = f"{i + 1:064x}"
        ledger.append(make_event(
            EventKind.TRADE_EXPERIENCE_ARTIFACT,
            "test-learning",
            {
                "artifact_hash": artifact_hash,
                "environment": "LIVE",
                "strategy_id": sid,
                "outcome": {"r_multiple": "-1.00"},
                "review": {"process_ok": False},
                "execution": {"tca": {"cost_ratio": "2.5"}},
            },
            event_time_ms=1_000 + i,
            received_time_ms=1_000 + i,
            correlation_id=f"intent-{i}",
        ))

    fresh = LearningHooks(environment=Environment.LIVE, broker="paper")
    report = restore_learning_runtime(
        ledger, fresh, {"EURUSD": engine})

    assert report.health_observations == 30
    assert report.capsule_multipliers >= 1
    assert engine.m.capsule_health[sid] < D("0.55")
    assert engine.registry.get(sid).state.value == "DEGRADED"
    assert fresh.health.verdict(sid).weighted_samples == D("30")


def test_restart_replays_broker_liquidity_cap_from_contextual_tca(eurusd, tmp_path):
    """A restart cannot turn a learned SUSPENDED broker profile back into 1.0."""
    cfg = fx_cfg(eurusd)
    engine = fx_engine(cfg)
    ledger = Ledger(tmp_path / "broker-replay.sqlite")
    for i in range(40):
        ledger.append(make_event(
            EventKind.TCA_RECORD,
            "test-learning",
            {
                "trade_intent_id": f"intent-{i}",
                "cost_ratio": "2.5",
                "slippage": "1.0",
                "learning_environment": "LIVE",
                "broker": "paper",
                "symbol": "EURUSD",
                "session": "LONDON",
                "event_window": "NORMAL",
                "rejected": False,
            },
            event_time_ms=2_000 + i,
            received_time_ms=2_000 + i,
            correlation_id=f"intent-{i}",
        ))

    fresh = LearningHooks(environment=Environment.LIVE, broker="paper")
    report = restore_learning_runtime(
        ledger, fresh, {"EURUSD": engine})

    assert report.tca_observations == 40
    assert report.broker_multipliers >= 1
    assert fresh.broker_liquidity("EURUSD") == D("0")
    assert engine.m.broker_liquidity["EURUSD"] == D("0")


# ------------------------------------------------------------ counterfactual
def test_counterfactual_variants_are_simulated_weight_0_2_and_sealed():
    bars = mk_bars([1.1000, 1.1010, 1.1005, 1.1030, 1.1050, 1.1080, 1.1070], start=0, step=60_000)
    out = run_counterfactuals(episode_id="ep1", bars=bars, entry_idx=2, entry=D("1.1005"), stop=D("1.0985"), target=D("1.1065"), direction=Direction.LONG, qty=D("1"), vppu=D("100000"),
                              cost_per_unit=D("2"), base_pnl=D("598"), structure_stop=D("1.0995"), htf_confirms=False)
    names = {o.variant for o in out}
    assert names == {v.value for v in CounterfactualVariant}
    assert all(o.weight == ENVIRONMENT_WEIGHT[Environment.COUNTERFACTUAL] == D("0.2") and o.label == "SIMULATED_EVIDENCE_NOT_CAUSAL" and len(o.artifact_hash) == 64 for o in out)
    by = {o.variant: o for o in out}
    assert by["SKIP_TRADE"].simulated_pnl == 0 and by["SKIP_TRADE"].delta_pnl == D("-598")
    assert by["HALF_SIZE"].simulated_pnl == by["HALF_SIZE"].base_pnl / 2 or by["HALF_SIZE"].simulated_pnl < by["HALF_SIZE"].base_pnl
    assert by["REQUIRE_HTF_CONFIRMATION"].simulated_pnl == 0
    assert by["ENTRY_ONE_BAR_LATER"].description.startswith("enter at next open")
    # a stop inside the bar is honoured before the target (conservative path)
    short = run_counterfactuals(episode_id="ep2", bars=mk_bars([1.1, 1.1, 1.09, 1.12], start=0, step=60_000), entry_idx=1, entry=D("1.1"), stop=D("1.105"), target=D("1.08"),
                                direction=Direction.SHORT, qty=D("1"), vppu=D("1"), cost_per_unit=D("0"), base_pnl=D("0"))
    assert {o.variant: o for o in short}["HALF_SIZE"].simulated_r == D("-1")


# ---------------------------------------------------------------- missed
def test_missed_opportunity_has_hindsight_guard_and_horizon_window():
    later = mk_bars([1.1000 + 0.0005 * i for i in range(40)], start=1_000_000, step=60_000)
    kw = dict(episode_id="m1", environment=Environment.LIVE, instrument="EURUSD", strategy_id="S", rejection_reason="edge below cost", rejection_layer="META_LABELER", horizon="SCALP",
              direction=Direction.LONG, entry=D("1.1000"), stop=D("1.0980"), later_bars=later, decision_ms=1_000_000)
    with pytest.raises(ValueError):
        evaluate_missed_opportunity(ex_ante_snapshot_hash="", ex_ante_valid=True, **kw)
    ep = evaluate_missed_opportunity(ex_ante_snapshot_hash="h" * 64, ex_ante_valid=True, **kw)
    assert ep.verdict == "COSTLY_NO_TRADE" and ep.later_path_summary["bars"] == 30 and ep.hypothetical_r >= 1 and len(ep.artifact_hash) == 64   # SCALP window = 30 min
    # the same path with an ex-ante invalid setup is a good no-trade: hindsight cannot rewrite the decision
    assert evaluate_missed_opportunity(ex_ante_snapshot_hash="h" * 64, ex_ante_valid=False, **kw).verdict == "GOOD_NO_TRADE"
    # a Risk Authority rejection is correct by definition
    assert evaluate_missed_opportunity(ex_ante_snapshot_hash="h" * 64, ex_ante_valid=True, **{**kw, "rejection_layer": "RISK_AUTHORITY"}).verdict == "GOOD_NO_TRADE"
    # adverse path → GOOD_NO_TRADE; no bars in window → INCONCLUSIVE
    down = mk_bars([1.1000 - 0.0005 * i for i in range(40)], start=1_000_000, step=60_000)
    assert evaluate_missed_opportunity(ex_ante_snapshot_hash="h" * 64, ex_ante_valid=True, **{**kw, "later_bars": down}).verdict == "GOOD_NO_TRADE"
    assert evaluate_missed_opportunity(ex_ante_snapshot_hash="h" * 64, ex_ante_valid=True, **{**kw, "later_bars": []}).verdict == "INCONCLUSIVE"


# -------------------------------------------------------------- priority
def test_research_priority_is_deterministic_and_meta_learns_tool_value():
    eng = ResearchPriorityEngine()
    a = eng.score(task_id="t-a", trigger="LARGE_LOSS", subject="S", question="why?", loss_or_value=D("-300"), recurrence=3, tractability=D("0.5"), evidence_refs=EV)
    b = eng.score(task_id="t-b", trigger="MISSED_OPPORTUNITY", subject="S", question="why not?", loss_or_value=D("100"), recurrence=1, tractability=D("2"), evidence_refs=EV)
    assert a.priority == D("450.00") and b.tractability == 1 and b.priority == D("100.00")
    assert [t.task_id for t in eng.rank([b, a])] == ["t-a", "t-b"]
    assert a.suggested_tools[0] == "ANALOGUE_STUDY"
    before = eng.tool_value["DEEP_RESEARCH"]
    for _ in range(10):
        eng.record_outcome("DEEP_RESEARCH", D("1"), D("5"))
    assert eng.tool_value["DEEP_RESEARCH"] > before and eng.tool_value["DEEP_RESEARCH"] <= D("1.5")
    for _ in range(20):
        eng.record_outcome("DEEP_RESEARCH", D("1"), D("0"))
    assert eng.tool_value["DEEP_RESEARCH"] >= D("0.1")


# ------------------------------------------------------------- evolution
def ep(sid, r, ctx_vol, env=Environment.LIVE, i=0):
    return ExperienceEpisode(f"e{sid}{i}", env, "EURUSD", "paper", "fx", sid, "1.0.0", "SWING", "LONG", "m" * 64, "act", {}, {}, {}, {"r_multiple": str(r)}, {"context": ctx_vol}, 0, 1, ()).sealed()


def test_failure_clustering_and_candidate_proposal_lands_in_research():
    eps = [ep("FX-TREND-PULLBACK-01", -1, "HIGH", i=i) for i in range(12)] + [ep("FX-TREND-PULLBACK-01", -0.5, "NORMAL", i=100 + i) for i in range(3)] + [ep("FX-TREND-PULLBACK-01", 2, "HIGH", i=200)]
    clusters = cluster_failures(eps, context_fn=lambda e: f"vol={e.review['context']}")
    assert clusters[0].context_key == "vol=HIGH" and clusters[0].episodes == 12 and clusters[0].share_of_losses == D("0.80") and clusters[0].mean_r == D("-1.00")
    reg = CapsuleRegistry.load_dir(REG)
    with pytest.raises(ValueError):
        propose_candidate(reg, clusters[1], constraint="HIGH", hypothesis="x")   # too small
    cand, cap = propose_candidate(reg, clusters[0], constraint="HIGH", hypothesis="losses cluster in HIGH vol; forbid it")
    assert cand.state == "RESEARCH" and cand.candidate_strategy_id == "FX-TREND-PULLBACK-02" and cap.state.value == "RESEARCH"
    assert "HIGH" in cap.forbidden_regimes and cap.data["supersedes"] == reg.get("FX-TREND-PULLBACK-01").capsule_hash and cap.data["approval_signature_ref"] is None
    assert reg.get("FX-TREND-PULLBACK-01").state.value == "DEMO"          # the parent is preserved untouched
    assert reg.get("FX-TREND-PULLBACK-02").capsule_hash == cap.capsule_hash


# ---------------------------------------------------------------- cycles
def test_reports_and_episodes_come_from_a_real_backtest_ledger(eurusd, tmp_path):
    cfg = fx_cfg(eurusd)
    bt = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix(), ledger_path=str(tmp_path / "bt.sqlite"))
    res = bt.run(synthetic_bars())
    assert res.trades >= 1
    led = Ledger(tmp_path / "bt.sqlite")
    intent_ids = [e.correlation_id for e in led.iter(EventKind.TRADE_REVIEW)]
    e = episode_from_ledger(led, intent_ids[0], environment=Environment.BACKTEST)
    assert e is not None and e.strategy_id.startswith("FX-") and e.risk["decision"] in ("APPROVED", "REDUCED") and e.review["outcome"] and e.closed_ms is not None
    assert e.weight() == D("0.3") and len(e.artifact_hash) == 64 and len(e.evidence_refs) >= 3
    assert episode_from_ledger(led, "no-such-intent", environment=Environment.BACKTEST) is None
    end = max(ev.event_time_ms for ev in led.iter())
    health = StrategyHealthTracker(sustain=1)
    for i in range(35):
        health.observe(obs("FX-TREND-PULLBACK-01", -1, process_ok=False, cost=D("2.5"), fit=False, i=i))
    brokers = BrokerLearner()
    for _ in range(40):
        brokers.observe(broker="paper", symbol="EURUSD", session="LONDON", environment=Environment.LIVE, cost_ratio=D("1.5"), slippage_pips=D("1"), rejected=False, in_event_window=False)
    m = monthly_report(led, month_end_ms=end, health=health, brokers=brokers)
    assert m.cadence == "MONTHLY" and m.trades_closed == res.trades and m.cycles > 0 and 0 <= m.no_trade_share <= 1
    assert m.demotion_recommendations == {"FX-TREND-PULLBACK-01": "SHADOW"} and m.broker_states == {"paper:EURUSD:LONDON": "DEGRADED"}
    assert "FX-TREND-PULLBACK-01 → SHADOW" in m.what_changed and any(x.startswith("broker paper") for x in m.what_changed)
    assert sum(m.outcomes.values()) == m.trades_closed
    d = daily_report(led, day_end_ms=end)
    w = weekly_report(led, week_end_ms=end)
    assert d.trades_closed <= w.trades_closed <= m.trades_closed and d.cadence == "DAILY" and w.cadence == "WEEKLY"
    assert daily_report(led, day_end_ms=0).cycles == 0


# ---------------------------------------------------------- memory bridge
def test_memory_bridge_refuses_secrets_and_free_text_evidence_and_expires():
    b = HermesMemoryBridge()
    r = b.remember(kind="OPEN_INVESTIGATION", subject="FX-TREND-PULLBACK-01", summary="HIGH-vol loss cluster under review", now_ms=1_000, evidence_hashes=EV)
    assert r.authority == "CONTINUITY_ONLY_NOT_EVIDENCE" and r.namespace == "trading" and len(r.record_hash) == 64
    with pytest.raises(MemoryBridgeError):
        b.remember(kind="BROKER_ANOMALY", subject="mt5-a", summary="login id 123456 password hunter2 rejected", now_ms=1_000)
    with pytest.raises(MemoryBridgeError):
        b.remember(kind="BROKER_ANOMALY", subject="api_key for deriv", summary="rotated", now_ms=1_000)
    with pytest.raises(MemoryBridgeError):
        b.remember(kind="REGIME_NOTE", subject="EURUSD", summary="gold up", now_ms=1_000, evidence_hashes=("I saw it on a forum",))
    with pytest.raises(MemoryBridgeError):
        b.remember(kind="BROKER_TOKENS", subject="x", summary="y", now_ms=1_000)
    assert [x.record_hash for x in b.recall(now_ms=2_000)] == [r.record_hash]
    assert "continuity" not in b.export_prompt_context(now_ms=2_000) and r.evidence_hashes[0][:8] in b.export_prompt_context(now_ms=2_000)
    assert b.recall(now_ms=r.expires_ms) == [] and b.expire(now_ms=r.expires_ms) == 1 and b.records == {}


# ------------------------------------------------------------- curriculum
def test_curriculum_gate_requires_every_stage_up_to_target():
    assert curriculum_gate(set(), "RESEARCH") == (True, "ok")
    assert curriculum_gate({1}, "VALIDATION")[0] and not curriculum_gate(set(), "VALIDATION")[0]
    ok, why = curriculum_gate({1, 2, 3}, "LIMITED_LIVE")
    assert not ok and "[4, 5, 6, 7]" in why
    assert curriculum_gate(set(range(1, 8)), "LIMITED_LIVE")[0] and not curriculum_gate(set(range(1, 8)), "CERTIFIED_LIVE")[0]
    assert curriculum_gate(set(range(1, 9)), "CERTIFIED_LIVE")[0] and not curriculum_gate(set(range(1, 9)), "GOD_MODE")[0]
    assert [s.stage for s in CURRICULUM] == list(range(1, 9))


# ------------------------------------------------- integration with the cycle
def test_cycle_emits_experience_artifacts_but_backtest_evidence_cannot_adjust_live(eurusd, tmp_path):
    from vati.learning import LearningHooks
    cfg = fx_cfg(eurusd)
    hooks = LearningHooks(environment=Environment.BACKTEST)
    bt = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix(), ledger_path=str(tmp_path / "bt.sqlite"), learning=hooks)
    res = bt.run(synthetic_bars())
    led = Ledger(tmp_path / "bt.sqlite")
    assert res.trades >= 1 and led.count(EventKind.TRADE_EXPERIENCE_ARTIFACT) == res.trades == len(hooks.episodes)
    assert all(e.environment is Environment.BACKTEST and e.review["outcome"] for e in hooks.episodes)
    assert hooks.adjustments == [] and hooks.demotions == [] and led.count(EventKind.CAPSULE_STATE) == 0   # 0.3 weight × few trades < 30 weighted samples
    assert sum((hooks.health.verdict(sid).weighted_samples for sid in hooks.health._obs), D(0)) == D("0.3") * res.trades
    assert res.ledger_ok and res.decision_replay_identical
    # broker execution facts from a backtest carry zero weight: no learned liquidity cap
    assert all(p._w() == 0 for p in hooks.brokers.profiles.values()) and hooks.broker_liquidity("EURUSD") == 1
    # a fresh backtest without hooks writes no artifacts and the two ledgers agree on decisions
    plain = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix()).run(synthetic_bars())
    assert plain.summary()["metrics"] == res.summary()["metrics"]


def test_cycle_applies_boundary_checked_demotion_and_capsule_stops_trading(eurusd, tmp_path):
    from vati.learning import LearningHooks
    cfg = fx_cfg(eurusd)
    hooks = LearningHooks(environment=Environment.LIVE, health=StrategyHealthTracker(sustain=1))
    # 35 weighted live observations of process breaches: the next close crosses the sustain gate
    for i in range(35):
        for sid in ("FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"):
            hooks.health.observe(obs(sid, -1.0, process_ok=False, cost=D("2.5"), fit=False, i=i))
    engine = fx_engine(cfg)
    bt = BacktestEngine(cfg=cfg, engine=engine, cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix(), ledger_path=str(tmp_path / "bt.sqlite"), learning=hooks)
    res = bt.run(synthetic_bars())
    led = Ledger(tmp_path / "bt.sqlite")
    # every capsule that closes a trade is demoted on that first close; a demoted capsule never trades again
    assert 1 <= res.trades <= 2 and len(hooks.demotions) == res.trades == led.count(EventKind.CAPSULE_STATE), res.summary()
    assert len({sid for sid, _ in hooks.demotions}) == res.trades and all(to == "DEGRADED" for _, to in hooks.demotions)
    evs = list(led.iter(EventKind.CAPSULE_STATE))
    for ev in evs:
        sid = ev.payload["strategy_id"]
        assert ev.payload["from"] == "DEMO" and ev.payload["to"] == "DEGRADED" and ev.payload["authority"] == "AUTOMATIC_DEMOTION_ONLY"
        assert ev.payload["capsule"]["capsule_hash"] == ev.payload["capsule_hash"]
        assert engine.registry.get(sid).state.value == "DEGRADED" and engine.registry.get(sid).data["supersedes"] == ev.payload["supersedes"]
        assert engine.m.capsule_health[sid] < D("0.55")
        assert any("not active" in r for c in led.iter(EventKind.OPPORTUNITY_ASSESSMENT) if c.event_time_ms > ev.event_time_ms for cand in c.payload["candidates"] if cand["strategy_id"] == sid for r in cand["reasons"])
    assert all(a.multiplier <= 1 and a.demote_to in (None, "DEGRADED", "SHADOW") for a in hooks.adjustments)
    last = max(ev.event_time_ms for ev in evs)
    later = [c for c in res.cycles if c.bar_end_ms > last]
    assert later and all(c.decision in ("NO_TRADE", "WAIT") for c in later)
    assert res.ledger_ok and res.decision_replay_identical


def test_meta_labeler_broker_liquidity_only_reduces():
    from test_strategies_arbiter import state_for
    from vati.arbiter import MetaLabel, MetaLabeler
    from vati.strategies import FxTrendPullback, StrategyContext
    from test_intelligence import pullback_fixture
    st = state_for(pullback_fixture())
    sig = FxTrendPullback(strategy_id="FX-TREND-PULLBACK-01").evaluate(st, StrategyContext(round_trip_cost_pct=D("0.0003")))
    assert sig is not None
    base = MetaLabeler().score(st, sig, D("5"))
    capped = MetaLabeler(broker_liquidity={sig.symbol: D("0.7")}).score(st, sig, D("5"))
    assert capped.liquidity_multiplier == D("0.7") <= base.liquidity_multiplier and any("learned broker liquidity" in r for r in capped.reasons)
    assert MetaLabeler(broker_liquidity={sig.symbol: D("0")}).score(st, sig, D("5")).label is MetaLabel.SKIP
    widened = MetaLabeler(broker_liquidity={sig.symbol: D("3")}).score(st, sig, D("5"))
    assert widened.liquidity_multiplier == base.liquidity_multiplier      # > 1 is clamped, never widens


def test_review_outcomes_include_broker_failure_and_unknown():
    from vati.execution.review import Outcome, review_trade
    kw = dict(trade_intent_id="t", strategy_id="S", entry=D("1.1"), exit_price=D("1.09"), stop=D("1.09"), direction_long=True, pnl=D("-100"), thesis_correct=False, process_ok=True)
    assert review_trade(**kw, broker_ok=False).outcome is Outcome.BROKER_FAILURE
    u = review_trade(**kw, exit_known=False)
    assert u.outcome is Outcome.UNKNOWN and u.polarity == "ANTI_PATTERN"
    assert review_trade(**kw).outcome is Outcome.GOOD_LOSS
