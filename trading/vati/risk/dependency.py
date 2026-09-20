"""PortfolioDependencyEngine (§17, TRD-ENH-041/043).

`TradeIntent.correlation_multiplier` has always existed, been serialised, and
been consumed by the Risk Authority. Nothing ever populated it, so it has been
1 since the field was added. This is what populates it.

Two rules:

* **Reduce-only.** The multiplier is clamped to [0, 1] like every other
  intelligence input. Dependency can shrink a position; it can never grow one.
* **Unknown is not independent.** With no covariance estimate the engine falls
  back to *structural* factor overlap, and if it has neither it uses a
  conservative default rather than 0. A portfolio that looks diversified because
  nobody measured it is the failure mode this guards.

Market-exposure dependency (this module) and strategy-return dependency
(`StrategyOverlapDetector`) answer different questions and are deliberately
separate: instrument covariance governs the live book, R-multiple correlation
governs slow capital allocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.risk.expected_shortfall import (
    DEFAULT_CONFIDENCE,
    Position,
    expected_shortfall,
)
from vati.risk.factors import FactorRegistry

ZERO, ONE = Decimal("0"), Decimal("1")

#: Used when neither covariance nor factor exposure is available. Deliberately
#: high: an unmeasured pair is assumed to move together until shown otherwise.
CONSERVATIVE_UNKNOWN_CORRELATION = 0.7

#: Stressed view: correlations converge under stress, so the tail is measured
#: against a matrix pushed toward 1 rather than the calm-market estimate.
STRESS_FLOOR = 0.8

DEPENDENCY_MODEL_VERSION = "dependency/1.0.0"


@dataclass(frozen=True)
class PortfolioDependencySnapshot:
    as_of_ms: int
    candidate_id: str
    symbol: str
    portfolio_snapshot_hash: str
    normal_model_hash: str
    stressed_model_hash: str
    es_before: Decimal
    es_after: Decimal
    incremental_es: Decimal
    stressed_incremental_es: Decimal
    factor_exposures: Mapping[str, float]
    correlation_multiplier: Decimal
    estimate_basis: str
    dependency_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "as_of_ms": self.as_of_ms, "candidate_id": self.candidate_id, "symbol": self.symbol,
            "portfolio_snapshot_hash": self.portfolio_snapshot_hash,
            "normal_model_hash": self.normal_model_hash,
            "stressed_model_hash": self.stressed_model_hash,
            "es_before": str(self.es_before), "es_after": str(self.es_after),
            "incremental_es": str(self.incremental_es),
            "stressed_incremental_es": str(self.stressed_incremental_es),
            "factor_exposures": dict(self.factor_exposures),
            "correlation_multiplier": str(self.correlation_multiplier),
            "estimate_basis": self.estimate_basis,
        }

    def sealed(self) -> "PortfolioDependencySnapshot":
        return PortfolioDependencySnapshot(
            **{**self.__dict__, "dependency_hash": canonical_hash(self.as_dict())})


class PortfolioDependencyEngine:
    def __init__(
        self,
        *,
        factors: Optional[FactorRegistry] = None,
        correlations: Optional[Mapping[tuple[str, str], float]] = None,
        confidence: float = DEFAULT_CONFIDENCE,
        unknown_correlation: float = CONSERVATIVE_UNKNOWN_CORRELATION,
        #: Fraction of the book's ES the incremental ES may be before the
        #: multiplier starts reducing. Above `full_cut` the candidate is zeroed.
        free_increment: Decimal = Decimal("0.25"),
        full_cut: Decimal = Decimal("1.50"),
        model_version: str = DEPENDENCY_MODEL_VERSION,
    ) -> None:
        self.factors = factors or FactorRegistry()
        self.correlations = dict(correlations or {})
        self.confidence = confidence
        self.unknown_correlation = unknown_correlation
        self.free_increment = free_increment
        self.full_cut = full_cut
        self.model_version = model_version

    # -- correlation estimation -------------------------------------------

    def _pair(self, a: str, b: str) -> tuple[float, str]:
        """Best available estimate, and how it was obtained."""
        key, rev = (a, b), (b, a)
        if key in self.correlations or rev in self.correlations:
            return self.correlations.get(key, self.correlations.get(rev)), "MEASURED"
        if self.factors.known(a) and self.factors.known(b):
            # Structural overlap works with no return history at all.
            return self.factors.exposure(a).overlap(self.factors.exposure(b)), "FACTOR_OVERLAP"
        return self.unknown_correlation, "CONSERVATIVE_DEFAULT"

    def _matrix(self, symbols: Sequence[str], *, stressed: bool) -> tuple[dict, str]:
        out: dict[tuple[str, str], float] = {}
        basis: list[str] = []
        for i, a in enumerate(symbols):
            for b in symbols[i + 1:]:
                rho, how = self._pair(a, b)
                if stressed:
                    # Under stress, diversification decays toward co-movement.
                    rho = max(rho, STRESS_FLOOR) if rho >= 0 else min(rho, -STRESS_FLOOR)
                out[(a, b)] = rho
                basis.append(how)
        label = "MEASURED" if basis and all(b == "MEASURED" for b in basis) else (
            "CONSERVATIVE_DEFAULT" if "CONSERVATIVE_DEFAULT" in basis else
            ("FACTOR_OVERLAP" if basis else "NO_PAIRS"))
        return out, label

    # -- the multiplier ----------------------------------------------------

    def _multiplier(self, es_before: Decimal, incremental: Decimal) -> Decimal:
        """Reduce-only. Clamped to [0, 1] by construction, not by convention."""
        if es_before <= 0:
            return ONE                  # first position in an empty book
        ratio = incremental / es_before
        if ratio <= self.free_increment:
            return ONE
        if ratio >= self.full_cut:
            return ZERO
        span = self.full_cut - self.free_increment
        m = (self.full_cut - ratio) / span
        return max(ZERO, min(ONE, m)).quantize(Decimal("0.0001"))

    def assess(
        self,
        *,
        candidate_id: str,
        symbol: str,
        candidate_risk: Decimal,
        direction: int,
        open_positions: Sequence[Position],
        now_ms: int,
        portfolio_snapshot_hash: str = "",
    ) -> PortfolioDependencySnapshot:
        symbols = [p.symbol for p in open_positions]
        with_candidate = list(open_positions) + [Position(symbol, candidate_risk, direction)]
        all_symbols = symbols + [symbol]

        normal, basis = self._matrix(all_symbols, stressed=False)
        stressed, _ = self._matrix(all_symbols, stressed=True)

        es_before = expected_shortfall(open_positions, normal, confidence=self.confidence,
                                       default_correlation=self.unknown_correlation)
        es_after = expected_shortfall(with_candidate, normal, confidence=self.confidence,
                                      default_correlation=self.unknown_correlation)
        stressed_after = expected_shortfall(with_candidate, stressed, confidence=self.confidence,
                                            default_correlation=max(self.unknown_correlation, STRESS_FLOOR))
        stressed_before = expected_shortfall(open_positions, stressed, confidence=self.confidence,
                                             default_correlation=max(self.unknown_correlation, STRESS_FLOOR))

        incremental = es_after - es_before
        stressed_incremental = stressed_after - stressed_before
        # The stressed view governs, because it is the one that matters when it
        # matters. Using the calm estimate would size for the easy case.
        multiplier = self._multiplier(stressed_before, stressed_incremental)

        return PortfolioDependencySnapshot(
            as_of_ms=now_ms, candidate_id=candidate_id, symbol=symbol,
            portfolio_snapshot_hash=portfolio_snapshot_hash,
            normal_model_hash=canonical_hash({"m": {f"{a}|{b}": v for (a, b), v in sorted(normal.items())},
                                              "v": self.model_version}),
            stressed_model_hash=canonical_hash({"m": {f"{a}|{b}": v for (a, b), v in sorted(stressed.items())},
                                                "v": self.model_version}),
            es_before=es_before, es_after=es_after, incremental_es=incremental,
            stressed_incremental_es=stressed_incremental,
            factor_exposures=dict(self.factors.exposure(symbol).exposures),
            correlation_multiplier=multiplier, estimate_basis=basis,
        ).sealed()


__all__ = [
    "CONSERVATIVE_UNKNOWN_CORRELATION", "DEPENDENCY_MODEL_VERSION", "STRESS_FLOOR",
    "PortfolioDependencyEngine", "PortfolioDependencySnapshot",
]
