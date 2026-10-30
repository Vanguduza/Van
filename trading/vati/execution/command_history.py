"""Original account command history for deterministic entry controls.

This reads the existing ledger owner. It is neither a parent grant nor an
all-origin financial reservation, and cannot authorize transport by itself.
"""
from dataclasses import fields
from decimal import Decimal, localcontext

from vati.core import EventKind
from vati.core.canonical import canonical_hash, canonical_json
from vati.execution.base import OrderCommand


class CommandHistoryUnavailable(ValueError):
    pass


def account_command_history(ledger, account_alias, *, now_ms, active=None,
                            producer='vati-execution-router', max_commands=100000, max_bytes=32*1024**2):
    """Retain each original admitted command; never reconstruct it from receipts.

    The router may identify its independently committed current command for a
    final pre-send check. Only that exact original command is excluded from
    *prior* history. No receipt, fee, exit, correction or elapsed local timer
    deletes an original admission. A duplicate original key is an integrity
    conflict, not another reusable allowance.
    """
    try:
        if type(now_ms) is not int or now_ms < 0:
            raise ValueError('command history clock unavailable')
        if type(account_alias) is not str or not account_alias:
            raise ValueError('command history account unavailable')
        if type(producer) is not str or not producer:
            raise ValueError('command history producer unavailable')
        if (type(max_commands) is not int or not 1<=max_commands<=1000000
            or type(max_bytes) is not int or not 1<=max_bytes<=256*1024**2):
            raise ValueError('command history capacity invalid')
        command_fields={f.name for f in fields(OrderCommand)}-{'command_hash'}
        rows=[];keys=set();size=0;selected=None
        # A standalone check gets a consistent read. The router's final check
        # uses its existing serialized writer; no provider read occurs here.
        with ledger.read_snapshot():
            if not ledger.verify_incremental()[0]:
                raise ValueError('command history chain invalid')
            for event in ledger.iter(EventKind.ORDER_COMMAND):
                payload=event.payload
                if type(payload) is not dict or type(payload.get('account_alias')) is not str or not payload['account_alias']:
                    raise ValueError('legacy command account ownership unresolved')
                if payload['account_alias']!=account_alias:
                    continue
                size+=len(canonical_json(event.body()).encode())
                if len(rows)>=max_commands or size>max_bytes:
                    raise ValueError('command history capacity exceeded')
                if (event.producer!=producer or event.hash!=canonical_hash(event.body())
                    or payload.get('command_hash')!=canonical_hash({k:v for k,v in payload.items() if k in command_fields})
                    or event.correlation_id!=payload.get('trade_intent_id')):
                    raise ValueError('original command identity invalid')
                for name in ('trade_intent_id','idempotency_key','venue','symbol','decision_hash'):
                    if type(payload.get(name)) is not str or not payload[name]:
                        raise ValueError('original command scope unavailable')
                if type(payload.get('quantity')) is not str or len(payload['quantity'])>512:
                    raise ValueError('original command quantity unavailable')
                with localcontext():
                    quantity=Decimal(payload['quantity'])
                if (not quantity.is_finite() or quantity<=0 or len(quantity.as_tuple().digits)>512
                    or abs(quantity.as_tuple().exponent)>128):
                    raise ValueError('original command quantity invalid')
                if any(type(t) is not int or not 0<=t<=now_ms for t in (event.event_time_ms,event.received_time_ms)):
                    raise ValueError('original command clock unavailable or in future')
                key=payload['idempotency_key']
                if key in keys:
                    raise ValueError('duplicate original command key requires reconciliation')
                keys.add(key)
                row={'ref':event.hash,'key':key,'at_ms':max(event.event_time_ms,event.received_time_ms),
                    'quantity':quantity,'payload':payload,'producer':event.producer}
                rows.append(row)
                if active is not None and event.hash==active['ref']:
                    if (selected is not None or payload['command_hash']!=active['command_hash']
                        or payload['decision_hash']!=active['decision_hash']
                        or payload['trade_intent_id']!=active['trade_intent_id']
                        or key!=active['key'] or event.producer!=active['producer']):
                        raise ValueError('active original command binding differs')
                    selected=row
        if active is not None and selected is None:
            raise ValueError('active original command unavailable')
        return tuple(row for row in rows if row is not selected),selected
    except CommandHistoryUnavailable:
        raise
    except Exception as error:
        raise CommandHistoryUnavailable('original account command history unavailable: '+type(error).__name__) from None
