"""Tier-1 event matrix (Rev 2 §14, Rev 3 C.3): blackout, quiet window, drift
window per instrument family. Times are UTC epoch ms; the calendar itself is
loaded from a T1 source at runtime and dual-verified; here we hold the rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


class EventWindowState(str, Enum):
    NONE = "NONE"
    PRE_BLACKOUT = "PRE_BLACKOUT"    # inside blackout before release: no new risk
    POST_BLACKOUT = "POST_BLACKOUT"  # inside blackout after release: no new risk
    QUIET = "QUIET"                  # after blackout, before drift window: event-certified only
    DRIFT = "DRIFT"                  # drift window: event-drift strategies eligible


@dataclass(frozen=True)
class Tier1Event:
    event_id: str
    name: str
    release_ms: int
    currencies: frozenset[str]          # affected currency legs, e.g. {"USD"}
    blackout_before_ms: int = 5 * 60_000
    blackout_after_ms: int = 15 * 60_000
    quiet_until_ms: int = 45 * 60_000   # from release
    drift_until_ms: int = 4 * 3_600_000 # from release
    verified_sources: int = 1           # dual-source verification count (≥2 required for live)

    def affects(self, base: str, quote: str) -> bool:
        return base in self.currencies or quote in self.currencies


@dataclass
class EventMatrix:
    events: list[Tier1Event] = field(default_factory=list)

    def add(self, e: Tier1Event) -> None:
        self.events.append(e)

    def state_at(self, now_ms: int, base: str, quote: str) -> tuple[EventWindowState, Optional[Tier1Event]]:
        best = (EventWindowState.NONE, None)
        rank = {EventWindowState.NONE: 0, EventWindowState.DRIFT: 1, EventWindowState.QUIET: 2, EventWindowState.POST_BLACKOUT: 3, EventWindowState.PRE_BLACKOUT: 3}
        for e in self.events:
            if not e.affects(base, quote):
                continue
            d = now_ms - e.release_ms
            if -e.blackout_before_ms <= d < 0:
                s = EventWindowState.PRE_BLACKOUT
            elif 0 <= d < e.blackout_after_ms:
                s = EventWindowState.POST_BLACKOUT
            elif e.blackout_after_ms <= d < e.quiet_until_ms:
                s = EventWindowState.QUIET
            elif e.quiet_until_ms <= d < e.drift_until_ms:
                s = EventWindowState.DRIFT
            else:
                continue
            if e.verified_sources < 2:
                # unverified release time: extend blackout to the whole pre-window (fail closed)
                s = EventWindowState.PRE_BLACKOUT if d < 0 else s
            if rank[s] > rank[best[0]]:
                best = (s, e)
        return best

    def minutes_to_next(self, now_ms: int, base: str, quote: str) -> Optional[int]:
        future = [e.release_ms - now_ms for e in self.events if e.affects(base, quote) and e.release_ms >= now_ms]
        return min(future) // 60_000 if future else None


DEFAULT_EVENT_MATRIX = EventMatrix()  # populated by the calendar adapter at runtime
