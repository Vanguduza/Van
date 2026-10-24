"""Cash-equity bounds calculated from native margin observations, never funds."""
from decimal import Decimal, localcontext


def cash_margin_bounds(equity, used, free, level):
    if used is None:
        return free,level
    with localcontext() as context:
        context.prec=512
        free=min(free,equity-used) if free is not None else None
    if used>0 and level is not None:
        with localcontext() as context:
            context.prec=80
            level=min(level,equity/used*Decimal('100'))
    return free,level
