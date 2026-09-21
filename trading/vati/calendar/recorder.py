"""Economic Calendar Recorder (TRD-REV51-090, G0b).

The existing calendar loader tells the event matrix what is *scheduled*. That
is enough to black out a window and nothing else: it cannot say what the
number was, when it landed, which source said so, or whether two sources
disagreed. Every downstream Rev 5.1 event component — the normaliser (112),
the surprise engine (113), the episode producer (114) — needs that record, and
needs it to be the same record on replay months later.

Two rules shape the design.

**Nothing is overwritten.** A source that revises its number produces a new
observation; the earlier one stays. Revisions are ordinary in macro data
(payrolls are revised twice), and a store that mutates in place cannot answer
"what did we know at decision time", which is the only question a replay asks
(INV-REPLAY-001).

**One source is not a fact.** A value carried by a single source is
PROVISIONAL and never VERIFIED. Two sources that agree make it VERIFIED; two
that disagree make it DISPUTED, which is a louder state than "unknown" because
it means one of our inputs is wrong. Consumers that require certainty read
`verified_only`; consumers that can act on less read the status and decide.
Nothing here infers a value from a single source's confidence in itself.

Failure is quiet and safe: an unparseable row is counted and skipped, never
guessed at, and a recorder with no sources produces an empty record rather
than an optimistic one (INV-FAIL-001).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Optional

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event

PRODUCER = "vati-calendar-recorder"
RECORDER_VERSION = "calendar-recorder/5.1.0"

#: A release value is only VERIFIED when this many independent sources agree.
MIN_AGREEING_SOURCES = 2

#: Two sources are treated as agreeing when their values are identical after
#: normalisation. Macro prints are published to a fixed precision, so a
#: tolerance band here would only paper over a real feed defect.
EXACT_AGREEMENT_ONLY = True


class ReleaseStatus(str, Enum):
    SCHEDULED = "SCHEDULED"        # expected, nothing observed yet
    PROVISIONAL = "PROVISIONAL"    # one source only
    VERIFIED = "VERIFIED"          # >= MIN_AGREEING_SOURCES agree
    DISPUTED = "DISPUTED"          # sources disagree; one of them is wrong
    MISSED = "MISSED"              # release time passed with no observation


class ObservationConflict(ValueError):
    """An observation contradicts a sealed one from the same source."""


def _parse_ms(v: Any) -> int:
    s = str(v).strip()
    if s.isdigit():
        return int(s) * (1000 if len(s) <= 10 else 1)
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() * 1000)


def _opt_dec(v: Any) -> Optional[Decimal]:
    if v is None or str(v).strip() == "":
        return None
    try:
        return dec(str(v).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass(frozen=True)
class ScheduledRelease:
    """A release we expect. Identity is name + scheduled time + currencies."""

    event_key: str
    name: str
    scheduled_ms: int
    currencies: tuple[str, ...]
    tier: int = 1
    unit: str = ""
    forecast: Optional[Decimal] = None
    previous: Optional[Decimal] = None

    def body(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key, "name": self.name, "scheduled_ms": self.scheduled_ms,
            "currencies": list(self.currencies), "tier": self.tier, "unit": self.unit,
            "forecast": None if self.forecast is None else str(self.forecast),
            "previous": None if self.previous is None else str(self.previous),
        }


@dataclass(frozen=True)
class ReleaseObservation:
    """One source's claim about what a release printed."""

    event_key: str
    source: str
    actual: Optional[Decimal]
    observed_ms: int          # when we saw it
    released_ms: int          # when the source says it printed
    forecast: Optional[Decimal] = None
    previous: Optional[Decimal] = None
    revision_of: str = ""     # observation_id this supersedes, if any

    @property
    def observation_id(self) -> str:
        return canonical_hash(self.body())[:32]

    def body(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key, "source": self.source,
            "actual": None if self.actual is None else str(self.actual),
            "observed_ms": self.observed_ms, "released_ms": self.released_ms,
            "forecast": None if self.forecast is None else str(self.forecast),
            "previous": None if self.previous is None else str(self.previous),
            "revision_of": self.revision_of,
        }


@dataclass(frozen=True)
class ReleaseRecord:
    """The recorder's answer for one event: every observation, and the verdict."""

    scheduled: ScheduledRelease
    observations: tuple[ReleaseObservation, ...]
    status: ReleaseStatus
    agreed_actual: Optional[Decimal]
    agreeing_sources: tuple[str, ...]
    dissenting: tuple[tuple[str, str], ...]   # (source, value) pairs that disagree
    first_observed_ms: Optional[int]

    @property
    def event_key(self) -> str:
        return self.scheduled.event_key

    @property
    def latency_ms(self) -> Optional[int]:
        """How long after the scheduled time the first source reported.

        Negative means a source reported before the release was due, which is
        a feed defect rather than a scoop, and the surprise engine treats it
        as one.
        """
        if self.first_observed_ms is None:
            return None
        return self.first_observed_ms - self.scheduled.scheduled_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.scheduled.body(),
            "status": self.status.value,
            "agreed_actual": None if self.agreed_actual is None else str(self.agreed_actual),
            "agreeing_sources": list(self.agreeing_sources),
            "dissenting": [list(d) for d in self.dissenting],
            "observations": [o.body() for o in self.observations],
            "first_observed_ms": self.first_observed_ms,
            "latency_ms": self.latency_ms,
            "recorder_version": RECORDER_VERSION,
        }


class CalendarRecorder:
    """Append-only calendar record. Optionally mirrored into the VATI ledger."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._scheduled: dict[str, ScheduledRelease] = {}
        self._observed: dict[str, list[ReleaseObservation]] = {}
        self._seen: set[str] = set()
        self.skipped: list[dict[str, str]] = []

    # ------------------------------------------------------------- scheduling
    def schedule(self, release: ScheduledRelease) -> ScheduledRelease:
        prior = self._scheduled.get(release.event_key)
        if prior is not None and prior.body() != release.body():
            # A moved release time is a new event, not an edit of this one.
            raise ObservationConflict(
                f"{release.event_key} is already scheduled with different terms")
        if prior is None:
            self._scheduled[release.event_key] = release
            self._emit(EventKind.CALENDAR_SCHEDULE, release.body(),
                       event_ms=release.scheduled_ms, corr=release.event_key)
        return release

    # ------------------------------------------------------------ observation
    def observe(self, obs: ReleaseObservation) -> ReleaseObservation:
        """Record one source's claim. Idempotent on identical claims."""
        if obs.event_key not in self._scheduled:
            raise ObservationConflict(
                f"observation for unscheduled event {obs.event_key}; schedule it first")
        oid = obs.observation_id
        if oid in self._seen:
            return obs
        existing = [o for o in self._observed.get(obs.event_key, ())
                    if o.source == obs.source and o.actual is not None]
        if existing and obs.actual is not None and not obs.revision_of:
            prior = existing[-1]
            if prior.actual != obs.actual:
                # A source changing its mind is normal; pretending it did not
                # is what breaks replay. Make the supersession explicit.
                raise ObservationConflict(
                    f"{obs.source} already reported {prior.actual} for {obs.event_key}; "
                    f"a different value must carry revision_of={prior.observation_id}")
        self._seen.add(oid)
        self._observed.setdefault(obs.event_key, []).append(obs)
        self._emit(EventKind.CALENDAR_RELEASE, {**obs.body(), "observation_id": oid},
                   event_ms=obs.released_ms, corr=obs.event_key)
        return obs

    # ----------------------------------------------------------------- verdict
    def record(self, event_key: str, *, now_ms: Optional[int] = None) -> ReleaseRecord:
        sched = self._scheduled.get(event_key)
        if sched is None:
            raise KeyError(event_key)
        obs = tuple(sorted(self._observed.get(event_key, ()), key=lambda o: (o.observed_ms, o.source)))

        #: Only the newest non-superseded claim per source counts toward agreement.
        superseded = {o.revision_of for o in obs if o.revision_of}
        current: dict[str, ReleaseObservation] = {}
        for o in obs:
            if o.observation_id in superseded or o.actual is None:
                continue
            prev = current.get(o.source)
            if prev is None or o.observed_ms >= prev.observed_ms:
                current[o.source] = o

        by_value: dict[str, list[str]] = {}
        for source, o in current.items():
            by_value.setdefault(str(o.actual), []).append(source)

        first_ms = min((o.observed_ms for o in obs), default=None)

        if not current:
            due = now_ms is not None and now_ms > sched.scheduled_ms
            status = ReleaseStatus.MISSED if due else ReleaseStatus.SCHEDULED
            return ReleaseRecord(sched, obs, status, None, (), (), first_ms)

        best_value, best_sources = max(by_value.items(), key=lambda kv: (len(kv[1]), kv[0]))
        dissent = tuple(sorted(
            (s, v) for v, srcs in by_value.items() if v != best_value for s in srcs))

        if len(by_value) > 1:
            status = ReleaseStatus.DISPUTED
            agreed = None
        elif len(best_sources) >= MIN_AGREEING_SOURCES:
            status = ReleaseStatus.VERIFIED
            agreed = Decimal(best_value)
        else:
            status = ReleaseStatus.PROVISIONAL
            agreed = Decimal(best_value)

        return ReleaseRecord(sched, obs, status, agreed,
                             tuple(sorted(best_sources)), dissent, first_ms)

    def records(self, *, now_ms: Optional[int] = None) -> list[ReleaseRecord]:
        return [self.record(k, now_ms=now_ms)
                for k in sorted(self._scheduled, key=lambda k: self._scheduled[k].scheduled_ms)]

    def verified_only(self, *, now_ms: Optional[int] = None) -> list[ReleaseRecord]:
        return [r for r in self.records(now_ms=now_ms) if r.status is ReleaseStatus.VERIFIED]

    # -------------------------------------------------------------- ingestion
    def ingest_schedule(self, rows: Iterable[Mapping[str, Any]]) -> int:
        n = 0
        for row in rows:
            try:
                rel = scheduled_from_row(row)
            except Exception as exc:  # noqa: BLE001 — a bad row is skipped, never guessed
                self.skipped.append({"stage": "schedule", "row": str(row)[:200], "error": str(exc)})
                continue
            try:
                self.schedule(rel)
            except ObservationConflict as exc:
                self.skipped.append({"stage": "schedule", "row": rel.event_key, "error": str(exc)})
                continue
            n += 1
        return n

    def ingest_observations(self, rows: Iterable[Mapping[str, Any]]) -> int:
        n = 0
        for row in rows:
            try:
                obs = observation_from_row(row)
            except Exception as exc:  # noqa: BLE001
                self.skipped.append({"stage": "observe", "row": str(row)[:200], "error": str(exc)})
                continue
            try:
                self.observe(obs)
            except ObservationConflict as exc:
                self.skipped.append({"stage": "observe", "row": obs.event_key, "error": str(exc)})
                continue
            n += 1
        return n

    # ------------------------------------------------------------------ report
    def report(self, *, now_ms: Optional[int] = None) -> dict[str, Any]:
        recs = self.records(now_ms=now_ms)
        by_status: dict[str, int] = {}
        for r in recs:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        disputed = [r.event_key for r in recs if r.status is ReleaseStatus.DISPUTED]
        return {
            "recorder_version": RECORDER_VERSION,
            "scheduled": len(self._scheduled),
            "observations": sum(len(v) for v in self._observed.values()),
            "by_status": dict(sorted(by_status.items())),
            "disputed": disputed,
            "skipped": self.skipped,
            "now_ms": now_ms,
        }

    # -------------------------------------------------------------- internals
    def _emit(self, kind: EventKind, payload: dict, *, event_ms: int, corr: str) -> None:
        if self._ledger is None:
            return
        self._ledger.append(make_event(kind, self._producer, payload,
                                       event_time_ms=event_ms, received_time_ms=event_ms,
                                       correlation_id=corr))


# --------------------------------------------------------------------- parsing
def event_key(name: str, scheduled_ms: int) -> str:
    return f"{name.upper().replace(' ', '_')}:{scheduled_ms}"


def scheduled_from_row(row: Mapping[str, Any]) -> ScheduledRelease:
    name = str(row["name"]).upper().replace(" ", "_")
    ms = _parse_ms(row.get("scheduled") or row["release"])
    ccy = tuple(sorted({c.strip().upper() for c in str(row.get("currencies", "USD")).split("|") if c.strip()}))
    if not ccy:
        raise ValueError("no currencies")
    return ScheduledRelease(
        event_key=event_key(name, ms), name=name, scheduled_ms=ms, currencies=ccy,
        tier=int(row.get("tier", 1)), unit=str(row.get("unit", "")),
        forecast=_opt_dec(row.get("forecast")), previous=_opt_dec(row.get("previous")))


def observation_from_row(row: Mapping[str, Any]) -> ReleaseObservation:
    key = str(row.get("event_key") or "").strip()
    if not key:
        key = event_key(str(row["name"]), _parse_ms(row.get("scheduled") or row["release"]))
    released = _parse_ms(row.get("released") or row.get("scheduled") or row["release"])
    observed = _parse_ms(row["observed"]) if row.get("observed") else released
    source = str(row.get("source", "")).strip()
    if not source:
        raise ValueError("observation has no source")
    return ReleaseObservation(
        event_key=key, source=source, actual=_opt_dec(row.get("actual")),
        observed_ms=observed, released_ms=released,
        forecast=_opt_dec(row.get("forecast")), previous=_opt_dec(row.get("previous")),
        revision_of=str(row.get("revision_of", "")).strip())


def rows_from_file(path: str | Path, key: str = "events") -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return list(data)
        return list(data.get(key, []))
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
