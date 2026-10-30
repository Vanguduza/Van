"""Fresh, explicit arithmetic contexts for native financial calculations."""
from decimal import Context, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
from functools import wraps


def native_decimal_context(*, precision=80):
    # Specify every field: Context defaults can themselves be changed by callers.
    # Return a new context so flags or traps never leak between operations.
    return Context(prec=precision,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,
                   capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])


def native_financial_arithmetic(function):
    """Use a fresh complete profile without mutating a caller's context."""
    @wraps(function)
    def bounded(*args, **kwargs):
        with localcontext(native_decimal_context()):
            return function(*args, **kwargs)
    return bounded
