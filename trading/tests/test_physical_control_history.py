"""Real test P256 journal receipts retain their own original native scope.

Keys and signatures here are isolated source fixtures, never live owner grants.
"""
import base64
from dataclasses import asdict, replace
import uuid

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from conftest import NOW
from test_native_risk_history_inputs import native_facts
from test_native_risk_history_index import other_context
from test_physical_financial_history import approval, close
from vati.app.runtime_control_protocol import RecoveryIntent, RecoveryProof, approval_statement
from vati.app.runtime_control_journal import RuntimeControlJournal
from vati.core import EventKind, make_event
from vati.risk.lockouts import LockoutPolicy, ACCOUNT_SCOPE
from vati.risk.physical_lockouts import PhysicalLossStreakGovernor
from vati.risk.physical_history import physical_financial_history


def original_control(ledger, context, *, action='reset_loss_streak', finish=True, damage=None):
    args = {'scope':ACCOUNT_SCOPE} if action == 'reset_loss_streak' else {}
    intent = RecoveryIntent.from_mapping({'schema':'vati.runtime-recovery/1',
        'device_id':'isolated-source-owner','account_alias':context.account_alias,
        'session_id':context.account_alias+':source-runtime','action':action,
        'state_ref':'a'*64,'issued_at_unix':NOW,'args':args})
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    operation = 'source_'+uuid.uuid4().hex
    expiry = NOW+120
    signature = key.sign(approval_statement(intent, operation, expiry).encode(), ec.ECDSA(hashes.SHA256()))
    proof = RecoveryProof(operation, expiry, 'isolated-source-key', base64.b64encode(signature).decode())
    journal = RuntimeControlJournal(ledger,clock=lambda:NOW)
    state = journal.enqueue(intent,proof,{proof.key_id:public})
    payload = {'account_alias':context.account_alias,'owner_signature_ref':state.authority_ref,
        'operation_id':operation,'native_account_context':asdict(context)}
    if action == 'reset_loss_streak':
        payload.update(event='LOSS_STREAK_RESET',scope=ACCOUNT_SCOPE)
    else:
        import json
        mark=json.loads(context.source_mark_json)
        payload.update(event='DRAWDOWN_RESUMED',old_peak_equity='15000',new_peak_equity=mark['net_equity'])
    if damage is not None:
        damage(payload)
    event = make_event(EventKind.SESSION,'vati-cycle',payload,event_time_ms=NOW*1000,
        received_time_ms=NOW*1000,correlation_id=intent.session_id)
    with ledger.atomic():
        ledger.append(event)
        if finish:
            journal.finish(state,'APPLIED',{'reason_code':'APPLIED','effect_refs':[event.hash],
                'entry_authority_granted':False,'remaining_kill':[],'state_ref':intent.state_ref})
    return event


def test_native_original_applied_reset_can_release_only_its_signed_alias_contribution(tmp_path, eurusd):
    ledger, adapter, account, _, facts = native_facts(tmp_path, eurusd)
    first = approval(ledger,facts,'a-loss');close(ledger,first,alias='native')
    current = other_context(ledger,adapter,account,facts,alias='another_label')
    second = approval(ledger,current,'b-loss');close(ledger,second,alias='another_label')
    control = original_control(ledger, facts.native_account_context)
    history = physical_financial_history(ledger,current.native_account_context,available_at_ms=NOW*1000)
    assert history.unresolved_refs == ()
    assert [(f.event_ref,f.origin_alias) for f in history.facts if f.kind=='SESSION']==[(control.hash,'native')]
    g=PhysicalLossStreakGovernor.rebuild(LockoutPolicy(5),ledger,account_alias='another_label',
        native_context=current.native_account_context,available_at_ms=NOW*1000)
    assert g._scopes[ACCOUNT_SCOPE].losses == 1
    assert g.original_contributors(ACCOUNT_SCOPE) == ('another_label',)
    assert g._scopes[first.payload['inputs']['intent']['strategy_id']].losses == 2
    assert not g.recovery_issue


def test_old_applied_control_is_history_after_expiry_not_fresh_entry_authority(tmp_path, eurusd):
    ledger, _, _, _, facts = native_facts(tmp_path,eurusd)
    event=original_control(ledger,facts.native_account_context)
    value=physical_financial_history(ledger,facts.native_account_context,available_at_ms=(NOW+86400)*1000)
    assert value.unresolved_refs == ()
    assert [f.event_ref for f in value.facts]==[event.hash]
    assert value.execution_authority is value.risk_capital_qualified is False


@pytest.mark.parametrize('damage',['missing_outcome','missing_context','other_query','other_alias','authority','changed_equity'])
def test_control_without_original_native_or_applied_proof_cannot_release_risk(tmp_path,eurusd,damage):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    def change(payload):
        if damage=='missing_context':payload.pop('native_account_context')
        elif damage=='other_query':payload['native_account_context']['source_query_ref']='0'*64
        elif damage=='other_alias':payload['native_account_context']['account_alias']='different_label'
        elif damage=='authority':payload['native_account_context']['execution_authority']=True
        elif damage=='changed_equity':payload['new_peak_equity']='999999'
    event=original_control(ledger,facts.native_account_context,finish=damage!='missing_outcome',
        action='resume_drawdown' if damage=='changed_equity' else 'reset_loss_streak',damage=change)
    value=physical_financial_history(ledger,facts.native_account_context,available_at_ms=NOW*1000)
    assert event.hash in value.unresolved_refs
    assert not [f for f in value.facts if f.kind=='SESSION']


def test_applied_control_for_another_proven_physical_account_is_not_a_local_reset(tmp_path,eurusd):
    ledger,adapter,account,_,facts=native_facts(tmp_path,eurusd)
    first=approval(ledger,facts,'a-loss');close(ledger,first,alias='native')
    other=other_context(ledger,adapter,account,facts,alias='native',server='Other-Broker-Demo')
    original_control(ledger,other.native_account_context)
    g=PhysicalLossStreakGovernor.rebuild(LockoutPolicy(5),ledger,account_alias='native',
        native_context=facts.native_account_context,available_at_ms=NOW*1000)
    assert not g.recovery_issue
    assert g._scopes[ACCOUNT_SCOPE].losses == 1
