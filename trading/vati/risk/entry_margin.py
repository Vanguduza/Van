"""Bind original native read-only estimates to a sealed intended order.

The existing NativeMarginBook owns both records. A binding is neither an
allocation nor proof of native price support, settlement or order authority.
"""
from dataclasses import asdict
from decimal import Decimal
import json
import re

from vati.core import EventKind,make_event
from vati.core.canonical import canonical_hash,canonical_json
from vati.core.ledger import committed_source_snapshot,require_committed_source_read
from vati.core.units import Money
from vati.execution.base import OrderCommand,StopMode
from vati.funding.native import native_int
from vati.risk.contracts import Direction,LossModel
from vati.risk.native_history import original_native_risk_input
from vati.risk.native_margin_book import NativeMarginError,NativeMarginUnknown,PRODUCER,ENTRY_EVENT

EVENT=ENTRY_EVENT
SCHEMA='vati.original-entry-margin-binding/1'
DIGEST=re.compile('[a-f0-9]{64}',re.ASCII)


class EntryMarginUnknown(NativeMarginUnknown):
    def __init__(self,command_hash,source_ref):
        self.command_hash=command_hash
        super().__init__(source_ref)


def _ref(value):
    if type(value) is not str or DIGEST.fullmatch(value) is None:
        raise NativeMarginError('ENTRY_MARGIN_REFERENCE_INVALID')
    return value


def _amount(value,*,positive=False):
    if (type(value) is not Decimal or not value.is_finite()
            or len(value.as_tuple().digits)>512 or abs(value.as_tuple().exponent)>128
            or (value<=0 if positive else value<0)):
        raise NativeMarginError('ENTRY_MARGIN_EXACT_COMMAND_AMOUNT_INVALID')
    return value


def _body(command):
    if (type(command) is not OrderCommand or type(command.direction) is not Direction
            or type(command.loss_model) is not LossModel or type(command.stop_mode) is not StopMode):
        raise NativeMarginError('ENTRY_MARGIN_SEALED_COMMAND_REQUIRED')
    _amount(command.quantity,positive=True);_amount(command.entry_price,positive=True)
    if command.protective_stop is not None:_amount(command.protective_stop,positive=True)
    if command.max_slippage is not None:_amount(command.max_slippage)
    if type(command.targets) is not tuple:raise NativeMarginError('ENTRY_MARGIN_COMMAND_TARGETS_INVALID')
    for target in command.targets:_amount(target,positive=True)
    if command.expires_at_ms is not None:native_int(command.expires_at_ms,minimum=1)
    if command.sealed().command_hash!=_ref(command.command_hash):
        raise NativeMarginError('ENTRY_MARGIN_SEALED_COMMAND_REQUIRED')
    return json.loads(canonical_json(asdict(command)))


def _decode(body):
    if type(body) is not dict or set(body)!=set(OrderCommand.__dataclass_fields__):
        raise NativeMarginError('ENTRY_MARGIN_STORED_COMMAND_INVALID')
    values=dict(body)
    for key in ['quantity','entry_price','protective_stop','max_slippage']:
        if values[key] is not None:
            if type(values[key]) is not str:raise NativeMarginError('ENTRY_MARGIN_STORED_AMOUNT_INVALID')
            values[key]=Decimal(values[key])
    values['targets']=tuple(Decimal(x) for x in values['targets'])
    values['direction']=Direction(values['direction']);values['stop_mode']=StopMode(values['stop_mode'])
    values['loss_model']=LossModel(values['loss_model'])
    result=OrderCommand(**values)
    if canonical_json(_body(result))!=canonical_json(body):raise NativeMarginError('ENTRY_MARGIN_STORED_COMMAND_INVALID')
    return result


def _original(book,original_input_ref,command,*,at):
    body=_body(command)
    source=original_native_risk_input(book.ledger,original_input_ref,available_at_ms=at)
    rows=[e for e in book.ledger.iter(EventKind.RISK_DECISION,correlation_id=source.trade_intent_id)
          if e.hash==original_input_ref]
    if len(rows)!=1:raise NativeMarginError('ENTRY_MARGIN_ORIGINAL_INPUT_UNAVAILABLE')
    event=rows[0];intent=event.payload['inputs']['intent'];decision=event.payload['decision']
    if (source.recorded_decision not in ('APPROVED','REDUCED')
            or body['trade_intent_id']!=source.trade_intent_id
            or body['decision_hash']!=source.decision_hash
            or any(body[k]!=intent[k] for k in ['account_alias','venue','symbol','direction',
                'strategy_id','strategy_version','idempotency_key'])
            or command.quantity>_amount(Decimal(decision['approved_size']),positive=True)
            or body['loss_model']!=event.payload['inputs']['snapshot']['symbol_contract']['loss_model']):
        raise NativeMarginError('ENTRY_MARGIN_COMMAND_ORIGINAL_APPROVAL_MISMATCH')
    return body,source


def _selection(command,quote):
    if quote['schema']=='vati.mt5-expected-margin/1':
        request=quote['request']
        if (request['symbol']!=command.symbol
                or request['type']!=('BUY' if command.direction is Direction.LONG else 'SELL')
                or Decimal(request['volume'])!=command.quantity
                or Decimal(request['price'])!=command.entry_price):
            raise NativeMarginError('ENTRY_MARGIN_NATIVE_REQUEST_MISMATCH')
        amount=quote['estimate_money'];price_binding='ORIGINAL_COMMAND_REFERENCE_PRICE'
    elif quote['schema']=='vati.ctrader-expected-margin/1':
        if quote['symbol']!=command.symbol or Decimal(quote['original_quantity'])!=command.quantity:
            raise NativeMarginError('ENTRY_MARGIN_NATIVE_REQUEST_MISMATCH')
        amount=quote['buy_margin' if command.direction is Direction.LONG else 'sell_margin']
        price_binding='PROVIDER_CURRENT_PRICE_ONLY'
    else:raise NativeMarginError('ENTRY_MARGIN_NATIVE_PROVIDER_UNAVAILABLE')
    Money.from_body(amount)
    return amount,price_binding


def _key(command_hash,source_ref):
    return canonical_hash({'command_hash':_ref(command_hash),'source_ref':_ref(source_ref)})


def _rows(book):
    quotes,quote_bytes,quote_last=book._rows();by_ref={e.hash:e for e in quotes.values()}
    found={};size=quote_bytes;last=-1;seen=set()
    for event in book.ledger.iter():
        p=event.payload
        if event.kind is not EventKind.SESSION or not isinstance(p,dict) or p.get('event')!=EVENT:
            seen.add(event.hash);continue
        size+=len(canonical_json(event.body()).encode())
        if len(found)>=book.max_records or size>book.max_bytes:raise NativeMarginError('ENTRY_MARGIN_BINDING_CAPACITY')
        if (set(p)!={'event','schema','original_input_ref','native_margin_record_ref','source_ref',
                    'command','estimate_money','price_binding'} or p['schema']!=SCHEMA
                or event.producer!=PRODUCER or event.schema_version!=1 or event.decision_time_ms is not None
                or event.hash!=canonical_hash(event.body()) or p['native_margin_record_ref'] not in seen):
            raise NativeMarginError('ENTRY_MARGIN_RECORD_INVALID')
        raw=by_ref.get(p['native_margin_record_ref'])
        if raw is None:raise NativeMarginError('ENTRY_MARGIN_NATIVE_RECORD_UNAVAILABLE')
        quote=raw.payload['observation'];cmd=_decode(p['command']);key=_key(cmd.command_hash,p['source_ref'])
        amount,price_binding=_selection(cmd,quote)
        if (raw.payload['original_input_ref']!=p['original_input_ref'] or quote['source_ref']!=p['source_ref']
                or canonical_json(amount)!=canonical_json(p['estimate_money']) or price_binding!=p['price_binding']
                or key!=event.correlation_id or key in found):raise NativeMarginError('ENTRY_MARGIN_RECORD_BINDING_INVALID')
        native_int(event.received_time_ms,minimum=max(last,raw.received_time_ms),maximum=quote['valid_until_ms']-1)
        if (type(event.event_time_ms) is not int or event.event_time_ms!=event.received_time_ms
                or cmd.expires_at_ms is not None and event.received_time_ms>=cmd.expires_at_ms):
            raise NativeMarginError('ENTRY_MARGIN_ORIGINAL_CREATION_CLOCK_INVALID')
        found[key]=(event,raw);last=event.received_time_ms;seen.add(event.hash)
    return found,size,max(last,quote_last)


def _receipt(event):
    p=event.payload
    return {'record_ref':event.hash,'command_hash':p['command']['command_hash'],
        'source_ref':p['source_ref'],'original_input_ref':p['original_input_ref'],
        'native_margin_record_ref':p['native_margin_record_ref'],'available_at_ms':event.received_time_ms,
        'state':'ORIGINAL_ENTRY_MARGIN_BOUND','reservation_qualified':False,'execution_authority':False}


def lookup_entry(book,command_hash,source_ref):
    key=_key(command_hash,source_ref)
    with committed_source_snapshot(book.ledger):
        pair=_rows(book)[0].get(key)
        if pair is None:return None
        event,raw=pair;book._original(raw)
        _original(book,event.payload['original_input_ref'],_decode(event.payload['command']),at=event.received_time_ms)
        return {'receipt':_receipt(event),'command':event.payload['command'],
            'observation':raw.payload['observation'],'estimate_money':event.payload['estimate_money'],
            'price_binding':event.payload['price_binding']}


def bind_entry(book,original_input_ref,command,source_ref):
    require_committed_source_read(book.ledger)
    body,_=_original(book,original_input_ref,command,at=book._now());key=_key(command.command_hash,source_ref)
    known=lookup_entry(book,command.command_hash,source_ref)
    if known is not None:
        if known['command']!=body or known['receipt']['original_input_ref']!=original_input_ref:
            raise NativeMarginError('ENTRY_MARGIN_ORIGINAL_BINDING_CONFLICT')
        return known['receipt']
    native=book.lookup(source_ref)
    if native is None or native['receipt']['original_input_ref']!=original_input_ref:
        raise NativeMarginError('ENTRY_MARGIN_ORIGINAL_QUOTE_UNAVAILABLE')
    quote=native['observation'];amount,price_binding=_selection(command,quote)
    before=book.ledger.head();started=False
    try:
        with book.ledger.atomic():
            rows,size,last=_rows(book);pair=rows.get(key)
            if pair is not None:
                event,_=pair
                if event.payload['command']!=body or event.payload['original_input_ref']!=original_input_ref:
                    raise NativeMarginError('ENTRY_MARGIN_ORIGINAL_BINDING_CONFLICT')
            else:
                if book.ledger.head()!=before:raise NativeMarginError('ENTRY_MARGIN_SOURCE_CHANGED_RETRY_ORIGINAL')
                now=book._now()
                if (not max(last,native['receipt']['available_at_ms'])<=now<quote['valid_until_ms']
                        or command.expires_at_ms is not None and now>=command.expires_at_ms):
                    raise NativeMarginError('ENTRY_MARGIN_BINDING_EXPIRED_OR_CLOCK_REGRESSED')
                if len(rows)>=book.max_records or book.ledger.count()>=book.max_ledger_events:
                    raise NativeMarginError('ENTRY_MARGIN_BINDING_CAPACITY')
                event=make_event(EventKind.SESSION,PRODUCER,{'event':EVENT,'schema':SCHEMA,
                    'original_input_ref':original_input_ref,'native_margin_record_ref':native['receipt']['record_ref'],
                    'source_ref':source_ref,'command':body,'estimate_money':amount,'price_binding':price_binding},
                    event_time_ms=now,received_time_ms=now,correlation_id=key)
                if size+len(canonical_json(event.body()).encode())>book.max_bytes:
                    raise NativeMarginError('ENTRY_MARGIN_BINDING_BYTE_CAPACITY')
                started=True;book.ledger.append(event)
        started=True
        confirmed=lookup_entry(book,command.command_hash,source_ref)
        if confirmed is None or confirmed['receipt']['record_ref']!=event.hash:
            raise EntryMarginUnknown(command.command_hash,source_ref)
        return confirmed['receipt']
    except EntryMarginUnknown:raise
    except Exception:
        if started:raise EntryMarginUnknown(command.command_hash,source_ref) from None
        raise


def capture_entry(book,adapter,original_input_ref,command,*,deadline_ms):
    _,original=_original(book,original_input_ref,command,at=book._now())
    native_int(deadline_ms,minimum=book._now()+1)
    if command.expires_at_ms is not None:
        if command.expires_at_ms<=book._now():raise NativeMarginError('ENTRY_MARGIN_COMMAND_EXPIRED')
        deadline_ms=min(deadline_ms,command.expires_at_ms)
    kwargs={'price':command.entry_price,'direction':command.direction} if original.context.provider=='MT5' else {}
    receipt=book.capture(adapter,original_input_ref,command.symbol,command.quantity,deadline_ms=deadline_ms,**kwargs)
    return bind_entry(book,original_input_ref,command,receipt['source_ref'])
