"""Transaction cost analysis per fill (Rev 2 §30)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from fractions import Fraction
import json

from vati.core.canonical import canonical_json
from vati.core.decimal_context import native_decimal_context
from vati.core.units import MAX_DIGITS, MAX_SCALE
from vati.execution.base import ExecutionReceipt
from vati.risk.contracts import Direction

ZERO = Decimal("0")


@dataclass(frozen=True)
class TcaRecord:
    trade_intent_id: str
    decision_price: Decimal
    arrival_price: Decimal
    submitted_price: Decimal
    fill_price: Decimal
    spread_cost: Decimal          # diagnostic half spread × qty × vppu; already embedded in fill cost
    slippage: Decimal             # signed, price units (positive = adverse)
    delay_cost: Decimal           # arrival - decision, adverse-signed
    fees: Decimal
    implementation_shortfall: Decimal  # total adverse cost in account currency
    modelled_cost_pct: Decimal
    realised_cost_pct: Decimal
    cost_ratio: Decimal           # realised / modelled; > 1.2 sustained = cost drift
    submission_cost: Decimal = ZERO  # signed submitted - arrival, price units
    filled_quantity: Decimal | None = None
    contract_value_per_price_unit: Decimal | None = None
    reference_notional: Decimal | None = None
    measurement_version: str = "tca/2.0.0"
    _arithmetic_json: str = field(default="", repr=False)

    def as_dict(self) -> dict:
        body = {k: (str(v) if isinstance(v, Decimal) else v)
                for k, v in self.__dict__.items() if k != '_arithmetic_json'}
        if self._arithmetic_json:
            body['arithmetic'] = json.loads(self._arithmetic_json)
        return body


def _finite_decimal(value: Fraction) -> Decimal:
    """Materialize a terminating rational without rounding or caller context."""
    denominator=value.denominator; twos=fives=0
    while denominator % 2 == 0:
        denominator //= 2; twos += 1
    while denominator % 5 == 0:
        denominator //= 5; fives += 1
    if denominator != 1:
        raise ValueError('TCA monetary value is not a finite decimal')
    scale=max(twos,fives)
    integer=value.numerator * 2**(scale-twos) * 5**(scale-fives)
    parts=Decimal(integer).as_tuple()
    return Decimal((parts.sign,parts.digits,-scale))


def _ratio(value: Fraction) -> Decimal:
    # Ratios may recur. Keep the established 28 significant-digit display,
    # independently rounded from the exact rational, never from another ratio.
    with localcontext(native_decimal_context(precision=28)):
        return Decimal(value.numerator)/Decimal(value.denominator)


def _fraction_body(value):
    # Decimal(int) is exact and avoids Python's configurable int-string limit.
    return {'numerator':format(Decimal(value.numerator),'f'),
            'denominator':format(Decimal(value.denominator),'f')}


def compute_tca(r: ExecutionReceipt, *, direction: Direction, qty: Decimal, value_per_unit: Decimal, modelled_cost_pct: Decimal) -> TcaRecord:
    values = (r.filled_qty, r.average_fill, r.decision_price, r.arrival_price,
              r.submitted_price, r.spread_at_submit, r.fees, qty, value_per_unit, modelled_cost_pct)
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
        raise ValueError("TCA requires finite Decimal economic inputs")
    if any(len(v.as_tuple().digits)>MAX_DIGITS or abs(v.as_tuple().exponent)>MAX_SCALE for v in values):
        raise ValueError('TCA decimal input capacity exceeded')
    if r.average_fill is None or r.filled_qty <= ZERO:
        raise ValueError("TCA requires a filled receipt")
    if qty != r.filled_qty:
        raise ValueError("TCA quantity must equal the receipt's filled quantity")
    if (min(r.decision_price, r.arrival_price, r.submitted_price, r.average_fill, value_per_unit) <= ZERO
        or r.spread_at_submit < ZERO or modelled_cost_pct < ZERO):
        raise ValueError("TCA requires positive prices and contract value, nonnegative spread and modelled cost")
    if not isinstance(direction, Direction):
        raise ValueError("TCA direction must be LONG or SHORT")
    sign = 1 if direction is Direction.LONG else -1
    decision,arrival,submitted,fill,quantity,value,fees,spread,model=map(Fraction,
        (r.decision_price,r.arrival_price,r.submitted_price,r.average_fill,qty,value_per_unit,
         r.fees,r.spread_at_submit,modelled_cost_pct))
    slippage = (fill-submitted)*sign
    delay = (arrival-decision)*sign
    submission = (submitted-arrival)*sign
    spread_cost = spread*quantity*value/2
    # Fill-versus-reference already includes the spread. Keep it as a diagnostic,
    # and retain favorable fills/rebates with their actual negative cost sign.
    shortfall = (fill-decision)*sign*quantity*value+fees
    notional = decision*quantity*value
    realised_pct = _ratio(shortfall/notional)
    ratio = _ratio(shortfall/(notional*model)) if model>0 else Decimal('Infinity')
    components={'delay':delay*quantity*value,'submission':submission*quantity*value,
                'slippage':slippage*quantity*value,'nonembedded_charges':fees}
    if sum(components.values(),Fraction(0))!=shortfall:
        raise ValueError('TCA signed cost decomposition differs from direct cost')
    arithmetic={'schema':'vati.tca-exact-arithmetic/1','direction':direction.value,
        'components':{k:_fraction_body(v) for k,v in components.items()},
        'direct_cost':_fraction_body(shortfall),'reference_notional':_fraction_body(notional),
        'realised_cost_fraction':_fraction_body(shortfall/notional),
        'cost_ratio_fraction':_fraction_body(shortfall/(notional*model)) if model>0 else None,
        'ratio_display':'28_SIGNIFICANT_DIGITS_HALF_EVEN_FROM_EXACT_FRACTION',
        'fee_completeness':'RECEIPT_INPUT_ONLY_NOT_PROVIDER_COMPLETENESS',
        'execution_authority':False,'settlement_qualified':False}
    return TcaRecord(r.trade_intent_id, r.decision_price, r.arrival_price, r.submitted_price, r.average_fill,
        _finite_decimal(spread_cost),_finite_decimal(slippage),_finite_decimal(delay),r.fees,
        _finite_decimal(shortfall),modelled_cost_pct,realised_pct,ratio,
        _finite_decimal(submission),qty,value_per_unit,_finite_decimal(notional),
        _arithmetic_json=canonical_json(arithmetic))


def validate_tca_arithmetic(payload):
    """Verify new exact claims at consumption; leave historical v2 rows intact.

    This validates arithmetic, not the provider's fee coverage or settlement.
    The evidence resolver separately owns original durable producer/scope.
    """
    if 'arithmetic' not in payload:
        return
    try:
        def d(name):
            if type(payload[name])is not str or len(payload[name])>MAX_DIGITS*8+64:
                raise ValueError('TCA decimal wire capacity invalid')
            return Decimal(payload[name])
        receipt=ExecutionReceipt(payload['trade_intent_id'],'','', 'FILLED',d('filled_quantity'),
            d('fill_price'),d('decision_price'),d('arrival_price'),d('submitted_price'),False,0,0,
            spread_at_submit=ZERO,fees=d('fees'))
        # Spread is an embedded-cost diagnostic, excluded from the signed sum.
        # Reconstruct it exactly from its recorded monetary amount.
        spread=Fraction(d('spread_cost'))*2/(Fraction(d('filled_quantity'))*Fraction(d('contract_value_per_price_unit')))
        from dataclasses import replace
        receipt=replace(receipt,spread_at_submit=_finite_decimal(spread))
        expected=compute_tca(receipt,direction=Direction(payload['arithmetic']['direction']),
            qty=receipt.filled_qty,value_per_unit=d('contract_value_per_price_unit'),
            modelled_cost_pct=d('modelled_cost_pct')).as_dict()
        for key in ('arithmetic','slippage','delay_cost','submission_cost','implementation_shortfall',
                    'reference_notional','realised_cost_pct','cost_ratio','measurement_version'):
            if canonical_json(payload[key])!=canonical_json(expected[key]):
                raise ValueError('TCA exact cost record differs from its inputs')
    except (KeyError,TypeError,ValueError,ArithmeticError):
        raise ValueError('TCA exact arithmetic evidence invalid') from None


def same_tca_measurement(original, current):
    """Compare legacy numeric values without rewriting their original record.

    Decimal spelling and absence of the additive exact witness alone do not
    invalidate an old measurement. A changed economic value still conflicts.
    """
    try:
        validate_tca_arithmetic(original)
        for key,value in current.items():
            if key=='arithmetic' and key not in original:
                continue
            old=original[key]
            if key in ('trade_intent_id','measurement_version','arithmetic') or value is None:
                if canonical_json(old)!=canonical_json(value):return False
            elif type(old)is not str or Decimal(old)!=Decimal(value):
                return False
        return True
    except (KeyError,TypeError,ValueError,ArithmeticError):
        return False
