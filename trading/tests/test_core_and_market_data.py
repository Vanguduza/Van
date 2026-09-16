from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal

import pytest

from vati.core import Ledger, LedgerError, EventKind, canonical_hash, make_event
from vati.market_data import FX_CALENDAR, Bar, BarAggregator, FeedSample, FxCostModel, IntegrityMonitor, MarketIntegrityState, Session, SpreadCurve, Tick
from vati.market_data.calendars import zse_calendar
from vati.observability import Metrics


def ev(kind=EventKind.MARKET_TICK, payload=None, corr="c1", t=1000):
    return make_event(kind, "test", payload or {"x": 1}, event_time_ms=t, received_time_ms=t + 1, correlation_id=corr)


def test_canonical_hash_is_order_independent_and_decimal_safe():
    assert canonical_hash({"a": Decimal("1.10"), "b": [1, 2]}) == canonical_hash({"b": [1, 2], "a": Decimal("1.10")})
    assert canonical_hash({"a": Decimal("1.10")}) != canonical_hash({"a": Decimal("1.1")})  # exactness preserved


def test_ledger_chain_and_tamper_detection(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    for i in range(5):
        led.append(ev(t=i))
    ok, n = led.verify_chain()
    assert ok and n == 5 and led.count() == 5
    led._conn.execute("UPDATE events SET payload_json = '{\"x\":2}' WHERE seq = 3")
    ok, n = led.verify_chain()
    assert not ok and n == 2
    with pytest.raises(LedgerError):
        led.append(make_event(EventKind.MARKET_TICK, "t", {"x": 1}, event_time_ms=1, received_time_ms=1).__class__(**{**ev().__dict__, "hash": "bad"}))


def test_ledger_replay_detects_divergence(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    led.append(ev(EventKind.RISK_DECISION, {"inputs": {"n": 1}, "decision": {"decision_hash": canonical_hash({"n": 1})}}, "a"))
    led.append(ev(EventKind.RISK_DECISION, {"inputs": {"n": 2}, "decision": {"decision_hash": "deadbeef"}}, "b"))
    rep = led.replay_decisions(lambda inputs: {"decision_hash": canonical_hash(inputs)})
    assert rep.checked == 2 and rep.identical == 1 and not rep.ok and rep.divergent[0]["correlation_id"] == "b"
    assert led.export_jsonl(tmp_path / "out.jsonl") == 2


def test_fx_calendar_sessions_and_weekend():
    assert FX_CALENDAR.session_at(datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)) is Session.LONDON
    assert FX_CALENDAR.session_at(datetime(2026, 9, 16, 13, 30, tzinfo=timezone.utc)) is Session.LONDON_NY_OVERLAP
    assert FX_CALENDAR.session_at(datetime(2026, 9, 16, 2, 0, tzinfo=timezone.utc)) is Session.ASIA
    assert FX_CALENDAR.session_at(datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc)) is Session.ROLLOVER
    assert FX_CALENDAR.session_at(datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)) is Session.CLOSED  # Saturday
    assert FX_CALENDAR.session_at(datetime(2026, 9, 18, 22, 30, tzinfo=timezone.utc)) is Session.CLOSED  # Friday after close
    assert FX_CALENDAR.session_at(datetime(2026, 9, 20, 22, 30, tzinfo=timezone.utc)) is Session.ASIA    # Sunday after open
    assert FX_CALENDAR.holds_over_weekend(datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc), datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        FX_CALENDAR.session_at(datetime(2026, 9, 16, 8, 0))


def test_zse_calendar_fails_closed_until_verified():
    unverified = zse_calendar(None, None, verified=False)
    ts = datetime(2026, 9, 16, 9, 0, tzinfo=timezone.utc)
    assert unverified.session_at(ts) is Session.UNVERIFIED and not unverified.is_open(ts)
    verified = zse_calendar(time(8, 0), time(13, 0), verified=True)
    assert verified.is_open(ts) and not verified.is_open(datetime(2026, 9, 16, 14, 0, tzinfo=timezone.utc))


def test_integrity_monitor_hysteresis():
    m = IntegrityMonitor(median_spread=Decimal("0.00010"), recover_after=3)
    clean = FeedSample(1000, Decimal("1.10000"), Decimal("1.10010"))
    assert m.observe(clean, 1100) is MarketIntegrityState.NORMAL
    wide = FeedSample(1200, Decimal("1.10000"), Decimal("1.10040"))  # 4× → ELEVATED
    assert m.observe(wide, 1300) is MarketIntegrityState.ELEVATED
    stale = FeedSample(1200, Decimal("1.10000"), Decimal("1.10010"))
    assert m.observe(stale, 5000) is MarketIntegrityState.ABNORMAL  # 3.8s old
    for i in range(2):
        assert m.observe(FeedSample(6000 + i, Decimal("1.1"), Decimal("1.10010")), 6001 + i) is MarketIntegrityState.ABNORMAL
    assert m.observe(FeedSample(6010, Decimal("1.1"), Decimal("1.10010")), 6011) is MarketIntegrityState.ELEVATED  # 3 clean → one step down
    crossed = FeedSample(7000, Decimal("1.10020"), Decimal("1.10000"))
    assert m.observe(crossed, 7001) is MarketIntegrityState.HALTED
    assert len(m.transitions) == 4


def test_bar_aggregation_deterministic():
    ticks = [Tick(ts, Decimal("1.1000") + Decimal(i) / Decimal(10000), Decimal("1.1001") + Decimal(i) / Decimal(10000), Decimal("1")) for i, ts in enumerate(range(0, 300000, 20000))]
    bars = list(BarAggregator("EURUSD", 60000).run(ticks))
    assert len(bars) == 5 and all(b.ticks == 3 for b in bars)
    assert bars[0].open == Decimal("1.10005") and bars[0].close == Decimal("1.10025") and bars[0].volume == Decimal("3")
    assert bars == list(BarAggregator("EURUSD", 60000).run(ticks))


def test_fx_cost_model_session_and_event_sensitivity():
    curve = SpreadCurve({Session.ASIA: Decimal("0.00015"), Session.LONDON: Decimal("0.00007"), Session.LONDON_NY_OVERLAP: Decimal("0.00006"), Session.NEW_YORK: Decimal("0.00008"), Session.ROLLOVER: Decimal("0.00040")})
    m = FxCostModel(curve, commission_per_lot_round_trip=Decimal("6"), contract_size=Decimal("100000"), swap_long_per_lot_day=Decimal("-8"), swap_short_per_lot_day=Decimal("2"))
    kw = dict(price=Decimal("1.10"), vol_percentile=Decimal("0.5"), holding_days=Decimal("0"), direction_long=True)
    quiet = m.round_trip_cost_pct(session=Session.LONDON_NY_OVERLAP, in_event_window=False, **kw)
    asia = m.round_trip_cost_pct(session=Session.ASIA, in_event_window=False, **kw)
    event = m.round_trip_cost_pct(session=Session.LONDON_NY_OVERLAP, in_event_window=True, **kw)
    closed = m.round_trip_cost_pct(session=Session.CLOSED, in_event_window=False, **kw)
    assert quiet < asia < event < closed
    swing = m.round_trip_cost_pct(session=Session.LONDON, in_event_window=False, price=Decimal("1.10"), vol_percentile=Decimal("0.5"), holding_days=Decimal("10"), direction_long=True)
    assert swing > m.round_trip_cost_pct(session=Session.LONDON, in_event_window=False, **kw)
    passive = m.round_trip_cost_pct(session=Session.LONDON, in_event_window=False, order_passive=True, **kw)
    assert passive < m.round_trip_cost_pct(session=Session.LONDON, in_event_window=False, **kw)


def test_metrics_exposition():
    mt = Metrics(); mt.inc("vati_intents_total", venue="mt5"); mt.inc("vati_intents_total", venue="mt5"); mt.set("vati_heat", 0.0123)
    text = mt.exposition()
    assert 'vati_intents_total{venue="mt5"} 2.0' in text and "vati_heat 0.0123" in text and mt.get("vati_intents_total", venue="mt5") == 2
