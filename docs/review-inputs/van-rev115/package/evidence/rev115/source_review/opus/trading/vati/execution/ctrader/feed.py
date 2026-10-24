"""cTrader trendbars → Bars. Prices are 1/100000 units relative to `low`."""

from __future__ import annotations

from decimal import Decimal

from vati.market_data.bars import Bar

PERIOD = {"M1": ("M1", 60_000), "M5": ("M5", 300_000), "M15": ("M15", 900_000), "H1": ("H1", 3_600_000), "H4": ("H4", 14_400_000), "D1": ("D1", 86_400_000)}
SCALE = Decimal("100000")


def trendbars(adapter, symbol: str, timeframe: str, *, from_ms: int, to_ms: int, count: int = 500) -> list[Bar]:
    period, step = PERIOD[timeframe]
    adapter._ensure_auth()
    sym = adapter.symbol(symbol)
    _, r = adapter.transport.call("ProtoOAGetTrendbarsReq", {"ctidTraderAccountId": adapter.ctid_trader_account_id, "fromTimestamp": from_ms, "toTimestamp": to_ms, "period": period, "symbolId": sym.symbol_id, "count": count})
    out = []
    for tb in r.get("trendbar", []):
        low = Decimal(tb.get("low", 0)) / SCALE
        start = int(tb.get("utcTimestampInMinutes", 0)) * 60_000
        out.append(Bar(symbol.upper(), start, start + step, low + Decimal(tb.get("deltaOpen", 0)) / SCALE, low + Decimal(tb.get("deltaHigh", 0)) / SCALE, low, low + Decimal(tb.get("deltaClose", 0)) / SCALE, Decimal(tb.get("volume", 0)), 1, Decimal("0")))
    return sorted(out, key=lambda b: b.start_ms)
