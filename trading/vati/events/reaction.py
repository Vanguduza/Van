"""Event surprise and reaction engine (TRD-REV51-113, G7b).

Two numbers, kept deliberately separate.

**Surprise** is what the release said against what was expected, divided by
how much that release usually misses by. The scale comes from the event class
(115) and the engine refuses to invent one: without a scale the same absolute
miss would look enormous for a rate decision and trivial for payrolls, and a
default would be a guess wearing a z-score.

**Reaction** is what the market actually did, measured at declared horizons in
units of the instrument's own recent range. Price units are useless for
comparison across instruments and so are percentages — a 0.3% move in EURUSD
and in a volatility index are not the same event. Range units make a move
comparable to the instrument's own normal day.

They are separate because their relationship is the interesting part. The
surprise is known within seconds; the reaction takes hours, and the point of
recording both is to learn where they disagree. Nothing here predicts the
second from the first, and nothing here sizes anything: this is measurement
feeding the analogue index and the offline laboratory.

Horizons are declared up front and scored when they complete. A horizon whose
mark never arrives expires as MISSING rather than being filled with the last
price seen — a reaction measured against a stale mark is worse than no
reaction, because it looks like data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.events.normaliser import NormalisedRelease

PRODUCER = "vati-event-reaction"
REACTION_VERSION = "event-reaction/5.1.0"

ZERO = Decimal("0")

#: Horizons measured after every release, in milliseconds. The first is the
#: knee-jerk, the last is after the market has had time to disagree with it.
DEFAULT_HORIZONS_MS: tuple[int, ...] = (60_000, 300_000, 1_800_000, 14_400_000)

#: |z| boundaries between magnitude classes.
LARGE_SURPRISE_Z = Decimal("2")
MODERATE_SURPRISE_Z = Decimal("1")


class SurpriseDirection(str, Enum):
    STRONGER = "STRONGER"
    WEAKER = "WEAKER"
    INLINE = "INLINE"


class MagnitudeClass(str, Enum):
    LARGE = "LARGE"
    MODERATE = "MODERATE"
    SMALL = "SMALL"
    NONE = "NONE"        # no scoreable surprise


@dataclass(frozen=True)
class Surprise:
    event_key: str
    name: str
    z: Optional[Decimal]
    direction: SurpriseDirection
    magnitude: MagnitudeClass
    deviation: Optional[Decimal]
    scale: Optional[Decimal]
    scored: bool
    detail: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "event_key": self.event_key, "name": self.name,
            "z": None if self.z is None else str(self.z),
            "direction": self.direction.value, "magnitude": self.magnitude.value,
            "deviation": None if self.deviation is None else str(self.deviation),
            "scale": None if self.scale is None else str(self.scale),
            "scored": self.scored, "detail": self.detail,
        }


@dataclass(frozen=True)
class HorizonReaction:
    horizon_ms: int
    mark: Optional[Decimal]
    move_in_ranges: Optional[Decimal]
    observed_ms: Optional[int]
    missing: bool

    def body(self) -> dict[str, Any]:
        return {
            "horizon_ms": self.horizon_ms,
            "mark": None if self.mark is None else str(self.mark),
            "move_in_ranges": None if self.move_in_ranges is None else str(self.move_in_ranges),
            "observed_ms": self.observed_ms, "missing": self.missing,
        }


@dataclass
class ReactionTrack:
    """One instrument's reaction to one release, across its horizons."""

    event_key: str
    symbol: str
    release_ms: int
    baseline_mark: Decimal
    typical_range: Decimal
    horizons_ms: tuple[int, ...]
    marks: dict[int, tuple[Decimal, int]] = field(default_factory=dict)

    def record(self, *, horizon_ms: int, mark: Decimal, observed_ms: int) -> None:
        if horizon_ms not in self.horizons_ms:
            raise KeyError(f"{horizon_ms} is not a declared horizon for {self.event_key}")
        self.marks.setdefault(horizon_ms, (dec(mark), observed_ms))

    def reaction(self, horizon_ms: int, *, now_ms: Optional[int] = None) -> HorizonReaction:
        got = self.marks.get(horizon_ms)
        if got is None:
            due = now_ms is not None and now_ms >= self.release_ms + horizon_ms
            return HorizonReaction(horizon_ms, None, None, None, missing=bool(due))
        mark, observed = got
        if self.typical_range <= ZERO:
            return HorizonReaction(horizon_ms, mark, None, observed, missing=False)
        return HorizonReaction(horizon_ms, mark,
                               (mark - self.baseline_mark) / self.typical_range,
                               observed, missing=False)

    def all_reactions(self, *, now_ms: Optional[int] = None) -> tuple[HorizonReaction, ...]:
        return tuple(self.reaction(h, now_ms=now_ms) for h in self.horizons_ms)

    def complete(self, *, now_ms: int) -> bool:
        """Every horizon has either a mark or has passed without one."""
        return all(r.mark is not None or r.missing
                   for r in self.all_reactions(now_ms=now_ms))


class ReactionEngine:
    """Scores surprises and tracks what followed them."""

    def __init__(self, *, horizons_ms: Sequence[int] = DEFAULT_HORIZONS_MS,
                 ledger=None, producer: str = PRODUCER) -> None:
        if not horizons_ms:
            raise ValueError("a reaction with no horizons measures nothing")
        self.horizons_ms = tuple(sorted(set(int(h) for h in horizons_ms)))
        self._ledger = ledger
        self._producer = producer
        self._tracks: dict[tuple[str, str], ReactionTrack] = {}

    # ------------------------------------------------------------- surprise
    def score(self, release: NormalisedRelease) -> Surprise:
        if not release.usable:
            return Surprise(release.event_key, release.name, None,
                            SurpriseDirection.INLINE, MagnitudeClass.NONE,
                            release.deviation, release.surprise_scale, False,
                            detail=f"release not scoreable: "
                                   f"{release.unusable_reason.value if release.unusable_reason else ''}")
        deviation, scale = release.deviation, release.surprise_scale
        if deviation is None or scale is None or scale <= ZERO:
            # Refused rather than defaulted: a default scale is a guess
            # wearing a z-score.
            return Surprise(release.event_key, release.name, None,
                            SurpriseDirection.INLINE, MagnitudeClass.NONE,
                            deviation, scale, False, detail="no usable surprise scale")

        z = deviation / scale
        if z > ZERO:
            direction = SurpriseDirection.STRONGER
        elif z < ZERO:
            direction = SurpriseDirection.WEAKER
        else:
            direction = SurpriseDirection.INLINE

        a = abs(z)
        if a >= LARGE_SURPRISE_Z:
            magnitude = MagnitudeClass.LARGE
        elif a >= MODERATE_SURPRISE_Z:
            magnitude = MagnitudeClass.MODERATE
        else:
            magnitude = MagnitudeClass.SMALL

        out = Surprise(release.event_key, release.name, z, direction, magnitude,
                       deviation, scale, True)
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.EVENT_REACTION, self._producer,
                {"surprise": out.body(), "release": release.body()},
                event_time_ms=release.released_ms, received_time_ms=release.released_ms,
                correlation_id=release.event_key))
        return out

    # ------------------------------------------------------------- reaction
    def track(self, *, event_key: str, symbol: str, release_ms: int,
              baseline_mark: Decimal, typical_range: Decimal) -> ReactionTrack:
        key = (event_key, symbol)
        if key not in self._tracks:
            self._tracks[key] = ReactionTrack(
                event_key=event_key, symbol=symbol, release_ms=release_ms,
                baseline_mark=dec(baseline_mark), typical_range=dec(typical_range),
                horizons_ms=self.horizons_ms)
        return self._tracks[key]

    def record_mark(self, *, event_key: str, symbol: str, horizon_ms: int,
                    mark: Decimal, observed_ms: int) -> ReactionTrack:
        t = self._tracks.get((event_key, symbol))
        if t is None:
            raise KeyError(f"no track for {event_key}/{symbol}")
        t.record(horizon_ms=horizon_ms, mark=mark, observed_ms=observed_ms)
        return t

    def tracks_for(self, event_key: str) -> list[ReactionTrack]:
        return sorted((t for (k, _s), t in self._tracks.items() if k == event_key),
                      key=lambda t: t.symbol)

    def complete_tracks(self, *, now_ms: int) -> list[ReactionTrack]:
        return sorted((t for t in self._tracks.values() if t.complete(now_ms=now_ms)),
                      key=lambda t: (t.event_key, t.symbol))
