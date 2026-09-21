"""MarketState assembly (Rev 2 §3.1). Deterministic: same bars, quotes, calendar
and event matrix → same state and hash."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.intelligence.events import EventMatrix, EventWindowState
from vati.intelligence.features import FeatureVector, compute_features
from vati.intelligence.regimes import RegimeEngine, RegimeState
from vati.market_data.bars import Bar
from vati.market_data.calendars import MarketCalendar, Session
from vati.risk.contracts import MarketIntegrityState


@dataclass(frozen=True)
class MarketState:
    symbol: str
    base: str
    quote: str
    as_of_ms: int
    session: Session
    features: FeatureVector
    regime: RegimeState
    integrity: MarketIntegrityState
    event_window: EventWindowState
    event_id: Optional[str]
    minutes_to_next_event: Optional[int]
    quote_age_ms: int
    activation_id: str
    state_hash: str = ""

    def in_event_window(self) -> bool:
        return self.event_window in (EventWindowState.PRE_BLACKOUT, EventWindowState.POST_BLACKOUT, EventWindowState.QUIET)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "as_of_ms": self.as_of_ms, "session": self.session.value, "features": self.features.as_dict(),
            "regime": {"trend": self.regime.trend.value, "vol": self.regime.vol.value, "phase": self.regime.phase.value, "confidence": str(self.regime.confidence)},
            "integrity": self.integrity.value, "event_window": self.event_window.value, "event_id": self.event_id,
            "minutes_to_next_event": self.minutes_to_next_event, "quote_age_ms": self.quote_age_ms, "activation_id": self.activation_id,
        }


def build_market_state(*, symbol: str, base: str, quote: str, bars: Sequence[Bar], regime_engine: RegimeEngine, calendar: MarketCalendar,
                       events: EventMatrix, integrity: MarketIntegrityState, now_ms: int, last_quote_ms: int, activation_id: str) -> MarketState:
    f = compute_features(bars)
    r = regime_engine.update(f)
    ts = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    ew, ev = events.state_at(now_ms, base, quote)
    st = MarketState(symbol, base, quote, now_ms, calendar.session_at(ts), f, r, integrity, ew, ev.event_id if ev else None,
                     events.minutes_to_next(now_ms, base, quote), now_ms - last_quote_ms, activation_id)
    return MarketState(**{**st.__dict__, "state_hash": canonical_hash(st.as_dict())})
