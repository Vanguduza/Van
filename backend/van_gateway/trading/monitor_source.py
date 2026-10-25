"""Server-only source boundary for monitors; no phone-supplied market-fact ingress."""
from __future__ import annotations

from collections import deque
from typing import Literal, Protocol
from pydantic import Field, StringConstraints, model_validator
from typing import Annotated
from decimal import Decimal

from .chart_models import StrictModel, Identity, InstrumentRef, Price, Timestamp
from .monitor_models import Timeframe

PERIOD_MS = {'M1': 60000, 'M5': 300000, 'M15': 900000, 'M30': 1800000,
             'H1': 3600000, 'H4': 14400000, 'D1': 86400000}


class MonitorBar(StrictModel):
    start_ms: Timestamp
    end_ms: Timestamp
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Price

    @model_validator(mode='after')
    def coherent(self):
        o, h, l, c, v = map(Decimal, (self.open, self.high, self.low, self.close, self.volume))
        if self.start_ms >= self.end_ms or l > min(o, c) or h < max(o, c) or h < l or v < 0:
            raise ValueError('inconsistent market bar')
        return self


class MarketSnapshot(StrictModel):
    instrument: InstrumentRef
    timeframe: Timeframe
    qualification: Literal['NATIVE_IDENTITY_BOUND']
    source_id: Identity
    source_revision: Identity
    available_at_ms: Timestamp
    bars: list[MonitorBar] = Field(min_length=1, max_length=2001)

    @model_validator(mode='after')
    def closed_contiguous_series(self):
        period = PERIOD_MS[self.timeframe]
        if any(b.end_ms-b.start_ms != period for b in self.bars):
            raise ValueError('bar interval differs from source timeframe')
        if any(a.end_ms != b.start_ms for a, b in zip(self.bars, self.bars[1:])):
            raise ValueError('bar series is not strictly ordered and contiguous')
        if self.bars[-1].end_ms > self.available_at_ms:
            raise ValueError('open/future bar cannot be an available closed observation')
        return self


class NewsObservation(StrictModel):
    sample_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    source_id: Identity
    trust: Literal['T1_PRIMARY', 'T2_SECONDARY', 'UNTRUSTED']
    title: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=8000)]
    excerpt: Annotated[str, StringConstraints(strict=True, max_length=4000)] = ''
    symbols: list[str] = Field(default_factory=list, max_length=128)
    published_ms: Timestamp
    available_at_ms: Timestamp

    @model_validator(mode='after')
    def causal(self):
        if self.available_at_ms < self.published_ms:
            raise ValueError('headline availability precedes publication')
        return self


class MonitorSource(Protocol):
    def market(self, instrument: InstrumentRef, timeframe: str) -> MarketSnapshot | None: ...
    def news(self) -> tuple[bool, list[NewsObservation]]: ...


class LedgerMonitorSource:
    """Reads existing recorded headlines. The symbol-only bar lake is NOT a native binding.

    A future qualified BE-008 producer must bind venue/environment/account/product,
    revision, closed bars and availability before technical alerts can fire. Returning
    no snapshot is an explicit hold, not a zero quote or a synthetic live feed.
    """
    def __init__(self, trading):
        self.trading = trading

    def market(self, instrument, timeframe):
        return None

    def news(self):
        if not self.trading.available():
            return False, []
        kinds, _, ledger = self.trading._open()
        try:
            with ledger.read_snapshot():
                captured = list(deque(ledger.iter(kinds.NEWS_HEADLINE), maxlen=500))
            rows = []
            for event in captured:
                p = event.payload
                rows.append(NewsObservation(
                    sample_id=event.hash, source_id=p['source_id'], trust=p['trust'],
                    title=p['title'], excerpt=p.get('body_excerpt', ''),
                    symbols=p.get('symbols', []), published_ms=event.event_time_ms,
                    available_at_ms=event.received_time_ms))
            return True, rows
        finally:
            ledger.close()
