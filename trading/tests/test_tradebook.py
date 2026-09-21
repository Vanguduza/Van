"""Trade book (Rev 4 K.4): past / current / potential trades with confidence scores, read from a real backtest ledger."""
from __future__ import annotations

from decimal import Decimal

import pytest

from test_backtest_runner_cli import fx_cfg, fx_engine, synthetic_bars
from vati.app import build_trade_book
from vati.arbiter import Confidence, band_for, confidence_score
from vati.backtest import BacktestEngine
from vati.core import EventKind, Ledger
from vati.intelligence.events import EventMatrix
from vati.market_data import FX_CALENDAR

D = Decimal


def test_confidence_score_is_reduce_only_display_signal():
    full = confidence_score({"regime_multiplier": "1", "volatility_multiplier": "1", "liquidity_multiplier": "1", "event_risk_multiplier": "1", "confidence_multiplier": "1"})
    assert full.score == 1 and full.band == "HIGH" and "never a size" in full.basis
    c = confidence_score({"regime_multiplier": "0.8", "confidence_multiplier": "0.9"}, capsule_health="0.9")
    assert c.score == D("0.65") and c.band == "MEDIUM"
    assert confidence_score({"regime_multiplier": "3"}).score == 1          # > 1 clamps; it can never amplify
    assert confidence_score({"regime_multiplier": "-1"}).score == 0
    assert confidence_score({"regime_multiplier": "abc"}).score == 1        # garbage ignored, not crashed
    assert [band_for(D(x)) for x in ("0.75", "0.5", "0.25", "0.24")] == ["HIGH", "MEDIUM", "LOW", "MINIMAL"]
    assert confidence_score({}).as_dict() == {"score": "1.00", "band": "HIGH", "basis": Confidence(D(1), "HIGH").basis}


def test_trade_book_from_backtest_ledger(eurusd, tmp_path):
    cfg = fx_cfg(eurusd)
    res = BacktestEngine(cfg=cfg, engine=fx_engine(cfg), cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix(), ledger_path=str(tmp_path / "bt.sqlite")).run(synthetic_bars())
    led = Ledger(tmp_path / "bt.sqlite")
    book = build_trade_book(led, view="all", limit=100)
    assert book["counts"]["past"] == res.trades >= 1 and book["counts"]["current"] == 0      # END_OF_TEST flattens everything
    p = book["past"][0]
    assert p["state"] == "CLOSED" and p["symbol"] == "EURUSD" and p["risk_decision"] in ("APPROVED", "REDUCED") and p["outcome"] and p["pnl"] is not None and p["r_multiple"] is not None
    assert p["confidence"]["band"] in ("HIGH", "MEDIUM", "LOW", "MINIMAL") and D("0") <= D(p["confidence"]["score"]) <= D("1") and len(p["decision_hash"]) == 64
    assert [r["closed_ms"] for r in book["past"]] == sorted((r["closed_ms"] for r in book["past"]), reverse=True)
    # Potential trades come from the latest assessment plus deterministic
    # refusals. Rev 5.1 adds a non-bypassable router/pre-trade boundary, so a
    # refusal may now be RISK_REJECTED or ROUTER_REFUSED depending on which
    # authority legitimately rejected it. Neither candidate rows nor refusals
    # acquire a new size from this read model.
    pot = book["potential"]
    assert pot and all("approved_size" not in r or r["kind"] != "CANDIDATE" for r in pot)
    kinds = {r["kind"] for r in pot}
    assert "CANDIDATE" in kinds
    assert kinds <= {"CANDIDATE", "RISK_REJECTED", "ROUTER_REFUSED"}
    refusals = [r for r in pot if r["kind"] in ("RISK_REJECTED", "ROUTER_REFUSED")]
    assert refusals
    assert all(
        r["label"].startswith("REJECTED:")
        for r in refusals if r["kind"] == "RISK_REJECTED"
    )
    assert all(
        r["label"] == "ROUTER_REFUSED"
        for r in refusals if r["kind"] == "ROUTER_REFUSED"
    )
    # Refusals older than a day of ledger time are history, not potential.
    newest = max(r["assessed_ms"] for r in pot)
    assert all(newest - r["assessed_ms"] <= 24 * 3_600_000 for r in refusals)
    assert all(set(r["confidence"]) == {"score", "band", "basis"} for r in pot)
    assert pot == sorted(pot, key=lambda r: (-r["assessed_ms"], -D(r["confidence"]["score"])))
    # per-view calls return only that view; limits apply
    assert set(build_trade_book(led, view="past", limit=1)) >= {"past", "counts"} and "current" not in build_trade_book(led, view="past")
    assert len(build_trade_book(led, view="past", limit=1)["past"]) == 1
    with pytest.raises(ValueError):
        build_trade_book(led, view="future")
    # assessments now carry per-candidate multipliers and confidence for the preview surface
    oa = next(e for e in led.iter(EventKind.OPPORTUNITY_ASSESSMENT) if any("confidence" in c for c in e.payload["candidates"]))
    cand = next(c for c in oa.payload["candidates"] if "confidence" in c)
    assert oa.payload["symbol"] == "EURUSD" and set(cand["multipliers"]) == {"regime_multiplier", "volatility_multiplier", "liquidity_multiplier", "event_risk_multiplier", "confidence_multiplier"}


def test_trade_book_current_state_from_open_position(eurusd, tmp_path):
    """Stop the walk before END_OF_TEST flattening to see an OPEN trade: drive the cycle directly."""
    from vati.app import DecisionCycle
    from vati.execution import PaperAdapter
    cfg = fx_cfg(eurusd)
    paper = PaperAdapter(venue="paper", account_alias="fx_primary", equity=D("10000"), value_per_price_unit_per_lot=eurusd.value_per_price_unit_per_lot)
    led = Ledger()
    cyc = DecisionCycle(cfg=cfg, adapter=paper, ledger=led, engine=fx_engine(cfg), cost_fn=lambda st: D("0.0003"), calendar=FX_CALENDAR, events=EventMatrix())
    bars = synthetic_bars()
    opened = None
    for i in range(60, len(bars)):
        r = cyc.step(bars[: i + 1], now_ms=bars[i].end_ms, last_quote_ms=bars[i].end_ms)
        if r.decision in ("APPROVED", "REDUCED"):
            opened = r; break
    assert opened is not None
    book = build_trade_book(led, view="current")
    assert book["counts"]["current"] == 1
    cur = book["current"][0]
    assert cur["state"] == "OPEN" and cur["protective_stop_confirmed"] is True and cur["fill"] is not None and D(cur["approved_size"]) > 0 and cur["owner_ticket"] is None
    assert cur["execution_channel"] == "ADAPTER" and cur["confidence"]["band"] in ("HIGH", "MEDIUM", "LOW", "MINIMAL")
