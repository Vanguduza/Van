"""MacroEventEpisode producer (TRD-REV51-114, G7b).

An episode is what remains once a release is old news: the surprise, what
followed it across every horizon, and enough context to find it again when
something similar happens. It is the unit the analogue index (097) retrieves
and the expansion laboratory (109) studies, so its worth depends entirely on
being an honest record rather than a tidy one.

Two decisions make it honest.

**Episodes close on the schedule, not on the data.** When the last horizon
passes, the episode closes with whatever it has, and horizons whose mark never
arrived are marked MISSING. The alternative — waiting for a complete set — has
the effect of silently dropping exactly the episodes where the venue went
quiet, which are the ones worth keeping.

**Unscoreable releases still produce an episode.** A release that could not be
scored, because it was DISPUTED or had no forecast, closes as UNSCORED. It is
a different fact from no release, and a sample that omits them would say
macro releases are always measurable (INV-EVID-001).

Conversion to an analogue episode is deliberately narrow. The feature vector
is the one the retrieval module already defines, so nothing here invents a
similarity dimension of its own, and episodes with no reaction data convert to
nothing rather than to a vector of defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.events.normaliser import NormalisedRelease
from vati.events.reaction import (
    HorizonReaction,
    MagnitudeClass,
    ReactionTrack,
    Surprise,
    SurpriseDirection,
)

PRODUCER = "vati-event-episode"
EPISODE_VERSION = "macro-event-episode/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")


class EpisodeState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"        # scored, with at least one horizon observed
    UNSCORED = "UNSCORED"    # the release could not be scored
    EMPTY = "EMPTY"          # closed with no horizon observed at all


@dataclass(frozen=True)
class MacroEventEpisode:
    episode_id: str
    event_key: str
    name: str
    symbol: str
    release_ms: int
    surprise: Surprise
    reactions: tuple[HorizonReaction, ...]
    state: EpisodeState
    closed_ms: Optional[int]
    episode_version: str = EPISODE_VERSION

    @property
    def observed_horizons(self) -> int:
        return sum(1 for r in self.reactions if r.mark is not None)

    @property
    def missing_horizons(self) -> int:
        return sum(1 for r in self.reactions if r.missing)

    @property
    def peak_move_in_ranges(self) -> Optional[Decimal]:
        moves = [r.move_in_ranges for r in self.reactions if r.move_in_ranges is not None]
        if not moves:
            return None
        return max(moves, key=abs)

    @property
    def move_direction(self) -> Optional[str]:
        """Which way the instrument went, at the last observed horizon.

        Reported beside the surprise direction and never reconciled with it.
        Whether a stronger USD print should push an instrument up or down
        depends on which side of the quote the currency sits, and on whether
        it is a currency exposure at all — the registry does not declare that,
        and guessing it here would encode an assumption that is simply wrong
        for every inverse-quoted pair. Learning the relationship is the
        laboratory's job; recording both honestly is this module's.
        """
        observed = [r for r in self.reactions if r.move_in_ranges is not None]
        if not observed:
            return None
        last = observed[-1].move_in_ranges
        if last > ZERO:
            return "UP"
        return "DOWN" if last < ZERO else "FLAT"

    def body(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "event_key": self.event_key,
            "name": self.name,
            "symbol": self.symbol,
            "release_ms": self.release_ms,
            "state": self.state.value,
            "closed_ms": self.closed_ms,
            "surprise": self.surprise.body(),
            "reactions": [r.body() for r in self.reactions],
            "observed_horizons": self.observed_horizons,
            "missing_horizons": self.missing_horizons,
            "peak_move_in_ranges": (None if self.peak_move_in_ranges is None
                                    else str(self.peak_move_in_ranges)),
            "move_direction": self.move_direction,
            "surprise_direction": self.surprise.direction.value,
            "episode_version": self.episode_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())

    # ------------------------------------------------------------- analogues
    def to_analogue_episode(self):
        """Convert to the retrieval module's Episode, or None.

        Narrow on purpose: the feature vector belongs to 097, and an episode
        with no reaction data converts to nothing rather than to defaults that
        would make it retrievable as if it were evidence.
        """
        from vati.cognition.analogues import Episode, EpisodeFeatures

        if self.state is not EpisodeState.CLOSED or self.peak_move_in_ranges is None:
            return None
        z = self.surprise.z or ZERO
        magnitude = {MagnitudeClass.LARGE: Decimal("1.0"),
                     MagnitudeClass.MODERATE: Decimal("0.6"),
                     MagnitudeClass.SMALL: Decimal("0.3"),
                     MagnitudeClass.NONE: ZERO}[self.surprise.magnitude]
        move = abs(self.peak_move_in_ranges)
        features = EpisodeFeatures(
            regime=_clamp(magnitude),
            event_proximity=ONE,                      # this is an event episode
            volatility_percentile=_clamp(move / Decimal("4")),
            trend_strength=_clamp((z + Decimal("4")) / Decimal("8")),
            spread_percentile=Decimal("0.5"),         # not measured in this record
            liquidity_percentile=Decimal("0.5"),
            session_bucket=_session_bucket(self.release_ms),
        )
        return Episode(episode_id=self.episode_id, symbol=self.symbol,
                       occurred_ms=self.release_ms, features=features,
                       outcome_r=self.peak_move_in_ranges,
                       label=f"{self.name} {self.surprise.direction.value}")


def _clamp(v: Decimal) -> Decimal:
    if v < ZERO:
        return ZERO
    return ONE if v > ONE else v


def _session_bucket(release_ms: int) -> Decimal:
    """Hour of the UTC day, normalised. Deterministic and arithmetic only."""
    hour = (release_ms // 3_600_000) % 24
    return Decimal(hour) / Decimal(24)


class EpisodeProducer:
    """Closes episodes when their horizons finish or expire."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._open: dict[str, tuple[NormalisedRelease, Surprise]] = {}
        self._closed: dict[str, MacroEventEpisode] = {}

    def open(self, release: NormalisedRelease, surprise: Surprise) -> str:
        self._open[release.event_key] = (release, surprise)
        return release.event_key

    def close(self, *, event_key: str, track: Optional[ReactionTrack],
              now_ms: int) -> MacroEventEpisode:
        entry = self._open.get(event_key)
        if entry is None:
            raise KeyError(event_key)
        release, surprise = entry
        reactions = track.all_reactions(now_ms=now_ms) if track is not None else ()
        observed = sum(1 for r in reactions if r.mark is not None)

        if not surprise.scored:
            state = EpisodeState.UNSCORED
        elif observed == 0:
            state = EpisodeState.EMPTY
        else:
            state = EpisodeState.CLOSED

        symbol = track.symbol if track is not None else ""
        episode = MacroEventEpisode(
            episode_id=canonical_hash({"e": event_key, "s": symbol})[:32],
            event_key=event_key, name=release.name, symbol=symbol,
            release_ms=release.released_ms, surprise=surprise,
            reactions=reactions, state=state, closed_ms=now_ms)
        self._closed[episode.episode_id] = episode

        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.MACRO_EVENT_EPISODE, self._producer, episode.body(),
                event_time_ms=release.released_ms, received_time_ms=now_ms,
                correlation_id=event_key))
        return episode

    def close_due(self, *, tracks: Sequence[ReactionTrack], now_ms: int,
                  ) -> list[MacroEventEpisode]:
        """Close every open episode whose last horizon has passed.

        Closing on the schedule rather than on the data is what stops the
        sample quietly excluding the releases where the venue went quiet.
        """
        out: list[MacroEventEpisode] = []
        by_key: dict[str, list[ReactionTrack]] = {}
        for t in tracks:
            by_key.setdefault(t.event_key, []).append(t)
        closed_keys: set[str] = set()
        for event_key in sorted(self._open):
            release, _ = self._open[event_key]
            event_tracks = sorted(by_key.get(event_key, ()), key=lambda t: t.symbol)
            last_horizon = max(
                (max(t.horizons_ms) for t in event_tracks),
                default=0,
            )
            if now_ms < release.released_ms + last_horizon:
                continue
            if event_tracks:
                for track in event_tracks:
                    out.append(self.close(
                        event_key=event_key, track=track, now_ms=now_ms))
            else:
                out.append(self.close(event_key=event_key, track=None, now_ms=now_ms))
            closed_keys.add(event_key)
        for event_key in closed_keys:
            self._open.pop(event_key, None)
        return out

    def episodes(self, *, state: Optional[EpisodeState] = None) -> list[MacroEventEpisode]:
        return sorted((e for e in self._closed.values() if state is None or e.state is state),
                      key=lambda e: (e.release_ms, e.episode_id))

    def analogue_episodes(self) -> list:
        out = [e.to_analogue_episode() for e in self.episodes()]
        return [e for e in out if e is not None]
