"""Session calendars (Rev 2 §4.5). FX is 24×5 with named sessions in UTC;
exchange calendars are parameterised and may carry UNVERIFIED hours, in which
case `is_open` refuses (fail closed) rather than guessing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Optional


class Session(str, Enum):
    CLOSED = "CLOSED"
    ASIA = "ASIA"
    LONDON = "LONDON"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    NEW_YORK = "NEW_YORK"
    ROLLOVER = "ROLLOVER"
    EXCHANGE_OPEN = "EXCHANGE_OPEN"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class SessionWindow:
    session: Session
    start: time  # UTC
    end: time    # UTC, exclusive; may be < start for wrap-around


@dataclass(frozen=True)
class MarketCalendar:
    name: str
    windows: tuple[SessionWindow, ...]
    weekend_close_utc: Optional[tuple[int, time]] = None  # (weekday, time) e.g. Friday 22:00
    weekend_open_utc: Optional[tuple[int, time]] = None   # (weekday, time) e.g. Sunday 22:00
    holidays: frozenset[str] = frozenset()                # ISO dates
    hours_verified: bool = True
    tz_note: str = "UTC"

    def is_weekend_closed(self, ts: datetime) -> bool:
        if self.weekend_close_utc is None or self.weekend_open_utc is None:
            return ts.weekday() >= 5
        cwd, ct = self.weekend_close_utc
        owd, ot = self.weekend_open_utc
        wd, t = ts.weekday(), ts.time()
        if wd == cwd and t >= ct:
            return True
        if wd == owd and t < ot:
            return True
        # days strictly between close and open weekdays (Sat when Fri→Sun)
        span = {(cwd + i) % 7 for i in range(1, ((owd - cwd) % 7))}
        return wd in span

    def session_at(self, ts: datetime) -> Session:
        if ts.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        ts = ts.astimezone(timezone.utc)
        if not self.hours_verified:
            return Session.UNVERIFIED
        if ts.date().isoformat() in self.holidays or self.is_weekend_closed(ts):
            return Session.CLOSED
        t = ts.time()
        for w in self.windows:
            if w.start <= w.end:
                if w.start <= t < w.end:
                    return w.session
            elif t >= w.start or t < w.end:
                return w.session
        return Session.CLOSED

    def is_open(self, ts: datetime) -> bool:
        s = self.session_at(ts)
        return s not in (Session.CLOSED, Session.UNVERIFIED)

    def holds_over_weekend(self, entry: datetime, expected_exit: datetime) -> bool:
        cur = entry
        while cur <= expected_exit:
            if self.is_weekend_closed(cur):
                return True
            cur += timedelta(hours=1)
        return False


# FX: sessions in UTC (standard-time approximations; DST handled by the adapter's session table at adoption)
FX_CALENDAR = MarketCalendar(
    name="FX_24x5",
    windows=(
        SessionWindow(Session.ROLLOVER, time(21, 55), time(22, 5)),
        SessionWindow(Session.ASIA, time(22, 5), time(7, 0)),
        SessionWindow(Session.LONDON, time(7, 0), time(12, 0)),
        SessionWindow(Session.LONDON_NY_OVERLAP, time(12, 0), time(16, 0)),
        SessionWindow(Session.NEW_YORK, time(16, 0), time(21, 55)),
    ),
    weekend_close_utc=(4, time(22, 0)),
    weekend_open_utc=(6, time(22, 0)),
)


def zse_calendar(open_utc: Optional[time], close_utc: Optional[time], verified: bool, holidays: frozenset[str] = frozenset()) -> MarketCalendar:
    """ZSE hours are CONFLICTING across sources at build time; pass verified=True only
    after broker confirmation. CAT = UTC+2, so 10:00 CAT = 08:00 UTC."""
    if open_utc is None or close_utc is None:
        return MarketCalendar("ZSE", (), None, None, holidays, hours_verified=False, tz_note="Africa/Harare (UTC+2)")
    return MarketCalendar("ZSE", (SessionWindow(Session.EXCHANGE_OPEN, open_utc, close_utc),), None, None, holidays, hours_verified=verified, tz_note="Africa/Harare (UTC+2)")


def session_at(cal: MarketCalendar, ts: datetime) -> Session:
    return cal.session_at(ts)
