"""Data quality and market integrity (Rev 2 §4.2, §31).

The IntegrityMonitor turns quote age, cross-feed divergence and spread
percentile into NORMAL → ELEVATED → ABNORMAL → HALTED with hysteresis, so a
single bad print does not flap the state. It never sees a model."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.risk.contracts import MarketIntegrityState

ZERO = Decimal("0")


@dataclass(frozen=True)
class FeedSample:
    ts_ms: int
    bid: Decimal
    ask: Decimal
    reference_mid: Optional[Decimal] = None  # from the reference feed, if any

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass
class IntegrityMonitor:
    max_quote_age_ms: int = 1500
    spread_elevated_x: Decimal = Decimal("3")     # × median spread
    spread_abnormal_x: Decimal = Decimal("8")
    divergence_elevated_bp: Decimal = Decimal("5")
    divergence_abnormal_bp: Decimal = Decimal("20")
    recover_after: int = 20                        # consecutive clean samples to step down one level
    median_spread: Decimal = Decimal("0")          # rolling median supplied by the caller (or learned)
    state: MarketIntegrityState = MarketIntegrityState.NORMAL
    _clean: int = 0
    _spreads: list = field(default_factory=list)
    transitions: list = field(default_factory=list)

    def _severity(self, s: FeedSample, now_ms: int) -> int:
        sev = 0
        if s.bid <= ZERO or s.ask <= ZERO or s.ask < s.bid:
            return 3  # crossed/invalid book → HALTED
        if now_ms - s.ts_ms > self.max_quote_age_ms:
            sev = max(sev, 2)
        if self.median_spread > ZERO:
            ratio = s.spread / self.median_spread
            if ratio >= self.spread_abnormal_x:
                sev = max(sev, 2)
            elif ratio >= self.spread_elevated_x:
                sev = max(sev, 1)
        if s.reference_mid is not None and s.reference_mid > ZERO:
            div_bp = abs(s.mid - s.reference_mid) / s.reference_mid * Decimal("10000")
            if div_bp >= self.divergence_abnormal_bp:
                sev = max(sev, 2)
            elif div_bp >= self.divergence_elevated_bp:
                sev = max(sev, 1)
        return sev

    def observe(self, s: FeedSample, now_ms: int) -> MarketIntegrityState:
        # learn median spread from the first 50 clean samples if none supplied
        if self.median_spread == ZERO and s.ask > s.bid:
            self._spreads.append(s.spread)
            if len(self._spreads) >= 50:
                self.median_spread = sorted(self._spreads)[len(self._spreads) // 2]
        order = [MarketIntegrityState.NORMAL, MarketIntegrityState.ELEVATED, MarketIntegrityState.ABNORMAL, MarketIntegrityState.HALTED]
        cur = order.index(self.state)
        sev = self._severity(s, now_ms)
        if sev > cur:
            new = order[sev]
            self._clean = 0
        elif sev < cur:
            self._clean += 1
            new = order[cur - 1] if self._clean >= self.recover_after else self.state
            if new != self.state:
                self._clean = 0
        else:
            new = self.state
            self._clean = 0 if sev > 0 else self._clean
        if new != self.state:
            self.transitions.append((now_ms, self.state.value, new.value))
            self.state = new
        return self.state
