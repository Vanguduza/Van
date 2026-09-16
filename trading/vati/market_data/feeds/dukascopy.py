"""Dukascopy tick history (free, no account): one LZMA-compressed `.bi5` file per
instrument-hour at
  https://datafeed.dukascopy.com/datafeed/{SYMBOL}/{YYYY}/{MM-1:02d}/{DD}/{HH}h_ticks.bi5
Each record is 20 bytes big-endian: ms offset (u32), ask (u32), bid (u32),
ask volume (f32), bid volume (f32); prices are integers scaled by the
instrument's point (1e5 for most FX, 1e3 for JPY pairs and XAU). The month is
zero-based in the URL: a famous trap, encoded here once."""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Iterable, Optional

from vati.market_data.bars import Bar, BarAggregator, Tick

RECORD = struct.Struct(">IIIff")
POINT = {"XAUUSD": 1000, "XAGUSD": 1000, "USDJPY": 1000, "EURJPY": 1000, "GBPJPY": 1000, "AUDJPY": 1000, "CHFJPY": 1000, "CADJPY": 1000, "NZDJPY": 1000}


def point_scale(symbol: str) -> int:
    return POINT.get(symbol.upper(), 100_000)


def dukascopy_url(symbol: str, at_utc: datetime) -> str:
    at = at_utc.astimezone(timezone.utc)
    return f"https://datafeed.dukascopy.com/datafeed/{symbol.upper()}/{at.year:04d}/{at.month - 1:02d}/{at.day:02d}/{at.hour:02d}h_ticks.bi5"


def decode_bi5(raw: bytes, *, symbol: str, hour_start_utc: datetime) -> list[Tick]:
    if not raw:
        return []
    data = lzma.decompress(raw)
    if len(data) % RECORD.size:
        raise ValueError(f"bi5 payload not a multiple of {RECORD.size} bytes")
    base_ms = int(hour_start_utc.astimezone(timezone.utc).timestamp() * 1000)
    scale = Decimal(point_scale(symbol))
    out = []
    for off, ask, bid, _av, _bv in RECORD.iter_unpack(data):
        out.append(Tick(base_ms + off, Decimal(bid) / scale, Decimal(ask) / scale))
    return out


def encode_bi5(ticks: Iterable[Tick], *, symbol: str, hour_start_utc: datetime) -> bytes:
    """Inverse of decode_bi5: used to build test fixtures that are byte-for-byte the real format."""
    base_ms = int(hour_start_utc.astimezone(timezone.utc).timestamp() * 1000)
    scale = point_scale(symbol)
    body = b"".join(RECORD.pack(t.ts_ms - base_ms, int(round(t.ask * scale)), int(round(t.bid * scale)), 1.0, 1.0) for t in ticks)
    return lzma.compress(body)


class DukascopyDownloader:
    def __init__(self, fetch: Optional[Callable[[str], bytes]] = None, *, timeout_s: float = 30.0) -> None:
        self._fetch = fetch or self._http_fetch
        self.timeout_s = timeout_s
        self.fetched: list[str] = []

    def _http_fetch(self, url: str) -> bytes:
        import urllib.request
        with urllib.request.urlopen(url, timeout=self.timeout_s) as r:  # noqa: S310 — fixed https host
            return r.read()

    def hours(self, symbol: str, start_utc: datetime, end_utc: datetime) -> Iterable[datetime]:
        cur = start_utc.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        while cur < end_utc:
            if cur.weekday() < 5 or (cur.weekday() == 6 and cur.hour >= 21):   # FX week: Sunday 21:00 UTC → Friday
                yield cur
            cur += timedelta(hours=1)

    def ticks(self, symbol: str, start_utc: datetime, end_utc: datetime) -> list[Tick]:
        out: list[Tick] = []
        for h in self.hours(symbol, start_utc, end_utc):
            url = dukascopy_url(symbol, h)
            raw = self._fetch(url)
            self.fetched.append(url)
            out.extend(decode_bi5(raw, symbol=symbol, hour_start_utc=h))
        return out

    def bars(self, symbol: str, start_utc: datetime, end_utc: datetime, *, interval_ms: int) -> list[Bar]:
        agg = BarAggregator(symbol, interval_ms)
        bars: list[Bar] = []
        for t in self.ticks(symbol, start_utc, end_utc):
            b = agg.push(t)
            if b is not None:
                bars.append(b)
        last = agg.finish()
        if last is not None:
            bars.append(last)
        return bars
