"""Original MT5 isolated-order margin, outside reservation/settlement authority."""
from dataclasses import asdict,dataclass
from decimal import Decimal
from fractions import Fraction
import json
import math
import time

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.units import Money
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_identity import Mt5Identity
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext,Direction

BASIS='ISOLATED_ORDER_AT_REQUEST_PRICE_EXCLUDES_EXISTING_POSITIONS_AND_PENDING_ORDERS'


def _exact(value,*,positive=False):
    if type(value) is not str or not 1<=len(value)<=128:raise ValueError('native exact decimal text required')
    result=Decimal(value)
    if (not result.is_finite() or abs(result.as_tuple().exponent)>64
            or (result<=0 if positive else result<0)):raise ValueError('native exact value unavailable')
    return result


def _money(amount,context,currency):
    return Money.from_decimal(amount,scale=max(0,-amount.as_tuple().exponent),
        currency=currency,asset_ref=context.monetary_scope_hash).body()


def _contract_amount(contract,key):
    value=contract[key]
    if 'native_numeric_format' in contract:
        if contract['native_numeric_format']!='MQL_BINARY64_ROUNDTRIP':raise ValueError('native number format unavailable')
        native=float(value)
        if not math.isfinite(native):raise ValueError('native binary64 metadata unavailable')
        # This reconstructs the original native double. Its original 17-digit
        # text remains in the observation; financial sizing never reads a float.
        value=str(native)
    return _exact(value,positive=True)


@dataclass(frozen=True,init=False)
class Mt5ExpectedMarginObservation:
    _body_json: bytes

    def body(self):return json.loads(self._body_json)

    @classmethod
    def from_body(cls,body):
        fields={'schema','native_account_context','observation','request','native_read_identity','requested_at_ms',
            'received_at_ms','valid_until_ms','estimate_money','reported_currency_digits',
            'reservation_amount','reservation_qualified','execution_authority','provider_qualified','source_ref'}
        if (type(body) is not dict or set(body)!=fields or body['schema']!='vati.mt5-expected-margin/1'
                or body['source_ref']!=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
                or any(body[k] is not False for k in ('reservation_qualified','execution_authority','provider_qualified'))
                or body['reservation_amount'] is not None):raise ValueError('original MT5 estimate format or authority invalid')
        context=NativeAccountRiskContext(**body['native_account_context']);source=inspect_context(context)
        if context.provider!='MT5':raise ValueError('original MT5 source required')
        mark=source['mark'];identity=Mt5Identity(str(mark['login']),mark['server'],mark['currency'],mark['demo'])
        start=body['requested_at_ms'];end=body['received_at_ms'];deadline=body['valid_until_ms']
        native_int(start,minimum=0);native_int(end,minimum=start);native_int(deadline,minimum=end+1)
        if source['observed_at_ms']>start:raise ValueError('future native account source')
        raw=body['observation'];request=body['request']
        read=body['native_read_identity']
        if type(read) is not dict:raise ValueError('original native read identity required')
        if read.get('kind')=='SIGNED_MTLS_READ':
            if set(read)!={'kind','request_nonce','worker_time_ms'}:raise ValueError('original native read identity format')
            native_int(read['request_nonce'],minimum=0,maximum=2**128-1)
            native_int(read['worker_time_ms'],minimum=0)
            if 'native_clock_basis' in raw or 'native_numeric_format' in raw['contract']:
                raise ValueError('signed native read format mismatch')
        elif read.get('kind')=='EA_PULL_READ':
            if set(read)!={'kind','queue_id'}:raise ValueError('original EA read identity format')
            native_int(read['queue_id'],minimum=1)
            if (raw.get('native_clock_basis')!='UTC_SECOND_INTERVAL'
                    or raw['contract'].get('native_numeric_format')!='MQL_BINARY64_ROUNDTRIP'):
                raise ValueError('original EA numeric or clock format unavailable')
        else:raise ValueError('original native read transport unavailable')
        if (raw['schema']!='van.mt5.expected-margin/1' or raw['state']!='OBSERVED'
                or raw['valuation_basis']!=BASIS or raw['account_snapshot_atomic'] is not False
                or raw['reservation_qualified'] is not False or raw['execution_authority'] is not False
                or canonical_json(raw['request'])!=canonical_json(request)
                or type(request) is not dict or set(request)!={'symbol','type','volume','price'}
                or request['type'] not in {'BUY','SELL'} or type(request['symbol']) is not str
                or not 1<=len(request['symbol'])<=256 or any(ord(c)<32 for c in request['symbol'])):
            raise ValueError('original native margin request mismatch')
        _exact(request['volume'],positive=True);_exact(request['price'],positive=True)
        contract=raw['contract']
        lo=_contract_amount(contract,'volume_min');hi=_contract_amount(contract,'volume_max')
        step=_contract_amount(contract,'volume_step');tick=_contract_amount(contract,'trade_tick_size')
        quantity=_exact(request['volume'],positive=True);price=_exact(request['price'],positive=True)
        if (not lo<=quantity<=hi or Fraction(quantity)%Fraction(step) or Fraction(price)%Fraction(tick)):
            raise ValueError('original native quantity or price increment changed')
        a,b=raw['account_before'],raw['account_after']
        try:identity.validate(a);identity.validate(b)
        except VenueUnavailable:raise ValueError('original native margin account differs from its source') from None
        digits=native_int(raw['currency_digits'],minimum=0,maximum=16)
        stable=('login','server','demo','currency','currency_digits','leverage','hedging','margin_mode')
        if (any(canonical_json(a[k])!=canonical_json(b[k]) for k in stable)
                or native_int(a['currency_digits'],minimum=0,maximum=16)!=digits
                or type(a['hedging']) is not bool or a['hedging']!=(a['margin_mode']==2)
                or native_int(a['margin_mode'],minimum=0,maximum=2) not in (0,1,2)):
            raise ValueError('original native margin account changed')
        native_int(a['leverage'],minimum=1)
        native_int(raw['requested_at_ms'],minimum=0)
        native_int(raw['received_at_ms'],minimum=raw['requested_at_ms'],maximum=deadline-1)
        if raw['deadline_ms']!=deadline or type(raw['deadline_ms']) is not int:
            raise ValueError('original native margin deadline changed')
        margin=_exact(raw['raw_margin'])
        if (body['estimate_money']!=_money(margin,context,source['currency'])
                or type(body['reported_currency_digits']) is not int or body['reported_currency_digits']!=digits):
            raise ValueError('original native margin estimate units changed')
        if raw['contract']['symbol']!=request['symbol']:raise ValueError('original native contract changed')
        value=object.__new__(cls);object.__setattr__(value,'_body_json',canonical_json(body).encode());return value


def read_bridge_expected_margin(adapter,symbol,lots,*,price,direction,context,deadline_ms):
    return _read_expected_margin(adapter,symbol,lots,price=price,direction=direction,context=context,
        deadline_ms=deadline_ms,pull=False)


def read_pull_expected_margin(adapter,symbol,lots,*,price,direction,context,deadline_ms):
    return _read_expected_margin(adapter,symbol,lots,price=price,direction=direction,context=context,
        deadline_ms=deadline_ms,pull=True)


def _read_expected_margin(adapter,symbol,lots,*,price,direction,context,deadline_ms,pull):
    try:
        start=native_int(adapter.clock(),minimum=0);native_int(deadline_ms,minimum=start+1)
        if type(lots) is not Decimal or type(price) is not Decimal or type(direction) is not Direction:
            raise ValueError('typed original native quote inputs required')
        if (type(symbol) is not str or not 1<=len(symbol)<=256
                or any(ord(c)<32 or ord(c)==127 or c=='|' for c in symbol)):
            raise ValueError('native product text cannot retain its protocol identity')
        _exact(str(lots),positive=True);_exact(str(price),positive=True)
        if (not math.isfinite(float(lots)) or not math.isfinite(float(price))
                or Decimal(str(float(lots)))!=lots or Decimal(str(float(price)))!=price):
            raise ValueError('original decimal request is not retained by native binary64 input')
        source=inspect_context(context)
        if (context.provider!='MT5' or context.account_alias!=adapter.account_alias
                or type(adapter.identity) is not Mt5Identity or source['observed_at_ms']>start):
            raise ValueError('registered native account binding unavailable')
        adapter.identity.validate(source['mark'])
        request={'symbol':symbol,'type':'BUY' if direction is Direction.LONG else 'SELL',
            'volume':str(lots),'price':str(price)}
        if pull:
            state=adapter._state()
            support=state['account'].get('expected_margin_constraints')
            if (support!={'schema':'van.mt5.ea-margin-constraints/1',
                    'required_op':'MARGIN_QUOTE','framed_fields':18,'explicit_deadline':True}
                    or type(support.get('explicit_deadline')) is not bool or type(support.get('framed_fields')) is not int):
                raise ValueError('native EA margin read protocol unavailable')
            cid=adapter.queue.enqueue(adapter.account_alias,'MARGIN_QUOTE',{**request,
                'expected_account':adapter.identity.as_dict(),'expires_at_ms':deadline_ms},now_ms=start)
            stop=time.monotonic()+adapter.timeout_s;response=None
            while time.monotonic()<stop and adapter.clock()<deadline_ms:
                response=adapter.queue.result(cid)
                if response is not None:break
                time.sleep(adapter.poll_s)
            if response is None or 'error' in response:raise ValueError('original native margin read result unavailable')
            # The authenticated poll handler joins result.id to this exact SQL
            # row and strips the envelope id before storing its original body.
            read_identity={'kind':'EA_PULL_READ','queue_id':cid}
        else:
            response=adapter._call('expected_margin',{'alias':adapter.account_alias,**request,
                'deadline_ms':deadline_ms},now_ms=start)
            read_identity={'kind':'SIGNED_MTLS_READ','request_nonce':response['nonce'],
                'worker_time_ms':response['worker_time_ms']}
        raw=response['observation'];end=native_int(adapter.clock(),minimum=start,maximum=deadline_ms-1)
        margin=_exact(raw['raw_margin'])
        body={'schema':'vati.mt5-expected-margin/1','native_account_context':asdict(context),
            'observation':raw,'request':request,'requested_at_ms':start,'received_at_ms':end,
            'native_read_identity':read_identity,
            'valid_until_ms':deadline_ms,'estimate_money':_money(margin,context,source['currency']),
            'reported_currency_digits':raw['currency_digits'],'reservation_amount':None,
            'reservation_qualified':False,'execution_authority':False,'provider_qualified':False}
        body['source_ref']=canonical_hash(body)
        return Mt5ExpectedMarginObservation.from_body(body)
    except Exception:
        raise VenueUnavailable('MT5 original expected-margin input, native scope, precision or deadline unavailable') from None
