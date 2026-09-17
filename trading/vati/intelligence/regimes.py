"""Deterministic regime engine (Rev 2 §3, Rev 3 A.6).

Trend and volatility regimes from features; a CUSUM change-point detector on
returns drives NORMAL → CAUTION → TRANSITION → NEW_REGIME; every classification
has hysteresis so it cannot flap bar to bar. Output is a probability-like
confidence that can only reduce risk downstream (multipliers ≤ 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.intelligence.features import FeatureVector

ZERO = Decimal("0")


class TrendRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class VolRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class TransitionPhase(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    TRANSITION = "TRANSITION"
    NEW_REGIME = "NEW_REGIME"


@dataclass(frozen=True)
class RegimeState:
    trend: TrendRegime
    vol: VolRegime
    phase: TransitionPhase
    confidence: Decimal          # 0..1; downstream may only reduce with it
    cusum_stat: Decimal
    bars_in_trend: int

    def risk_multiplier(self) -> Decimal:
        """Regime-derived multiplier, always ≤ 1 (Rev 2 §27.1)."""
        m = self.confidence
        if self.phase is TransitionPhase.CAUTION:
            m = min(m, Decimal("0.75"))
        elif self.phase is TransitionPhase.TRANSITION:
            m = min(m, Decimal("0.40"))
        elif self.phase is TransitionPhase.NEW_REGIME:
            m = min(m, Decimal("0.60"))
        if self.vol is VolRegime.EXTREME:
            m = min(m, Decimal("0.25"))
        elif self.vol is VolRegime.HIGH:
            m = min(m, Decimal("0.60"))
        return max(ZERO, min(Decimal(1), m))


@dataclass
class RegimeEngine:
    slope_enter: Decimal = Decimal("0.5")   # |slope| to enter a trend (ATR units)
    slope_exit: Decimal = Decimal("0.2")    # |slope| below which a trend ends (hysteresis)
    cusum_k: Decimal = Decimal("0.5")       # allowance in sigma units
    cusum_h: Decimal = Decimal("4")         # decision threshold
    transition_bars: int = 10               # bars to confirm NEW_REGIME
    trend: TrendRegime = TrendRegime.UNKNOWN
    phase: TransitionPhase = TransitionPhase.NORMAL
    _pos: Decimal = ZERO
    _neg: Decimal = ZERO
    _last_close: Optional[Decimal] = None
    _bars_in_trend: int = 0
    _bars_since_break: int = 0

    def _vol_regime(self, f: FeatureVector) -> VolRegime:
        p = f.vol_percentile
        if f.realised_vol is None:
            return VolRegime.UNKNOWN
        if p >= Decimal("0.97"):
            return VolRegime.EXTREME
        if p >= Decimal("0.80"):
            return VolRegime.HIGH
        if p <= Decimal("0.20"):
            return VolRegime.LOW
        return VolRegime.NORMAL

    def _update_trend(self, f: FeatureVector) -> None:
        s = f.trend_slope
        if s is None:
            self.trend = TrendRegime.UNKNOWN
            self._bars_in_trend = 0
            return
        prev = self.trend
        if self.trend is TrendRegime.BULL and s < self.slope_exit:
            self.trend = TrendRegime.RANGE
        elif self.trend is TrendRegime.BEAR and s > -self.slope_exit:
            self.trend = TrendRegime.RANGE
        elif self.trend in (TrendRegime.RANGE, TrendRegime.UNKNOWN):
            if s >= self.slope_enter:
                self.trend = TrendRegime.BULL
            elif s <= -self.slope_enter:
                self.trend = TrendRegime.BEAR
            else:
                self.trend = TrendRegime.RANGE
        self._bars_in_trend = self._bars_in_trend + 1 if self.trend == prev else 1

    def _update_cusum(self, f: FeatureVector) -> bool:
        """Two-sided CUSUM on standardised returns. Returns True on a break."""
        if self._last_close is None or f.realised_vol is None or f.realised_vol <= ZERO:
            self._last_close = f.close
            return False
        r = (f.close - self._last_close) / self._last_close
        z = r / f.realised_vol
        self._last_close = f.close
        self._pos = max(ZERO, self._pos + z - self.cusum_k)
        self._neg = max(ZERO, self._neg - z - self.cusum_k)
        if self._pos > self.cusum_h or self._neg > self.cusum_h:
            self._pos = self._neg = ZERO
            return True
        return False

    def update(self, f: FeatureVector) -> RegimeState:
        broke = self._update_cusum(f)
        self._update_trend(f)
        vol = self._vol_regime(f)
        # phase machine
        if broke:
            self.phase = TransitionPhase.TRANSITION if self.phase in (TransitionPhase.CAUTION, TransitionPhase.TRANSITION) else TransitionPhase.CAUTION
            self._bars_since_break = 0
        else:
            self._bars_since_break += 1
            if self.phase is TransitionPhase.CAUTION and self._bars_since_break >= self.transition_bars:
                self.phase = TransitionPhase.NORMAL
            elif self.phase is TransitionPhase.TRANSITION and self._bars_since_break >= self.transition_bars:
                self.phase = TransitionPhase.NEW_REGIME
            elif self.phase is TransitionPhase.NEW_REGIME and self._bars_since_break >= 2 * self.transition_bars:
                self.phase = TransitionPhase.NORMAL
        stat = max(self._pos, self._neg)
        conf = Decimal(1) - min(Decimal(1), stat / self.cusum_h) * Decimal("0.5")
        if not f.complete:
            conf = ZERO
        return RegimeState(self.trend, vol, self.phase, conf, stat, self._bars_in_trend)
