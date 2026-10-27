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
from vati.risk.arithmetic import fraction, decimal
from fractions import Fraction

ZERO = Decimal("0")


def exact_position_risk(position: OpenPosition):
    """Account-currency loss if the protective level of `position` is hit.

    A position without a broker-side stop has *undefined* risk; it is reported
    as infinite so every heat check fails closed until the stop is restored.
    """
    if position.loss_model is LossModel.FULL_STAKE:
        return fraction(position.stake)
    if position.loss_model is LossModel.ILLIQUID_EQUITY:
        # No venue stop exists; the software stop plus the haircut IS the protection.
        if position.stop_distance <= ZERO or position.liquidity_haircut_per_unit < ZERO:
            return None
        return fraction(position.lots) * (fraction(position.stop_distance) + fraction(position.liquidity_haircut_per_unit)) * fraction(position.value_per_price_unit_per_lot)
    if not position.has_broker_side_stop:
        return None
    return fraction(position.lots) * fraction(position.stop_distance) * fraction(position.value_per_price_unit_per_lot)


def position_risk(position: OpenPosition) -> Decimal:
    value = exact_position_risk(position)
    return Decimal('Infinity') if value is None else decimal(value)


def exact_open_stop_risk(positions: Iterable[OpenPosition], equity: Decimal, *, additional_loss=Fraction(0)):
    if equity <= ZERO:
        return None
    values = [exact_position_risk(p) for p in positions]
    if any(value is None for value in values):
        return None
    return (sum(values, Fraction(0)) + Fraction(additional_loss)) / fraction(equity)


def open_stop_risk(positions: Iterable[OpenPosition], equity: Decimal) -> Decimal:
    value = exact_open_stop_risk(positions, equity)
    return Decimal('Infinity') if value is None else decimal(value)


def exact_currency_leg_exposure(positions: Iterable[OpenPosition], equity: Decimal, *,
                               additional_loss=None, base_currency=None, quote_currency=None, direction=None):
    """Net stop-risk per currency leg as a fraction of equity (absolute value)."""
    if equity <= ZERO:
        return None
    legs = defaultdict(Fraction)
    for p in positions:
        r = exact_position_risk(p)
        if r is None:
            return None
        sign = 1 if p.direction is Direction.LONG else -1
        legs[p.base_currency] += sign * r
        legs[p.quote_currency] -= sign * r
    if additional_loss is not None:
        sign = 1 if direction is Direction.LONG else -1
        legs[base_currency] += sign * Fraction(additional_loss)
        legs[quote_currency] -= sign * Fraction(additional_loss)
    return {ccy: abs(v) / fraction(equity) for ccy, v in legs.items()}


def currency_leg_exposure(positions: Iterable[OpenPosition], equity: Decimal) -> dict[str, Decimal]:
    values = exact_currency_leg_exposure(positions, equity)
    return {'*': Decimal('Infinity')} if values is None else {key: decimal(value) for key, value in values.items()}
