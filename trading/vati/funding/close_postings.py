"""Balanced original native closing-balance observations, never settlement.

These projections preserve native fee fields without guessing their component
sign conventions or treating an absent fee as zero. The existing financial
movement owner must independently resolve both original records in its ledger;
standalone Event objects and hashes do not establish durable observation.
"""
from dataclasses import dataclass
import json

from vati.core import EventKind
from vati.core.events import Event
from vati.core.canonical import canonical_hash,canonical_json
from vati.core.units import Money,Posting,UnitError,balanced_postings
from vati.funding.native import native_int,NativeAccountMark
from vati.funding.journal import FundingBook
from vati.funding.deal_journal import DealBook
from vati.funding.valuation import ValuationSnapshot


def _scope(statement):
    return {key:getattr(statement,key) for key in
        ('provider','environment','native_account_id','deposit_asset_id','currency')}


def _statement(event,owner):
    if (type(event)is not Event or event.kind is not owner.kind or event.producer!=owner.producer
            or type(event.schema_version)is not int or event.schema_version!=1
            or event.decision_time_ms is not None or event.hash!=canonical_hash(event.body())):
        raise UnitError('FINANCIAL_CLOSE_ORIGINAL_SOURCE_EVENT_REQUIRED')
    p=event.payload
    if (type(p)is not dict or set(p)!={'schema','scope_hash','content_key','state','statement',
            'conflicting_original_refs','execution_authority'} or p['schema']!=owner.schema
            or p['state']!='OBSERVED' or p['conflicting_original_refs']!={}
            or p['execution_authority'] is not False):
        raise UnitError('FINANCIAL_CLOSE_OBSERVED_SOURCE_REQUIRED')
    statement=owner.statement_type.from_body(p['statement']);owner._validate(statement)
    if (p['scope_hash']!=statement.scope_hash or p['content_key']!=owner._key(statement)
            or event.correlation_id!=owner.correlation_prefix+statement.scope_hash
            or type(event.event_time_ms)is not int or event.event_time_ms!=statement.to_ms):
        raise UnitError('FINANCIAL_CLOSE_SOURCE_BINDING_INVALID')
    native_int(event.received_time_ms,minimum=statement.observed_at_ms)
    return statement


def _point(event,native_id):
    if type(event)is not Event:raise UnitError('FINANCIAL_CLOSE_BALANCE_ANCHOR_REQUIRED')
    if event.kind is EventKind.ACCOUNT_SNAPSHOT:
        if native_id is not None:raise UnitError('FINANCIAL_CLOSE_MARK_ANCHOR_ID_INVALID')
        valuation=ValuationSnapshot(event)
        mark=NativeAccountMark.from_body(valuation.body()['native_mark'])
        scope,balance,version=_scope(mark),mark.balance,mark.balance_version
    elif event.kind is EventKind.FUNDING_STATEMENT:
        native_int(native_id,minimum=1);statement=_statement(event,FundingBook)
        rows=[r for r in statement.movements if r.native_id==native_id]
        if len(rows)!=1:raise UnitError('FINANCIAL_CLOSE_BALANCE_ANCHOR_UNAVAILABLE')
        row=rows[0];scope,balance,version=_scope(statement),row.balance_after,row.balance_version
    elif event.kind is EventKind.FUNDING_DEAL_STATEMENT:
        native_int(native_id,minimum=1);statement=_statement(event,DealBook)
        rows=[r for r in statement.deals if r.native_id==native_id and r.close is not None]
        if len(rows)!=1:raise UnitError('FINANCIAL_CLOSE_BALANCE_ANCHOR_UNAVAILABLE')
        row=rows[0];scope,balance,version=_scope(statement),row.close.balance_after,row.close.balance_version
    else:raise UnitError('FINANCIAL_CLOSE_BALANCE_ANCHOR_KIND_INVALID')
    native_int(version,minimum=0)
    return scope,balance,version,{'kind':event.kind.value,'record_ref':event.hash,
        'native_id':None if native_id is None else str(native_id),'available_at_ms':event.received_time_ms}


@dataclass(frozen=True,init=False)
class FinancialCloseMovement:
    _body_json:bytes

    def __init__(self,source,native_id,balance_anchor,*,anchor_native_id=None,recorded_at_ms):
        native_int(native_id,minimum=1)
        statement=_statement(source,DealBook)
        rows=[row for row in statement.deals if row.native_id==native_id and row.close is not None]
        if len(rows)!=1:raise UnitError('FINANCIAL_CLOSE_ORIGINAL_NATIVE_ID_UNAVAILABLE')
        row=rows[0];detail=row.close;scope=_scope(statement)
        before_scope,before,version,anchor=_point(balance_anchor,anchor_native_id)
        native_int(detail.balance_version,minimum=1)
        if before_scope!=scope or version+1!=detail.balance_version:
            raise UnitError('FINANCIAL_CLOSE_ADJACENT_NATIVE_BALANCE_REQUIRED')
        available=max(source.received_time_ms,balance_anchor.received_time_ms)
        native_int(recorded_at_ms,minimum=available)
        scale=max(detail.money_digits,max(0,-before.as_tuple().exponent))
        asset=canonical_hash({k:scope[k] for k in ('provider','environment','deposit_asset_id','currency')})
        first=Money.from_decimal(before,scale=scale,currency=statement.currency,asset_ref=asset)
        last=Money.from_decimal(detail.balance_after,scale=scale,currency=statement.currency,asset_ref=asset)
        amount=Money(last.minor_units-first.minor_units,scale,statement.currency,asset)
        postings=balanced_postings((Posting('observed-broker-cash:'+statement.scope_hash,amount),
            Posting('clearing-native-close-observation:'+statement.scope_hash,-amount)))
        body={'schema':'vati.financial-close-movement/1','policy_version':'native-close-balance-posting/1.0.0',
            'movement_id':canonical_hash({'source_kind':'CTRADER_NATIVE_CLOSE','scope_hash':statement.scope_hash,
                'native_id':str(native_id)}),'source_kind':'CTRADER_NATIVE_CLOSE',
            'scope_hash':statement.scope_hash,'native_scope':scope,'native_id':str(native_id),
            'source_origin_alias':statement.account_alias,'source_statement_ref':source.hash,
            'source_row_digest':canonical_hash(row.body()),'balance_anchor':anchor,
            'native_balance_version_before':version,'native_balance_version_after':detail.balance_version,
            'balance_before':first.body(),'balance_after':last.body(),'amount':amount.body(),
            'occurred_at_ms':row.occurred_at_ms,'source_observed_at_ms':statement.observed_at_ms,
            'source_available_at_ms':available,'recorded_at_ms':recorded_at_ms,
            'availability_basis':'LOCAL_CAPTURE_CLOCK_NOT_NATIVE_CLOCK_QUALIFICATION',
            'raw_fee_observations':{'deal_commission':None if row.commission is None else str(row.commission),
                'deal_money_digits':row.money_digits,'close':detail.body()},
            'fee_allocation_state':'UNQUALIFIED_NOT_INFERRED_FROM_BALANCE_DELTA',
            'classification':{'state':'OBSERVED_NOT_ECONOMICALLY_ADMITTED','category':'NATIVE_CLOSE_BALANCE_DELTA'},
            'postings':[p.body() for p in postings],'state':'OBSERVED_CLOSE_BALANCE_NOT_SETTLEMENT',
            'posting_basis':'ADJACENT_ORIGINAL_NATIVE_BALANCE_VERSIONS',
            'settlement_qualification':'NOT_ISSUED','risk_capital_qualified':False,
            'trade_alpha_claimed':False,'execution_authority':False}
        object.__setattr__(self,'_body_json',canonical_json(body).encode())

    def body(self):return json.loads(self._body_json)

    @property
    def digest(self):return canonical_hash(self.body())

    @property
    def postings(self):return tuple(Posting.from_body(p) for p in self.body()['postings'])
