"""Portfolio heat and currency-leg exposure (Rev 2 §27.2).

Rev 1 tracked "currency exposure" as a phrase. Rev 2 defines it: a position in
BASE/QUOTE is +risk on BASE and −risk on QUOTE for a LONG (reversed for a
SHORT). Two positions that each look small can stack on one leg (EURUSD long
plus USDJPY short is a doubled USD short). Exposure per currency is the
absolute net stop-risk on that leg, as a fraction of equity.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from vati.risk.contracts import Direction, LossModel, OpenPosition

ZERO = Decimal("0")


def position_risk(position: OpenPosition) -> Decimal:
    """Account-currency loss if the protective level of `position` is hit.

    A position without a broker-side stop has *undefined* risk; it is reported
    as infinite so every heat check fails closed until the stop is restored.
    """
    if position.loss_model is LossModel.FULL_STAKE:
        return position.stake
    if not position.has_broker_side_stop:
        return Decimal("Infinity")
    return position.lots * position.stop_distance * position.value_per_price_unit_per_lot


def open_stop_risk(positions: Iterable[OpenPosition], equity: Decimal) -> Decimal:
    if equity <= ZERO:
        return Decimal("Infinity")
    total = sum((position_risk(p) for p in positions), ZERO)
    return total / equity


def currency_leg_exposure(positions: Iterable[OpenPosition], equity: Decimal) -> dict[str, Decimal]:
    """Net stop-risk per currency leg as a fraction of equity (absolute value)."""
    if equity <= ZERO:
        return {"*": Decimal("Infinity")}
    legs: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in positions:
        r = position_risk(p)
        if not r.is_finite():
            return {"*": Decimal("Infinity")}
        sign = Decimal("1") if p.direction is Direction.LONG else Decimal("-1")
        legs[p.base_currency] += sign * r
        legs[p.quote_currency] -= sign * r
    return {ccy: abs(v) / equity for ccy, v in legs.items()}
