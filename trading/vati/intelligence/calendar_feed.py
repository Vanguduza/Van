"""Tier-1 economic calendar loader (NFP / Event Engine input). The matrix rules
live in `intelligence/events.py`; this module turns an owner-maintained or
vendor-exported calendar file into verified `Tier1Event`s. A release time is
LIVE-eligible only when two independent sources agree (verified_sources ≥ 2);
otherwise the matrix fails closed (whole pre-window is blackout)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from vati.intelligence.events import EventMatrix, Tier1Event

TIER1_NAMES = {"NFP", "NONFARM_PAYROLLS", "CPI", "FOMC", "FOMC_RATE_DECISION", "ECB_RATE_DECISION", "BOE_RATE_DECISION", "GDP_ADVANCE", "ISM_MANUFACTURING", "PCE", "RETAIL_SALES", "JOLTS", "PPI", "UNEMPLOYMENT_CLAIMS"}


def _parse_ms(v: str) -> int:
    v = v.strip()
    if v.isdigit():
        return int(v) * (1000 if len(v) <= 10 else 1)
    return int(datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() * 1000)


def events_from_records(records: Iterable[dict]) -> list[Tier1Event]:
    out: list[Tier1Event] = []
    seen: dict[str, dict] = {}
    for r in records:
        name = str(r.get("name", "")).upper().replace(" ", "_")
        if name not in TIER1_NAMES and str(r.get("tier", "1")) != "1":
            continue
        release = _parse_ms(str(r["release"]))
        currencies = frozenset(c.strip().upper() for c in str(r.get("currencies", "USD")).split("|") if c.strip())
        source = str(r.get("source", "owner"))
        key = f"{name}:{release}"
        e = seen.setdefault(key, {"name": name, "release": release, "currencies": currencies, "sources": set()})
        e["sources"].add(source)
    for key, e in sorted(seen.items(), key=lambda kv: kv[1]["release"]):
        out.append(Tier1Event(event_id=key, name=e["name"], release_ms=e["release"], currencies=e["currencies"], verified_sources=len(e["sources"])))
    return out


def load_calendar(path: str | Path) -> list[Tier1Event]:
    """JSON: {"events":[{name, release, currencies:"USD|EUR", source}]}  or CSV with the same columns.
    Two rows for the same event from different sources → verified_sources = 2."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return events_from_records(data.get("events", data if isinstance(data, list) else []))
    with open(p, newline="", encoding="utf-8") as f:
        return events_from_records(csv.DictReader(f))


def build_matrix(path: str | Path | None) -> EventMatrix:
    m = EventMatrix()
    if path:
        for e in load_calendar(path):
            m.add(e)
    return m


def calendar_report(events: list[Tier1Event], *, now_ms: int) -> dict:
    upcoming = [e for e in events if e.release_ms >= now_ms]
    return {"events": len(events), "upcoming": len(upcoming), "live_eligible": sum(1 for e in upcoming if e.verified_sources >= 2),
            "unverified": [e.event_id for e in upcoming if e.verified_sources < 2][:20],
            "next": {"event_id": upcoming[0].event_id, "in_minutes": (upcoming[0].release_ms - now_ms) // 60_000} if upcoming else None}
