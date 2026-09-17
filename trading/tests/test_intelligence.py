from __future__ import annotations

from decimal import Decimal

from vati.intelligence import DEFAULT_EVENT_MATRIX, EventMatrix, EventWindowState, RegimeEngine, Tier1Event, TransitionPhase, TrendRegime, VolRegime, build_market_state, compute_features
from vati.market_data import FX_CALENDAR, Bar
from vati.risk.contracts import MarketIntegrityState


def mk_bars(closes, symbol="EURUSD", start=1_757_980_800_000, step=3_600_000, spread=Decimal("0.00008")):
    out = []
    for i, c in enumerate(closes):
        c = Decimal(str(c))
        h, l = c + Decimal("0.0005"), c - Decimal("0.0005")
        out.append(Bar(symbol, start + i * step, start + (i + 1) * step, c, h, l, c, Decimal("100"), 10, spread))
    return out


def trending(n=120, start=1.10, drift=0.0006):
    return [start + drift * i for i in range(n)]


def noisy_trend(n=120, start=1.10, drift=0.0006, amp=0.0018):
    """Uptrend with deterministic sawtooth noise so realised vol is realistic."""
    return [start + drift * i + amp * ((i % 6) - 2.5) / 2.5 for i in range(n)]


def pullback_fixture(bars=5, step=0.0015):
    closes = noisy_trend()
    for _ in range(bars):
        closes.append(closes[-1] - step)
    return closes


def ranging(n=120, start=1.10):
    return [start + (0.0004 if i % 2 else -0.0004) for i in range(n)]


def test_features_complete_and_deterministic():
    bars = mk_bars(trending())
    f1, f2 = compute_features(bars), compute_features(bars)
    assert f1 == f2 and f1.complete and f1.trend_slope is not None and f1.trend_slope > 0
    assert compute_features(mk_bars(trending(30))).complete is False


def test_regime_engine_trend_with_hysteresis():
    eng = RegimeEngine()
    state = None
    for i in range(60, 121):
        state = eng.update(compute_features(mk_bars(trending(i))))
    assert state.trend is TrendRegime.BULL and state.bars_in_trend > 5
    # flatten slowly: trend should persist until slope < exit threshold, then RANGE
    closes = trending(120)
    for k in range(1, 200):
        closes.append(closes[-1])
        state = eng.update(compute_features(mk_bars(closes)))
    assert state.trend is TrendRegime.RANGE
    assert state.risk_multiplier() <= Decimal(1)


def test_regime_engine_detects_break_and_recovers():
    eng = RegimeEngine(cusum_h=Decimal("3"), transition_bars=5)
    closes = trending(120, drift=0.0001)
    for i in range(60, 121):
        eng.update(compute_features(mk_bars(closes[:i])))
    # shock: a 3% gap up then continue
    closes.append(closes[-1] * 1.03)
    st = eng.update(compute_features(mk_bars(closes)))
    assert st.phase in (TransitionPhase.CAUTION, TransitionPhase.TRANSITION)
    assert st.risk_multiplier() <= Decimal("0.75")
    for _ in range(12):
        closes.append(closes[-1] * 1.0001)
        st = eng.update(compute_features(mk_bars(closes)))
    assert st.phase in (TransitionPhase.NORMAL, TransitionPhase.NEW_REGIME)


def test_vol_regime_extreme_caps_multiplier():
    eng = RegimeEngine()
    closes = ranging(120)
    for i in range(60, 121):
        st = eng.update(compute_features(mk_bars(closes[:i])))
    closes += [closes[-1] * (1.05 if i % 2 else 0.95) for i in range(25)]
    st = eng.update(compute_features(mk_bars(closes)))
    assert st.vol in (VolRegime.HIGH, VolRegime.EXTREME)
    assert st.risk_multiplier() <= Decimal("0.60")


def test_event_matrix_windows_and_unverified_fail_closed():
    m = EventMatrix()
    rel = 10_000_000
    m.add(Tier1Event("NFP-2026-10", "Nonfarm Payrolls", rel, frozenset({"USD"}), verified_sources=2))
    assert m.state_at(rel - 4 * 60_000, "EUR", "USD")[0] is EventWindowState.PRE_BLACKOUT
    assert m.state_at(rel + 10 * 60_000, "EUR", "USD")[0] is EventWindowState.POST_BLACKOUT
    assert m.state_at(rel + 30 * 60_000, "EUR", "USD")[0] is EventWindowState.QUIET
    assert m.state_at(rel + 2 * 3_600_000, "EUR", "USD")[0] is EventWindowState.DRIFT
    assert m.state_at(rel + 5 * 3_600_000, "EUR", "USD")[0] is EventWindowState.NONE
    assert m.state_at(rel + 30 * 60_000, "EUR", "GBP")[0] is EventWindowState.NONE  # not affected
    assert m.minutes_to_next(rel - 90 * 60_000, "XAU", "USD") == 90
    single = EventMatrix([Tier1Event("CPI", "CPI", rel, frozenset({"USD"}), verified_sources=1)])
    assert single.state_at(rel - 4 * 60_000, "EUR", "USD")[0] is EventWindowState.PRE_BLACKOUT


def test_market_state_hash_deterministic():
    bars = mk_bars(trending())
    kw = dict(symbol="EURUSD", base="EUR", quote="USD", bars=bars, calendar=FX_CALENDAR, events=DEFAULT_EVENT_MATRIX, integrity=MarketIntegrityState.NORMAL,
              now_ms=bars[-1].end_ms, last_quote_ms=bars[-1].end_ms - 200, activation_id="vtil-act-test")
    a = build_market_state(regime_engine=RegimeEngine(), **kw)
    b = build_market_state(regime_engine=RegimeEngine(), **kw)
    assert a.state_hash == b.state_hash and a.quote_age_ms == 200 and a.session.value in ("LONDON", "LONDON_NY_OVERLAP", "NEW_YORK", "ASIA", "ROLLOVER", "CLOSED")
