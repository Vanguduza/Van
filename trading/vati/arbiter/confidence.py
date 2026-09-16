"""Trading confidence score (Rev 2 §34 confidence matrix, Rev 4 Part K.4).

A single 0–1 number and a band, derived deterministically from the rule
multipliers the meta-labeller already emits (regime, volatility, liquidity,
event risk, confidence) and the learned capsule health. It is a *display and
ranking* signal for the owner: it is labelled uncalibrated, it never sizes a
trade, and it never feeds the Risk Authority."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional

ONE, ZERO = Decimal(1), Decimal(0)
BASIS = "RULES_V0_UNCALIBRATED: product of reduce-only rule multipliers × capsule health; display/ranking only, never a size"
MULTIPLIER_KEYS = ("regime_multiplier", "volatility_multiplier", "liquidity_multiplier", "event_risk_multiplier", "confidence_multiplier")


@dataclass(frozen=True)
class Confidence:
    score: Decimal            # 0..1, quantised to 0.01
    band: str                 # HIGH | MEDIUM | LOW | MINIMAL
    basis: str = BASIS

    def as_dict(self) -> dict:
        return {"score": str(self.score), "band": self.band, "basis": self.basis}


def band_for(score: Decimal) -> str:
    if score >= Decimal("0.75"):
        return "HIGH"
    if score >= Decimal("0.50"):
        return "MEDIUM"
    if score >= Decimal("0.25"):
        return "LOW"
    return "MINIMAL"


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def confidence_score(multipliers: Mapping[str, object], *, capsule_health: Decimal | str | None = None) -> Confidence:
    """Product of the five rule multipliers (missing ones count as 1) × capsule health, clamped to [0, 1]."""
    product = ONE
    for k in MULTIPLIER_KEYS:
        m = _dec(multipliers.get(k))
        if m is None:
            continue
        product *= min(ONE, max(ZERO, m))
    h = _dec(capsule_health)
    if h is not None:
        product *= min(ONE, max(ZERO, h))
    score = min(ONE, max(ZERO, product)).quantize(Decimal("0.01"))
    return Confidence(score, band_for(score))
