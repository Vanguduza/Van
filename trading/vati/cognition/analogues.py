"""Deterministic analogue retrieval (TRD-REV51-097, G3).

"Have we seen this before?" is the most useful question to put in front of a
model, and the most dangerous one to answer with an embedding. An embedding
index is a moving target: it changes when the encoder changes, it cannot be
recomputed from the ledger months later, and it gives no account of *why* two
situations were judged similar. A context built on one is not replayable, and
INV-REPLAY-001 is not negotiable for anything that feeds an externally
consequential decision.

So retrieval here is arithmetic over a fixed, named feature vector. Each
feature is normalised to [0, 1] at construction, distance is weighted L1, and
ties break on episode id. Given the same index and the same query it returns
the same episodes in the same order, forever, on any machine.

The weights are the interesting part and they are deliberately visible. They
say what "similar" means for this system: regime and event proximity dominate,
because a setup that looks identical on price but sits on the wrong side of a
rate decision is not the same setup. They are starting points, not measured
optima — the expansion laboratory (109) and the decision exam (102) are how
they get argued with.

Retrieval also reports its own thinness. `coverage` and `mean_distance` are
returned alongside the episodes so the caller can cite ANALOGUE_ABSENT or
EVIDENCE_THIN rather than treating three vaguely similar days as a precedent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash, dec

RETRIEVAL_VERSION = "analogue-retrieval/5.1.0"

#: What "similar" means, as numbers rather than as a paragraph.
#:
#: regime and event_proximity carry the most weight because they change what a
#: pattern *means* rather than how it looks: the same pullback into the same
#: moving average is a different trade the hour before a rate decision.
#: session_bucket is light — it separates Tokyo from New York without letting
#: the clock dominate a genuine structural match.
FEATURE_WEIGHTS: dict[str, Decimal] = {
    "regime": Decimal("0.25"),
    "event_proximity": Decimal("0.20"),
    "volatility_percentile": Decimal("0.15"),
    "trend_strength": Decimal("0.15"),
    "spread_percentile": Decimal("0.10"),
    "liquidity_percentile": Decimal("0.08"),
    "session_bucket": Decimal("0.07"),
}

#: Beyond this weighted distance two situations are not analogues, however
#: few better ones exist. A retrieval that returns its least-bad match is how
#: a thin sample becomes a confident answer.
MAX_ANALOGUE_DISTANCE = Decimal("0.35")

#: Fewer than this many in-scope episodes and the retrieval reports itself as
#: thin, whatever the distances say.
MIN_COVERAGE_FOR_CONFIDENCE = 30

ZERO, ONE = Decimal("0"), Decimal("1")


class FeatureError(ValueError):
    pass


@dataclass(frozen=True)
class EpisodeFeatures:
    """A situation reduced to the dimensions retrieval compares.

    Every value is a fraction in [0, 1]. Callers normalise at the boundary,
    where the units are known; doing it here would need the historical
    distribution, which is exactly the moving target this module avoids.
    """

    regime: Decimal
    event_proximity: Decimal
    volatility_percentile: Decimal
    trend_strength: Decimal
    spread_percentile: Decimal
    liquidity_percentile: Decimal
    session_bucket: Decimal

    def __post_init__(self) -> None:
        for name in FEATURE_WEIGHTS:
            v = getattr(self, name)
            if not isinstance(v, Decimal):
                raise FeatureError(f"{name} must be a Decimal, got {type(v).__name__}")
            if not (ZERO <= v <= ONE):
                raise FeatureError(f"{name}={v} is outside [0, 1]; normalise at the boundary")

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "EpisodeFeatures":
        missing = sorted(set(FEATURE_WEIGHTS) - set(m))
        if missing:
            raise FeatureError(f"missing features: {', '.join(missing)}")
        return cls(**{k: dec(m[k]) for k in FEATURE_WEIGHTS})

    def body(self) -> dict[str, str]:
        return {k: str(getattr(self, k)) for k in sorted(FEATURE_WEIGHTS)}

    def distance_to(self, other: "EpisodeFeatures") -> Decimal:
        """Weighted L1. Weights sum to 1, so the result is itself in [0, 1]."""
        total = ZERO
        for name, w in FEATURE_WEIGHTS.items():
            total += w * abs(getattr(self, name) - getattr(other, name))
        return total


@dataclass(frozen=True)
class Episode:
    """One historical situation and what came of it."""

    episode_id: str
    symbol: str
    occurred_ms: int
    features: EpisodeFeatures
    #: What actually happened, as the attribution engine measured it (101).
    outcome_r: Optional[Decimal] = None     # realised result in R multiples
    strategy_id: str = ""
    label: str = ""                          # owner-readable, never parsed

    def body(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id, "symbol": self.symbol,
            "occurred_ms": self.occurred_ms, "features": self.features.body(),
            "outcome_r": None if self.outcome_r is None else str(self.outcome_r),
            "strategy_id": self.strategy_id, "label": self.label,
        }


@dataclass(frozen=True)
class Analogue:
    episode: Episode
    distance: Decimal

    def body(self) -> dict[str, Any]:
        return {**self.episode.body(), "distance": str(self.distance)}


@dataclass(frozen=True)
class RetrievalResult:
    """Analogues plus an honest account of how much there was to choose from."""

    analogues: tuple[Analogue, ...]
    coverage: int                 # in-scope episodes considered
    mean_distance: Optional[Decimal]
    query_features: EpisodeFeatures
    retrieval_version: str = RETRIEVAL_VERSION

    @property
    def is_thin(self) -> bool:
        return self.coverage < MIN_COVERAGE_FOR_CONFIDENCE or not self.analogues

    @property
    def is_absent(self) -> bool:
        return not self.analogues

    @property
    def mean_outcome_r(self) -> Optional[Decimal]:
        vals = [a.episode.outcome_r for a in self.analogues if a.episode.outcome_r is not None]
        if not vals:
            return None
        return sum(vals, ZERO) / Decimal(len(vals))

    def reason_codes(self) -> tuple[str, ...]:
        """The vocabulary terms this retrieval justifies, if any."""
        if self.is_absent:
            return ("ANALOGUE_ABSENT",)
        if self.is_thin:
            return ("EVIDENCE_THIN",)
        return ()

    def body(self) -> dict[str, Any]:
        return {
            "retrieval_version": self.retrieval_version,
            "query": self.query_features.body(),
            "coverage": self.coverage,
            "mean_distance": None if self.mean_distance is None else str(self.mean_distance),
            "mean_outcome_r": None if self.mean_outcome_r is None else str(self.mean_outcome_r),
            "is_thin": self.is_thin,
            "reason_codes": list(self.reason_codes()),
            "analogues": [a.body() for a in self.analogues],
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class AnalogueIndex:
    """A flat, ordered, hashable index. No encoder, no state beyond episodes."""

    def __init__(self, episodes: Optional[Iterable[Episode]] = None) -> None:
        self._episodes: dict[str, Episode] = {}
        for e in episodes or ():
            self.add(e)

    def add(self, episode: Episode) -> Episode:
        prior = self._episodes.get(episode.episode_id)
        if prior is not None and prior.body() != episode.body():
            raise FeatureError(
                f"episode {episode.episode_id} is already indexed with different features")
        self._episodes[episode.episode_id] = episode
        return episode

    def __len__(self) -> int:
        return len(self._episodes)

    @property
    def digest(self) -> str:
        return canonical_hash([e.body() for e in sorted(self._episodes.values(),
                                                        key=lambda e: e.episode_id)])

    def retrieve(self, query: EpisodeFeatures, *, k: int = 5,
                 symbol: Optional[str] = None, strategy_id: Optional[str] = None,
                 before_ms: Optional[int] = None,
                 max_distance: Decimal = MAX_ANALOGUE_DISTANCE) -> RetrievalResult:
        """The k closest in-scope episodes, closest first.

        `before_ms` is how the caller avoids looking at its own future. The
        index does not apply it by default, because the exam (102) deliberately
        retrieves across the whole history; a live-path caller that omits it is
        making a choice, not inheriting one.
        """
        scope: list[Episode] = []
        for e in self._episodes.values():
            if symbol is not None and e.symbol != symbol:
                continue
            if strategy_id is not None and e.strategy_id != strategy_id:
                continue
            if before_ms is not None and e.occurred_ms >= before_ms:
                continue
            scope.append(e)

        scored = [(query.distance_to(e.features), e.episode_id, e) for e in scope]
        # Distance first, then episode_id: two equally close episodes always
        # come back in the same order, on any machine, forever.
        scored.sort(key=lambda t: (t[0], t[1]))
        kept = [Analogue(e, d) for d, _eid, e in scored if d <= max_distance][:max(0, k)]
        mean = (sum((a.distance for a in kept), ZERO) / Decimal(len(kept))) if kept else None
        return RetrievalResult(tuple(kept), len(scope), mean, query)
