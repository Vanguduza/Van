"""Recorded MT5 entry-deal cash components, never future fees or finality."""
from decimal import Decimal
from fractions import Fraction

from vati.execution.base import VenueUnavailable
from vati.risk.contracts import Direction


SCHEMA = 'van.mt5.recorded-entry-charges/1'
FIELDS = frozenset({'schema','identity','deal_id','order_id','position_identifier','position_ticket',
    'symbol','side','volume','commission_delta','fee_delta','native_time_ms','entry_type',
    'cash_convention','complete_future_charges','settlement_final'})


def _ticket(value):
    if type(value) is int:
        if not 0 < value < 2**64:
            raise ValueError('native ticket out of range')
        return str(value)
    if (type(value) is not str or not 1 <= len(value) <= 20 or not value.isascii()
        or not value.isdecimal() or value.startswith('0') or not 0 < int(value) < 2**64):
        raise ValueError('native ticket unavailable')
    return value


def _amount(value):
    if type(value) is not str or not 1 <= len(value) <= 256:
        raise ValueError('native decimal text unavailable')
    number = Decimal(value)
    if (not number.is_finite() or len(number.as_tuple().digits) > 128
        or abs(number.as_tuple().exponent) > 128):
        raise ValueError('native recorded charge capacity exceeded')
    return number


def recorded_entry_fees(command, result, identity):
    """Return an exactly joined recorded cost, or preserve an unknown fee.

    The producer reads actual deal properties. A zero field is evidence only
    when explicitly present in a correctly bound observation. These components
    do not account for deferred daily/monthly commission, financing, other
    deals, future obligations or settlement. Identity/cost data is not order
    authority. Malformed optional charges must never erase the native effect.
    """
    try:
        if identity is None or result.get('status') not in ('FILLED','PARTIAL'):
            return None
        observation = result['recorded_entry_charges']
        if type(observation) is not dict or set(observation) != FIELDS:
            return None
        if (observation['schema'] != SCHEMA or observation['entry_type'] != 'IN'
            or observation['cash_convention'] != 'MT5_SIGNED_DEAL_CASH_COMPONENTS'
            or observation['complete_future_charges'] is not False
            or observation['settlement_final'] is not False):
            return None
        observed_identity = observation['identity']
        if type(observed_identity) is not dict or set(observed_identity) != set(identity.as_dict()):
            return None
        identity.validate(observed_identity)
        for field, raw in (('deal_id','deal'),('order_id','order'),('position_ticket','position')):
            if type(observation[field]) is not str or _ticket(observation[field]) != _ticket(result[raw]):
                return None
        _ticket(observation['position_identifier'])
        if (observation['symbol'] != command.symbol
            or observation['side'] != ('BUY' if command.direction is Direction.LONG else 'SELL')):
            return None
        # The EA emits the same native JSON number as its fill receipt; the
        # Windows SDK emits the same decimal text. Normalize both identically.
        if type(observation['volume']) not in (str, int, float, Decimal):
            return None
        volume = _amount(str(observation['volume']))
        if volume <= 0 or volume != _amount(str(result['volume'])):
            return None
        clock = observation['native_time_ms']
        if type(clock) is not int or not 0 < clock < 2**63:
            return None
        commission = _amount(observation['commission_delta'])
        fee = _amount(observation['fee_delta'])
        total = -(Fraction(commission) + Fraction(fee))
        scale = max(0, -commission.as_tuple().exponent, -fee.as_tuple().exponent)
        coefficient = total.numerator * (10**scale // total.denominator)
        # Exact tuple construction does not depend on the caller's context.
        return Decimal((int(coefficient < 0), tuple(map(int, str(abs(coefficient)))), -scale))
    except (KeyError, TypeError, ValueError, ArithmeticError, VenueUnavailable):
        return None
