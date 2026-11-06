"""Cash-equity bounds calculated from native margin observations, never funds."""
from decimal import Decimal
from vati.core.decimal_context import native_financial_arithmetic
from vati.risk.arithmetic import fraction, decimal


def exact_cash_margin_bounds(equity, used, free, level):
    """Permission comparisons use original values, never a rounded level."""
    free = fraction(free) if free is not None else None
    level = fraction(level) if level is not None else None
    if used is None:
        return free, level
    if free is not None:
        free = min(free, fraction(equity) - fraction(used))
    if used > 0 and level is not None:
        level = min(level, fraction(equity) / fraction(used) * 100)
    return free, level


@native_financial_arithmetic
def cash_margin_bounds(equity, used, free, level):
    if used is None:
        return free,level
    if free is not None:
        difference = fraction(equity) - fraction(used)
        if fraction(free) > difference:
            # Preserve the original subtraction scale and exponent exactly.
            free = decimal(difference, exponent=min(equity.as_tuple().exponent, used.as_tuple().exponent))
    if used>0 and level is not None:
        # The historical public report keeps its original Decimal spelling.
        # Its repeated ratio is never used as a permission input.
        level=min(level,equity/used*Decimal('100'))
    return free,level
