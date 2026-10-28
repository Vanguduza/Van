"""Original all-alias order exposure for a proven native monetary scope.

Commands and receipts are original durable data. A missing receipt, ACK,
margin quote or ownership proof never supplies a zero reservation or release.
This read cannot reserve, spend, cancel, settle or authorize an order.
"""
from dataclasses import dataclass, fields
from decimal import Decimal
import json

from vati.core import EventKind
from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import committed_source_snapshot
from vati.execution.base import OrderCommand, ExecutionReceipt
from vati.execution.recovery_scope import RELATED_PRODUCERS, _positive
from vati.risk.native_history import (
    native_risk_history_for_context, _from_original_event,
    _original_nonfinancial_rejection, NativeRiskSourceUnavailable,
)


@dataclass(frozen=True)
class OriginalOrderExposure:
    command_ref: str
    original_input_ref: str
    origin_alias: str
    trade_intent_id: str
    state: str
    quantity: Decimal
    reported_filled_quantity: Decimal | None
    reported_unfilled_quantity: Decimal | None
    active_quantity_bound: Decimal
    last_reported_status: str | None
    command_json: str
    receipt_refs: tuple[str, ...]
    required_margin: None = None
    execution_authority: bool = False

    @property
    def command(self):
        return json.loads(self.command_json)


@dataclass(frozen=True)
class PhysicalOrderExposure:
    physical_account_key: str
    monetary_scope_hash: str
    orders: tuple[OriginalOrderExposure, ...]
    unresolved_refs: tuple[str, ...]
    execution_authority: bool = False

    @property
    def unpriced_order_refs(self):
        return tuple(o.command_ref for o in self.orders if o.state != 'NO_EFFECT')


def _quantity(value):
    if type(value) is not str:
        raise ValueError('order exposure requires original exact quantity text')
    result=Decimal(value)
    if not result.is_finite() or result<0:
        raise ValueError('order exposure quantity is invalid')
    return result


def physical_order_exposure(ledger, context, *, available_at_ms):
    with committed_source_snapshot(ledger):
        source=native_risk_history_for_context(ledger,context,available_at_ms=available_at_ms)
        rows=tuple(e for e in ledger.iter() if max(e.event_time_ms,e.received_time_ms)<=available_at_ms)
        unresolved=set(source.unresolved_refs)-set(source.nonfinancial_rejection_refs)
        approvals={};queries={}
        positions={e.hash:index for index,e in enumerate(rows)}
        for event in rows:
            if event.kind is not EventKind.RISK_DECISION:continue
            try:
                value=_from_original_event(ledger,event,available_at_ms=available_at_ms,queries=queries)
                if value.recorded_decision in {'APPROVED','REDUCED'}:
                    approvals.setdefault(value.decision_hash,[]).append((event,value))
            except NativeRiskSourceUnavailable:
                if not _original_nonfinancial_rejection(event):unresolved.add(event.hash)
        command_fields={f.name for f in fields(OrderCommand)}-{'command_hash'}
        receipt_fields={f.name for f in fields(ExecutionReceipt)}-{'receipt_hash'}
        commands={};selected=[];selected_keys=set()
        for event in rows:
            if event.kind is not EventKind.ORDER_COMMAND:continue
            p=event.payload
            try:
                matches=approvals.get(p['decision_hash'],[])
                if len(matches)!=1:raise ValueError('original approving input is not unique')
                original,value=matches[0];native=value.context
                intent=original.payload['inputs']['intent']
                quantity=_quantity(p['quantity'])
                _positive(p['entry_price'])
                if p.get('protective_stop') is not None:_positive(p['protective_stop'])
                if (type(event.event_time_ms) is not int or type(event.received_time_ms) is not int
                        or min(event.event_time_ms,event.received_time_ms)<0
                        or event.producer!='vati-execution-router' or event.hash!=canonical_hash(event.body())
                        or p['command_hash']!=canonical_hash({k:v for k,v in p.items() if k in command_fields})
                        or p.get('stop_mode') not in {'VENUE','SOFTWARE'}
                        or p.get('loss_model') not in {'STOP_DISTANCE','FULL_STAKE','ILLIQUID_EQUITY'}
                        or quantity<=0 or quantity>Decimal(original.payload['decision']['approved_size'])
                        or p['trade_intent_id']!=event.correlation_id or event.correlation_id!=original.correlation_id
                        or positions[original.hash]>=positions[event.hash]
                        or max(original.event_time_ms,original.received_time_ms)>min(event.event_time_ms,event.received_time_ms)
                        or any(p[k]!=intent[k] for k in ('account_alias','venue','symbol','direction',
                            'strategy_id','strategy_version','idempotency_key'))):
                    raise ValueError('command does not bind its original approval')
                commands.setdefault(event.correlation_id,set()).add(p['command_hash'])
                if native.physical_account_key!=context.physical_account_key:continue
                if native.monetary_scope_hash!=context.monetary_scope_hash:
                    raise ValueError('original command monetary scope changed')
                key=(event.correlation_id,p['command_hash'])
                if key in selected_keys:continue
                selected_keys.add(key)
                selected.append((event,original,value,quantity))
            except (KeyError,TypeError,ValueError,ArithmeticError):unresolved.add(event.hash)
        out=[]
        for event,original,value,quantity in selected:
            p=event.payload;fills=[];refs=[];invalid=False
            if len(commands[event.correlation_id])!=1:
                unresolved.add(event.hash);continue
            for receipt in rows:
                if receipt.kind is not EventKind.EXECUTION_RECEIPT or receipt.correlation_id!=event.correlation_id:continue
                r=receipt.payload
                # Exit receipts have their own original-operation protocol.
                if isinstance(r,dict) and r.get('exit_action'):continue
                try:
                    filled=_quantity(r['filled_qty'])
                    if (type(receipt.event_time_ms) is not int or type(receipt.received_time_ms) is not int
                            or min(receipt.event_time_ms,receipt.received_time_ms)<0
                            or type(r.get('received_time_unix_ms')) is not int
                            or not 0<=r['received_time_unix_ms']<=receipt.received_time_ms
                            or receipt.producer not in RELATED_PRODUCERS[EventKind.EXECUTION_RECEIPT]
                            or receipt.hash!=canonical_hash(receipt.body())
                            or r['receipt_hash']!=canonical_hash({k:v for k,v in r.items() if k in receipt_fields})
                            or r['trade_intent_id']!=event.correlation_id
                            or r['decision_hash']!=p['decision_hash'] or r['venue']!=p['venue']
                            or r.get('account_alias',p['account_alias'])!=p['account_alias']
                            or positions[receipt.hash]<=positions[event.hash]
                            or max(event.event_time_ms,event.received_time_ms)>min(receipt.event_time_ms,receipt.received_time_ms)
                            or filled>quantity or fills and filled<fills[-1][1]):
                        raise ValueError('receipt does not bind original entry')
                    refs.append(receipt.hash);fills.append((r,filled))
                except (KeyError,TypeError,ValueError,ArithmeticError):
                    invalid=True;unresolved.add(receipt.hash)
            filled=max((q for _,q in fills),default=None)
            state='UNCERTAIN' if invalid else 'UNCONFIRMED'
            if fills and not invalid:
                last=fills[-1][0];status=last['status']
                no_effect={'REJECTED','CANCELLED','EXPIRED'}
                if status in no_effect and filled==0:
                    native_no_effect=last.get('native_entry_observation')=={
                        'schema':'vati.native-entry-observation/1','command_hash':p['command_hash'],
                        'source':'ORIGINAL_NATIVE_RESULT'}
                    state='NO_EFFECT' if all(r['status'] in no_effect for r,_ in fills) or native_no_effect else 'UNCERTAIN'
                elif status in {'FILLED','OWNER_EXECUTED','BROKER_CONFIRMED'} and filled==quantity:
                    try:
                        price=_quantity(last['average_fill'])
                        state='OPEN' if price>0 else 'UNCERTAIN'
                    except (KeyError,TypeError,ValueError,ArithmeticError):state='UNCERTAIN'
                elif status=='PARTIAL' and 0<filled<quantity:state='PARTIAL'
                elif status in {'ACCEPTED','PENDING'} and filled==0:state='PENDING'
                else:state='UNCERTAIN'
            out.append(OriginalOrderExposure(event.hash,original.hash,value.context.account_alias,
                event.correlation_id,state,quantity,filled,quantity-filled if filled is not None else None,
                Decimal(0) if state=='NO_EFFECT' else quantity,
                fills[-1][0]['status'] if fills else None,
                canonical_json(p),tuple(refs)))
        return PhysicalOrderExposure(context.physical_account_key,context.monetary_scope_hash,
            tuple(out),tuple(sorted(unresolved)))
