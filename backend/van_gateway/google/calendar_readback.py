"""Compare independently fetched calendar content with the approved write."""
from __future__ import annotations

from datetime import datetime
from typing import Any

_FIELDS = {"summary", "start", "end", "location", "description", "attendees", "recurrence"}


def _matches(expected: Any, observed: Any, key: str = "") -> bool:
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            field in observed and _matches(value, observed[field], field)
            for field, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) != len(observed):
            return False
        if key == "attendees":
            # Provider may reorder attendees and add response metadata.
            remaining = list(observed)
            for attendee in expected:
                match = next((i for i, item in enumerate(remaining) if _matches(attendee, item)), None)
                if match is None:
                    return False
                remaining.pop(match)
            return True
        return all(_matches(a, b) for a, b in zip(expected, observed))
    if key == "dateTime":
        try:
            a = datetime.fromisoformat(str(expected).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
            return a.tzinfo is not None and b.tzinfo is not None and a == b
        except (TypeError, ValueError):
            return False
    return type(expected) is type(observed) and expected == observed


def event_content_matches(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    body = {key: value for key, value in expected.items() if key in _FIELDS}
    if not str(body.get("summary") or "").strip():
        return False
    if any(not isinstance(body.get(key), dict) or not body[key] for key in ("start", "end")):
        return False
    return observed.get("status") != "cancelled" and _matches(body, observed)
