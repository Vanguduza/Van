"""Original recorded CTrader entry/exit charges for price-derived reviews.

This is not complete fee, cash, FX or settlement qualification. Original
receipts remain immutable. Conflicting/unbound or unmeasured closing charges
cannot become a measured zero; independently reported net cash keeps its own
existing precedence in closed_trade_pnl.
"""
from dataclasses import fields
from decimal import Decimal
from fractions import Fraction

from vati.core import EventKind
from vati.core.canonical import canonical_hash,canonical_json
from vati.core.ledger import committed_source_snapshot
from vati.execution.base import ExecutionReceipt,OrderCommand
from vati.execution.exit_journal import ExitJournal,VERSION
from vati.execution.recovery_scope import RELATED_PRODUCERS
from vati.risk.arithmetic import fraction,decimal


def _amount(value,*,positive=False):
    if type(value) is not str or len(value)>512:
        raise ValueError('original recorded close amount text unavailable')
    amount=Decimal(value)
    if (not amount.is_finite() or len(amount.as_tuple().digits)>512 or abs(amount.as_tuple().exponent)>128
            or (amount<=0 if positive else amount<0)):
        raise ValueError('original recorded close amount invalid')
    return amount


def recorded_close_cost_entry(ledger,entry,*,trade_intent_id,venue,account_alias,available_at_ms):
    """Copy PnL inputs; never overwrite entry TCA or original fee knowledge."""
    if venue!='ctrader':
        return entry
    result=dict(entry);refs=[]
    try:
        if type(available_at_ms) is not int or available_at_ms<0:
            raise ValueError('recorded close availability unavailable')
        with committed_source_snapshot(ledger):
            if not ledger.verify_incremental()[0]:
                raise ValueError('recorded close source integrity unavailable')
            rows=[];size=0
            for kind in (EventKind.ORDER_COMMAND,EventKind.EXECUTION_RECEIPT):
                for event in ledger.iter(kind,correlation_id=trade_intent_id):
                    if max(event.event_time_ms,event.received_time_ms)>available_at_ms:
                        continue
                    size+=len(canonical_json(event.body()).encode())
                    if len(rows)>=10000 or size>32*1024**2:
                        raise ValueError('recorded close source capacity')
                    rows.append(event)
            closes=[e for e in rows if e.kind is EventKind.EXECUTION_RECEIPT
                    and e.payload.get('exit_action')=='CLOSE'
                    and e.payload.get('status') in {'FILLED','PARTIAL','OWNER_EXECUTED','BROKER_CONFIRMED'}]
            if not closes:
                raise ValueError('original native close charge observation unavailable')
            position=entry.get('broker_position_id')
            if type(position) is not str or not position:
                raise ValueError('original recorded position unavailable')
            commands=[e for e in rows if e.kind is EventKind.ORDER_COMMAND]
            if len(commands)!=1:
                raise ValueError('original recorded command ambiguous')
            command=commands[0];p=command.payload
            command_fields={f.name for f in fields(OrderCommand)}-{'command_hash'}
            if (command.producer!='vati-execution-router' or command.hash!=canonical_hash(command.body())
                    or p['command_hash']!=canonical_hash({k:v for k,v in p.items() if k in command_fields})
                    or p['account_alias']!=account_alias or p['venue']!=venue or p['symbol']!=entry['symbol']
                    or p['trade_intent_id']!=trade_intent_id):
                raise ValueError('original recorded command scope differs')
            receipt_fields={f.name for f in fields(ExecutionReceipt)}-{'receipt_hash'}
            def receipt(event,*,opening=False):
                body=event.payload
                if (event.producer not in RELATED_PRODUCERS[EventKind.EXECUTION_RECEIPT]
                        or event.hash!=canonical_hash(event.body())
                        or body['receipt_hash']!=canonical_hash({k:v for k,v in body.items() if k in receipt_fields})
                        or body['venue']!=venue or body['broker_position_id']!=position
                        or body['trade_intent_id'] not in ({trade_intent_id} if opening else {'',trade_intent_id})
                        or body['status'] not in {'FILLED','PARTIAL','OWNER_EXECUTED','BROKER_CONFIRMED'}
                        or type(body.get('received_time_unix_ms')) is not int
                        or not 0<=body['received_time_unix_ms']<=event.received_time_ms
                        or min(event.event_time_ms,event.received_time_ms)<max(command.event_time_ms,command.received_time_ms)):
                    raise ValueError('original recorded execution scope unavailable')
                quantity=_amount(body['filled_qty'],positive=True)
                price=_amount(body['average_fill'],positive=True)
                cost=None if body.get('fees') is None else _amount(body['fees'])
                if cost is not None or body.get('recorded_native_charge') is not None:
                    from vati.execution.ctrader.charge_source import validate_charge_source
                    validate_charge_source(body.get('recorded_native_charge'),body,
                        account_alias=account_alias,closing=not opening)
                return body,quantity,price,cost
            openings={}
            for event in rows:
                if event.kind is not EventKind.EXECUTION_RECEIPT or event.payload.get('exit_action'):
                    continue
                if event.payload.get('status') not in {'FILLED','PARTIAL','OWNER_EXECUTED','BROKER_CONFIRMED'}:
                    continue
                body,q,price,cost=receipt(event,opening=True)
                if body['decision_hash']!=p['decision_hash']:
                    raise ValueError('original recorded entry decision differs')
                openings.setdefault(body['receipt_hash'],(event,q,price,cost))
            if len(openings)!=1:
                # Scalar receipts cannot resolve cumulative versus per-deal
                # multi-fill costs. The native deal/economic owner must do so.
                raise ValueError('recorded entry charge vintage ambiguous')
            original,opened,entry_price,entry_fee=next(iter(openings.values()))
            if fraction(entry['entry'])!=fraction(entry_price):
                raise ValueError('original recorded entry price differs')
            requests={};executions={};native_deals=set();total=Fraction(0);costs=[];legs=[]
            original_charge=original.payload.get('recorded_native_charge')
            if original_charge is not None:
                native_deals.add((original_charge['native_account_id'],original_charge['native_deal_id']))
            for event in ledger.iter(EventKind.EXIT_ATTEMPT,correlation_id=ExitJournal.scope(venue,position)):
                if max(event.event_time_ms,event.received_time_ms)<=available_at_ms:
                    requests[event.hash]=event
            for event in closes:
                body,quantity,price,cost=receipt(event)
                ref=body.get('exit_request_ref');request=requests.get(ref)
                if (request is None or request.producer!='vati-execution-router'
                        or request.hash!=canonical_hash(request.body())
                        or request.payload.get('version')!=VERSION or request.payload.get('state')!='REQUESTED'
                        or request.payload.get('venue')!=venue or request.payload.get('position_id')!=position
                        or request.payload.get('trade_intent_id')!=trade_intent_id
                        or max(request.event_time_ms,request.received_time_ms)>min(event.event_time_ms,event.received_time_ms)
                        or max(original.event_time_ms,original.received_time_ms)>min(request.event_time_ms,request.received_time_ms)):
                    raise ValueError('original close request binding unavailable')
                previous=executions.get(ref)
                if previous is not None:
                    if previous!=body['receipt_hash']:
                        raise ValueError('original close execution costs conflict')
                    continue
                native_charge=body.get('recorded_native_charge')
                if native_charge is not None:
                    if original_charge is not None and any(native_charge[k]!=original_charge[k]
                            for k in ('native_account_id','native_symbol_id')):
                        raise ValueError('original native charge scope differs')
                    native_key=(native_charge['native_account_id'],native_charge['native_deal_id'])
                    if native_key in native_deals:
                        raise ValueError('same original native deal cannot fund another close')
                    native_deals.add(native_key)
                if not any(r.producer=='vati-execution-router' and r.hash==canonical_hash(r.body())
                        and r.payload.get('request_ref')==ref and r.payload.get('receipt_event_ref')==event.hash
                        and r.payload.get('state') in {'CONFIRMED','PARTIAL_CONFIRMED','UNKNOWN'}
                        for r in requests.values()):
                    raise ValueError('original close disposition unavailable')
                executions[ref]=body['receipt_hash'];refs.append(event.hash)
                if request.payload.get('action')=='PARTIAL_CLOSE':
                    if fraction(quantity)>fraction(_amount(request.payload['quantity'],positive=True)):
                        raise ValueError('original partial close exceeds requested quantity')
                elif request.payload.get('action')!='FULL_CLOSE' or request.payload.get('quantity') is not None:
                    raise ValueError('original close action unavailable')
                total+=fraction(quantity);costs.append(cost)
                legs.append({'quantity':str(quantity),'price':str(price),'receipt_ref':event.hash})
            if total!=fraction(opened):
                raise ValueError('original closed volume incomplete or excessive')
            fees=None if entry_fee is None or any(c is None for c in costs) else decimal(
                fraction(entry_fee)+sum((fraction(c) for c in costs),Fraction(0)))
            result.update(fees=fees,quantity=opened,entry=entry_price,recorded_exit_fills=legs,
                recorded_close_costs={'state':'RECORDED_CHARGES_AVAILABLE' if fees is not None else 'RECORDED_CHARGES_UNAVAILABLE',
                    'entry_receipt_ref':original.hash,'exit_receipt_refs':refs,'fees_final':False,'cash_reconciled':False})
            return result
    except Exception as error:
        result.update(fees=None,recorded_close_costs={'state':'RECORDED_CHARGES_UNAVAILABLE',
            'reason':type(error).__name__,'exit_receipt_refs':refs,'fees_final':False,'cash_reconciled':False})
        return result
