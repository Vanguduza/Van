"""Deterministic tick → bar aggregation (time bars, UTC-aligned)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Iterator, Optional


@dataclass(frozen=True)
class Tick:
    ts_ms: int
    bid: Decimal
    ask: Decimal
    volume: Decimal = Decimal("0")

    @property
    def mid(self) -> Decimal:
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
        return self.high - self.low


class BarAggregator:
    def __init__(self, symbol: str, interval_ms: int) -> None:
        if interval_ms <= 0:
            raise ValueError("interval_ms must be > 0")
        self.symbol, self.interval_ms = symbol, interval_ms
        self._cur: Optional[dict] = None

    def _flush(self) -> Bar:
        c = self._cur
        assert c is not None
        bar = Bar(self.symbol, c["start"], c["start"] + self.interval_ms, c["o"], c["h"], c["l"], c["c"], c["v"], c["n"], c["spread"] / c["n"])
        self._cur = None
        return bar

    def push(self, t: Tick) -> Optional[Bar]:
        start = t.ts_ms - (t.ts_ms % self.interval_ms)
        out = None
        if self._cur is not None and start != self._cur["start"]:
            out = self._flush()
        if self._cur is None:
            self._cur = {"start": start, "o": t.mid, "h": t.mid, "l": t.mid, "c": t.mid, "v": Decimal("0"), "n": 0, "spread": Decimal("0")}
        c = self._cur
        c["h"] = max(c["h"], t.mid); c["l"] = min(c["l"], t.mid); c["c"] = t.mid
        c["v"] += t.volume; c["n"] += 1; c["spread"] += (t.ask - t.bid)
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
