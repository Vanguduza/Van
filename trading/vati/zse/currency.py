"""ZiG currency-regime model.

Evidence (search corpus 2026-09-16): official ZiG/USD 25–29 through 2026 with
a parallel premium of roughly 20–35% and a 2024 peak of 137.84% before the
27 Sep 2024 devaluation (13.9987 → 24.8831). The ZSE All Share Index rose 28%
in the weeks the ZiG slid (Aug–Sep 2024) and 160% from its 8 Apr 2024 rebase,
i.e. the ZiG-priced index behaves partly as a currency-weakness proxy.
VATI therefore values every ZSE position in USD at BOTH rates and classifies
the premium regime before any ZSE strategy is eligible."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class CurrencyRegime(str, Enum):
    ANCHORED = "ANCHORED"          # premium < 10%: ZiG returns ≈ USD returns
    ELEVATED = "ELEVATED"          # 10–35%: currency-proxy behaviour likely
    STRESSED = "STRESSED"          # 35–80%: index driven by currency flight; official-rate P&L unreliable
    DISORDERLY = "DISORDERLY"      # > 80% or devaluation event: no new ZSE risk


@dataclass(frozen=True)
class RateSnapshot:
    official_zig_per_usd: Decimal
    parallel_zig_per_usd: Decimal
    official_move_1d: Decimal = Decimal("0")  # fraction; a step devaluation shows here

    @property
    def premium(self) -> Decimal:
        if self.official_zig_per_usd <= 0:
            return Decimal("Infinity")
        return self.parallel_zig_per_usd / self.official_zig_per_usd - Decimal("1")


def classify_currency_regime(rates: RateSnapshot) -> CurrencyRegime:
    if rates.official_zig_per_usd <= 0 or rates.parallel_zig_per_usd <= 0:
        return CurrencyRegime.DISORDERLY
    if abs(rates.official_move_1d) >= Decimal("0.10"):
        return CurrencyRegime.DISORDERLY  # step devaluation in the last session
    p = rates.premium
    if p < Decimal("0.10"):
        return CurrencyRegime.ANCHORED
    if p < Decimal("0.35"):
        return CurrencyRegime.ELEVATED
    if p < Decimal("0.80"):
        return CurrencyRegime.STRESSED
    return CurrencyRegime.DISORDERLY


def usd_equivalent(zig_amount: Decimal, rates: RateSnapshot) -> dict[str, Decimal]:
    """Value a ZiG amount at both rates; VATI reports both and sizes risk on the worse."""
    return {
        "usd_at_official": zig_amount / rates.official_zig_per_usd,
        "usd_at_parallel": zig_amount / rates.parallel_zig_per_usd,
        "usd_conservative": zig_amount / max(rates.official_zig_per_usd, rates.parallel_zig_per_usd),
    }
