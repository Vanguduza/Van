"""Deterministic monitor measurements; observations and comparisons cannot trade."""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace
from .monitor_source import MarketSnapshot
from .monitor_models import DrawingCondition, IndicatorCondition


def text(value: Decimal) -> str:
    return str(value)


def _ema_series(values, period):
    if len(values) < period:
        return []
    values = [v if isinstance(v, Fraction) else Fraction(v) for v in values]
    initial = sum(values[:period], Fraction(0))/period
    out = [None]*(period-1)+[initial]
    k = Fraction(2, period+1)
    for value in values[period:]:
        out.append(out[-1]+k*(value-out[-1]))
    return out


def _decimal(value):
    return Decimal(value.numerator)/Decimal(value.denominator)


def measurement(snapshot: MarketSnapshot, condition) -> Decimal | None:
    bars = snapshot.bars
    closes = [Decimal(b.close) for b in bars]
    if condition.kind == 'PRICE':
        return closes[-1]
    if isinstance(condition, IndicatorCondition):
        from vati.intelligence.features import rsi, atr
    with localcontext() as ctx:
        ctx.prec = 80
        if isinstance(condition, DrawingCondition):
            anchors = condition.drawing.anchors
            level = Decimal(anchors[0].price)
            if condition.drawing.kind == 'TREND':
                a, b = anchors
                level += ((Decimal(b.price)-level) * Decimal(bars[-1].end_ms-a.time_ms)
                          / Decimal(b.time_ms-a.time_ms))
            # A crossing is the sign change of price minus the pinned drawing at
            # each observation's own time; a moving line is never held constant.
            return closes[-1]-level
        if not isinstance(condition, IndicatorCondition):
            return None
        indicator = condition.indicator
        kind = indicator.kind
        if kind in {'SMA', 'EMA', 'RSI', 'ATR'}:
            period = indicator.period
            if kind == 'SMA':
                return None if len(closes) < period else sum(closes[-period:])/Decimal(period)
            if kind == 'EMA':
                values = _ema_series(closes, period)
                return _decimal(values[-1]) if values else None
            if kind == 'RSI':
                return rsi(closes, period)
            native = [SimpleNamespace(high=Decimal(b.high), low=Decimal(b.low),
                                      close=Decimal(b.close)) for b in bars]
            return atr(native, period)
        if kind == 'MACD':
            fast = _ema_series(closes, indicator.fast)
            slow = _ema_series(closes, indicator.slow)
            lines = [a-b for a, b in zip(fast, slow) if a is not None and b is not None]
            if not lines:
                return None
            if condition.component == 'MACD':
                return _decimal(lines[-1])
            signals = _ema_series(lines, indicator.signal)
            if not signals:
                return None
            signal = signals[-1]
            return _decimal(signal if condition.component == 'SIGNAL' else lines[-1]-signal)
        if kind == 'BOLLINGER':
            if len(closes) < indicator.period:
                return None
            values = closes[-indicator.period:]
            mean = sum(values)/Decimal(indicator.period)
            variance = sum((v-mean)**2 for v in values)/Decimal(indicator.period)
            deviation = variance.sqrt()*Decimal(indicator.deviations)
            return {'MIDDLE': mean, 'UPPER': mean+deviation, 'LOWER': mean-deviation}[condition.component]
        if kind == 'VWAP':
            # An anchor older than captured history is not silently rebased.
            if indicator.anchor_ms not in {b.start_ms for b in bars}:
                return None
            selected = [b for b in bars if b.start_ms >= indicator.anchor_ms]
            volume = sum((Decimal(b.volume) for b in selected), Decimal(0))
            if not volume:
                return None
            return sum(((Decimal(b.high)+Decimal(b.low)+Decimal(b.close))/Decimal(3)
                        * Decimal(b.volume) for b in selected), Decimal(0))/volume
    return None


def matched(comparator: str, value: Decimal, threshold: Decimal,
            previous: Decimal | None = None) -> bool:
    if comparator == 'AT_OR_ABOVE':
        return value >= threshold
    if comparator == 'AT_OR_BELOW':
        return value <= threshold
    if previous is None:
        return False
    if comparator == 'CROSS_ABOVE':
        return previous <= threshold < value
    if comparator == 'CROSS_BELOW':
        return previous >= threshold > value
    raise ValueError('unsupported comparison')
