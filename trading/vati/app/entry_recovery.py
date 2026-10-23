"""Observe original in-flight entries without a second order submission."""
from contextlib import nullcontext
from dataclasses import fields
from decimal import Decimal

from vati.execution.base import OrderCommand,StopMode
from vati.execution.recovery_scope import NativePositionHistory
from vati.risk.contracts import Direction,LossModel


def original_command(cycle,iid):
    history=NativePositionHistory(cycle.ledger,account_alias=cycle.cfg.account_alias,venue=cycle.cfg.venue)
    payload=history.commands[iid][0]
    values={f.name:payload[f.name] for f in fields(OrderCommand) if f.name in payload}
    for name in ('quantity','entry_price','protective_stop','max_slippage'):
        if values.get(name) is not None:values[name]=Decimal(str(values[name]))
    values['targets']=tuple(Decimal(str(v)) for v in values.get('targets',()))
    values['direction']=Direction(values['direction']);values['stop_mode']=StopMode(values['stop_mode'])
    values['loss_model']=LossModel(values['loss_model'])
    command=OrderCommand(**values)
    if command.sealed().command_hash!=command.command_hash:raise ValueError('original command schema requires native adjudication')
    return command


def reconcile_inflight_entries(cycle,*,now_ms):
    """Current epoch may publish readback; neither path can resend an entry."""
    reader=getattr(cycle.adapter,'recover_entry',None)
    if not cycle.unresolved_entry_attempts or not callable(reader):return
    guard=(cycle.runtime_lease.submission_guard(cycle.runtime_lease.epoch,now_ms=cycle._lease_clock())
           if cycle.runtime_lease is not None else nullcontext(True))
    with guard as current:
        if not current:return
        for iid in tuple(cycle.unresolved_entry_attempts):
            row=cycle._entries.get(iid)
            if row is None:continue
            try:
                command=row.get('_native_command')
                if command is None:command=row['_native_command']=original_command(cycle,iid)
                receipt=reader(command,now_ms=now_ms)
                if receipt is None or receipt.status=='UNKNOWN':continue
                if (receipt.trade_intent_id!=iid or receipt.decision_hash!=command.decision_hash
                    or receipt.venue!=command.venue or receipt.sealed().receipt_hash!=receipt.receipt_hash):continue
                positions=cycle.adapter.positions()
                if receipt.status in {'REJECTED','CANCELLED','EXPIRED'} and receipt.filled_qty==0:
                    from vati.core import EventKind
                    history=NativePositionHistory(cycle.ledger,account_alias=cycle.cfg.account_alias,venue=cycle.cfg.venue)
                    if any(Decimal(str(e.payload.get('filled_qty','0')))!=0
                           for e in history.events(EventKind.EXECUTION_RECEIPT)
                           if e.correlation_id==iid and not e.payload.get('exit_action')):continue
                    if any(p.trade_intent_id==iid or not p.trade_intent_id for p in positions):continue
                    cycle._settle_pending(receipt,row,now_ms=now_ms,native_observation=True)
                    cycle.unresolved_entry_attempts.discard(iid)
                    continue
                owned=[p for p in positions if p.trade_intent_id==iid and p.position_id==receipt.broker_position_id]
                if len(owned)!=1:continue
                position=owned[0]
                stop=position.stop_price
                if (position.symbol!=command.symbol or position.direction is not command.direction
                    or position.loss_model is not command.loss_model or stop is None or not stop.is_finite()
                    or command.protective_stop is None
                    or (stop<command.protective_stop if command.direction is Direction.LONG else stop>command.protective_stop)):
                    continue
                # Keep real protection on a partial/contradictory pending outcome;
                # that is not authority to release its remaining gross budget.
                cycle.protection.restore(position.position_id,symbol=position.symbol,direction=position.direction,
                    entry=position.entry_price,initial_stop=command.protective_stop,current_stop=stop,
                    target=command.targets[0] if command.targets else None,opened_ms=row['opened_ms'],
                    software_stop=command.stop_mode is StopMode.SOFTWARE)
                if (receipt.status!='FILLED' or receipt.filled_qty!=command.quantity
                    or position.quantity!=receipt.filled_qty or position.entry_price!=receipt.average_fill
                    or receipt.protective_stop_confirmed is not True or row.get('_approval') is None):continue
                row['stop']=stop
                cycle._settle_pending(receipt,row,now_ms=now_ms,native_observation=True)
                from vati.core import EventKind
                from vati.lifecycle.thesis import TradeThesis
                history=NativePositionHistory(cycle.ledger,account_alias=cycle.cfg.account_alias,venue=cycle.cfg.venue)
                claims={}
                for event in history.events(EventKind.TRADE_THESIS):
                    if event.correlation_id!=iid:continue
                    thesis=TradeThesis.from_payload(event.payload)
                    if (thesis.seal_ok() and thesis.symbol==command.symbol and thesis.strategy_id==command.strategy_id
                        and thesis.direction==command.direction.value and thesis.entry==position.entry_price):
                        claims[thesis.seal]=thesis
                if len(claims)!=1:continue
                cycle.thesis.adopt(next(iter(claims.values())))
                row['recovery_context_complete']=True;row.pop('_approval',None)
                cycle.unresolved_entry_attempts.discard(iid)
            except Exception:
                # Store/receipt/protection faults retain the original claim. A
                # failed read, missing row or empty snapshot is never NoEffect.
                continue


def command_outcome_unconfirmed(cycle,iid):
    """A durable dispatch with no terminal original receipt cannot be retried."""
    from vati.core import EventKind
    history=NativePositionHistory(cycle.ledger,account_alias=cycle.cfg.account_alias,venue=cycle.cfg.venue)
    if iid not in history.commands:return False
    receipts=[e.payload for e in history.events(EventKind.EXECUTION_RECEIPT)
              if e.correlation_id==iid and not e.payload.get('exit_action')]
    return not receipts or receipts[-1].get('status') in {'UNKNOWN','PARTIAL'}
