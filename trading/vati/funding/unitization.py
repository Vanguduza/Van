"""Exact sampled account returns after verified external flows, never risk authority.

Inputs must already be native-scoped net equity (withdrawal-restricted credit is
excluded by the provider normalizer). Missing valuation or ordering stays unknown.
The journal/collector supplies coverage; this calculator cannot certify a statement.
"""
from dataclasses import dataclass
from decimal import Context,Decimal,DivisionByZero,InvalidOperation,Overflow,ROUND_HALF_EVEN,localcontext
from enum import Enum
from fractions import Fraction
from itertools import groupby

POLICY_VERSION='funding-unitization/1.0.0'

class FlowKind(str,Enum):
    EXTERNAL='EXTERNAL_CAPITAL'
    INTERNAL='INTERNAL_ACCOUNT_PNL'
    CREDIT_EXCLUDED='CREDIT_ALREADY_EXCLUDED_FROM_NET_EQUITY'
    UNKNOWN='UNKNOWN'

@dataclass(frozen=True)
class NetEquityPoint:
    scope_hash: str
    at_ms: int
    equity: Decimal
    source_ref: str
    native_order: int | None=None

@dataclass(frozen=True)
class FlowPoint:
    scope_hash: str
    at_ms: int
    delta: Decimal
    net_equity_after: Decimal | None
    kind: FlowKind
    source_ref: str
    native_order: int | None=None


def _number(value):
    if not isinstance(value,Decimal) or not value.is_finite():raise ValueError('funding_exact_finite_decimal_required')
    if len(value.as_tuple().digits)>4096 or abs(value.as_tuple().exponent)>4096:
        raise ValueError('funding_numeric_resource_bound')
    return Fraction(value)


def _render(value):
    if value is None:return None
    # Exact fractions above are unchanged. Report serialization uses a fixed
    # context rather than inheriting another caller's rounding, traps or limits.
    with localcontext(Context(prec=80,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,
            capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])):
        return str(Decimal(value.numerator)/Decimal(value.denominator))


def unitize(baseline: NetEquityPoint, closing: NetEquityPoint, flows=()):
    """Unit issuance/redemption removes cash movement from sampled account return.

    Equal-time flows need native order; equal-time boundary valuations must also
    supply native order. This is marked account performance, not settled trade alpha.
    Prior sampled drawdown is retained when capital is added, removed or exhausted.
    """
    if not baseline.scope_hash or baseline.scope_hash!=closing.scope_hash or not baseline.source_ref or not closing.source_ref:
        raise ValueError('funding_valuation_scope_invalid')
    for point in (baseline,closing):
        if type(point.at_ms) is not int or point.at_ms<0:raise ValueError('funding_valuation_time_invalid')
        if point.native_order is not None and (type(point.native_order) is not int or point.native_order<0):raise ValueError('funding_native_order_invalid')
    if closing.at_ms<baseline.at_ms:raise ValueError('funding_valuation_time_invalid')
    initial=_number(baseline.equity);final=_number(closing.equity)
    supplied=list(flows);seen=set();ordered=[]
    for point in supplied:
        if point.scope_hash!=baseline.scope_hash or not point.source_ref or point.source_ref in seen:
            raise ValueError('funding_flow_identity_scope_invalid')
        if type(point.at_ms) is not int or not baseline.at_ms<=point.at_ms<=closing.at_ms:raise ValueError('funding_flow_time_invalid')
        if point.native_order is not None and (type(point.native_order) is not int or point.native_order<0):raise ValueError('funding_native_order_invalid')
        if not isinstance(point.kind,FlowKind):raise ValueError('funding_flow_classification_invalid')
        _number(point.delta)
        if point.net_equity_after is not None:_number(point.net_equity_after)
        seen.add(point.source_ref);ordered.append(point)
    ordered.sort(key=lambda p:p.at_ms)
    units=initial;nav=Fraction(1);peak=nav;worst=Fraction(0);external=Fraction(0);references=[baseline.source_ref]
    def report(status,reason=None):
        return {'policy_version':POLICY_VERSION,'status':status,'reason':reason,'scope_hash':baseline.scope_hash,
            'valuation_basis':'NORMALIZED_NATIVE_NET_EQUITY','return_basis':'MARKED_ACCOUNT_RETURN_NOT_SETTLED_TRADE_ALPHA',
            'from_ms':baseline.at_ms,'to_ms':closing.at_ms,'units':_render(units) if status!='UNMEASURED' else None,
            'known_prefix_units':_render(units),
            'nav_per_unit':_render(nav) if status!='UNMEASURED' else None,
            'flow_neutral_return':_render(nav-1) if status!='UNMEASURED' else None,
            'worst_observed_drawdown':_render(worst) if status!='UNMEASURED' else None,
            'known_prefix_drawdown':_render(worst) if initial>0 else None,
            'external_net_flow':_render(external) if status!='UNMEASURED' else None,'known_prefix_external_net_flow':_render(external),
            'net_account_pnl':_render(final-initial-external) if status!='UNMEASURED' else None,
            'input_refs':[baseline.source_ref]+[p.source_ref for p in supplied]+[closing.source_ref],
            'evidence_refs':references+[closing.source_ref] if status!='UNMEASURED' else [],'execution_authority':False}
    if initial<=0:return report('UNMEASURED','INITIAL_NET_EQUITY_NOT_POSITIVE')
    for at,group in groupby(ordered,key=lambda p:p.at_ms):
        group=list(group)
        if len(group)>1:
            if any(p.native_order is None for p in group) or len({p.native_order for p in group})!=len(group):
                return report('UNMEASURED','NATIVE_FLOW_ORDER_UNAVAILABLE')
            group.sort(key=lambda p:p.native_order)
        for point in group:
            if at==baseline.at_ms and (baseline.native_order is None or point.native_order is None or point.native_order<=baseline.native_order):
                return report('UNMEASURED','BASELINE_FLOW_ORDER_UNAVAILABLE')
            if at==closing.at_ms and (closing.native_order is None or point.native_order is None or point.native_order>closing.native_order):
                return report('UNMEASURED','CLOSING_FLOW_ORDER_UNAVAILABLE')
            if point.kind is FlowKind.UNKNOWN:return report('UNMEASURED','UNCLASSIFIED_NATIVE_MOVEMENT')
            if point.net_equity_after is None:return report('UNMEASURED','NATIVE_NET_FLOW_VALUATION_UNAVAILABLE')
            after=_number(point.net_equity_after);delta=_number(point.delta)
            before=after-delta if point.kind is FlowKind.EXTERNAL else after
            if units>0:
                nav=before/units;peak=max(peak,nav);worst=max(worst,(peak-nav)/peak)
            elif before!=0:return report('UNMEASURED','ECONOMIC_CHANGE_WITHOUT_ACTIVE_UNITS')
            if point.kind is FlowKind.EXTERNAL:
                if nav<=0:return report('UNMEASURED','NONPOSITIVE_NAV_AT_EXTERNAL_FLOW')
                next_units=units+delta/nav
                if next_units<0:return report('UNMEASURED','OUTFLOW_EXCEEDS_NET_CAPITAL')
                units=next_units;external+=delta
            references.append(point.source_ref)
            if max(units.numerator.bit_length(),units.denominator.bit_length())>65536:
                return report('UNMEASURED','EXACT_CALCULATION_RESOURCE_BOUND')
    if units>0:
        nav=final/units;peak=max(peak,nav);worst=max(worst,(peak-nav)/peak)
    elif final!=0:return report('UNMEASURED','CLOSING_EQUITY_WITHOUT_ACTIVE_UNITS')
    return report('MEASURED' if units>0 else 'NO_ACTIVE_CAPITAL')
