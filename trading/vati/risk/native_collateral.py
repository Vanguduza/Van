"""Exact original cash-backed capacity, not collateral admission or a grant.

The source reader independently resolves the original sealed native input.
Reported credit-inclusive free margin cannot replenish cash risk capacity.
Reservations, settlement, fresh native checks and execution keep their owners.
"""
from dataclasses import dataclass
from decimal import Decimal
import json

from vati.core.canonical import canonical_json
from vati.core.units import Money
from vati.risk.account_context import inspect_context
from vati.risk.margin import cash_margin_bounds
from vati.risk.native_history import original_native_risk_input


def _money(value, context, currency):
    # This is an account-scoped budget denomination. It is not a cross-account
    # payment asset or a conversion proof; monetary scope cannot be discarded.
    return Money.from_decimal(value, scale=max(0,-value.as_tuple().exponent),
        currency=currency, asset_ref=context.monetary_scope_hash).body()


@dataclass(frozen=True, init=False)
class OriginalNativeCollateral:
    _body_json: bytes

    def body(self):
        return json.loads(self._body_json)


def original_native_collateral(ledger, event_ref, *, available_at_ms):
    """Read historical capacity independently; expired approvals stay data."""
    body={'schema':'vati.original-native-collateral/1','state':'UNAVAILABLE',
        'reason':'ORIGINAL_NATIVE_INPUT_UNAVAILABLE','source_event_ref':event_ref,
        'execution_authority':False,'risk_capital_qualified':False,
        'settlement_qualification':'NOT_ISSUED','available_capacity':None}
    try:
        original=original_native_risk_input(ledger,event_ref,available_at_ms=available_at_ms)
        context=original.context;source=inspect_context(context)
        snap=json.loads(original.snapshot_json)
        equity=Decimal(snap['equity'])
        body.update(physical_account_key=context.physical_account_key,
            monetary_scope_hash=context.monetary_scope_hash,origin_alias=context.account_alias,
            observation_ref=context.observation_ref,source_query_ref=context.source_query_ref,
            original_event_time_ms=original.event_time_ms,
            original_available_at_ms=original.received_time_ms,
            native_observed_at_ms=source['observed_at_ms'],
            currency=source['currency'],net_equity=_money(equity,context,source['currency']),
            value_basis='ORIGINAL_NATIVE_NET_EQUITY_AND_SEALED_MARGIN_CASH_BOUND',
            budget_denomination='ACCOUNT_MONETARY_SCOPE_NOT_PAYMENT_ASSET_OR_CONVERSION_PROOF')
        raw=[snap.get(k) for k in ('used_margin','free_margin','margin_level_pct')]
        if any(v is not None and type(v) is not str for v in raw):
            raise ValueError('native margin requires exact decimal source strings')
        used,free,level=[None if v is None else Decimal(v) for v in raw]
        if any(v is not None and not v.is_finite() for v in (used,free,level)):
            raise ValueError('native margin must be finite')
        if used is None or free is None or used>0 and level is None:
            body.update(state='UNMEASURED',reason='ORIGINAL_NATIVE_MARGIN_NOT_OBSERVED')
        elif used<0 or level is not None and level<0 or used==0 and level is not None:
            raise ValueError('native margin usage/ratio is inconsistent')
        else:
            bound,_=cash_margin_bounds(equity,used,free,level)
            body.update(state='MEASURED',reason='',used_margin=_money(used,context,source['currency']),
                reported_free_margin=_money(free,context,source['currency']),
                cash_free_margin_bound=_money(bound,context,source['currency']),
                available_capacity=_money(max(Decimal(0),bound),context,source['currency']))
    except Exception as exc:
        # This read cannot supply an input fallback or expose native details.
        body.update(state='UNAVAILABLE',reason=('ORIGINAL_NATIVE_MARGIN_INVALID'
            if 'physical_account_key' in body else 'ORIGINAL_NATIVE_INPUT_UNAVAILABLE'),
            available_capacity=None)
    value=object.__new__(OriginalNativeCollateral)
    object.__setattr__(value,'_body_json',canonical_json(body).encode())
    return value
