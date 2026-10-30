"""Adapt the account runtime to the shared recovery actor; never send orders."""
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace

from vati.accounts import BrokerKind
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.recovery_scope import NativePositionHistory
from vati.risk.contracts import KillSwitchTrigger


def _positive_price(value):
    try:
        price=Decimal(str(value))
        return price.is_finite() and price>0
    except (ValueError,TypeError,ArithmeticError):return False


def unresolved_account_entries(service):
    """Absence of a position is not proof that an original order had no effect."""
    unresolved={iid for iid,row in service._entries.items() if row.get('pending')}
    unresolved.update(getattr(service,'_recovery_unresolved',()))
    try:
        history=NativePositionHistory(service._ledger,account_alias=service.cfg.account_alias,
            venue=service.adapter.venue)
        unresolved.update(e.correlation_id for e in history.rows
            if e.kind is EventKind.ORDER_COMMAND and e.payload.get('account_alias')==service.cfg.account_alias
            and e.correlation_id in history.conflicts)
        receipts={iid:[] for iid in history.commands}
        for event in history.events(EventKind.EXECUTION_RECEIPT):
            if not event.payload.get('exit_action'):
                receipts[event.correlation_id].append(event.payload)
        for iid,(command,_when) in history.commands.items():
            facts=receipts[iid]
            if not facts:
                unresolved.add(iid);continue
            quantities=[Decimal(str(p.get('filled_qty','0'))) for p in facts]
            if any(not q.is_finite() or q<0 for q in quantities):
                unresolved.add(iid);continue
            last=facts[-1];status=last.get('status');quantity=Decimal(str(command['quantity']))
            final_fill=(status in {'FILLED','OWNER_EXECUTED','BROKER_CONFIRMED'}
                and quantities[-1]==quantity and all(q<=quantity for q in quantities)
                and _positive_price(last.get('average_fill')))
            no_effect={'REJECTED','CANCELLED','EXPIRED'}
            final_refusal=(status in no_effect and all(q==0 for q in quantities)
                and (all(p.get('status') in no_effect for p in facts)
                    or last.get('native_entry_observation')=={'schema':'vati.native-entry-observation/1',
                        'command_hash':command['command_hash'],'source':'ORIGINAL_NATIVE_RESULT'}))
            if not final_fill and not final_refusal:unresolved.add(iid)
    except (OSError,ValueError,TypeError,KeyError,ArithmeticError):
        unresolved.add('native-order-history-unavailable')
    return unresolved


class AccountRecoveryView:
    """References the real account lifecycle, risk state and native ledger."""
    def __init__(self,service):self.service=service

    @property
    def cfg(self):
        service=self.service
        identity=canonical_hash({'account_alias':service.cfg.account_alias,
            'holder_instance_id':service.lease.instance_id,'lease_epoch':service.lease.epoch,
            'specs':{k:asdict(v) for k,v in sorted(service.specs.items())},
            'contracts':{k:asdict(v) for k,v in sorted(service.contracts.items())},
            'software_stops':service.account.broker==BrokerKind.ZSE_OWNER_TICKET,
            'activation_id':service.cfg.activation_id})
        return SimpleNamespace(account_alias=service.cfg.account_alias,session_id='account:'+identity,
            contract=SimpleNamespace(account_currency=service.account.currency))

    @property
    def ledger(self):return self.service._ledger
    @property
    def adapter(self):return self.service.adapter
    @property
    def mandate(self):return self.service.mandate
    @property
    def kill(self):return self.service.kill
    @property
    def _entries(self):return self.service._entries
    @property
    def recovery_unresolved(self):return tuple(getattr(self.service,'_recovery_unresolved',()))
    @property
    def unresolved_entry_attempts(self):return unresolved_account_entries(self.service)
    @property
    def streaks(self):return self.service.lifecycle.streaks
    @streaks.setter
    def streaks(self,value):self.service.lifecycle.streaks=value
    @property
    def peak_equity(self):return self.service.peak_equity
    @peak_equity.setter
    def peak_equity(self,value):self.service.peak_equity=value

    def ledger_positions(self):return self.service._ledger_positions()

    def hold_entries(self):
        self.service.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE,self.service.clock())
