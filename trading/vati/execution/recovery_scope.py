"""Native account/command provenance for restart recovery; never an order path."""
from dataclasses import fields
from decimal import Decimal,InvalidOperation

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.base import OrderCommand,ExecutionReceipt


class PositionRecoveryError(ValueError):
    pass


RELATED_PRODUCERS = {
    EventKind.EXECUTION_RECEIPT: frozenset({'vati-execution-router','vati-cycle','vati-account-service','vati-account-lifecycle'}),
    EventKind.TCA_RECORD: frozenset({'vati-cycle','vati-account-lifecycle'}),
    EventKind.OWNER_TICKET: frozenset({'vati-execution-router','vati-account-service','vati-account-lifecycle','van-gateway'}),
}


def _positive(value):
    result=Decimal(str(value))
    if not result.is_finite() or result<=0:
        raise ValueError('native position value must be finite and positive')
    return result


class NativePositionHistory:
    def __init__(self,ledger,*,account_alias,venue):
        if not isinstance(account_alias,str) or not account_alias or not isinstance(venue,str) or not venue:
            raise PositionRecoveryError('native account/venue binding is unavailable')
        if not ledger.verify_chain()[0]:
            raise PositionRecoveryError('native recovery ledger chain is invalid')
        self.rows=tuple(ledger.iter())
        self.account_alias=account_alias;self.venue=venue
        self.commands={};self.conflicts=set()
        candidates={};identities={}
        command_fields={f.name for f in fields(OrderCommand)}-{'command_hash'}
        for event in self.rows:
            if event.kind is not EventKind.ORDER_COMMAND or event.producer!='vati-execution-router':
                continue
            p=event.payload;iid=p.get('trade_intent_id')
            if not isinstance(iid,str) or not iid:
                continue
            try:
                digest=canonical_hash({k:v for k,v in p.items() if k in command_fields})
                if (event.hash!=canonical_hash(event.body()) or event.correlation_id!=iid
                    or p.get('command_hash')!=digest
                    or not isinstance(p.get('account_alias'),str) or not p['account_alias']
                    or not isinstance(p.get('venue'),str) or not p['venue']
                    or not isinstance(p.get('symbol'),str) or not p['symbol']
                    or p.get('direction') not in {'LONG','SHORT'}
                    or p.get('stop_mode') not in {'VENUE','SOFTWARE'}
                    or p.get('loss_model') not in {'STOP_DISTANCE','FULL_STAKE','ILLIQUID_EQUITY'}):
                    raise ValueError('invalid original native command')
                _positive(p['quantity']);_positive(p['entry_price'])
                identities.setdefault(iid,set()).add(digest)
                candidates.setdefault(iid,(dict(p),event.event_time_ms))
            except (KeyError,TypeError,ValueError,InvalidOperation):
                self.conflicts.add(iid)
        for iid,(p,when) in candidates.items():
            if len(identities[iid])!=1:
                self.conflicts.add(iid)
            if iid not in self.conflicts and p['account_alias']==account_alias and p['venue']==venue:
                self.commands[iid]=(p,when)

    def events(self,kind):
        """Native related facts must join the unique original account command."""
        producers=RELATED_PRODUCERS.get(kind,frozenset())
        receipt_fields={f.name for f in fields(ExecutionReceipt)}-{'receipt_hash'}
        for event in self.rows:
            if event.kind is not kind or event.producer not in producers:
                continue
            joined=self.commands.get(event.correlation_id)
            if joined is None or event.hash!=canonical_hash(event.body()):
                continue
            p=event.payload;command=joined[0]
            if (p.get('trade_intent_id',event.correlation_id)!=event.correlation_id
                or p.get('account_alias',self.account_alias)!=self.account_alias
                or p.get('venue',self.venue)!=self.venue
                or (p.get('decision_hash') and p['decision_hash']!=command.get('decision_hash'))):
                continue
            if kind is EventKind.EXECUTION_RECEIPT and p.get('receipt_hash')!=canonical_hash({k:v for k,v in p.items() if k in receipt_fields}):
                continue
            yield event

    def position_command(self,position):
        joined=self.commands.get(position.trade_intent_id)
        if joined is None:
            return None
        p=joined[0]
        try:
            if (position.symbol!=p['symbol'] or position.direction!=p['direction']
                or position.loss_model!=p['loss_model'] or _positive(position.quantity)>_positive(p['quantity'])):
                return None
            _positive(position.entry_price)
        except (KeyError,ValueError,TypeError,InvalidOperation):
            return None
        return joined
