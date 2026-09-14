from __future__ import annotations

from datetime import datetime, timezone

from van_gateway.reminders.timeparse import TimeParseError, parse_due_expression


def test_relative_and_tomorrow():
    now = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    assert parse_due_expression("in 30 minutes", now=now) == int((now.timestamp() + 1800))
    due = parse_due_expression("tomorrow at 2pm", now=now)
    assert due > int(now.timestamp())


def test_unknown_fails_closed():
    try:
        parse_due_expression("sometime soon")
        assert False, "expected fail"
    except TimeParseError:
        pass
