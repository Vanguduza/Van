"""Immutable exact account valuations derived from original native snapshots.

The reader resolves actual existing ledger rows. A factory result alone proves
neither durable observation nor current collateral, settlement or authority.
"""
from dataclasses import dataclass
import json
import re

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import Event, EventKind
from vati.core.units import Money, UnitError
from vati.funding.native import NativeAccountMark, native_int
from vati.funding.unitization import NetEquityPoint

POLICY_VERSION='native-net-equity/1.0.0'
DIGEST=re.compile(r'[0-9a-f]{64}',re.ASCII)


def _money(value,mark):
    scale=max(0,-value.as_tuple().exponent)
    asset={key:getattr(mark,key) for key in ('provider','environment','deposit_asset_id','currency')}
    return Money.from_decimal(value,scale=scale,currency=mark.currency,asset_ref=canonical_hash(asset))


@dataclass(frozen=True,init=False)
class ValuationSnapshot:
    _body_json: bytes

    def __init__(self,source):
        try:
            if (type(source) is not Event or source.kind is not EventKind.ACCOUNT_SNAPSHOT
                    or source.producer not in {'vati-account-service','vati-service'}
                    or type(source.schema_version) is not int or source.schema_version!=1
                    or source.decision_time_ms is not None or source.hash!=canonical_hash(source.body())):
                raise UnitError('VALUATION_ORIGINAL_NATIVE_SNAPSHOT_REQUIRED')
            p=source.payload;mark=NativeAccountMark.from_body(p['native_account_mark'])
            native_int(source.event_time_ms,minimum=0)
            native_int(source.received_time_ms,minimum=mark.observed_at_ms)
            if (p.get('verified') is not True or p.get('account_alias')!=mark.account_alias
                    or p.get('currency')!=mark.currency
                    or source.event_time_ms>source.received_time_ms
                    or any(not isinstance(p.get(key),str) or not 1<=len(p[key])<=128
                        for key in ('balance','equity'))):
                raise UnitError('VALUATION_ORIGINAL_NATIVE_BINDING_INVALID')
            from decimal import Decimal
            balance=Decimal(p['balance']);equity=Decimal(p['equity'])
            if not balance.is_finite() or not equity.is_finite() or balance!=mark.balance or equity!=mark.net_equity:
                raise UnitError('VALUATION_ORIGINAL_NATIVE_BINDING_INVALID')
            cash=_money(mark.balance,mark);net=_money(mark.net_equity,mark)
            credits={name:None if getattr(mark,name) is None else _money(getattr(mark,name),mark).body()
                for name in ('manager_bonus','ib_bonus','nonwithdrawable_bonus')}
            body={'schema':'vati.valuation-snapshot/1','policy_version':POLICY_VERSION,
                'source_ref':source.hash,'scope_hash':mark.scope_hash,'native_mark':mark.body(),
                'source_event_at_ms':source.event_time_ms,'observed_at_ms':mark.observed_at_ms,
                'available_at_ms':source.received_time_ms,'native_balance_version':mark.balance_version,
                'cash_balance':cash.body(),'net_equity':net.body(),'separate_credits':credits,
                'value_basis':'BALANCE_PLUS_NATIVE_NET_UNREALIZED_EXCLUDING_SEPARATE_BONUSES',
                'scale_basis':'EXACT_STORED_DECIMAL_SCALE_NOT_SETTLEMENT_PRECISION',
                'availability_basis':'LOCAL_CAPTURE_CLOCK_NOT_NATIVE_CLOCK_QUALIFICATION',
                'conversion_basis':'NATIVE_DEPOSIT_ASSET_ONLY','holdings_valuation_complete':False,
                'settlement_qualification':'NOT_ISSUED','risk_capital_qualified':False,
                'execution_authority':False}
            object.__setattr__(self,'_body_json',canonical_json(body).encode())
        except UnitError:
            raise
        except (KeyError,TypeError,ValueError,ArithmeticError) as error:
            raise UnitError('VALUATION_ORIGINAL_NATIVE_SNAPSHOT_INVALID') from error

    def body(self):
        return json.loads(self._body_json)

    @property
    def net_equity(self):
        return Money.from_body(self.body()['net_equity'])

    def equity_point(self):
        body=self.body()
        return NetEquityPoint(body['scope_hash'],body['observed_at_ms'],
            self.net_equity.decimal,body['source_ref'],body['native_balance_version'])


def read_valuation(ledger,*,source_ref,scope_hash,max_snapshots=100000,max_bytes=128*1024**2):
    """Bounded read of a committed original; no append, inference or alias lookup."""
    if any(not isinstance(value,str) or DIGEST.fullmatch(value) is None for value in (source_ref,scope_hash)):
        raise UnitError('VALUATION_EXACT_SOURCE_AND_SCOPE_REQUIRED')
    if (type(max_snapshots) is not int or not 1<=max_snapshots<=100000
            or type(max_bytes) is not int or not 1<=max_bytes<=256*1024**2):
        raise UnitError('VALUATION_READ_CAPACITY_INVALID')
    # Reuse the existing financial ledger transaction guard. Uncommitted rows
    # in a caller's writer cannot become independently verified source facts.
    from vati.funding.movement_journal import FinancialMovementBook
    FinancialMovementBook(ledger)._transaction()
    with ledger.read_snapshot():
        expected=ledger.count(EventKind.ACCOUNT_SNAPSHOT)
        if expected>max_snapshots:
            raise UnitError('VALUATION_SOURCE_COUNT_CAPACITY')
        if not ledger.verify_chain()[0]:raise UnitError('VALUATION_ORIGINAL_JOURNAL_INTEGRITY_UNAVAILABLE')
        selected=None;size=0;count=0
        for source in ledger.iter(EventKind.ACCOUNT_SNAPSHOT):
            count+=1;size+=len(canonical_json(source.body()).encode())
            if size>max_bytes or count>max_snapshots:raise UnitError('VALUATION_SOURCE_BYTE_OR_COUNT_CAPACITY')
            if source.hash==source_ref:
                if selected is not None:raise UnitError('VALUATION_DUPLICATE_SOURCE_REFERENCE')
                selected=source
        if count!=expected:raise UnitError('VALUATION_ORIGINAL_READBACK_COUNT_INVALID')
        if selected is None:raise UnitError('VALUATION_ORIGINAL_SOURCE_UNAVAILABLE')
        valuation=ValuationSnapshot(selected)
        if valuation.body()['scope_hash']!=scope_hash:raise UnitError('VALUATION_ORIGINAL_NATIVE_SCOPE_MISMATCH')
        return valuation
