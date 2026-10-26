"""Balanced native-cash source projections, never settlement or spend authority.

The source event still has to be independently resolved by the journal owner.
A sealed Python Event supplied by a caller is not proof of durable observation.
"""
from dataclasses import dataclass

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import Event, EventKind
from vati.core.units import Money, Posting, UnitError, balanced_postings
from vati.funding.classification import classify
from vati.funding.journal import FundingBook, PRODUCER, SCHEMA
from vati.funding.native import NativeCashStatement, native_int

POLICY_VERSION = 'native-cash-posting/1.0.0'


@dataclass(frozen=True, init=False)
class FinancialMovement:
    _body_json: bytes

    def __init__(self, source, native_id, *, recorded_at_ms):
        native_int(native_id, minimum=1)
        if (type(source) is not Event or source.kind is not EventKind.FUNDING_STATEMENT
                or source.producer != PRODUCER or type(source.schema_version) is not int
                or source.schema_version != 1 or source.decision_time_ms is not None
                or source.hash != canonical_hash(source.body())):
            raise UnitError('FINANCIAL_MOVEMENT_ORIGINAL_SOURCE_EVENT_REQUIRED')
        p = source.payload
        if (not isinstance(p, dict) or set(p) != {'schema','scope_hash','content_key','state',
                    'statement','conflicting_original_refs','execution_authority'}
                or p.get('schema') != SCHEMA or p.get('state') != 'OBSERVED'
                or p['conflicting_original_refs'] != {} or p['execution_authority'] is not False):
            raise UnitError('FINANCIAL_MOVEMENT_OBSERVED_SOURCE_REQUIRED')
        statement = NativeCashStatement.from_body(p['statement'])
        FundingBook._validate(statement)
        if (p['scope_hash'] != statement.scope_hash or p['content_key'] != FundingBook._key(statement)
                or source.correlation_id != FundingBook.correlation_prefix + statement.scope_hash
                or type(source.event_time_ms) is not int or source.event_time_ms != statement.to_ms):
            raise UnitError('FINANCIAL_MOVEMENT_SOURCE_BINDING_INVALID')
        native_int(source.received_time_ms, minimum=statement.observed_at_ms)
        native_int(recorded_at_ms, minimum=source.received_time_ms)
        rows = [row for row in statement.movements if row.native_id == native_id]
        if len(rows) != 1:
            raise UnitError('FINANCIAL_MOVEMENT_ORIGINAL_NATIVE_ID_UNAVAILABLE')
        row = rows[0]
        scope = {key:getattr(statement,key) for key in
            ('provider','environment','native_account_id','deposit_asset_id','currency')}
        asset = {key:scope[key] for key in ('provider','environment','deposit_asset_id','currency')}
        amount = Money.from_decimal(row.delta, scale=row.money_digits,
            currency=statement.currency, asset_ref=canonical_hash(asset))
        classification = classify(row.operation, row.delta)
        category = classification['category']
        if classification['state'] != 'CLASSIFIED':
            debit, credit = 'unresolved-native-control', 'native-suspense'
            state, basis = 'UNRESOLVED_NATIVE_MOVEMENT', 'UNRESOLVED_NATIVE_CONTROL'
        elif category == 'RESTRICTED_CREDIT':
            debit, credit = 'restricted-credit-control', 'restricted-credit-source'
            state, basis = 'RESTRICTED_CREDIT_MEMORANDUM', 'NONWITHDRAWABLE_CREDIT_CONTROL'
        else:
            debit, credit = 'observed-broker-cash', 'clearing-' + category.lower()
            state, basis = 'OBSERVED_CASH_NOT_SETTLEMENT', 'ORIGINAL_NATIVE_CASH_DELTA'
        postings = balanced_postings((Posting(debit + ':' + statement.scope_hash, amount),
            Posting(credit + ':' + statement.scope_hash, -amount)))
        body = {'schema':'vati.financial-movement/1','policy_version':POLICY_VERSION,
            'movement_id':canonical_hash({'source_kind':'CTRADER_NATIVE_CASH',
                'scope_hash':statement.scope_hash,'native_id':str(native_id)}),
            'source_kind':'CTRADER_NATIVE_CASH','native_scope':scope,'scope_hash':statement.scope_hash,
            'native_id':str(native_id),'native_operation':row.operation,
            'source_statement_ref':source.hash,'source_row_digest':canonical_hash(row.body()),
            'occurred_at_ms':row.occurred_at_ms,'source_observed_at_ms':statement.observed_at_ms,
            'source_available_at_ms':source.received_time_ms,'recorded_at_ms':recorded_at_ms,
            'availability_basis':'LOCAL_CAPTURE_CLOCK_NOT_NATIVE_CLOCK_QUALIFICATION',
            'amount':amount.body(),'classification':classification,
            'postings':[posting.body() for posting in postings], 'state':state,'posting_basis':basis,
            'settlement_qualification':'NOT_ISSUED','risk_capital_qualified':False,
            'trade_alpha_claimed':False,'execution_authority':False}
        object.__setattr__(self, '_body_json', canonical_json(body).encode())

    def body(self):
        import json
        return json.loads(self._body_json)

    @property
    def digest(self):
        return canonical_hash(self.body())

    @property
    def postings(self):
        return tuple(Posting.from_body(row) for row in self.body()['postings'])
