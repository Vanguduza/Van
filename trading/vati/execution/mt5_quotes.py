"""Original full native tick snapshots and explicit causal quote states."""
from dataclasses import dataclass,asdict
import json,time

from vati.core.canonical import canonical_hash,canonical_json
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.mt5_expected_margin import _exact
from vati.execution.mt5_symbol_contract import AMOUNTS,INTEGERS,CURRENCIES,_symbol
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext

TICK_TIME='BROKER_UTC_LATEST_FULL_TICK_SNAPSHOT_NOT_INDIVIDUAL_SIDE_TIMES'
VOLUME_BASIS='NATIVE_LAST_TRADE_VOLUME_NOT_LOTS_OR_GENUINE_DEPTH'


def _integer_text(value):
    if value is None:return None
    if (type(value) is not str or not value.isascii() or not value.isdigit()
            or len(value)>20 or str(int(value))!=value):raise ValueError('native tick integer text unavailable')
    return native_int(int(value),minimum=0,maximum=2**64-1)


@dataclass(frozen=True,init=False)
class Mt5QuoteObservation:
    _body_json: bytes

    def body(self):return json.loads(self._body_json)

    @classmethod
    def from_body(cls,body):
        try:
            fields={'schema','native_account_context','request','observation','native_read_identity',
                'requested_at_ms','received_at_ms','valid_until_ms','source_ref',
                'risk_terms_qualified','provider_qualified','execution_authority'}
            if (type(body) is not dict or set(body)!=fields or body['schema']!='vati.mt5-quote-snapshot/1'
                    or body['source_ref']!=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
                    or any(body[k] is not False for k in ('risk_terms_qualified','provider_qualified','execution_authority'))):
                raise ValueError('original native quote envelope invalid')
            ctx=NativeAccountRiskContext(**body['native_account_context']);source=inspect_context(ctx)
            if ctx.provider!='MT5':raise ValueError('original MT5 quote scope required')
            mark=source['mark'];identity=Mt5Identity(str(mark['login']),mark['server'],mark['currency'],mark['demo'])
            start=body['requested_at_ms'];end=body['received_at_ms'];deadline=body['valid_until_ms']
            native_int(start,minimum=source['observed_at_ms']);native_int(end,minimum=start)
            native_int(deadline,minimum=end+1)
            request=body['request'];raw=body['observation'];read=body['native_read_identity']
            if type(request) is not dict or set(request)!={'symbol'}:raise ValueError('native quote request mismatch')
            _symbol(request['symbol'])
            raw_fields={'schema','request','account_before','account_after','contract_before','contract_after','tick',
                'symbol_selected','subscription_delayed','requested_at_ms','received_at_ms','deadline_ms',
                'native_clock_basis','native_numeric_format','tick_time_basis','volume_basis',
                'account_snapshot_atomic','risk_terms_qualified','execution_authority'}
            if (type(raw) is not dict or set(raw)!=raw_fields or raw['schema']!='van.mt5.quote-snapshot/1'
                    or raw['request']!=request or raw['tick_time_basis']!=TICK_TIME or raw['volume_basis']!=VOLUME_BASIS
                    or any(raw[k] is not False for k in ('account_snapshot_atomic','risk_terms_qualified','execution_authority'))
                    or type(raw['deadline_ms']) is not int or raw['deadline_ms']!=deadline):
                raise ValueError('native quote data or semantics changed')
            for key in ('symbol_selected','subscription_delayed'):
                if raw[key] is not None and type(raw[key]) is not bool:raise ValueError('native quote subscription fact invalid')
            for key in ('account_before','account_after'):
                identity.validate(raw[key])
                if type(raw[key].get('currency_digits')) is not int or raw[key]['currency_digits']!=mark['currency_digits']:
                    raise ValueError('native quote monetary units changed')
            for key in ('contract_before','contract_after'):
                c=raw[key]
                if type(c) is not dict or set(c)!={'symbol',*AMOUNTS,*INTEGERS,*CURRENCIES} or c['symbol']!=request['symbol']:
                    raise ValueError('native quote contract changed')
                for name in AMOUNTS:_exact(c[name],positive=name not in {'trade_tick_value','trade_tick_value_profit','trade_tick_value_loss'})
                for name in INTEGERS:native_int(c[name],minimum=0,maximum=2**31-1)
                for name in CURRENCIES:
                    if type(c[name]) is not str or len(c[name])>64 or any(ord(ch)<32 or ord(ch)==127 for ch in c[name]):
                        raise ValueError('native quote currency metadata invalid')
                if _exact(c['volume_max'])<_exact(c['volume_min']):raise ValueError('native quote unit bounds invalid')
            fixed=('symbol','currency_base','currency_profit','currency_margin','trade_contract_size','trade_tick_size','digits','trade_calc_mode')
            if any(raw['contract_before'][k]!=raw['contract_after'][k] for k in fixed):raise ValueError('native quote instrument migrated')
            native_int(raw['requested_at_ms'],minimum=0,maximum=end)
            native_int(raw['received_at_ms'],minimum=raw['requested_at_ms'],maximum=deadline-1)
            if type(read) is not dict:raise ValueError('native quote read identity required')
            if read.get('kind')=='SIGNED_MTLS_READ':
                if set(read)!={'kind','request_nonce','worker_time_ms'} or raw['native_clock_basis']!='UTC_HOST_MS' or raw['native_numeric_format']!='PYTHON_BINARY64_SHORTEST':
                    raise ValueError('native quote signed protocol invalid')
                native_int(read['request_nonce'],minimum=0,maximum=2**128-1)
                native_int(read['worker_time_ms'],minimum=raw['received_at_ms'],maximum=deadline-1)
            elif read.get('kind')=='EA_PULL_READ':
                if (set(read)!={'kind','queue_id'} or raw['native_clock_basis']!='UTC_SECOND_INTERVAL'
                        or raw['native_numeric_format']!='MQL_BINARY64_ROUNDTRIP'
                        or raw['requested_at_ms']%1000 or raw['received_at_ms']%1000!=999
                        or raw['received_at_ms']<start):raise ValueError('native quote EA protocol invalid')
                native_int(read['queue_id'],minimum=1)
            else:raise ValueError('native quote transport invalid')
            tick=raw['tick']
            if tick is not None:
                if type(tick) is not dict or set(tick)!={'bid','ask','last','volume_real','volume','time','time_msc','flags'}:
                    raise ValueError('native full tick shape invalid')
                for key in ('bid','ask','last','volume_real'):
                    if tick[key] is not None:_exact(tick[key])
                for key in ('time','time_msc','flags','volume'):_integer_text(tick[key])
            result=object.__new__(cls);object.__setattr__(result,'_body_json',canonical_json(body).encode());return result
        except (KeyError,TypeError,ValueError,ArithmeticError,VenueUnavailable):
            raise ValueError('original MT5 quote, scope, clock, units or read identity invalid') from None

    def snapshot(self,*,now_ms,max_age_ms):
        now=native_int(now_ms,minimum=0);native_int(max_age_ms,minimum=1)
        body=self.body();raw=body['observation'];tick=raw['tick'];age=None
        bid=None if tick is None or tick['bid'] is None else _exact(tick['bid'])
        ask=None if tick is None or tick['ask'] is None else _exact(tick['ask'])
        at=None if tick is None else _integer_text(tick['time_msc'])
        seconds=None if tick is None else _integer_text(tick['time'])
        if now<body['received_at_ms']:state='HOST_CLOCK_BEHIND_OBSERVATION'
        elif tick is None:state='WAITING_NATIVE_QUOTE'
        elif raw['symbol_selected'] is not True:state='SYMBOL_SUBSCRIPTION_UNVERIFIED'
        elif raw['subscription_delayed'] is None:state='NATIVE_ENTITLEMENT_UNVERIFIED'
        elif raw['subscription_delayed']:state='DELAYED_NATIVE_QUOTE'
        elif bid is None or bid==0:state='WAITING_NATIVE_BID'
        elif ask is None or ask==0:state='WAITING_NATIVE_ASK'
        elif at is None or at==0 or seconds is None:state='NATIVE_TIME_UNAVAILABLE'
        elif seconds!=at//1000:state='NATIVE_TIME_INCONSISTENT'
        elif at>now:state='HOST_CLOCK_BEHIND_NATIVE_QUOTE'
        elif ask<bid:state='CROSSED_NATIVE_QUOTE'
        else:
            age=now-at;state='STALE_NATIVE_QUOTE' if age>max_age_ms else 'OBSERVED_UNQUALIFIED'
        return {'schema':'vati.mt5-quote-view/1','source_ref':body['source_ref'],'state':state,
            'symbol':body['request']['symbol'],'bid':None if bid is None else str(bid),
            'ask':None if ask is None else str(ask),'native_tick_time_ms':at,'evaluated_at_ms':now,
            'base_currency':raw['contract_after']['currency_base'],
            'quote_currency':raw['contract_after']['currency_profit'],
            'account_currency':raw['account_after']['currency'],
            'max_age_ms':max_age_ms,'age_ms':age,'provider_qualified':False,
            'risk_terms_qualified':False,'execution_authority':False}


def read_quote_snapshot(adapter,symbol,*,context,deadline_ms,pull=False):
    try:
        start=native_int(adapter.clock(),minimum=0);native_int(deadline_ms,minimum=start+1)
        request={'symbol':_symbol(symbol)};source=inspect_context(context)
        if context.provider!='MT5' or context.account_alias!=adapter.account_alias or type(adapter.identity) is not Mt5Identity or source['observed_at_ms']>start:
            raise ValueError('registered native quote scope required')
        adapter.identity.validate(source['mark'])
        if pull:
            support=adapter._state()['account'].get('quote_snapshot_constraints')
            if (support!={'schema':'van.mt5.ea-quote-constraints/1','required_op':'QUOTE_SNAPSHOT','framed_fields':18,'explicit_deadline':True}
                    or type(support.get('framed_fields')) is not int or type(support.get('explicit_deadline')) is not bool):
                raise ValueError('native quote EA capability unavailable')
            cid=adapter.queue.enqueue(adapter.account_alias,'QUOTE_SNAPSHOT',{**request,'expected_account':adapter.identity.as_dict(),
                'expires_at_ms':deadline_ms},now_ms=start)
            stop=time.monotonic()+adapter.timeout_s;response=None
            while time.monotonic()<stop and adapter.clock()<deadline_ms:
                response=adapter.queue.result(cid)
                if response is not None:break
                time.sleep(adapter.poll_s)
            if response is None or 'error' in response:raise ValueError('native quote original reply unavailable')
            read={'kind':'EA_PULL_READ','queue_id':cid}
        else:
            response=adapter._call('quote_snapshot',{'alias':adapter.account_alias,**request,'deadline_ms':deadline_ms},now_ms=start)
            read={'kind':'SIGNED_MTLS_READ','request_nonce':response['nonce'],'worker_time_ms':response['worker_time_ms']}
        end=native_int(adapter.clock(),minimum=start,maximum=deadline_ms-1)
        body={'schema':'vati.mt5-quote-snapshot/1','native_account_context':asdict(context),'request':request,
            'observation':response['observation'],'native_read_identity':read,'requested_at_ms':start,
            'received_at_ms':end,'valid_until_ms':deadline_ms,'risk_terms_qualified':False,
            'provider_qualified':False,'execution_authority':False}
        body['source_ref']=canonical_hash(body);return Mt5QuoteObservation.from_body(body)
    except Exception:
        raise VenueUnavailable('MT5 original native quote, scope, clock, units or deadline unavailable') from None
