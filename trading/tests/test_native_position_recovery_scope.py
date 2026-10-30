"""A matching trade label alone cannot establish native position ownership."""
from dataclasses import asdict,replace
from decimal import Decimal as D

import pytest

from test_account_lifecycle import _command,_lifecycle
from vati.core import EventKind,Ledger,make_event
from vati.execution.paper import PaperAdapter
from vati.core.canonical import canonical_hash


def publish(ledger,command,*,producer='vati-execution-router',correlation=None,payload=None):
    body=asdict(command) if payload is None else payload
    ledger.append(make_event(EventKind.ORDER_COMMAND,producer,body,event_time_ms=1000,
        received_time_ms=1000,correlation_id=correlation or command.trade_intent_id))


@pytest.mark.parametrize('fault',['foreign-owner','ambiguous-owner','wrong-symbol','wrong-venue',
    'foreign-producer','bad-command-seal','wrong-correlation','missing-native-stop','excess-quantity','missing-position-identity'])
def test_native_recovery_cannot_adopt_a_label_with_missing_or_conflicting_provenance(fault):
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct',slippage=D('0'))
    original=_command('original-native-intent')
    result=adapter.submit(original,now_ms=1000)
    changed=original;producer='vati-execution-router';correlation=None;payload=None
    if fault=='foreign-owner':changed=replace(original,account_alias='another_owner',command_hash='').sealed()
    elif fault=='ambiguous-owner':
        publish(ledger,original)
        changed=replace(original,account_alias='another_owner',command_hash='').sealed()
    elif fault=='wrong-symbol':changed=replace(original,symbol='GBPUSD',command_hash='').sealed()
    elif fault=='wrong-venue':changed=replace(original,venue='deriv',command_hash='').sealed()
    elif fault=='foreign-producer':producer='untrusted-import'
    elif fault=='bad-command-seal':payload={**asdict(original),'command_hash':'0'*64}
    elif fault=='wrong-correlation':correlation='some-other-original-operation'
    elif fault=='missing-native-stop':adapter._positions[result.broker_position_id]['stop']=None
    elif fault=='excess-quantity':adapter._positions[result.broker_position_id]['qty']*=2
    elif fault=='missing-position-identity':adapter._positions['']=adapter._positions.pop(result.broker_position_id)
    publish(ledger,changed,producer=producer,correlation=correlation,payload=payload)
    lifecycle=_lifecycle(ledger,adapter)
    restored,unresolved=lifecycle.recover_from_venue()
    assert not restored and unresolved
    assert original.trade_intent_id not in lifecycle.entries


def test_genuine_native_partial_position_and_tighter_stop_are_recoverable_without_sending():
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct',slippage=D('0'))
    command=_command('original-native-intent');publish(ledger,command)
    receipt=adapter.submit(command,now_ms=1000)
    adapter._positions[receipt.broker_position_id]['qty']/=2
    adapter.modify_stop(receipt.broker_position_id,D('1.095'),now_ms=1100)
    lifecycle=_lifecycle(ledger,adapter);before=adapter._seq
    restored,unresolved=lifecycle.recover_from_venue()
    assert restored==(command.trade_intent_id,) and not unresolved and adapter._seq==before
    assert lifecycle.entries[command.trade_intent_id]['quantity']==D('.05')
    assert lifecycle.protection.stop_of(receipt.broker_position_id)==D('1.095')


@pytest.mark.parametrize('fault',['foreign-owner','foreign-producer','invalid-units'])
def test_unrelated_or_invalid_tca_cannot_replace_this_positions_native_cost(fault):
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct',slippage=D('0'))
    cmd=_command('original-native-intent');publish(ledger,cmd);adapter.submit(cmd,now_ms=1000)
    for ratio,owner,producer in [('1.5','acct','vati-cycle'),
        ('NaN' if fault=='invalid-units' else '900','another_owner' if fault=='foreign-owner' else 'acct',
         'untrusted-import' if fault=='foreign-producer' else 'vati-cycle')]:
        ledger.append(make_event(EventKind.TCA_RECORD,producer,{'trade_intent_id':cmd.trade_intent_id,
            'account_alias':owner,'cost_ratio':ratio},event_time_ms=1100,received_time_ms=1100,
            correlation_id=cmd.trade_intent_id))
    lifecycle=_lifecycle(ledger,adapter);restored,unresolved=lifecycle.recover_from_venue()
    assert restored==(cmd.trade_intent_id,) and not unresolved
    assert lifecycle.entries[cmd.trade_intent_id]['cost_ratio']==D('1.5')


def test_recovery_preserves_a_genuine_historical_command_before_lease_epoch_existed():
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct',slippage=D('0'))
    cmd=_command('original-native-intent');adapter.submit(cmd,now_ms=1000)
    body=asdict(cmd);body.pop('lease_epoch')
    body['command_hash']=canonical_hash({k:v for k,v in body.items() if k!='command_hash'})
    publish(ledger,cmd,payload=body);publish(ledger,cmd,payload=body)
    lifecycle=_lifecycle(ledger,adapter)
    assert lifecycle.recover_from_venue()==((cmd.trade_intent_id,),())
    assert lifecycle.entries[cmd.trade_intent_id]['opened_ms']==1000


def test_invalid_native_chain_cannot_be_used_for_position_recovery():
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct',slippage=D('0'))
    cmd=_command('original-native-intent');publish(ledger,cmd);adapter.submit(cmd,now_ms=1000)
    ledger.append(make_event(EventKind.SESSION,'vati-account-service',{'event':'NATIVE_DIAGNOSTIC'},
        event_time_ms=1000,received_time_ms=1000))
    lifecycle=_lifecycle(ledger,adapter)
    ledger._conn.execute("UPDATE events SET payload_json='{}' WHERE kind='SESSION'")
    restored,unresolved=lifecycle.recover_from_venue()
    assert not restored and unresolved and not lifecycle.entries


def test_current_mandate_alias_cannot_relabel_a_different_native_adapter():
    from types import SimpleNamespace
    ledger=Ledger();adapter=PaperAdapter(account_alias='acct',slippage=D('0'))
    cmd=replace(_command('original-native-intent'),account_alias='another_owner',command_hash='').sealed()
    publish(ledger,cmd);adapter.submit(cmd,now_ms=1000)
    lifecycle=_lifecycle(ledger,adapter);lifecycle.mandate=SimpleNamespace(account_alias='another_owner')
    restored,unresolved=lifecycle.recover_from_venue()
    assert not restored and unresolved and not lifecycle.entries
