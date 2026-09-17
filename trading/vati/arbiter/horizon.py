"""Horizon Arbiter (Rev 2 §2.2, Rev 3 D1): expected move must exceed k × cost;
k = 3 for SCALP, 2 otherwise; MICRO does not exist."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

HORIZONS = ("SCALP", "INTRADAY", "SESSION", "OVERNIGHT", "SWING", "POSITION")
K = {"SCALP": Decimal("3"), "INTRADAY": Decimal("2"), "SESSION": Decimal("2"), "OVERNIGHT": Decimal("2"), "SWING": Decimal("2"), "POSITION": Decimal("2")}
MAX_QUOTE_AGE_MS = {"SCALP": 500, "INTRADAY": 1500, "SESSION": 5000, "OVERNIGHT": 5000, "SWING": 5000, "POSITION": 5000}


@dataclass(frozen=True)
class HorizonVerdict:
    horizon: Optional[str]
    reason: str
    cost_multiple: Decimal


class HorizonArbiter:
    def decide(self, requested: str, expected_gross_move_pct: Decimal, round_trip_cost_pct: Decimal, quote_age_ms: int) -> HorizonVerdict:
        if requested not in HORIZONS:
            return HorizonVerdict(None, f"unknown or removed horizon {requested}", Decimal(0))
        if round_trip_cost_pct <= 0:
            return HorizonVerdict(None, "cost unknown; fail closed", Decimal(0))
        mult = expected_gross_move_pct / round_trip_cost_pct
        if mult < K[requested]:
            return HorizonVerdict(None, f"expected move {expected_gross_move_pct} is {mult:.2f}× cost; need ≥ {K[requested]}× for {requested}", mult)
        if quote_age_ms > MAX_QUOTE_AGE_MS[requested]:
            return HorizonVerdict(None, f"quote age {quote_age_ms}ms exceeds {MAX_QUOTE_AGE_MS[requested]}ms for {requested}", mult)
        return HorizonVerdict(requested, "eligible", mult)
