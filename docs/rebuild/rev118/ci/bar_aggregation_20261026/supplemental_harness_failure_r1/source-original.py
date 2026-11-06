"""Deterministic tick → bar aggregation (time bars, UTC-aligned)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Iterable, Iterator, Optional

from vati.core.decimal_context import native_decimal_context


@dataclass(frozen=True)
class Tick:
    ts_ms: int
    bid: Decimal
    ask: Decimal
    volume: Decimal = Decimal("0")

    @property
    def mid(self) -> Decimal:
        with localcontext(native_decimal_context()):
            return (self.bid + self.ask) / Decimal("2")


@dataclass(frozen=True)
class Bar:
    symbol: str
    start_ms: int
    end_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    ticks: int
    avg_spread: Decimal

    @property
    def range(self) -> Decimal:
        with localcontext(native_decimal_context()):
            return self.high - self.low


class BarAggregator:
    def __init__(self, symbol: str, interval_ms: int) -> None:
        if type(interval_ms) is not int or interval_ms <= 0:
            raise ValueError("interval_ms must be > 0")
        self.symbol, self.interval_ms = symbol, interval_ms
        self._cur: Optional[dict] = None
        self._last_ts: Optional[int] = None

    def _bar(self, c: dict) -> Bar:
        with localcontext(native_decimal_context()):
            return Bar(self.symbol, c["start"], c["start"] + self.interval_ms, c["o"], c["h"], c["l"], c["c"], c["v"], c["n"], c["spread"] / c["n"])

    def _flush(self) -> Bar:
        c = self._cur
        assert c is not None
        bar = self._bar(c)
        self._cur = None
        return bar

    def push(self, t: Tick) -> Optional[Bar]:
        # Validate before flushing the previous interval. In particular a late
        # or malformed next tick cannot publish or discard the original bar.
        if not isinstance(t, Tick) or type(t.ts_ms) is not int:
            raise ValueError("tick timestamp must be an integer")
        if any(not isinstance(value, Decimal) or not value.is_finite()
               for value in (t.bid, t.ask, t.volume)):
            raise ValueError("tick prices and volume must be finite Decimals")
        if t.ask < t.bid or t.volume < 0:
            raise ValueError("tick spread or volume is invalid")
        if self._last_ts is not None and t.ts_ms < self._last_ts:
            raise ValueError("tick timestamp order regressed")
        start = t.ts_ms - (t.ts_ms % self.interval_ms)
        previous = self._cur
        # Stage all arithmetic and output before committing either state change.
        # Equal timestamps retain arrival order; no native sequence is invented.
        with localcontext(native_decimal_context()):
            mid = t.mid
            c = (dict(previous) if previous is not None and start == previous["start"] else
                 {"start": start, "o": mid, "h": mid, "l": mid, "c": mid, "v": Decimal("0"), "n": 0, "spread": Decimal("0")})
            c["h"] = max(c["h"], mid); c["l"] = min(c["l"], mid); c["c"] = mid
            c["v"] += t.volume; c["n"] += 1; c["spread"] += (t.ask - t.bid)
            out = self._bar(previous) if previous is not None and start != previous["start"] else None
        self._cur, self._last_ts = c, t.ts_ms
        return out

    def finish(self) -> Optional[Bar]:
        return self._flush() if self._cur is not None else None

    def run(self, ticks: Iterable[Tick]) -> Iterator[Bar]:
        for t in ticks:
            b = self.push(t)
            if b is not None:
                yield b
        last = self.finish()
        if last is not None:
            yield last
