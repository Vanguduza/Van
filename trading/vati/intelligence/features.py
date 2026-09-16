"""Indicators as features (Rev 2 §10). Pure functions over bar sequences,
Decimal in/out, no state. They are evidence, never buy/sell commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Optional, Sequence

from vati.market_data.bars import Bar

getcontext().prec = 28
ZERO = Decimal("0")


def ema(values: Sequence[Decimal], period: int) -> Optional[Decimal]:
    if period <= 0 or len(values) < period:
        return None
    k = Decimal(2) / Decimal(period + 1)
    e = sum(values[:period], ZERO) / Decimal(period)
    for v in values[period:]:
        e = v * k + e * (Decimal(1) - k)
    return e


def atr(bars: Sequence[Bar], period: int) -> Optional[Decimal]:
    if len(bars) < period + 1:
        return None
    trs = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(trs[-period:], ZERO) / Decimal(period)


def rsi(closes: Sequence[Decimal], period: int = 14) -> Optional[Decimal]:
    if len(closes) < period + 1:
        return None
    gains = losses = ZERO
    for a, b in zip(closes[-period - 1:-1], closes[-period:]):
        d = b - a
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == ZERO:
        return Decimal(100)
    rs = gains / losses
    return Decimal(100) - Decimal(100) / (Decimal(1) + rs)


def realised_vol(closes: Sequence[Decimal], period: int) -> Optional[Decimal]:
    """Std-dev of simple returns over `period` (per-bar, not annualised)."""
    if len(closes) < period + 1:
        return None
    rets = [(b - a) / a for a, b in zip(closes[-period - 1:-1], closes[-period:]) if a != ZERO]
    if len(rets) < 2:
        return None
    mean = sum(rets, ZERO) / Decimal(len(rets))
    var = sum(((r - mean) ** 2 for r in rets), ZERO) / Decimal(len(rets) - 1)
    return var.sqrt()


def zscore(values: Sequence[Decimal], period: int) -> Optional[Decimal]:
    if len(values) < period:
        return None
    w = values[-period:]
    mean = sum(w, ZERO) / Decimal(period)
    var = sum(((v - mean) ** 2 for v in w), ZERO) / Decimal(max(1, period - 1))
    sd = var.sqrt()
    return (values[-1] - mean) / sd if sd > ZERO else ZERO


def percentile_rank(values: Sequence[Decimal], x: Decimal) -> Decimal:
    """Mid-rank percentile: strictly-below plus half of ties, so a constant
    series ranks 0.5 rather than 1.0."""
    if not values:
        return Decimal("0.5")
    below = sum(1 for v in values if v < x)
    ties = sum(1 for v in values if v == x)
    return (Decimal(below) + Decimal(ties) / Decimal(2)) / Decimal(len(values))


@dataclass(frozen=True)
class FeatureVector:
    symbol: str
    as_of_ms: int
    close: Decimal
    ema_fast: Optional[Decimal]
    ema_slow: Optional[Decimal]
    atr: Optional[Decimal]
    rsi: Optional[Decimal]
    realised_vol: Optional[Decimal]
    vol_percentile: Decimal
    spread_percentile: Decimal
    trend_slope: Optional[Decimal]        # (ema_fast - ema_slow) / atr
    range_compression: Optional[Decimal]  # last-N range / atr-implied range
    swing_high: Optional[Decimal]
    swing_low: Optional[Decimal]
    complete: bool
    feature_version: str = "features/1.0.0"

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}


def compute_features(bars: Sequence[Bar], *, fast: int = 20, slow: int = 50, atr_period: int = 14, vol_period: int = 20, lookback: int = 100) -> FeatureVector:
    closes = [b.close for b in bars]
    last = bars[-1]
    ef, es, a = ema(closes, fast), ema(closes, slow), atr(bars, atr_period)
    rv = realised_vol(closes, vol_period)
    vol_hist = [realised_vol(closes[: i + 1], vol_period) for i in range(max(vol_period + 1, len(closes) - lookback), len(closes))]
    vol_hist = [v for v in vol_hist if v is not None]
    spreads = [b.avg_spread for b in bars[-lookback:]]
    slope = (ef - es) / a if (ef is not None and es is not None and a and a > ZERO) else None
    recent = bars[-5:]
    compression = ((max(b.high for b in recent) - min(b.low for b in recent)) / (a * Decimal(5))) if (a and a > ZERO and len(recent) == 5) else None
    window = bars[-20:]
    return FeatureVector(
        symbol=last.symbol, as_of_ms=last.end_ms, close=last.close, ema_fast=ef, ema_slow=es, atr=a, rsi=rsi(closes),
        realised_vol=rv, vol_percentile=percentile_rank(vol_hist, rv) if rv is not None else Decimal("0.5"),
        spread_percentile=percentile_rank(spreads, last.avg_spread), trend_slope=slope, range_compression=compression,
        swing_high=max(b.high for b in window) if window else None, swing_low=min(b.low for b in window) if window else None,
        complete=all(x is not None for x in (ef, es, a, rv)),
    )
