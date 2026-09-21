"""Ledger-driven macro event research runtime (TRD-REV51-112..115).

CalendarRecorder remains the source of release observations.  This runtime consumes those
durable facts, normalises verified releases, scores surprise, schedules deterministic
reaction horizons and closes macro-event episodes.  It never authorises a trade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Optional

from vati.calendar.recorder import (
    CalendarRecorder, ReleaseObservation, ScheduledRelease,
)
from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind
from vati.events.episodes import EpisodeProducer
from vati.events.normaliser import ReleaseNormaliser
from vati.events.reaction import DEFAULT_HORIZONS_MS, ReactionEngine
from vati.events.registry import (
    AssetClass, EventRegistry, InstrumentExposure,
)

DEFAULT_BASELINE_LAG_MS = 60_000
DEFAULT_HORIZON_LAG_MS = 60_000


def infer_instrument_exposure(*, symbol: str, venue: str, base: str, quote: str,
                              is_synthetic: bool = False) -> InstrumentExposure:
    """Conservative default exposure used by the trading service at startup."""
    s, v, b, q = symbol.upper(), venue.lower(), base.upper(), quote.upper()
    if is_synthetic:
        cls = AssetClass.SYNTHETIC
        currencies = frozenset()
    elif v in ("zse", "vfex") or s.endswith((".ZW", ".VFEX")):
        cls = AssetClass.EQUITY
        currencies = frozenset({q}) if q else frozenset()
    elif b in {"XAU", "XAG", "XPT", "XPD"}:
        cls = AssetClass.METAL
        currencies = frozenset({q}) if q else frozenset()
    elif b in {"BTC", "ETH", "SOL", "XRP", "ADA"}:
        cls = AssetClass.CRYPTO
        currencies = frozenset({q}) if q else frozenset()
    else:
        cls = AssetClass.FX
        currencies = frozenset(x for x in (b, q) if x)
    return InstrumentExposure(s, venue, cls, currencies)


class EventResearchRuntime:
    """Persistent event-release -> reaction -> episode coordinator.

    Marks are accepted only near the horizon they claim to measure.  A late mark is not
    backfilled into an earlier horizon; that horizon remains missing, which is evidence.
    """

    def __init__(self, registry: EventRegistry, *, ledger,
                 horizons_ms=DEFAULT_HORIZONS_MS,
                 baseline_lag_ms: int = DEFAULT_BASELINE_LAG_MS,
                 horizon_lag_ms: int = DEFAULT_HORIZON_LAG_MS) -> None:
        self.registry = registry
        self.ledger = ledger
        self.normaliser = ReleaseNormaliser(registry, ledger=ledger)
        self.reactions = ReactionEngine(horizons_ms=horizons_ms, ledger=ledger)
        self.episodes = EpisodeProducer(ledger=ledger)
        self.baseline_lag_ms = baseline_lag_ms
        self.horizon_lag_ms = horizon_lag_ms
        self._processed_record: dict[str, str] = {}
        self._releases = {}

    def _calendar(self) -> CalendarRecorder:
        recorder = CalendarRecorder()
        for event in self.ledger.iter(EventKind.CALENDAR_SCHEDULE):
            p = event.payload
            recorder.schedule(ScheduledRelease(
                event_key=str(p["event_key"]),
                name=str(p["name"]),
                scheduled_ms=int(p["scheduled_ms"]),
                currencies=tuple(str(x) for x in p.get("currencies", ())),
                tier=int(p.get("tier", 1)),
                unit=str(p.get("unit", "")),
                forecast=(None if p.get("forecast") is None else dec(p["forecast"])),
                previous=(None if p.get("previous") is None else dec(p["previous"])),
            ))
        for event in self.ledger.iter(EventKind.CALENDAR_RELEASE):
            p = event.payload
            recorder.observe(ReleaseObservation(
                event_key=str(p["event_key"]),
                source=str(p["source"]),
                actual=(None if p.get("actual") is None else dec(p["actual"])),
                observed_ms=int(p["observed_ms"]),
                released_ms=int(p["released_ms"]),
                forecast=(None if p.get("forecast") is None else dec(p["forecast"])),
                previous=(None if p.get("previous") is None else dec(p["previous"])),
                revision_of=str(p.get("revision_of") or ""),
            ))
        return recorder

    def sync_calendar(self, *, now_ms: int) -> list[str]:
        """Consume changed release records. Returns event keys newly processed."""
        recorder = self._calendar()
        changed: list[str] = []
        for record in recorder.records(now_ms=now_ms):
            if not record.observations:
                continue
            digest = canonical_hash(record.to_dict())
            if self._processed_record.get(record.event_key) == digest:
                continue
            release = self.normaliser.normalise(record, now_ms=now_ms)
            surprise = self.reactions.score(release)
            self.episodes.open(release, surprise)
            self._releases[release.event_key] = release
            self._processed_record[record.event_key] = digest
            changed.append(record.event_key)
        return changed

    def on_mark(self, *, symbol: str, mark: Decimal, observed_ms: int,
                typical_range: Decimal) -> list:
        """Feed one real market mark and close any episodes whose horizons are due."""
        self.sync_calendar(now_ms=observed_ms)
        symbol = symbol.upper()
        mark = dec(mark)
        typical_range = dec(typical_range)

        for event_key, release in sorted(self._releases.items()):
            if observed_ms < release.released_ms:
                continue
            if not self.registry.affects(release.name, symbol):
                continue
            tracks = {t.symbol: t for t in self.reactions.tracks_for(event_key)}
            track = tracks.get(symbol)
            if track is None:
                lag = observed_ms - release.released_ms
                if lag < 0 or lag > self.baseline_lag_ms:
                    continue
                track = self.reactions.track(
                    event_key=event_key, symbol=symbol,
                    release_ms=release.released_ms,
                    baseline_mark=mark, typical_range=typical_range,
                )

            for horizon in track.horizons_ms:
                if horizon in track.marks:
                    continue
                due = release.released_ms + horizon
                lag = observed_ms - due
                if 0 <= lag <= self.horizon_lag_ms:
                    self.reactions.record_mark(
                        event_key=event_key, symbol=symbol,
                        horizon_ms=horizon, mark=mark, observed_ms=observed_ms)

        tracks = [
            t for event_key in sorted(self._releases)
            for t in self.reactions.tracks_for(event_key)
        ]
        closed = self.episodes.close_due(tracks=tracks, now_ms=observed_ms)
        for ep in closed:
            # close_due may emit multiple symbol episodes for the same event.
            # Retire the release after the producer has closed its event.
            if ep.event_key not in getattr(self.episodes, "_open", {}):
                self._releases.pop(ep.event_key, None)
        return closed

    def report(self, *, now_ms: int) -> dict:
        self.sync_calendar(now_ms=now_ms)
        return {
            "registry_digest": self.registry.digest,
            "processed_release_records": len(self._processed_record),
            "open_releases": sorted(self._releases),
            "tracks": sum(len(self.reactions.tracks_for(k)) for k in self._releases),
            "episodes": len(self.episodes.episodes()),
            "non_authoritative": True,
        }
