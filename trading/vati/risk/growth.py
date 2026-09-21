"""Offline growth-optimality diagnostic (TRD-REV51-127).

This module can describe whether a risk regime looks conservative/aggressive under
explicit assumptions. It has no path to RiskAuthority and cannot change live risk.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event

ZERO = Decimal("0")
ONE = Decimal("1")
VERSION = "growth-diagnostic/5.1.0"


@dataclass(frozen=True)
class GrowthDiagnostic:
    diagnostic_id: str
    data_window: str
    regime_segments: tuple[str, ...]
    assumptions: tuple[str, ...]
    uncertainty: str
    drawdown_constraint: Decimal
    estimated_growth_fraction: Decimal
    current_risk_fraction: Decimal
    classification: str
    proposal_id: str
    created_ms: int

    def body(self) -> dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "data_window": self.data_window,
            "regime_segments": list(self.regime_segments),
            "assumptions": list(self.assumptions),
            "uncertainty": self.uncertainty,
            "drawdown_constraint": str(self.drawdown_constraint),
            "estimated_growth_fraction": str(self.estimated_growth_fraction),
            "current_risk_fraction": str(self.current_risk_fraction),
            "classification": self.classification,
            "proposal_id": self.proposal_id,
            "created_ms": self.created_ms,
            "version": VERSION,
            "live_authority": False,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class GrowthOptimalityDiagnostic:
    def __init__(self, *, ledger=None, producer: str = "vati-growth-diagnostic") -> None:
        self._ledger = ledger
        self._producer = producer

    def evaluate(self, *, diagnostic_id: str, win_probability: Decimal,
                 payoff_ratio: Decimal, current_risk_fraction: Decimal,
                 drawdown_constraint: Decimal, data_window: str,
                 regime_segments: tuple[str, ...], assumptions: tuple[str, ...],
                 uncertainty: str, proposal_id: str, now_ms: int) -> GrowthDiagnostic:
        p = dec(win_probability)
        b = dec(payoff_ratio)
        q = ONE - p
        if not (ZERO < p < ONE) or b <= ZERO:
            raise ValueError("win probability/payoff ratio are outside diagnostic domain")
        raw = max(ZERO, p - (q / b))
        estimate = min(raw, dec(drawdown_constraint))
        current = dec(current_risk_fraction)
        if current < estimate * Decimal("0.5"):
            classification = "CONSERVATIVE_RELATIVE_TO_ASSUMPTIONS"
        elif current > estimate:
            classification = "AGGRESSIVE_RELATIVE_TO_ASSUMPTIONS"
        else:
            classification = "WITHIN_DIAGNOSTIC_BAND"
        d = GrowthDiagnostic(
            diagnostic_id=diagnostic_id, data_window=data_window,
            regime_segments=regime_segments, assumptions=assumptions,
            uncertainty=uncertainty, drawdown_constraint=dec(drawdown_constraint),
            estimated_growth_fraction=estimate, current_risk_fraction=current,
            classification=classification, proposal_id=proposal_id, created_ms=now_ms,
        )
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.GROWTH_DIAGNOSTIC, self._producer,
                d.body() | {"diagnostic_hash": d.digest},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=diagnostic_id,
            ))
        return d
