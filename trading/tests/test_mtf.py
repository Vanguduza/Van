"""TRD-ENH-010/011: multi-timeframe state, as-of discipline, no fusion."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.intelligence.mtf import (
    TIMEFRAME_ORDER,
    MtfError,
    MultiTimeframeMarketState,
    TimeframeContract,
    build_multi_timeframe_state,
    closed_bars_at,
)
from vati.market_data.bars import Bar
from vati.app.instrument_evaluator import InstrumentEvaluator, InstrumentEvaluatorConfig


def _bars(symbol: str, step_ms: int, n: int, start: int = 0) -> list[Bar]:
    out = []
    for i in range(n):
        s = start + i * step_ms
        px = Decimal("1.1000") + Decimal(i) / Decimal(10000)
        out.append(Bar(symbol, s, s + step_ms, px, px + Decimal("0.001"),
                       px - Decimal("0.001"), px, Decimal("10"), 5, Decimal("0.0001")))
    return out


class _FakeState:
    """Stands in for MarketState: only the hash matters to assembly."""

    def __init__(self, timeframe: str, bars):
        self.timeframe = timeframe
        self.state_hash = f"{timeframe}:{len(bars)}:{bars[-1].end_ms}"


def _builder(*, bars, timeframe, now_ms):
    return _FakeState(timeframe, bars)


def _bars_for(step_by_tf, n=200):
    store = {tf: _bars("EURUSD", step, n) for tf, step in step_by_tf.items()}
    return lambda tf: store.get(tf, [])


# --- contract -------------------------------------------------------------

def test_contract_required_timeframes_are_coarse_to_fine():
    c = TimeframeContract.from_capsule(
        {"timeframe_contract": {"execution": "M5", "structural": "H4", "setup": "M15", "regime": "H1"}})
    assert c.required_timeframes == ("H4", "H1", "M15", "M5")


def test_contract_deduplicates_shared_timeframes():
    c = TimeframeContract.from_capsule({"timeframe_contract": {"setup": "M15", "execution": "M15"}})
    assert c.required_timeframes == ("M15",)


def test_single_timeframe_capsule_uses_primary():
    c = TimeframeContract.from_capsule({"timeframe_contract": {"primary": "D1"}})
    assert c.required_timeframes == ("D1",)


def test_capsule_without_contract_returns_none():
    assert TimeframeContract.from_capsule({"strategy_id": "X"}) is None


def test_unknown_role_is_refused():
    with pytest.raises(MtfError, match="role"):
        TimeframeContract.from_capsule({"timeframe_contract": {"vibes": "H1"}})


def test_unknown_timeframe_is_refused():
    with pytest.raises(MtfError, match="timeframe"):
        TimeframeContract.from_capsule({"timeframe_contract": {"setup": "M7"}})


# --- as-of discipline -----------------------------------------------------

def test_closed_bars_excludes_a_still_forming_bar():
    bars = _bars("EURUSD", 60_000, 10)
    assert closed_bars_at(bars, bars[4].end_ms)[-1].end_ms == bars[4].end_ms
    assert len(closed_bars_at(bars, bars[4].end_ms)) == 5


def test_no_look_ahead_from_a_higher_timeframe():
    """An H4 bar that has not closed must not enter an M5-time decision."""
    m5 = _bars("EURUSD", 300_000, 200)
    h4 = _bars("EURUSD", 14_400_000, 200)
    as_of = m5[50].end_ms
    mtf = build_multi_timeframe_state(
        symbol="EURUSD", as_of_ms=as_of, required_timeframes=("H4", "M5"),
        bars_for=lambda tf: {"M5": m5, "H4": h4}[tf], state_builder=_builder)
    for tf, c in mtf.constituent_states.items():
        assert c.as_of_ms <= as_of, tf


def test_a_timeframe_without_enough_closed_history_is_missing_not_short():
    m5 = _bars("EURUSD", 300_000, 200)
    h4 = _bars("EURUSD", 14_400_000, 200)
    mtf = build_multi_timeframe_state(
        symbol="EURUSD", as_of_ms=m5[10].end_ms, required_timeframes=("H4", "M5"),
        bars_for=lambda tf: {"M5": m5, "H4": h4}[tf], state_builder=_builder)
    assert "H4" in mtf.missing_timeframes
    assert not mtf.complete


# --- identity -------------------------------------------------------------

def test_mtf_hash_covers_every_constituent():
    bf = _bars_for({"H4": 14_400_000, "H1": 3_600_000, "M15": 900_000, "M5": 300_000})
    as_of = 14_400_000 * 190
    a = build_multi_timeframe_state(symbol="EURUSD", as_of_ms=as_of,
                                    required_timeframes=("H4", "H1", "M15", "M5"),
                                    bars_for=bf, state_builder=_builder)
    b = build_multi_timeframe_state(symbol="EURUSD", as_of_ms=as_of,
                                    required_timeframes=("H4", "H1", "M15"),
                                    bars_for=bf, state_builder=_builder)
    assert a.mtf_state_hash and a.mtf_state_hash != b.mtf_state_hash


def test_mtf_hash_is_order_independent_in_input_but_deterministic():
    bf = _bars_for({"H1": 3_600_000, "M5": 300_000})
    as_of = 3_600_000 * 190
    a = build_multi_timeframe_state(symbol="EURUSD", as_of_ms=as_of, required_timeframes=("H1", "M5"),
                                    bars_for=bf, state_builder=_builder)
    b = build_multi_timeframe_state(symbol="EURUSD", as_of_ms=as_of, required_timeframes=("M5", "H1"),
                                    bars_for=bf, state_builder=_builder)
    assert a.mtf_state_hash == b.mtf_state_hash


def test_role_lookup_returns_the_right_constituent():
    bf = _bars_for({"H4": 14_400_000, "M5": 300_000})
    c = TimeframeContract.from_capsule({"timeframe_contract": {"structural": "H4", "execution": "M5"}})
    mtf = build_multi_timeframe_state(symbol="EURUSD", as_of_ms=14_400_000 * 190,
                                      required_timeframes=c.required_timeframes,
                                      bars_for=bf, state_builder=_builder)
    assert mtf.for_role(c, "structural").timeframe == "H4"
    assert mtf.for_role(c, "execution").timeframe == "M5"
    assert mtf.for_role(c, "setup") is None


def test_unknown_timeframe_in_assembly_is_refused():
    with pytest.raises(MtfError):
        build_multi_timeframe_state(symbol="EURUSD", as_of_ms=1, required_timeframes=("M7",),
                                    bars_for=lambda tf: [], state_builder=_builder)


def test_lake_timeframes_and_mtf_order_agree():
    """The MTF layer must not invent a timeframe the lake cannot store."""
    from vati.market_data.feeds.lake import TIMEFRAMES_MS
    assert set(TIMEFRAME_ORDER) == set(TIMEFRAMES_MS)


def test_instrument_evaluator_abstains_when_required_mtf_is_incomplete():
    class _Engine:
        def assess_candidates(self, *args, **kwargs):
            raise AssertionError("strategy engine must not run on incomplete MTF")

    incomplete = MultiTimeframeMarketState(
        symbol="EURUSD", as_of_ms=1_000, constituent_states={},
        required_timeframes=("H4", "H1", "M15", "M5"),
        missing_timeframes=("H4",),
    ).sealed()
    evaluator = InstrumentEvaluator(
        InstrumentEvaluatorConfig(
            symbol="EURUSD", base="EUR", quote="USD", venue="deriv",
            account_alias="a", timeframe="M5"),
        engine=_Engine(),
        state_fn=lambda bars, now_ms: (_ for _ in ()).throw(
            AssertionError("single-timeframe fallback must not run")),
        ctx_fn=lambda state: None,
        mtf_state_fn=lambda now_ms: incomplete,
    )
    assert evaluator.evaluate([object()], now_ms=1_000) == ()
    assert evaluator.last_mtf_state.missing_timeframes == ("H4",)
