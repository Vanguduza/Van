"""Original MT5 symbol metadata, separate from native risk/FX qualification."""
from dataclasses import dataclass,asdict
import json,time

from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.mt5_expected_margin import _exact
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext

AMOUNTS=('volume_min','volume_step','volume_max','point','trade_contract_size','trade_tick_size',
         'trade_tick_value','trade_tick_value_profit','trade_tick_value_loss')
INTEGERS=('digits','trade_stops_level','trade_freeze_level','trade_mode','trade_calc_mode','spread')
CURRENCIES=('currency_base','currency_profit','currency_margin')
BASIS='NATIVE_SYMBOL_ACCOUNT_CURRENCY_VALUES_NO_SEPARATE_FX_TIMESTAMP'


def _symbol(value):
    if (type(value) is not str or not 1<=len(value)<=256
            or any(ord(c)<32 or ord(c)==127 or c=='|' for c in value)):
        raise ValueError('original native symbol text unavailable')
    return value


@dataclass(frozen=True,init=False)
class Mt5SymbolContractObservation:
    _body_json: bytes

    def body(self):return json.loads(self._body_json)

    @classmethod
    def from_body(cls,body):
        try:
            fields={'schema','native_account_context','request','observation','native_read_identity',
                'requested_at_ms','received_at_ms','valid_until_ms','state','source_ref',
                'risk_terms_qualified','provider_qualified','execution_authority'}
            if (type(body) is not dict or set(body)!=fields or body['schema']!='vati.mt5-symbol-contract/1'
                    or body['source_ref']!=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
                    or any(body[k] is not False for k in ('risk_terms_qualified','provider_qualified','execution_authority'))):
                raise ValueError('original symbol envelope or authority invalid')
            context=NativeAccountRiskContext(**body['native_account_context']);source=inspect_context(context)
            if context.provider!='MT5':raise ValueError('original MT5 context required')
            mark=source['mark'];identity=Mt5Identity(str(mark['login']),mark['server'],mark['currency'],mark['demo'])
            start=body['requested_at_ms'];end=body['received_at_ms'];deadline=body['valid_until_ms']
            native_int(start,minimum=source['observed_at_ms']);native_int(end,minimum=start)
            native_int(deadline,minimum=end+1)
            request=body['request'];raw=body['observation'];read=body['native_read_identity']
            if type(request) is not dict or set(request)!={'symbol'}:raise ValueError('symbol request changed')
            _symbol(request['symbol'])
            raw_fields={'schema','request','account_before','account_after','contract','requested_at_ms',
                'received_at_ms','deadline_ms','native_clock_basis','native_numeric_format','tick_value_basis',
                'account_snapshot_atomic','risk_terms_qualified','execution_authority'}
            if (type(raw) is not dict or set(raw)!=raw_fields or raw['schema']!='van.mt5.symbol-contract/1'
                    or raw['request']!=request or raw['tick_value_basis']!=BASIS
                    or any(raw[k] is not False for k in ('account_snapshot_atomic','risk_terms_qualified','execution_authority'))
                    or type(raw['deadline_ms']) is not int or raw['deadline_ms']!=deadline):
                raise ValueError('native symbol observation changed')
            for name in ('account_before','account_after'):
                account=raw[name];identity.validate(account)
                if (type(account.get('currency_digits')) is not int
                        or account['currency_digits']!=mark['currency_digits']):
                    raise ValueError('native symbol currency precision changed')
            native_int(raw['requested_at_ms'],minimum=0,maximum=end)
            native_int(raw['received_at_ms'],minimum=raw['requested_at_ms'],maximum=deadline-1)
            if type(read) is not dict:raise ValueError('original native read identity unavailable')
            if read.get('kind')=='SIGNED_MTLS_READ':
                if (set(read)!={'kind','request_nonce','worker_time_ms'}
                        or raw['native_clock_basis']!='UTC_HOST_MS'
                        or raw['native_numeric_format']!='PYTHON_BINARY64_SHORTEST'):
                    raise ValueError('native symbol signed protocol mismatch')
                native_int(read['request_nonce'],minimum=0,maximum=2**128-1)
                native_int(read['worker_time_ms'],minimum=raw['received_at_ms'],maximum=deadline-1)
            elif read.get('kind')=='EA_PULL_READ':
                if (set(read)!={'kind','queue_id'} or raw['native_clock_basis']!='UTC_SECOND_INTERVAL'
                        or raw['native_numeric_format']!='MQL_BINARY64_ROUNDTRIP'
                        or raw['requested_at_ms']%1000!=0 or raw['received_at_ms']%1000!=999
                        or raw['received_at_ms']<start):
                    raise ValueError('native symbol EA protocol or clock interval mismatch')
                native_int(read['queue_id'],minimum=1)
            else:raise ValueError('native symbol read transport unavailable')
            contract=raw['contract']
            if (type(contract) is not dict or set(contract)!={'symbol',*AMOUNTS,*INTEGERS,*CURRENCIES}
                    or contract['symbol']!=request['symbol']):raise ValueError('native symbol identity changed')
            values={key:_exact(contract[key],positive=key not in
                {'trade_tick_value','trade_tick_value_profit','trade_tick_value_loss'}) for key in AMOUNTS}
            if values['volume_max']<values['volume_min']:raise ValueError('native quantity bounds invalid')
            for key in INTEGERS:native_int(contract[key],minimum=0,maximum=2**31-1)
            for key in CURRENCIES:
                text=contract[key]
                if type(text) is not str or len(text)>64 or any(ord(c)<32 or ord(c)==127 for c in text):
                    raise ValueError('native currency metadata unavailable')
            expected='UNPRICED' if values['trade_tick_value_loss']==0 or not contract['currency_profit'] else 'OBSERVED_NATIVE_TERMS'
            if body['state']!=expected:raise ValueError('native terms availability changed')
            result=object.__new__(cls);object.__setattr__(result,'_body_json',canonical_json(body).encode());return result
        except (KeyError,TypeError,ValueError,ArithmeticError,VenueUnavailable):
            raise ValueError('original MT5 symbol contract, scope, units or read identity invalid') from None


def read_symbol_contract(adapter,symbol,*,context,deadline_ms,pull=False):
    try:
        start=native_int(adapter.clock(),minimum=0);native_int(deadline_ms,minimum=start+1)
        request={'symbol':_symbol(symbol)};source=inspect_context(context)
        if (context.provider!='MT5' or context.account_alias!=adapter.account_alias
                or type(adapter.identity) is not Mt5Identity or source['observed_at_ms']>start):
            raise ValueError('registered original native account required')
        adapter.identity.validate(source['mark'])
        if pull:
            support=adapter._state()['account'].get('symbol_contract_constraints')
            if (support!={'schema':'van.mt5.ea-symbol-constraints/1','required_op':'SYMBOL_CONTRACT',
                    'framed_fields':18,'explicit_deadline':True} or type(support.get('framed_fields')) is not int
                    or type(support.get('explicit_deadline')) is not bool):
                raise ValueError('native symbol EA read protocol unavailable')
            cid=adapter.queue.enqueue(adapter.account_alias,'SYMBOL_CONTRACT',{**request,
                'expected_account':adapter.identity.as_dict(),'expires_at_ms':deadline_ms},now_ms=start)
            stop=time.monotonic()+adapter.timeout_s;response=None
            while time.monotonic()<stop and adapter.clock()<deadline_ms:
                response=adapter.queue.result(cid)
                if response is not None:break
                time.sleep(adapter.poll_s)
            if response is None or 'error' in response:raise ValueError('native symbol original result unavailable')
            read={'kind':'EA_PULL_READ','queue_id':cid}
        else:
            response=adapter._call('symbol_contract',{'alias':adapter.account_alias,**request,
                'deadline_ms':deadline_ms},now_ms=start)
            read={'kind':'SIGNED_MTLS_READ','request_nonce':response['nonce'],'worker_time_ms':response['worker_time_ms']}
        end=native_int(adapter.clock(),minimum=start,maximum=deadline_ms-1);raw=response['observation']
        state='UNPRICED' if _exact(raw['contract']['trade_tick_value_loss'])==0 or not raw['contract']['currency_profit'] else 'OBSERVED_NATIVE_TERMS'
        body={'schema':'vati.mt5-symbol-contract/1','native_account_context':asdict(context),
            'request':request,'observation':raw,'native_read_identity':read,'requested_at_ms':start,
            'received_at_ms':end,'valid_until_ms':deadline_ms,'state':state,
            'risk_terms_qualified':False,'provider_qualified':False,'execution_authority':False}
        body['source_ref']=canonical_hash(body)
        return Mt5SymbolContractObservation.from_body(body)
    except Exception:
        raise VenueUnavailable('MT5 original symbol contract, native scope, units or deadline unavailable') from None
