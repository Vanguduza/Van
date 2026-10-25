"""Scoped cTrader historical bars, using the pinned native protobuf contract.

Native volume counts ticks. Trendbars contain no quote spread. The legacy Bar
adapter retains its required zero spread placeholder; the observation body
exposes an explicit unavailable spread. Neither is live provider qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from vati.core.canonical import canonical_hash
from vati.execution.base import VenueUnavailable
from vati.market_data.bars import Bar

PERIOD = {"M1": ("M1", 60_000), "M5": ("M5", 300_000), "M15": ("M15", 900_000),
          "M30": ("M30", 1_800_000), "H1": ("H1", 3_600_000),
          "H4": ("H4", 14_400_000), "D1": ("D1", 86_400_000)}
SCALE = Decimal("100000")
MAX_TIMESTAMP = 2_147_483_646_000  # Pinned ProtoOAGetTrendbarsReq contract.


def native_integer(value, *, minimum=0, maximum=2**63-1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("native integer missing or outside its declared range")
    return value


@dataclass(frozen=True)
class TrendbarObservation:
    native_account_id: int
    native_symbol_id: int
    symbol: str
    timeframe: str
    from_ms: int
    to_ms: int
    received_at_ms: int
    transport_host: str | None
    contract_revision: str | None
    has_more: bool | None
    bars: tuple[Bar, ...]
    excluded_open_bars: int
    defaulted_delta_fields: tuple[tuple[int, tuple[str, ...]], ...] = ()

    def body(self):
        data = {"schema": "vati.ctrader-trendbars/1", "native_account_id": self.native_account_id,
                "native_symbol_id": self.native_symbol_id, "symbol": self.symbol,
                "timeframe": self.timeframe, "from_ms": self.from_ms, "to_ms": self.to_ms,
                "received_at_ms": self.received_at_ms, "transport_host": self.transport_host,
                "contract_revision": self.contract_revision, "has_more": self.has_more,
                "excluded_open_bars": self.excluded_open_bars, "volume_basis": "NATIVE_TICK_COUNT",
                "field_default_profile": "COORDINATES_EXPLICIT_OPTIONAL_DELTAS_PROTO2_ZERO",
                "defaulted_delta_fields": [{"start_ms": start, "fields": list(fields)}
                    for start,fields in self.defaulted_delta_fields],
                "interval_basis": "FIXED_DURATION_FROM_NATIVE_OPEN_MINUTE_CALENDAR_UNQUALIFIED",
                "spread_state": "UNAVAILABLE_NATIVE_TRENDBAR_HAS_NO_SPREAD", "spread": None,
                "authority_effect": "NONE", "provider_qualified": False,
                "bars": [{"start_ms": b.start_ms, "end_ms": b.end_ms,
                          **{k: str(getattr(b,k)) for k in ("open","high","low","close","volume")},
                          "ticks": b.ticks} for b in self.bars]}
        return data | {"observation_sha256": canonical_hash(data)}


def read_trendbars(adapter, symbol: str, timeframe: str, *, from_ms: int, to_ms: int,
                  count: int = 500) -> TrendbarObservation:
    if not isinstance(symbol, str) or not symbol or len(symbol) > 256:
        raise ValueError("native bar symbol required")
    if not isinstance(timeframe, str) or timeframe not in PERIOD:
        raise ValueError("unsupported native bar timeframe")
    native_integer(from_ms, maximum=MAX_TIMESTAMP)
    native_integer(to_ms, minimum=from_ms, maximum=MAX_TIMESTAMP)
    native_integer(count, minimum=1, maximum=2001)
    account = native_integer(adapter.ctid_trader_account_id, minimum=1)
    period, step = PERIOD[timeframe]
    adapter._ensure_auth()
    sym = adapter.symbol(symbol)
    product = native_integer(sym.symbol_id, minimum=1)
    name, response = adapter.transport.call("ProtoOAGetTrendbarsReq", {
        "ctidTraderAccountId": account, "fromTimestamp": from_ms, "toTimestamp": to_ms,
        "period": period, "symbolId": product, "count": count})
    try:
        received = native_integer(adapter.clock(),maximum=253402300799000)
        # The deprecated response timestamp must not redefine the original window.
        if (name != "ProtoOAGetTrendbarsRes" or not isinstance(response,dict)
                or native_integer(response["ctidTraderAccountId"],minimum=1) != account
                or native_integer(response["symbolId"],minimum=1) != product
                or response["period"] != period):
            raise ValueError("native response scope mismatch")
        more = response.get("hasMore")
        if more is not None and type(more) is not bool:
            raise ValueError("native pagination state invalid")
        rows = response.get("trendbar", [])
        if not isinstance(rows,list) or len(rows) > count:
            raise ValueError("native bar count invalid")
        out, seen, excluded, defaults = [], set(), 0, []
        with localcontext() as context:
            context.prec = 80
            for row in rows:
                if not isinstance(row,dict): raise ValueError("native bar invalid")
                low = native_integer(row["low"],minimum=-(2**63))
                # These optional unsigned deltas have the proto2 zero default.
                # Low/time remain explicit application coordinates; an absent
                # coordinate does not become a measured current market fact.
                opening, closing, high = [native_integer(row.get(k,0),maximum=2**64-1)
                    for k in ("deltaOpen","deltaClose","deltaHigh")]
                volume = native_integer(row["volume"])
                start = native_integer(row["utcTimestampInMinutes"],maximum=2**32-1)*60_000
                if high < max(opening,closing): raise ValueError("native OHLC incoherent")
                if start in seen or not from_ms <= start <= to_ms or start > received:
                    raise ValueError("duplicate or outside-window native bar")
                seen.add(start)
                if start+step > min(to_ms,received):
                    excluded += 1
                    continue
                missing=tuple(k for k in ("deltaOpen","deltaClose","deltaHigh") if k not in row)
                if missing:defaults.append((start,missing))
                out.append(Bar(symbol.upper(),start,start+step,Decimal(low+opening)/SCALE,
                    Decimal(low+high)/SCALE,Decimal(low)/SCALE,Decimal(low+closing)/SCALE,
                    Decimal(volume),volume,Decimal("0")))
        return TrendbarObservation(account,product,symbol.upper(),timeframe,from_ms,to_ms,received,
            getattr(adapter.transport,"host",None),getattr(sym,"contract_revision",None),more,
            tuple(sorted(out,key=lambda b:b.start_ms)),excluded,tuple(sorted(defaults)))
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        raise VenueUnavailable("cTrader native trendbar scope, window or market fields invalid") from exc


def trendbars(adapter, symbol: str, timeframe: str, *, from_ms: int, to_ms: int,
              count: int = 500) -> list[Bar]:
    """Closed-bar compatibility adapter; avg_spread zero is an unavailable placeholder.

    Use read_trendbars for scope, availability, pagination and source semantics.
    A list is not a complete-history or live provider qualification.
    """
    return list(read_trendbars(adapter,symbol,timeframe,from_ms=from_ms,to_ms=to_ms,count=count).bars)
