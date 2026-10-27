"""Cash-equity bounds calculated from native margin observations, never funds."""
from vati.core.decimal_context import native_financial_arithmetic
from vati.risk.arithmetic import fraction, decimal


@native_financial_arithmetic
def cash_margin_bounds(equity, used, free, level):
    if used is None:
        return free,level
    free=decimal(min(fraction(free),fraction(equity)-fraction(used))) if free is not None else None
    if used>0 and level is not None:
        level=decimal(min(fraction(level),fraction(equity)/fraction(used)*100))
    return free,level
