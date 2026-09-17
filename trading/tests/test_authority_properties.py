"""Seeded fuzz over the Risk Authority (Rev 2 §51 property tests).

For thousands of random mandates, snapshots and intents these invariants must
hold without exception:

  P1  approved risk never exceeds the mandate per-trade limit;
  P2  approved risk never exceeds the requested risk;
  P3  portfolio heat after approval never exceeds the mandate open-risk cap;
  P4  no currency leg after approval exceeds the mandate leg cap;
  P5  approved size respects venue min/step/max;
  P6  any false platform-health flag, kill-switch trigger, expired mandate or
      non-order mode yields REJECTED with zero size;
  P7  the same inputs always produce the same decision (determinism);
  P8  a replayed idempotency key is REJECTED as a duplicate.
"""

from __future__ import annotations

import random
from decimal import Decimal

from conftest import NOW, intent, mandate_dict, snapshot
from vati.risk import (
    Decision,
    currency_leg_exposure,
    Direction,
    KillSwitchTrigger,
    MarketIntegrityState,
    OpenPosition,
    RiskAuthority,
    StrategyState,
    SymbolContract,
    TradingMandate,
)

CASES = 3000


def _dec(rng: random.Random, lo: float, hi: float, places: int = 5) -> Decimal:
    return Decimal(str(round(rng.uniform(lo, hi), places)))


def _contract(rng: random.Random, symbol: str) -> SymbolContract:
    base, quote = symbol[:3], symbol[3:]
    tick = Decimal("0.00001") if quote != "JPY" else Decimal("0.001")
    return SymbolContract(
        symbol=symbol, venue="mt5", base_currency=base, quote_currency=quote, account_currency="USD",
        contract_size=Decimal("100000"), tick_size=tick, tick_value=_dec(rng, 0.5, 1.5, 2),
        volume_min=Decimal("0.01"), volume_step=Decimal(rng.choice(["0.01", "0.05", "0.10"])),
        volume_max=Decimal(rng.choice(["5", "50", "100"])), min_stop_distance=tick * rng.choice([10, 30]),
    )


def _positions(rng: random.Random, equity: Decimal) -> tuple[OpenPosition, ...]:
    out = []
    for _ in range(rng.randint(0, 3)):
        sym = rng.choice(["GBPUSD", "USDJPY", "EURGBP", "AUDUSD", "XAUUSD"])
        base, quote = (sym[:3], sym[3:])
        risk = equity * _dec(rng, 0.0005, 0.006, 5)
        vppu = Decimal("100000")
        stop = _dec(rng, 0.0005, 0.01, 5)
        lots = (risk / (stop * vppu)).quantize(Decimal("0.01"))
        if lots <= 0:
            continue
        out.append(OpenPosition(sym, rng.choice(list(Direction)), lots, stop, vppu, base, quote, "FX-TREND-03"))
    return tuple(out)


def _case(rng: random.Random):
    per_trade = _dec(rng, 0.001, 0.02, 4)
    open_risk = max(per_trade, _dec(rng, 0.005, 0.06, 4))
    m = TradingMandate.from_mapping(
        mandate_dict(
            mode=rng.choices(
                ["LIMITED_LIVE", "AUTONOMOUS_LIVE", "DEMO_TRADER", "OBSERVE", "HALTED", "SHADOW_TRADER"],
                weights=[35, 25, 15, 8, 8, 9],
            )[0],
            max_risk_per_trade=str(per_trade),
            max_open_stop_risk=str(open_risk),
            max_currency_leg_exposure=str(_dec(rng, 0.002, 0.04, 4)),
            max_total_positions=rng.randint(1, 6),
            max_positions_per_instrument=rng.randint(1, 2),
            tier1_event_policy=rng.choice(["flat", "strategy_specific"]),
            weekend_hold_allowed=rng.random() < 0.5,
        )
    )
    symbol = rng.choices(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD"], weights=[30, 25, 20, 15, 10])[0]
    contract = _contract(rng, symbol)
    equity = _dec(rng, 500, 250000, 2)
    peak = equity * _dec(rng, 1.0, 1.05, 4)
    # Each fault is injected independently and rarely, so that single-cause
    # rejections occur and every fail-closed branch is reached on its own.
    fault = lambda p: rng.random() < p  # noqa: E731
    snap = snapshot(
        contract,
        equity=equity,
        balance=equity,
        peak_equity=peak,
        day_start_equity=equity * _dec(rng, 0.97, 1.02, 4),
        week_start_equity=equity * _dec(rng, 0.95, 1.03, 4),
        consecutive_losses=rng.choices([0, 1, 2, 3, 4, 5], weights=[50, 20, 12, 8, 6, 4])[0],
        open_positions=_positions(rng, equity),
        quote_age_ms=rng.choice([1600, 9000, -1]) if fault(0.05) else rng.choice([50, 300, 1400]),
        broker_connected=not fault(0.04),
        reconciliation_ok=not fault(0.04),
        clock_sync_ok=not fault(0.03),
        risk_store_ok=not fault(0.03),
        account_verified=not fault(0.04),
        market_integrity=rng.choices(list(MarketIntegrityState), weights=[80, 10, 6, 4])[0],
        tier1_event_blackout_active=fault(0.12),
        kill_switch_triggers=frozenset({rng.choice(list(KillSwitchTrigger))}) if fault(0.06) else frozenset(),
        now_unix=NOW + 400 * 86400 if fault(0.04) else NOW,
    )
    direction = rng.choice(list(Direction))
    entry = _dec(rng, 0.9, 1.6, 5) if "JPY" not in symbol else _dec(rng, 100, 160, 3)
    dist = contract.tick_size * rng.choices([5, 20, 50, 200, 800], weights=[6, 20, 30, 30, 14])[0]
    stop = entry - dist if direction is Direction.LONG else entry + dist
    it = intent(
        idempotency_key=f"k-{rng.random()}",
        symbol=symbol,
        direction=direction,
        entry=entry,
        stop=None if rng.random() < 0.05 else stop,
        requested_risk_pct=_dec(rng, 0.0005, 0.03, 4),
        strategy_state=rng.choices(list(StrategyState), weights=[2, 2, 2, 5, 5, 12, 64, 3, 3, 2])[0],
        strategy_id=rng.choices(["FX-TREND-03", "FX-LONDON-BREAKOUT-04", "ROGUE"], weights=[45, 45, 10])[0],
        is_event_certified=rng.random() < 0.3,
        holds_over_weekend=rng.random() < 0.1,
        regime_multiplier=_dec(rng, -0.5, 2.0, 3),
        confidence_multiplier=_dec(rng, 0.0, 1.5, 3),
        volatility_multiplier=_dec(rng, 0.2, 1.2, 3),
    )
    return m, snap, it


def test_risk_authority_invariants():
    rng = random.Random(20260916)
    approved = rejected = 0
    for i in range(CASES):
        m, snap, it = _case(rng)
        auth = RiskAuthority(m)
        d = auth.evaluate(it, snap)
        d2 = RiskAuthority(m).evaluate(it, snap)
        assert d == d2, f"P7 determinism violated at case {i}"
        must_reject = (
            snap.kill_switch_triggers or not snap.account_verified or not snap.data_fresh or not snap.broker_connected
            or not snap.reconciliation_ok or not snap.clock_sync_ok or not snap.risk_store_ok
            or snap.market_integrity in (MarketIntegrityState.ABNORMAL, MarketIntegrityState.HALTED)
            or m.is_expired(snap.now_unix) or not m.sends_orders() or it.stop is None
        )
        if must_reject:
            assert d.decision is Decision.REJECTED and d.approved_size == 0, f"P6 violated at case {i}: {d}"
        if d.decision is Decision.REJECTED:
            rejected += 1
            continue
        approved += 1
        c = snap.symbol_contract
        assert d.approved_risk_pct <= m.max_risk_per_trade, f"P1 at {i}: {d}"
        assert d.approved_risk_pct <= it.requested_risk_pct, f"P2 at {i}: {d}"
        assert d.portfolio_heat_after <= m.max_open_stop_risk, f"P3 at {i}: {d}"
        assert c.volume_min <= d.approved_size <= c.volume_max, f"P5 at {i}: {d}"
        assert (d.approved_size / c.volume_step) % 1 == 0, f"P5 step at {i}: {d}"
        new = OpenPosition(it.symbol, it.direction, d.approved_size, abs(it.entry - it.stop), c.value_per_price_unit_per_lot, c.base_currency, c.quote_currency)
        legs = currency_leg_exposure(snap.open_positions + (new,), snap.equity)
        assert all(v <= m.max_currency_leg_exposure for v in legs.values()), f"P4 at {i}: {legs}"
        replay = auth.evaluate(it, snap)
        assert replay.decision is Decision.REJECTED and replay.reason_code == "DUPLICATE_INTENT", f"P8 at {i}"
    # The fuzz must exercise both branches or it proves nothing.
    assert approved > 200 and rejected > 200, (approved, rejected)


def test_currency_leg_invariant_after_approval():
    rng = random.Random(7)
    checked = 0
    for _ in range(CASES):
        m, snap, it = _case(rng)
        d = RiskAuthority(m).evaluate(it, snap)
        if d.decision is Decision.REJECTED:
            continue
        c = snap.symbol_contract
        new = OpenPosition(it.symbol, it.direction, d.approved_size, abs(it.entry - it.stop), c.value_per_price_unit_per_lot, c.base_currency, c.quote_currency)
        legs = currency_leg_exposure(snap.open_positions + (new,), snap.equity)
        assert all(v <= m.max_currency_leg_exposure for v in legs.values()), (legs, m.max_currency_leg_exposure)
        checked += 1
    assert checked > 50
