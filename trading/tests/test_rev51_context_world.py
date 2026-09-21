"""TRD-REV51-092 world model, 093 context compiler, 097 analogue retrieval.

The three together are what a model is allowed to know. Everything here is
about determinism and about failing closed rather than thin.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.cognition.analogues import (
    FEATURE_WEIGHTS,
    MAX_ANALOGUE_DISTANCE,
    MIN_COVERAGE_FOR_CONFIDENCE,
    AnalogueIndex,
    Episode,
    EpisodeFeatures,
    FeatureError,
)
from vati.cognition.context import (
    OPTIONAL_DROP_ORDER,
    REQUIRED_SECTIONS,
    CompiledContext,
    ContextCompiler,
    ContextContaminated,
    ContextIncomplete,
    compile_decision_context,
)
from vati.cognition.world_model import (
    RECENT_DECISIONS_PER_SYMBOL,
    CognitionStore,
    StoreError,
    TradingWorldModel,
)
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger

D = Decimal


# ------------------------------------------------------------------ 092 world
def _ledger_with_a_rejection() -> Ledger:
    led = Ledger(":memory:")
    led.append(make_event(EventKind.TRADE_INTENT, "p", {"symbol": "EURUSD", "strategy_id": "s1"},
                          event_time_ms=1, received_time_ms=1, correlation_id="t1"))
    led.append(make_event(EventKind.RISK_DECISION, "p",
                          {"decision": {"decision": "REJECTED", "reason_code": "HEAT_CAP"}},
                          event_time_ms=2, received_time_ms=2, correlation_id="t1"))
    return led


def test_rebuilding_from_the_ledger_matches_the_incremental_fold():
    """The whole of INV-REPLAY-001 for this component."""
    led = _ledger_with_a_rejection()
    rebuilt = TradingWorldModel.from_ledger(led)
    incremental = TradingWorldModel()
    for ev in led.iter():
        incremental.apply(ev)
    assert rebuilt.digest() == incremental.digest()


def test_the_projection_has_no_clock_of_its_own():
    """Folding the same prefix twice, at different wall times, is identical."""
    led = _ledger_with_a_rejection()
    assert TradingWorldModel.from_ledger(led).digest() == TradingWorldModel.from_ledger(led).digest()


def test_a_decision_lands_on_both_the_instrument_and_the_strategy():
    w = TradingWorldModel.from_ledger(_ledger_with_a_rejection())
    assert w.instruments["EURUSD"].last_decision == "REJECTED"
    assert w.instruments["EURUSD"].last_reason_code == "HEAT_CAP"
    assert w.strategies["s1"].rejected == 1
    assert w.strategies["s1"].rejection_rate == 1.0


def test_closing_a_position_clears_the_open_intent():
    led = _ledger_with_a_rejection()
    led.append(make_event(EventKind.POSITION_CHANGE, "p", {"state": "CLOSED"},
                          event_time_ms=3, received_time_ms=3, correlation_id="t1"))
    w = TradingWorldModel.from_ledger(led)
    assert w.open_intents == {}
    assert w.instruments["EURUSD"].open_intents == set()


def test_the_decision_history_per_symbol_is_bounded():
    """An unbounded projection would make context size a function of uptime."""
    led = Ledger(":memory:")
    led.append(make_event(EventKind.TRADE_INTENT, "p", {"symbol": "X", "strategy_id": "s"},
                          event_time_ms=0, received_time_ms=0, correlation_id="t"))
    for i in range(RECENT_DECISIONS_PER_SYMBOL * 3):
        led.append(make_event(EventKind.RISK_DECISION, "p",
                              {"decision": {"decision": "APPROVED", "reason_code": "OK"}},
                              event_time_ms=i, received_time_ms=i, correlation_id="t"))
    w = TradingWorldModel.from_ledger(led)
    assert len(w.instruments["X"].decisions) == RECENT_DECISIONS_PER_SYMBOL


def test_kill_switch_triggers_are_set_and_cleared():
    led = Ledger(":memory:")
    led.append(make_event(EventKind.KILL_SWITCH, "p", {"trigger": "STALE_DATA", "active": True},
                          event_time_ms=1, received_time_ms=1))
    led.append(make_event(EventKind.KILL_SWITCH, "p", {"trigger": "STALE_DATA", "active": False},
                          event_time_ms=2, received_time_ms=2))
    assert TradingWorldModel.from_ledger(led).kill_switch_triggers == set()


def test_degrading_strategies_is_descriptive_and_needs_a_sample():
    w = TradingWorldModel()
    led = Ledger(":memory:")
    led.append(make_event(EventKind.TRADE_INTENT, "p", {"symbol": "Y", "strategy_id": "bad"},
                          event_time_ms=0, received_time_ms=0, correlation_id="c"))
    for i in range(3):
        led.append(make_event(EventKind.RISK_DECISION, "p",
                              {"decision": {"decision": "REJECTED", "reason_code": "R"}},
                              event_time_ms=i, received_time_ms=i, correlation_id="c"))
    w = TradingWorldModel.from_ledger(led)
    assert w.degrading_strategies() == []          # three decisions is not a record
    assert w.degrading_strategies(min_decisions=3) == ["bad"]


# ------------------------------------------------------------------ 092 store
def test_the_store_refuses_to_rewrite_an_artifact():
    s = CognitionStore()
    s.put(artifact_key="a", kind="assessment", context_hash="c", payload={"v": 1}, created_ms=1)
    s.put(artifact_key="a", kind="assessment", context_hash="c", payload={"v": 1}, created_ms=1)
    with pytest.raises(StoreError):
        s.put(artifact_key="a", kind="assessment", context_hash="c", payload={"v": 2}, created_ms=2)


def test_artifacts_come_back_for_their_context_in_order():
    s = CognitionStore()
    s.put(artifact_key="b", kind="k", context_hash="ctx", payload={"n": 2}, created_ms=20)
    s.put(artifact_key="a", kind="k", context_hash="ctx", payload={"n": 1}, created_ms=10)
    assert [a["n"] for a in s.for_context("ctx")] == [1, 2]
    assert s.count("k") == 2


# ---------------------------------------------------------------- 093 context
def _compiler_with_required() -> ContextCompiler:
    c = ContextCompiler()
    for name in REQUIRED_SECTIONS:
        c.register(name, f"{name}/1.0", lambda n=name: {"n": n})
    return c


def test_a_compiled_context_is_sealed_and_ordered():
    ctx = _compiler_with_required().compile(now_ms=5)
    assert ctx.seal_ok()
    assert [s.name for s in ctx.sections] == sorted(REQUIRED_SECTIONS)


def test_the_same_inputs_compile_to_the_same_hash():
    a = _compiler_with_required().compile(now_ms=5)
    b = _compiler_with_required().compile(now_ms=5)
    assert a.context_hash == b.context_hash


def test_a_section_version_change_changes_the_context_hash():
    """Contexts compiled either side of a component change are visibly not
    comparable, which is the honest outcome."""
    a = _compiler_with_required().compile(now_ms=5)
    c = _compiler_with_required()
    c.register("world", "world/2.0", lambda: {"n": "world"})
    assert c.compile(now_ms=5).context_hash != a.context_hash


def test_a_missing_required_section_fails_closed():
    c = ContextCompiler()
    c.register("decision_point", "v", lambda: {})
    with pytest.raises(ContextIncomplete) as e:
        c.compile(now_ms=1)
    assert "risk_state" in str(e.value)


def test_a_required_section_that_raises_fails_closed():
    c = _compiler_with_required()
    c.register("risk_state", "v", lambda: (_ for _ in ()).throw(RuntimeError("store down")))
    with pytest.raises(ContextIncomplete):
        c.compile(now_ms=1)


def test_an_optional_section_that_raises_is_recorded_as_dropped():
    c = _compiler_with_required()
    c.register("calendar", "v", lambda: (_ for _ in ()).throw(RuntimeError("feed down")))
    ctx = c.compile(now_ms=1)
    assert "calendar" in ctx.dropped_sections
    assert not ctx.is_complete


def test_the_budget_drops_optional_sections_in_the_declared_order_and_says_so():
    c = _compiler_with_required()
    big = {"blob": "x" * 5_000}
    for name in OPTIONAL_DROP_ORDER:
        c.register(name, "v", lambda b=big: dict(b))
    ctx = ContextCompiler(budget_bytes=12_000)
    for name in REQUIRED_SECTIONS:
        ctx.register(name, "v", lambda n=name: {"n": n})
    for name in OPTIONAL_DROP_ORDER:
        ctx.register(name, "v", lambda b=big: dict(b))
    out = ctx.compile(now_ms=1)
    assert out.size_bytes <= 12_000
    assert out.dropped_sections           # the shrink is inside the sealed record
    assert set(out.dropped_sections) <= set(OPTIONAL_DROP_ORDER)


def test_required_sections_that_cannot_fit_raise_rather_than_truncate():
    c = ContextCompiler(budget_bytes=100)
    for name in REQUIRED_SECTIONS:
        c.register(name, "v", lambda: {"blob": "x" * 5_000})
    with pytest.raises(ContextIncomplete) as e:
        c.compile(now_ms=1)
    assert "budget" in str(e.value)


@pytest.mark.parametrize("key", ["password", "api_key", "AUTHORIZATION", "private_key", "session_id"])
def test_a_credential_reaching_the_compiler_is_refused_not_masked(key):
    c = _compiler_with_required()
    c.register("calendar", "v", lambda: {"nested": {key: "value"}})
    with pytest.raises(ContextContaminated) as e:
        c.compile(now_ms=1)
    assert key in str(e.value)


def test_the_standard_wiring_produces_the_expected_sections():
    ctx = compile_decision_context(decision_point={"symbol": "EURUSD"},
                                   risk_state={"heat": "0.02"},
                                   world=TradingWorldModel(), now_ms=9)
    assert ctx.seal_ok()
    assert set(REQUIRED_SECTIONS) <= set(ctx.versions())
    assert ctx.section("world").payload["world_digest"]


# -------------------------------------------------------------- 097 analogues
def _feat(**over) -> EpisodeFeatures:
    base = {k: D("0.5") for k in FEATURE_WEIGHTS}
    base.update({k: D(str(v)) for k, v in over.items()})
    return EpisodeFeatures(**base)


def test_feature_weights_sum_to_one_so_distance_is_a_fraction():
    assert sum(FEATURE_WEIGHTS.values()) == D("1")


def test_a_feature_outside_the_unit_interval_is_refused():
    with pytest.raises(FeatureError):
        _feat(regime=1.5)


def test_retrieval_is_ordered_by_distance_then_by_id():
    idx = AnalogueIndex([
        Episode("b", "EURUSD", 10, _feat(regime=0.5)),
        Episode("a", "EURUSD", 10, _feat(regime=0.5)),
        Episode("c", "EURUSD", 10, _feat(regime=0.6)),
    ])
    got = [a.episode.episode_id for a in idx.retrieve(_feat(regime=0.5), k=3).analogues]
    assert got == ["a", "b", "c"]


def test_the_same_index_and_query_retrieve_identically():
    idx = AnalogueIndex([Episode(f"e{i}", "S", i, _feat(regime=i / 25)) for i in range(20)])
    q = _feat(regime=0.3)
    assert idx.retrieve(q, k=5).digest == idx.retrieve(q, k=5).digest


def test_nothing_beyond_the_distance_ceiling_is_returned_however_thin_the_field():
    """A retrieval that returns its least-bad match is how a thin sample
    becomes a confident answer."""
    idx = AnalogueIndex([Episode("far", "S", 1, _feat(regime=0, event_proximity=0,
                                                      volatility_percentile=0, trend_strength=0,
                                                      spread_percentile=0, liquidity_percentile=0,
                                                      session_bucket=0))])
    res = idx.retrieve(_feat(regime=1, event_proximity=1, volatility_percentile=1,
                             trend_strength=1, spread_percentile=1, liquidity_percentile=1,
                             session_bucket=1), k=5)
    assert res.is_absent and res.reason_codes() == ("ANALOGUE_ABSENT",)


def test_thin_coverage_is_reported_even_when_matches_are_close():
    idx = AnalogueIndex([Episode(f"e{i}", "S", i, _feat()) for i in range(3)])
    res = idx.retrieve(_feat(), k=3)
    assert res.analogues and res.is_thin
    assert res.reason_codes() == ("EVIDENCE_THIN",)


def test_sufficient_coverage_cites_nothing():
    idx = AnalogueIndex([Episode(f"e{i}", "S", i, _feat())
                         for i in range(MIN_COVERAGE_FOR_CONFIDENCE + 1)])
    assert idx.retrieve(_feat(), k=5).reason_codes() == ()


def test_before_ms_keeps_a_caller_out_of_its_own_future():
    idx = AnalogueIndex([Episode("past", "S", 10, _feat()), Episode("future", "S", 100, _feat())])
    got = [a.episode.episode_id for a in idx.retrieve(_feat(), k=5, before_ms=50).analogues]
    assert got == ["past"]


def test_scope_filters_narrow_coverage_not_just_results():
    idx = AnalogueIndex([Episode("a", "EURUSD", 1, _feat()), Episode("b", "GBPUSD", 1, _feat())])
    res = idx.retrieve(_feat(), k=5, symbol="EURUSD")
    assert res.coverage == 1


def test_mean_outcome_is_reported_when_episodes_carry_one():
    idx = AnalogueIndex([
        Episode("a", "S", 1, _feat(), outcome_r=D("2")),
        Episode("b", "S", 2, _feat(), outcome_r=D("-1")),
    ])
    assert idx.retrieve(_feat(), k=5).mean_outcome_r == D("0.5")


def test_reindexing_an_episode_with_different_features_is_refused():
    idx = AnalogueIndex([Episode("a", "S", 1, _feat(regime=0.1))])
    with pytest.raises(FeatureError):
        idx.add(Episode("a", "S", 1, _feat(regime=0.9)))
