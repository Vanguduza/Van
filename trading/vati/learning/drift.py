"""Feature and edge drift (§26, TRD-ENH-072/073).

`StrategyHealthTracker` measures realised performance, process, cost ratio and
regime fit — all at capsule level, and all *after* the capsule has already lost
money. Capsule health is a lagging indicator of feature decay.

This is the leading one: it asks whether the inputs still carry information,
per feature and per segment, before the strategy built on them degrades.

It proposes. It never rewrites a live capsule, and there is no call path from
here into the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import mean, pstdev
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash

ZERO = Decimal("0")

STABLE = "STABLE"
WATCH = "WATCH"
DEGRADED = "DEGRADED"
INSUFFICIENT = "INSUFFICIENT"

#: Below this, a comparison between windows is noise.
MIN_WINDOW = 30


@dataclass(frozen=True)
class DriftSegment:
    feature_id: str
    strategy_id: str
    instrument: str
    timeframe: str
    regime: str

    def key(self) -> str:
        return "|".join((self.feature_id, self.strategy_id, self.instrument,
                         self.timeframe, self.regime))


@dataclass(frozen=True)
class FeatureDriftObservation:
    segment_key: str
    baseline_n: int
    recent_n: int
    distribution_shift: Optional[Decimal]
    incremental_contribution_baseline: Optional[Decimal]
    incremental_contribution_recent: Optional[Decimal]
    contribution_delta: Optional[Decimal]
    missingness: Decimal
    staleness_rate: Decimal
    state: str
    reasons: tuple[str, ...] = ()
    observation_hash: str = ""

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if k != "observation_hash"} | {
            "reasons": list(self.reasons)}

    def sealed(self) -> "FeatureDriftObservation":
        return FeatureDriftObservation(
            **{**self.__dict__, "observation_hash": canonical_hash(self.as_dict())})


def standardised_shift(baseline: Sequence[float], recent: Sequence[float]) -> Optional[Decimal]:
    """Mean shift in baseline standard deviations. Scale-free across features."""
    if len(baseline) < 2 or not recent:
        return None
    sd = pstdev(baseline)
    if sd == 0:
        return Decimal("0") if mean(recent) == mean(baseline) else Decimal("999")
    return Decimal(str(round((mean(recent) - mean(baseline)) / sd, 6)))


class FeatureDriftMonitor:
    def __init__(self, *, min_window: int = MIN_WINDOW,
                 shift_watch: Decimal = Decimal("1.0"),
                 shift_degraded: Decimal = Decimal("2.0"),
                 contribution_drop: Decimal = Decimal("0.5")) -> None:
        self.min_window = min_window
        self.shift_watch = shift_watch
        self.shift_degraded = shift_degraded
        self.contribution_drop = contribution_drop

    def observe(
        self,
        segment: DriftSegment,
        *,
        baseline_values: Sequence[float],
        recent_values: Sequence[float],
        baseline_contribution: Optional[Decimal] = None,
        recent_contribution: Optional[Decimal] = None,
        missing: int = 0,
        stale: int = 0,
    ) -> FeatureDriftObservation:
        reasons: list[str] = []
        n_recent = len(recent_values)
        total = n_recent + missing

        if len(baseline_values) < self.min_window or n_recent < self.min_window:
            return FeatureDriftObservation(
                segment.key(), len(baseline_values), n_recent, None, baseline_contribution,
                recent_contribution, None,
                Decimal(missing) / Decimal(max(1, total)), Decimal(stale) / Decimal(max(1, total)),
                INSUFFICIENT, (f"window<{self.min_window}",)).sealed()

        shift = standardised_shift(baseline_values, recent_values)
        delta = None
        if baseline_contribution is not None and recent_contribution is not None:
            delta = (recent_contribution - baseline_contribution).quantize(Decimal("0.000001"))

        state = STABLE
        if shift is not None and abs(shift) >= self.shift_degraded:
            state = DEGRADED
            reasons.append(f"distribution_shift:{shift}")
        elif shift is not None and abs(shift) >= self.shift_watch:
            state = WATCH
            reasons.append(f"distribution_shift:{shift}")

        # A feature that has stopped contributing is the real signal; a shifted
        # distribution that still contributes may just be a different market.
        if (delta is not None and baseline_contribution and baseline_contribution > ZERO
                and delta < -(baseline_contribution * self.contribution_drop)):
            state = DEGRADED
            reasons.append(f"contribution_drop:{delta}")

        missingness = Decimal(missing) / Decimal(max(1, total))
        if missingness > Decimal("0.1"):
            state = DEGRADED if state == WATCH else max(state, WATCH, key=lambda s: (s == DEGRADED, s == WATCH))
            reasons.append(f"missingness:{missingness}")

        return FeatureDriftObservation(
            segment.key(), len(baseline_values), n_recent, shift,
            baseline_contribution, recent_contribution, delta,
            missingness, Decimal(stale) / Decimal(max(1, total)), state, tuple(reasons)).sealed()


@dataclass(frozen=True)
class EdgeDriftObservation:
    strategy_id: str
    segment: str
    baseline_expectancy_R: Decimal
    recent_expectancy_R: Decimal
    baseline_edge_floor_R: Optional[Decimal]
    recent_edge_floor_R: Optional[Decimal]
    cost_adjusted_delta: Decimal
    hit_rate_delta: Decimal
    holding_time_delta: Decimal
    state: str
    reasons: tuple[str, ...] = ()
    observation_hash: str = ""

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if k != "observation_hash"} | {
            "reasons": list(self.reasons)}

    def sealed(self) -> "EdgeDriftObservation":
        return EdgeDriftObservation(
            **{**self.__dict__, "observation_hash": canonical_hash(self.as_dict())})


class EdgeDriftMonitor:
    """Whether the *edge* decayed, separately from whether a feature did."""

    def __init__(self, *, degraded_drop_R: Decimal = Decimal("0.15"),
                 watch_drop_R: Decimal = Decimal("0.05")) -> None:
        self.degraded_drop_R = degraded_drop_R
        self.watch_drop_R = watch_drop_R

    def observe(self, *, strategy_id: str, segment: str,
                baseline_expectancy_R: Decimal, recent_expectancy_R: Decimal,
                baseline_edge_floor_R: Optional[Decimal] = None,
                recent_edge_floor_R: Optional[Decimal] = None,
                cost_adjusted_delta: Decimal = ZERO,
                hit_rate_delta: Decimal = ZERO,
                holding_time_delta: Decimal = ZERO) -> EdgeDriftObservation:
        drop = baseline_expectancy_R - recent_expectancy_R
        reasons: list[str] = []
        state = STABLE
        if drop >= self.degraded_drop_R:
            state, _ = DEGRADED, reasons.append(f"expectancy_drop:{drop}")
        elif drop >= self.watch_drop_R:
            state, _ = WATCH, reasons.append(f"expectancy_drop:{drop}")
        # An edge floor that has gone non-positive matters even when the mean
        # still looks acceptable: the evidence no longer supports the mean.
        if recent_edge_floor_R is not None and recent_edge_floor_R <= ZERO:
            state = DEGRADED
            reasons.append(f"edge_floor_not_positive:{recent_edge_floor_R}")
        if cost_adjusted_delta < -self.watch_drop_R:
            reasons.append(f"cost_adjusted_delta:{cost_adjusted_delta}")
            if state == STABLE:
                state = WATCH
        return EdgeDriftObservation(
            strategy_id, segment, baseline_expectancy_R, recent_expectancy_R,
            baseline_edge_floor_R, recent_edge_floor_R, cost_adjusted_delta,
            hit_rate_delta, holding_time_delta, state, tuple(reasons)).sealed()


__all__ = [
    "DEGRADED", "INSUFFICIENT", "MIN_WINDOW", "STABLE", "WATCH",
    "DriftSegment", "EdgeDriftMonitor", "EdgeDriftObservation",
    "FeatureDriftMonitor", "FeatureDriftObservation", "standardised_shift",
]
