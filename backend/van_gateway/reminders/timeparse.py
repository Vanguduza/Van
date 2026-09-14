from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


RELATIVE_RE = re.compile(
    r"(?i)^\s*(?:in\s+)?(?P<n>\d+)\s*(?P<u>seconds?|minutes?|mins?|hours?|hrs?|days?)\s*$"
)
TOMORROW_RE = re.compile(r"(?i)^\s*tomorrow(?:\s+at\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?)?\s*$")
AT_RE = re.compile(r"(?i)^\s*at\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?\s*$")


class TimeParseError(ValueError):
    pass


def parse_due_expression(expr: str, *, now: datetime | None = None) -> int:
    """Parse relative/absolute owner phrases into unix seconds. Fail closed on ambiguity."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    text = expr.strip()
    if text.isdigit():
        return int(text)

    m = RELATIVE_RE.match(text)
    if m:
        n = int(m.group("n"))
        u = m.group("u").lower()
        if u.startswith("sec"):
            delta = timedelta(seconds=n)
        elif u.startswith("min"):
            delta = timedelta(minutes=n)
        elif u.startswith("hour") or u.startswith("hr"):
            delta = timedelta(hours=n)
        else:
            delta = timedelta(days=n)
        return int((now + delta).timestamp())

    m = TOMORROW_RE.match(text)
    if m:
        target = (now + timedelta(days=1)).replace(second=0, microsecond=0)
        if m.group("h"):
            hour = int(m.group("h"))
            minute = int(m.group("m") or 0)
            ampm = (m.group("ampm") or "").lower()
            hour = _to_24h(hour, ampm)
            target = target.replace(hour=hour, minute=minute)
        else:
            target = target.replace(hour=9, minute=0)
        return int(target.timestamp())

    m = AT_RE.match(text)
    if m:
        hour = _to_24h(int(m.group("h")), (m.group("ampm") or "").lower())
        minute = int(m.group("m") or 0)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        return int(target.timestamp())

    raise TimeParseError(f"unrecognized_time_expression:{expr}")


def _to_24h(hour: int, ampm: str) -> int:
    if hour < 0 or hour > 23:
        raise TimeParseError("invalid_hour")
    if ampm == "pm" and hour < 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    return hour
