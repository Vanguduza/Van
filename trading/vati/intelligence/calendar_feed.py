"""Tier-1 economic calendar loader (NFP / Event Engine input). The matrix rules
live in `intelligence/events.py`; this module turns an owner-maintained or
vendor-exported calendar file into declared `Tier1Event`s. Source labels count
declared agreement, not publisher independence or native feed admission.
These files retain their blackout use and never grant live eligibility."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from vati.intelligence.events import EventMatrix, Tier1Event
from vati.core.calendar_time import parse_calendar_ms
from vati.calendar.recorder import declared_event_key,rows_from_file

TIER1_NAMES = {"NFP", "NONFARM_PAYROLLS", "CPI", "FOMC", "FOMC_RATE_DECISION", "ECB_RATE_DECISION", "BOE_RATE_DECISION", "GDP_ADVANCE", "ISM_MANUFACTURING", "PCE", "RETAIL_SALES", "JOLTS", "PPI", "UNEMPLOYMENT_CLAIMS"}


def _parse_ms(v: str) -> int:
    return parse_calendar_ms(v)


def events_from_records(records: Iterable[dict]) -> list[Tier1Event]:
    out: list[Tier1Event] = []
    seen: dict[str, dict] = {}
    for r in records:
        if not isinstance(r,dict):raise ValueError('calendar schedule row must be an object')
        name = str(r.get("name", "")).upper().replace(" ", "_")
        if name not in TIER1_NAMES and str(r.get("tier", "1")) != "1":
            continue
        release = _parse_ms(r['release'])
        currencies = frozenset(c.strip().upper() for c in str(r.get("currencies", "USD")).split("|") if c.strip())
        if not name or not currencies:raise ValueError('calendar event name and currency scope required')
        source = str(r.get("source", "owner")).strip()
        if not source:raise ValueError('calendar declared source label required')
        key = declared_event_key(r,name,release)
        e = seen.setdefault(key, {"name": name, "release": release, "currencies": currencies, "sources": set()})
        if (e['name'],e['release'],e['currencies'])!=(name,release,currencies):
            raise ValueError('calendar event key has conflicting time/name/currency scope; use original distinct keys')
        e["sources"].add(source)
    for key, e in sorted(seen.items(), key=lambda kv: (kv[1]['release'],kv[0])):
        out.append(Tier1Event(event_id=key, name=e["name"], release_ms=e["release"], currencies=e["currencies"], verified_sources=len(e["sources"])))
    return out


def load_calendar(path: str | Path) -> list[Tier1Event]:
    """JSON: {"events":[{name, release, currencies:"USD|EUR", source}]}  or CSV with the same columns.
    verified_sources is the legacy declared label count, never source admission."""
    return events_from_records(rows_from_file(path))


def build_matrix(path: str | Path | None) -> EventMatrix:
    m = EventMatrix()
    if path:
        for e in load_calendar(path):
            m.add(e)
    return m


def calendar_report(events: list[Tier1Event], *, now_ms: int) -> dict:
    upcoming = sorted((e for e in events if e.release_ms >= now_ms),key=lambda event:(event.release_ms,event.event_id))
    return {"events": len(events), "upcoming": len(upcoming), "live_eligible": 0,
            "declared_agreement": sum(1 for e in upcoming if e.verified_sources>=2),
            "provider_qualified":False,"authority_effect":"NONE",
            "source_state":"DECLARED_SCHEDULE_ONLY_NOT_NATIVE_FEED_ADMISSION",
            "unverified": [e.event_id for e in upcoming if e.verified_sources < 2][:20],
            "next": {"event_id": upcoming[0].event_id, "in_minutes": (upcoming[0].release_ms - now_ms) // 60_000} if upcoming else None}
