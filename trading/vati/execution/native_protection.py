"""Observe an existing adapter's native protective effect; never send an order.

Paper is the implemented source producer here. Other providers need their own
admitted original-effect reader; a flat current position is never such proof.
"""
from dataclasses import fields, asdict
from decimal import Decimal

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.execution.base import ExecutionReceipt

SCHEMA='paper-native-protection-effect/1'
REASONS=frozenset({'VENUE_STOP','VENUE_TARGET'})


def original_native_protection(history, receipt_event):
    r=receipt_event.payload
    if r.get('exit_origin')!='NATIVE_PROTECTION':
        return None
    proof=next((e for e in history.rows if e.kind is EventKind.SESSION
        and e.producer=='vati-execution-router' and e.hash==r.get('native_protection_ref')
        and e.hash==canonical_hash(e.body())),None)
    if proof is None:
        return None
    p=proof.payload;iid=receipt_event.correlation_id;command=history.commands.get(iid)
    opening=next((e for e in history.events(EventKind.EXECUTION_RECEIPT)
        if e.hash==p.get('original_entry_ref') and not e.payload.get('exit_action')),None)
    if (command is None or opening is None or p.get('schema')!=SCHEMA
            or p.get('source_environment')!='PAPER' or history.venue!='paper'
            or p.get('account_alias')!=history.account_alias or p.get('venue')!=history.venue
            or p.get('trade_intent_id')!=iid or p.get('original_command_ref')!=history.command_refs[iid]
            or p.get('receipt_hash')!=r.get('receipt_hash') or r.get('status')!='FILLED'
            or p.get('position_id')!=r.get('broker_position_id')
            or opening.payload.get('broker_position_id')!=p.get('position_id')
            or r.get('reject_reason') not in REASONS or p.get('reason')!=r.get('reject_reason')
            or proof.correlation_id!=iid or proof.received_time_ms>receipt_event.received_time_ms):
        return None
    close=p.get('native_close',{})
    if (not close.get('close_id') or close.get('position_id')!=p['position_id']
            or close.get('intent')!=iid or close.get('symbol')!=command[0]['symbol']
            or close.get('reason')!=p['reason'] or close.get('pnl_scope')!='EXECUTION_DELTA'
            or close.get('closed_ms')!=r.get('received_time_unix_ms')
            or Decimal(str(close.get('qty')))!=Decimal(str(r.get('filled_qty')))
            or Decimal(str(close.get('exit')))!=Decimal(str(r.get('average_fill')))
            or p.get('native_close_hash')!=canonical_hash(close)):
        return None
    return proof


def observe_paper_native_protection(router, adapter, receipt, *, now_ms):
    """Persist an actual returned Paper close and its original source evidence."""
    from vati.execution.paper import PaperAdapter
    from vati.execution.recovery_scope import NativePositionHistory
    if type(adapter) is not PaperAdapter or adapter.inject_disconnect:
        raise ValueError('original native protection reader is not qualified for this adapter')
    if (receipt.receipt_hash!=receipt.sealed().receipt_hash or receipt.venue!=adapter.venue
            or receipt.status!='FILLED' or receipt.reject_reason not in REASONS
            or not receipt.filled_qty.is_finite() or receipt.filled_qty<=0):
        raise ValueError('original native protection receipt is not a confirmed bound fill')
    history=NativePositionHistory(router.ledger,account_alias=adapter.account_alias,venue=adapter.venue)
    iid=receipt.trade_intent_id;command=history.commands.get(iid)
    entries=[e for e in history.events(EventKind.EXECUTION_RECEIPT)
        if e.correlation_id==iid and not e.payload.get('exit_action')
        and e.payload.get('broker_position_id')==receipt.broker_position_id
        and e.payload.get('status') in {'FILLED','PARTIAL'}]
    entries={e.payload['receipt_hash']:e for e in entries}
    closes=[r for r in adapter.closed if r.get('intent')==iid
        and r.get('position_id')==receipt.broker_position_id and r.get('qty')==receipt.filled_qty
        and r.get('exit')==receipt.average_fill and r.get('closed_ms')==receipt.received_time_unix_ms
        and r.get('reason')==receipt.reject_reason]
    if command is None or len(entries)!=1 or len(closes)!=1:
        raise ValueError('original native protection lacks unambiguous original command/fill/effect')
    entry=next(iter(entries.values()));close=closes[0]
    with router.ledger.atomic():
        previous=[e for e in router.ledger.iter(EventKind.SESSION,correlation_id=iid)
            if e.producer==router.producer and e.payload.get('schema')==SCHEMA
            and e.payload.get('native_close',{}).get('close_id')==close['close_id']]
        if previous:
            if len(previous)!=1 or previous[0].payload['receipt_hash']!=receipt.receipt_hash:
                raise ValueError('native protective effect identity conflicts with original observation')
            return previous[0]
        body=dict(schema=SCHEMA,source_environment='PAPER',provider_qualified=False,
            account_alias=adapter.account_alias,venue=adapter.venue,trade_intent_id=iid,
            position_id=receipt.broker_position_id,original_command_ref=history.command_refs[iid],
            original_entry_ref=entry.hash,receipt_hash=receipt.receipt_hash,reason=receipt.reject_reason,
            native_close=close,native_close_hash=canonical_hash(close),execution_authority=False)
        proof=make_event(EventKind.SESSION,router.producer,body,event_time_ms=now_ms,
            received_time_ms=now_ms,correlation_id=iid);router.ledger.append(proof)
        router._log(EventKind.EXECUTION_RECEIPT,{**asdict(receipt),'exit_action':'CLOSE',
            'exit_origin':'NATIVE_PROTECTION','native_protection_ref':proof.hash},now_ms=now_ms,corr=iid)
    return proof
