"""Original account effects survive lost replies, faults and process death."""
from dataclasses import asdict, replace
import json
import multiprocessing
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

import pytest
from fastapi import HTTPException

from commander.account_effects import (AccountEffectIntent, AccountEffectJournal, AccountEffectConflict,
    AccountEffectUnknown, AccountOperationUnconfirmed, AccountOperationBlocked, PRODUCER, SCHEMA)
from commander.accounts import AccountControlSettings, build_account_handlers
from vati.accounts import AccountRegistry
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger


def intent(**overrides):
    value = AccountEffectIntent(secrets.token_urlsafe(24), "owner-device", "consumed-a4-reference",
        "account_upsert", ("account:paper_lab",), "1"*64, "2"*64, int(time.time())+60)
    return replace(value, **overrides)


def handlers(tmp_path):
    return build_account_handlers(AccountControlSettings(str(tmp_path/'accounts.json'), str(tmp_path/'secrets'),
        operation_ledger=str(tmp_path/'native.sqlite')))


def prepared(h, command='mt5_ea_issue_key', **overrides):
    args = {'alias':'mt5_owner', 'login':'12345678', 'server':'Broker-Demo', **overrides}
    args['_expected_resource_version'] = h['account_revision']({'alias':args['alias']})['resource_version']
    args['_native_operation'] = {'operation_id':secrets.token_urlsafe(24), 'device_id':'owner-device',
        'authority_ref':'consumed-a4-reference', 'request_digest':canonical_hash({k:v for k,v in args.items() if not k.startswith('_')}),
        'expires_at_unix':int(time.time())+60}
    return args


def test_completed_original_returns_its_original_result_without_reissuing_a_key(tmp_path):
    h=handlers(tmp_path); args=prepared(h)
    first=h['mt5_ea_issue_key'](args)
    before=(tmp_path/'secrets/mt5_owner.env').read_bytes()
    cold=handlers(tmp_path); second=cold['mt5_ea_issue_key'](args)
    assert second['account']==first['account'] and second['credential_export_available'] is False
    assert 'signing_key' not in second and (tmp_path/'secrets/mt5_owner.env').read_bytes()==before
    state=cold['account_operation']({'operation_id':args['_native_operation']['operation_id'], 'device_id':'owner-device'})
    assert state['effect_state']=='APPLIED' and state['native_event_ref'] and state['result']==second
    led=Ledger(tmp_path/'native.sqlite')
    try:
        assert len(list(led.iter(EventKind.ACCOUNT_OPERATION)))==2 and led.verify_chain()[0]
        assert first['signing_key'] not in json.dumps([asdict(e) for e in led.iter()])
    finally: led.close()


@pytest.mark.parametrize('change',[{'device_id':'other-owner'}, {'authority_ref':'other-approval'},
    {'request_digest':'3'*64}, {'expires_at_unix':1}])
def test_operation_identity_cannot_be_reassigned_after_completion(tmp_path,change):
    h=handlers(tmp_path); args=prepared(h); h['mt5_ea_issue_key'](args)
    before=(tmp_path/'secrets/mt5_owner.env').read_bytes()
    args['_native_operation'].update(change)
    with pytest.raises((AccountOperationUnconfirmed, AccountOperationBlocked, ValueError)):
        h['mt5_ea_issue_key'](args)
    assert (tmp_path/'secrets/mt5_owner.env').read_bytes()==before


def test_failure_after_a_registry_effect_fences_original_and_new_approvals(tmp_path,monkeypatch):
    h=handlers(tmp_path); args=prepared(h)
    import commander.accounts as module
    original=module._write_secrets
    def fail_after_empty_file(path,values,**kw):
        if values: raise OSError('private-fixture-write-failure')
        return original(path,values,**kw)
    with monkeypatch.context() as m:
        m.setattr(module,'_write_secrets',fail_after_empty_file)
        with pytest.raises(AccountOperationUnconfirmed): h['mt5_ea_issue_key'](args)
    assert AccountRegistry(tmp_path/'accounts.json').get('mt5_owner').broker=='MT5_EA'
    with pytest.raises(AccountOperationUnconfirmed): handlers(tmp_path)['mt5_ea_issue_key'](args)
    with pytest.raises(AccountOperationBlocked): h['mt5_ea_issue_key'](prepared(h))
    assert 'BRIDGE_SIGNING_KEY' not in (tmp_path/'secrets/mt5_owner.env').read_text()
    state=h['account_operation']({'operation_id':args['_native_operation']['operation_id'], 'device_id':'owner-device'})
    assert state['effect_state']=='UNKNOWN' and state['reconciliation_required']
    assert h['mt5_ea_issue_key'](prepared(h,alias='other_owner'))['signing_key']


def test_validation_refusal_before_effect_does_not_permanently_fence_the_target(tmp_path):
    h=handlers(tmp_path); args=prepared(h,demo='false')
    with pytest.raises(HTTPException) as error: h['mt5_ea_issue_key'](args)
    assert error.value.status_code==422 and not (tmp_path/'accounts.json').exists()
    state=h['account_operation']({'operation_id':args['_native_operation']['operation_id'],'device_id':'owner-device'})
    assert state['effect_state']=='REFUSED' and not state['reconciliation_required']
    assert h['mt5_ea_issue_key'](prepared(h,demo=True))['signing_key']


def test_actual_child_death_after_native_effect_cannot_reopen_the_original_attempt(tmp_path):
    h=handlers(tmp_path); args=prepared(h)
    source='''import json,os,sys
from commander.accounts import AccountControlSettings,build_account_handlers
from commander.account_effects import AccountEffectJournal
root=sys.argv[1]
def die(*args,**kwargs): os._exit(74)
AccountEffectJournal.complete=die
h=build_account_handlers(AccountControlSettings(root+'/accounts.json',root+'/secrets',operation_ledger=root+'/native.sqlite'))
h['mt5_ea_issue_key'](json.loads(sys.argv[2]))
'''
    result=subprocess.run([sys.executable,'-c',source,str(tmp_path),json.dumps(args)],capture_output=True,text=True,timeout=8)
    assert result.returncode==74, result.stderr
    before=(tmp_path/'secrets/mt5_owner.env').read_bytes()
    assert b'BRIDGE_SIGNING_KEY=' in before
    cold=handlers(tmp_path)
    with pytest.raises(AccountOperationUnconfirmed): cold['mt5_ea_issue_key'](args)
    with pytest.raises(AccountOperationBlocked): cold['mt5_ea_issue_key'](prepared(cold))
    assert (tmp_path/'secrets/mt5_owner.env').read_bytes()==before
    state=cold['account_operation']({'operation_id':args['_native_operation']['operation_id'],'device_id':'owner-device'})
    assert state['native_phase']=='IN_FLIGHT' and state['effect_state']=='UNKNOWN'


def test_postcommit_reply_failure_reads_confirmed_history_without_another_effect(tmp_path,monkeypatch):
    h=handlers(tmp_path); args=prepared(h)
    complete=AccountEffectJournal.complete
    def lost_reply(self,*a,**kw):
        complete(self,*a,**kw)
        raise OSError('fixture-lost-native-commit-reply')
    with monkeypatch.context() as m:
        m.setattr(AccountEffectJournal,'complete',lost_reply)
        result=h['mt5_ea_issue_key'](args)
    assert result['credential_export_available'] is False
    before=(tmp_path/'secrets/mt5_owner.env').read_bytes()
    assert handlers(tmp_path)['mt5_ea_issue_key'](args)==result
    assert (tmp_path/'secrets/mt5_owner.env').read_bytes()==before


@pytest.mark.parametrize('fault',['producer','intent','predecessor','phase','secret'])
def test_well_sealed_but_invalid_operation_history_refuses_all_new_effects(tmp_path,fault):
    led=Ledger(tmp_path/'history.sqlite'); journal=AccountEffectJournal(led); original=intent(); claim=journal.claim(original)
    payload={'schema':SCHEMA,'intent':asdict(original),'intent_hash':canonical_hash(asdict(original)),
        'phase':'APPLIED','previous_ref':claim.event_ref,'result':{'alias':'paper_lab'}}
    producer=PRODUCER
    if fault=='producer': producer='untrusted-import'
    if fault=='intent': payload['intent']['device_id']='forged-device'
    if fault=='predecessor': payload['previous_ref']='0'*64
    if fault=='phase': payload['phase']='IN_FLIGHT'
    if fault=='secret': payload['result']={'signing_key':'fixture-no-export'}
    led.append(make_event(EventKind.ACCOUNT_OPERATION,producer,payload,event_time_ms=10,received_time_ms=10,correlation_id=original.operation_id))
    try:
        assert led.verify_chain()[0]
        with pytest.raises(AccountEffectUnknown): journal.claim(intent())
    finally: led.close()


def test_in_flight_scope_survives_authority_expiry_and_cold_reader(tmp_path):
    path=tmp_path/'history.sqlite'; led=Ledger(path); original=intent(); journal=AccountEffectJournal(led)
    journal.claim(original,now_unix=1); led.close()
    cold=Ledger(path)
    try:
        journal=AccountEffectJournal(cold)
        with pytest.raises(AccountEffectUnknown): journal.claim(original,now_unix=original.expires_at_unix+100)
        with pytest.raises(AccountEffectConflict): journal.claim(intent(),now_unix=1)
        assert journal.claim(intent(targets=('account:other_owner',)),now_unix=1).phase=='IN_FLIGHT'
    finally: cold.close()


def test_missing_native_operation_is_unknown_and_a_foreign_device_cannot_read_result(tmp_path):
    h=handlers(tmp_path)
    with pytest.raises(AccountOperationUnconfirmed): h['account_operation']({'operation_id':secrets.token_urlsafe(24),'device_id':'owner-device'})
    args=prepared(h); h['mt5_ea_issue_key'](args)
    with pytest.raises(HTTPException) as error:
        h['account_operation']({'operation_id':args['_native_operation']['operation_id'],'device_id':'foreign-device'})
    assert error.value.status_code==409 and 'account' not in str(error.value.detail)


def test_provider_link_cannot_bypass_an_unconfirmed_account_target(tmp_path):
    h=handlers(tmp_path)
    led=Ledger(tmp_path/'native.sqlite')
    try: AccountEffectJournal(led).claim(intent(targets=('account:mt5_owner',)))
    finally: led.close()
    with pytest.raises(AccountOperationBlocked):
        h['ctrader_link']({'alias':'mt5_owner','ctid_trader_account_id':12345,
            'client_id':'fixture','client_secret':'fixture','access_token':'fixture'})
    assert not (tmp_path/'accounts.json').exists()


def test_expired_original_authority_is_refused_before_any_native_effect(tmp_path):
    h=handlers(tmp_path); args=prepared(h); args['_native_operation']['expires_at_unix']=int(time.time())-1
    with pytest.raises(HTTPException) as error: h['mt5_ea_issue_key'](args)
    assert error.value.status_code==403
    assert not (tmp_path/'accounts.json').exists() and not (tmp_path/'secrets/mt5_owner.env').exists()


def test_postgres_original_operation_is_atomic_and_isolated_between_named_ledgers():
    spec=os.environ.get('VATI_TEST_PG_DSN')
    if not spec or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
        pytest.skip('requires explicitly isolated native PostgreSQL fixture')
    from vati.core.ledger_pg import PostgresLedger
    scope='native-effects-'+secrets.token_hex(8)
    led=PostgresLedger(spec,ledger_name=scope); other=PostgresLedger(spec,ledger_name=scope+'-other')
    original=intent(); journal=AccountEffectJournal(led)
    try:
        claim=journal.claim(original)
        append=led.append
        def failed_commit(event):
            append(event)
            raise OSError('induced atomic completion rollback')
        led.append=failed_commit
        with pytest.raises(OSError): journal.complete(claim,{'alias':'paper_lab'})
        led.append=append
        assert journal.status(original.operation_id,'owner-device').phase=='IN_FLIGHT'
        assert AccountEffectJournal(other).status(original.operation_id,'owner-device') is None
        journal.complete(claim,{'alias':'paper_lab'})
        cold=PostgresLedger(spec,ledger_name=scope)
        try: assert AccountEffectJournal(cold).claim(original).result=={'alias':'paper_lab'}
        finally: cold.close()
        assert led.verify_chain()[0] and other.verify_chain()[0]
    finally:
        led.close(); other.close()


def concurrent_claim(spec,scope,value,start,output):
    from vati.core.ledger_pg import open_ledger
    led=open_ledger(spec,ledger_name=scope)
    try:
        if not start.wait(5):
            output.put(('ERROR','start unavailable')); return
        try:
            state=AccountEffectJournal(led).claim(value)
            output.put((state.phase,os.getpid()))
        except AccountEffectConflict:
            output.put(('BLOCKED',os.getpid()))
        except Exception as exc:
            output.put(('ERROR',type(exc).__name__))
    finally: led.close()


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_concurrent_native_claim_writers_cannot_admit_two_effects_for_a_target(tmp_path,backend):
    from vati.core.ledger_pg import open_ledger
    scope='native-concurrent-'+secrets.token_hex(8)
    if backend=='postgres':
        spec=os.environ.get('VATI_TEST_PG_DSN')
        if not spec or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
            pytest.skip('requires explicitly isolated native PostgreSQL fixture')
    else: spec=str(tmp_path/'concurrent.sqlite')
    led=open_ledger(spec,ledger_name=scope); led.close()
    ctx=multiprocessing.get_context('spawn'); start=ctx.Event(); output=ctx.Queue()
    children=[ctx.Process(target=concurrent_claim,args=(spec,scope,intent(),start,output)) for _ in range(2)]
    try:
        for child in children: child.start()
        start.set()
        results=[output.get(timeout=10) for _ in children]
        for child in children:
            child.join(5); assert child.exitcode==0
        assert sorted(row[0] for row in results)==['BLOCKED','IN_FLIGHT'],results
        assert len({row[1] for row in results})==2
        led=open_ledger(spec,ledger_name=scope)
        try:
            assert len(list(led.iter(EventKind.ACCOUNT_OPERATION)))==1 and led.verify_chain()[0]
        finally: led.close()
    finally:
        for child in children:
            if child.is_alive(): child.terminate(); child.join(3)
        output.close()
