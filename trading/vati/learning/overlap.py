"""StrategyOverlapDetector (§18, TRD-ENH-044).

Two capsules can express the same latent bet and consume risk twice. Return
correlation alone will not reveal it early, because early is exactly when the
sample is too small to be significant — so the detector combines structural
overlap (instrument, factor, direction, regime, entry timing) with return
correlation and drawdown co-occurrence, and reports UNKNOWN when it has neither
enough structure nor enough sample.

Live effect is reduce-only. The slow effect informs capital proposals, where
two strategies that are really one should not receive two budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

LOW, MEDIUM, HIGH, UNKNOWN = "LOW", "MEDIUM", "HIGH", "UNKNOWN"

#: Below this many paired observations, return correlation is not evidence.
MIN_PAIRED_SAMPLE = 30


@dataclass(frozen=True)
class OverlapEvidence:
    strategy_a: str
    strategy_b: str
    instrument_overlap: float
    factor_overlap: float
    direction_overlap: float
    regime_overlap: float
    entry_time_overlap: float
    return_correlation: Optional[float]
    drawdown_co_occurrence: Optional[float]
    paired_sample: int

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class OverlapVerdict:
    strategy_a: str
    strategy_b: str
    level: str
    score: Optional[float]
    basis: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"strategy_a": self.strategy_a, "strategy_b": self.strategy_b,
                "level": self.level, "score": self.score, "basis": self.basis,
                "reasons": list(self.reasons)}


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class StrategyOverlapDetector:
    def __init__(self, *, min_paired_sample: int = MIN_PAIRED_SAMPLE) -> None:
        self.min_paired_sample = min_paired_sample

    def structural_score(self, e: OverlapEvidence) -> float:
        """Weighted structural overlap, available with zero return history."""
        return (
            0.30 * e.instrument_overlap
            + 0.30 * e.factor_overlap
            + 0.20 * e.direction_overlap
            + 0.10 * e.regime_overlap
            + 0.10 * e.entry_time_overlap
        )

    def assess(self, e: OverlapEvidence) -> OverlapVerdict:
        reasons: list[str] = []
        structural = self.structural_score(e)

        has_returns = (e.return_correlation is not None
                       and e.paired_sample >= self.min_paired_sample)
        if e.return_correlation is not None and not has_returns:
            reasons.append(f"return_sample_too_small:{e.paired_sample}<{self.min_paired_sample}")

        if has_returns:
            # Returns confirm or contradict the structural read; take the worse.
            score = max(structural, abs(e.return_correlation))
            basis = "STRUCTURAL_AND_RETURNS"
            if e.drawdown_co_occurrence is not None:
                score = max(score, e.drawdown_co_occurrence)
                reasons.append(f"drawdown_co_occurrence:{e.drawdown_co_occurrence:.2f}")
        elif e.instrument_overlap or e.factor_overlap:
            score = structural
            basis = "STRUCTURAL_ONLY"
        else:
            return OverlapVerdict(e.strategy_a, e.strategy_b, UNKNOWN, None,
                                  "INSUFFICIENT_EVIDENCE",
                                  tuple(reasons + ["no structural or return evidence"]))

        level = HIGH if score >= 0.70 else (MEDIUM if score >= 0.40 else LOW)
        reasons.append(f"structural:{structural:.2f}")
        return OverlapVerdict(e.strategy_a, e.strategy_b, level, round(score, 4), basis, tuple(reasons))

    def multiplier(self, verdict: OverlapVerdict) -> Decimal:
        """Reduce-only live effect. UNKNOWN is treated as MEDIUM, not as LOW."""
        return {
            LOW: Decimal("1"),
            MEDIUM: Decimal("0.75"),
            HIGH: Decimal("0.5"),
            UNKNOWN: Decimal("0.75"),
        }[verdict.level]


__all__ = ["HIGH", "LOW", "MEDIUM", "MIN_PAIRED_SAMPLE", "UNKNOWN",
           "OverlapEvidence", "OverlapVerdict", "StrategyOverlapDetector", "_jaccard"]
