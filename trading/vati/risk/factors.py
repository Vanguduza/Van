"""Factor tags for portfolio dependency (§17, TRD-ENH-040).

Versioned configuration, not inference. An instrument's exposures are declared
here so a dependency estimate can fall back to structural overlap when there is
not enough return history — which is most of the time early on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

FACTOR_REGISTRY_VERSION = "factors/1.0.0"

USD, EUR, GBP, JPY = "USD", "EUR", "GBP", "JPY"
GOLD, RATES, RISK_ON_OFF = "GOLD", "RATES", "RISK_ON_OFF"
ZIG, ZSE_SECTOR, VFEX_USD = "ZIG", "ZSE_SECTOR", "VFEX_USD"

ALL_FACTORS = (USD, EUR, GBP, JPY, GOLD, RATES, RISK_ON_OFF, ZIG, ZSE_SECTOR, VFEX_USD)


@dataclass(frozen=True)
class FactorExposure:
    """Signed exposures. +1 long the factor, -1 short it."""

    symbol: str
    exposures: Mapping[str, float]

    def overlap(self, other: "FactorExposure") -> float:
        """Cosine similarity over shared factors, in [-1, 1].

        Structural, so it works with zero return history. Two USD-quoted majors
        overlap even when their price histories are short.
        """
        keys = set(self.exposures) | set(other.exposures)
        a = [self.exposures.get(k, 0.0) for k in keys]
        b = [other.exposures.get(k, 0.0) for k in keys]
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return max(-1.0, min(1.0, dot / (na * nb)))


#: FX majors decompose into their legs; metals and ZSE carry their own factors.
DEFAULT_EXPOSURES: dict[str, dict[str, float]] = {
    "EURUSD": {EUR: 1.0, USD: -1.0, RISK_ON_OFF: 0.3},
    "GBPUSD": {GBP: 1.0, USD: -1.0, RISK_ON_OFF: 0.3},
    "USDJPY": {USD: 1.0, JPY: -1.0, RATES: 0.4, RISK_ON_OFF: -0.2},
    "EURGBP": {EUR: 1.0, GBP: -1.0},
    "XAUUSD": {GOLD: 1.0, USD: -0.6, RATES: -0.4, RISK_ON_OFF: -0.3},
}


class FactorRegistry:
    def __init__(self, exposures: Mapping[str, Mapping[str, float]] | None = None,
                 *, version: str = FACTOR_REGISTRY_VERSION) -> None:
        self._e = {k: dict(v) for k, v in (exposures or DEFAULT_EXPOSURES).items()}
        self.version = version

    def exposure(self, symbol: str) -> FactorExposure:
        return FactorExposure(symbol, self._e.get(symbol.upper(), {}))

    def known(self, symbol: str) -> bool:
        return symbol.upper() in self._e

    def register(self, symbol: str, exposures: Mapping[str, float]) -> None:
        bad = sorted(set(exposures) - set(ALL_FACTORS))
        if bad:
            raise ValueError(f"unknown factor(s) for {symbol}: {bad}")
        self._e[symbol.upper()] = dict(exposures)


__all__ = ["ALL_FACTORS", "DEFAULT_EXPOSURES", "FACTOR_REGISTRY_VERSION",
           "FactorExposure", "FactorRegistry"]
