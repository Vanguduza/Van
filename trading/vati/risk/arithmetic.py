"""Exact internal risk arithmetic; Decimal reports keep their existing types."""
from decimal import Decimal, localcontext
from fractions import Fraction

from vati.core.decimal_context import native_decimal_context
from vati.core.units import MAX_DIGITS, MAX_SCALE, MAX_MINOR


def fraction(value):
    if (type(value) is not Decimal or not value.is_finite()
            or len(value.as_tuple().digits) > MAX_DIGITS
            or abs(value.as_tuple().exponent) > MAX_SCALE):
        raise ValueError('native risk requires bounded finite Decimal facts')
    return Fraction(value)


def decimal(value):
    """Preserve terminating values exactly; round only nonterminating reports.

    A rounded reporting ratio must never supply a permission comparison. Risk
    gates compare the original Fractions; raw-size reports are not quantities.
    """
    value = Fraction(value)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1; denominator //= 2
    while denominator % 5 == 0:
        fives += 1; denominator //= 5
    if denominator == 1:
        scale = max(twos, fives)
        if scale > MAX_SCALE:
            raise ValueError('native risk output scale capacity')
        coefficient = value.numerator * 2**(scale-twos) * 5**(scale-fives)
        if abs(coefficient) > MAX_MINOR:
            raise ValueError('native risk output digit capacity')
        return Decimal((int(coefficient < 0), tuple(int(c) for c in str(abs(coefficient))), -scale))
    # Fraction inputs may contain products wider than the output precision.
    # Decimal(int) is exact; only this declared display division is rounded.
    with localcontext(native_decimal_context()):
        return Decimal(value.numerator) / Decimal(value.denominator)


def round_down(value, step):
    step = fraction(step)
    if step <= 0:
        raise ValueError('native risk quantization requires a positive step')
    return decimal((Fraction(value) // step) * step)


def multiplier_product(multipliers):
    clamped = multipliers.clamped()
    result = Fraction(1)
    for name in ('regime', 'confidence', 'volatility', 'liquidity', 'event_risk', 'correlation', 'drawdown'):
        result *= fraction(getattr(clamped, name))
    return result


def exact_loss_amount(quantity, contract, *, entry=None, stop=None):
    """Recompute loss from original quantity/tick terms, never a display ratio."""
    from vati.risk.contracts import LossModel
    quantity = fraction(quantity)
    if contract.loss_model is LossModel.FULL_STAKE:
        return quantity
    distance = abs(fraction(entry) - fraction(stop))
    if contract.loss_model is LossModel.ILLIQUID_EQUITY:
        return quantity * (distance + fraction(entry) * fraction(contract.liquidity_haircut))
    return quantity * distance * fraction(contract.tick_value) / fraction(contract.tick_size)
