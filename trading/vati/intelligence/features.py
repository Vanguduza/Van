"""Indicators as features (Rev 2 §10). Pure functions over bar sequences,
Decimal in/out, no state. They are evidence, never buy/sell commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Optional, Sequence

from vati.core.canonical import canonical_hash
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
    #: TRD-ENH-004. Without this, an M5 vector and an H1 vector for the same
    #: symbol and instant are indistinguishable by their recorded fields, so the
    #: state hash on a decision cannot say what the system actually looked at.
    #: `UNKNOWN` is the compatibility value for a caller that has not yet been
    #: given a timeframe; it is a distinct value, never treated as "any".
    timeframe: str = "UNKNOWN"

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}

    def feature_hash(self) -> str:
        """Identity of this vector, timeframe included (TRD-ENH-004)."""
        return canonical_hash(self.as_dict())


def compute_features(bars: Sequence[Bar], *, fast: int = 20, slow: int = 50, atr_period: int = 14, vol_period: int = 20, lookback: int = 100, timeframe: str = "UNKNOWN") -> FeatureVector:
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
        timeframe=timeframe,
    )


# --------------------------------------------------------------------------
# First research tranche (§7.3, TRD-ENH-015..018).
#
# Pure functions over bars, like everything above. They are *candidates*: a
# capsule may not declare one in `required_features` until a
# FeatureValidationCertificate admits it, and the redundant-pair rule means a
# second member of a pair must beat the first, not the baseline without either.
# --------------------------------------------------------------------------


def _true_ranges(bars: Sequence[Bar]) -> list[Decimal]:
    return [max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))
            for prev, cur in zip(bars[:-1], bars[1:])]


def _wilder(values: Sequence[Decimal], period: int) -> Optional[Decimal]:
    """Wilder's smoothing — the one ADX is defined against."""
    if len(values) < period:
        return None
    acc = sum(values[:period], ZERO)
    for v in values[period:]:
        acc = acc - (acc / Decimal(period)) + v
    return acc


def dmi(bars: Sequence[Bar], period: int = 14) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """+DI and -DI. Directional movement, normalised by true range."""
    if len(bars) < period + 1:
        return None, None
    plus_dm: list[Decimal] = []
    minus_dm: list[Decimal] = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        up = cur.high - prev.high
        down = prev.low - cur.low
        plus_dm.append(up if (up > down and up > ZERO) else ZERO)
        minus_dm.append(down if (down > up and down > ZERO) else ZERO)
    tr = _wilder(_true_ranges(bars), period)
    if tr is None or tr == ZERO:
        return None, None
    p, m = _wilder(plus_dm, period), _wilder(minus_dm, period)
    if p is None or m is None:
        return None, None
    hundred = Decimal(100)
    return (hundred * p / tr), (hundred * m / tr)


def adx(bars: Sequence[Bar], period: int = 14) -> Optional[Decimal]:
    """Trend *strength*, direction-agnostic. High ADX in a range is the tell
    that the range is about to stop being one."""
    if len(bars) < 2 * period + 1:
        return None
    dxs: list[Decimal] = []
    for end in range(period + 1, len(bars) + 1):
        p, m = dmi(bars[:end], period)
        if p is None or m is None:
            continue
        total = p + m
        if total == ZERO:
            continue
        dxs.append(Decimal(100) * abs(p - m) / total)
    if len(dxs) < period:
        return None
    return sum(dxs[-period:], ZERO) / Decimal(period)


def donchian(bars: Sequence[Bar], period: int = 20) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Upper, lower, and position within the channel in [0, 1].

    Donchian rather than Keltner for the tranche: it is a pure price-structure
    statement with no volatility term, so it is less colinear with `atr` and
    `range_compression`, which the registry already carries.
    """
    if len(bars) < period:
        return None, None, None
    window = bars[-period:]
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    if hi == lo:
        return hi, lo, Decimal("0.5")
    pos = (window[-1].close - lo) / (hi - lo)
    return hi, lo, max(ZERO, min(Decimal(1), pos))


def ppo(closes: Sequence[Decimal], fast: int = 12, slow: int = 26) -> Optional[Decimal]:
    """Percentage price oscillator: MACD normalised by the slow EMA.

    PPO rather than MACD for the tranche. They are the same construction, and
    the redundant-pair rule admits only one — PPO because its output is
    comparable across instruments and price levels, which MACD's is not.
    """
    if len(closes) < slow:
        return None
    ef, es = ema(closes, fast), ema(closes, slow)
    if ef is None or es is None or es == ZERO:
        return None
    return Decimal(100) * (ef - es) / es


def roc(closes: Sequence[Decimal], period: int) -> Optional[Decimal]:
    """Rate of change over one horizon, in percent."""
    if len(closes) < period + 1 or closes[-period - 1] == ZERO:
        return None
    return Decimal(100) * (closes[-1] - closes[-period - 1]) / closes[-period - 1]


def multi_horizon_roc(closes: Sequence[Decimal], periods: Sequence[int] = (5, 20, 60)) -> dict[str, Optional[Decimal]]:
    """Momentum at several horizons. One number cannot say "up this week,
    down this quarter", and that disagreement is the informative part."""
    return {f"roc_{p}": roc(closes, p) for p in periods}
