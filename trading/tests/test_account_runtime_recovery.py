"""Real multi-instrument actor/PG recovery, account isolation and original outcomes."""
import base64
from dataclasses import replace
from decimal import Decimal as D
import json
import os
from pathlib import Path
import secrets
import time
import uuid

import pytest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec

from conftest import mandate_dict,owner_authority
from conftest_owner_authority import OWNER_KEY_ID
from test_single_session_lease import config
from vati.accounts import AccountRegistry
from vati.app.account_service import AccountCoordinatorService
from vati.app.runtime_control_actor import outstanding_owner_halts
from vati.app.runtime_control_journal import RuntimeControlJournal
from vati.app.runtime_control_protocol import RecoveryIntent,RecoveryProof,approval_statement
from vati.core import EventKind,make_event
from vati.core.canonical import canonical_hash
from vati.risk.contracts import KillSwitchTrigger
from vati.risk.serde import contract_to_dict


@pytest.fixture
def book(tmp_path,monkeypatch,eurusd):
    if not os.environ.get('VATI_TEST_PG_DSN'):pytest.skip('requires real isolated PostgreSQL fixture')
    import psycopg
    from psycopg import sql
    from urllib.parse import urlsplit,urlunsplit
    # Each scenario needs empty native history; otherwise the known foreign-halt
    # bug can pre-halt the next scenario and make its negative control vacuous.
    assert os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')=='1'
    dsn=os.environ['VATI_TEST_PG_DSN'];database='source_recovery_'+uuid.uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    book_dsn=urlunsplit(urlsplit(dsn)._replace(path='/'+database))
    with psycopg.connect(book_dsn,autocommit=True) as setup:setup.execute('CREATE SCHEMA vati')
    cfg=config(tmp_path,eurusd,ledger=book_dsn)
    clock={'now':int(time.time()*1000)}
    policy_keys=tmp_path/'policy-owner.json'
    policy_keys.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}))
    monkeypatch.setenv('VAN_OWNER_AUTHORITY_KEYS',str(policy_keys))
    registry=AccountRegistry(cfg.registry_path);account=registry.get(cfg.account_alias)
    cfg.account_alias='recovery_book_'+uuid.uuid4().hex[:12]
    registry.add(replace(account,alias=cfg.account_alias))
    cfg.mandate=mandate_dict(venue='paper',mode='DEMO_TRADER',account_alias=cfg.account_alias,
        allowed_strategies=['FX-TREND-PULLBACK-01'],signed_at_unix=clock['now']//1000-1,
        expires_at_unix=clock['now']//1000+86400)
    cfg.lake_root=str(tmp_path/'lake')
    cfg.instruments=[{'symbol':'GBPUSD','base':'GBP','quote':'USD',
        'contract':contract_to_dict(replace(eurusd,symbol='GBPUSD',base_currency='GBP'))}]
    private=ec.generate_private_key(ec.SECP256R1())
    pem=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    cfg.owner_authority_keys=str(tmp_path/'recovery-owner.json');keys={'recovery-owner':pem}
    Path(cfg.owner_authority_keys).write_text(json.dumps({'keys':keys}))
    service=AccountCoordinatorService(cfg,clock=lambda:clock['now']).build();service.start()
    assert KillSwitchTrigger.OWNER_HALT not in service.kill.active,'fixture must begin without an inherited owner halt'
    def review():
        service._heartbeat('RUNNING')
        hb=json.loads(Path(cfg.heartbeat_path).read_text())
        assert 'runtime_recovery' in hb,'multi-instrument runtime omits the owner recovery contract'
        value=hb['runtime_recovery'];assert value['state_ref']==canonical_hash(value['state'])
        return value
    def request(action='clear_kill_switch',args=None,**overrides):
        current=review()
        body={'schema':'vati.runtime-recovery/1','device_id':'source-s24',
            'account_alias':cfg.account_alias,'session_id':current['state']['session_id'],
            'action':action,'state_ref':current['state_ref'],'issued_at_unix':clock['now']//1000,
            'args':args if args is not None else {'trigger':'OWNER_HALT'},**overrides}
        intent=RecoveryIntent.from_mapping(body);op=secrets.token_urlsafe(24);expiry=clock['now']//1000+60
        signature=private.sign(approval_statement(intent,op,expiry).encode(),ec.ECDSA(hashes.SHA256()))
        proof=RecoveryProof(op,expiry,'recovery-owner',base64.b64encode(signature).decode())
        journal=RuntimeControlJournal(service._ledger,clock=lambda:clock['now']//1000)
        return journal,journal.enqueue(intent,proof,keys)
    yield service,clock,review,request
    service.lease.release(now_ms=clock['now']);service._lease_store.close();service._ledger.close()
    with psycopg.connect(dsn,autocommit=True) as admin:
        admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))


def halt(service,alias=None,cleared=False):
    payload={'trigger':'OWNER_HALT','account_alias':alias or service.cfg.account_alias}
    if cleared:payload['cleared']=True
    event=make_event(EventKind.KILL_SWITCH,'van-commander',payload,event_time_ms=service.clock(),
        received_time_ms=service.clock(),correlation_id='source-owner')
    service._ledger.append(event)
    return event


def test_foreign_account_owner_halt_cannot_stop_this_book(book):
    service,clock,review,request=book
    halt(service,'some_other_account');service._observe_owner_halt(clock['now'])
    assert KillSwitchTrigger.OWNER_HALT not in service.kill.active


def test_a_foreign_or_unverified_boolean_clear_cannot_hide_the_account_owner_halt(book):
    service,clock,review,request=book
    source=halt(service);halt(service,'other_account',cleared=True)
    halt(service,cleared=True)
    service._observe_owner_halt(clock['now'])
    assert KillSwitchTrigger.OWNER_HALT in service.kill.active
    assert source in outstanding_owner_halts(service._ledger,service.cfg.account_alias)


def test_account_review_is_stable_between_polls_and_binds_the_real_actor_and_scope(book):
    service,clock,review,request=book
    first=review();clock['now']+=1;second=review()
    assert first['state']==second['state'] and first['state_ref']==second['state_ref']
    assert first['state']['lease_epoch']==service.lease.epoch
    assert first['state']['holder_instance_id']==service.lease.instance_id
    assert first['state']['account_alias']==service.cfg.account_alias
    service.specs['EURUSD']=replace(service.specs['EURUSD'],timeframe='M5')
    assert review()['state_ref']!=first['state_ref']


def test_signed_account_owner_clear_changes_only_the_cited_cause_and_never_submits(book):
    service,clock,review,request=book
    source=halt(service);service._observe_owner_halt(clock['now'])
    service.kill.trip(KillSwitchTrigger.STALE_DATA,clock['now'])
    journal,original=request();service.step_once()
    done=journal.status(original.proof.operation_id,original.intent.device_id)
    assert done.phase=='APPLIED' and len(done.result['effect_refs'])==1
    assert done.result['entry_authority_granted'] is False
    assert service.kill.active=={KillSwitchTrigger.STALE_DATA}
    assert not outstanding_owner_halts(service._ledger,service.cfg.account_alias)
    count=service._ledger.count(EventKind.KILL_SWITCH)
    service.step_once();assert journal.enqueue(original.intent,original.proof,{}).phase=='APPLIED'
    assert service._ledger.count(EventKind.KILL_SWITCH)==count
    assert service._ledger.count(EventKind.ORDER_COMMAND)==0


@pytest.mark.parametrize('change,reason',[('halt','STATE_CHANGED'),('expired','APPROVAL_EXPIRED'),
    ('revoked','OWNER_KEY_UNREGISTERED'),('session','SESSION_CHANGED'),('lease','ACTOR_LEASE_LOST')])
def test_changed_account_recovery_authority_refuses_without_clearing(book,change,reason):
    from vati.app.runtime_control_actor import process_recovery_requests
    service,clock,review,request=book
    halt(service);service._observe_owner_halt(clock['now'])
    journal,original=request(session_id='a_previous_actor') if change=='session' else request()
    if change=='halt':clock['now']+=1;halt(service)
    elif change=='expired':clock['now']+=61000
    elif change=='revoked':Path(service.cfg.owner_authority_keys).write_text(json.dumps({'keys':{}}))
    elif change=='lease':service.lease.release(now_ms=clock['now'])
    if change=='lease':process_recovery_requests(service)
    else:service.step_once()
    done=journal.status(original.proof.operation_id,original.intent.device_id)
    assert done.phase=='REFUSED' and done.result['reason_code']==reason
    assert done.result['effect_refs']==[] and done.result['entry_authority_granted'] is False
    assert KillSwitchTrigger.OWNER_HALT in service.kill.active


def test_no_market_data_does_not_expire_the_owner_recovery_actor(book):
    service,clock,review,request=book
    epoch=service.lease.epoch
    clock['now']+=31000;service.step_once()
    assert service.lease.fence(epoch,now_ms=clock['now'])
    assert review()['state']['lease_epoch']==epoch


def test_signed_account_drawdown_resume_records_current_money_without_entry_permission(book):
    service,clock,review,request=book
    service.peak_equity=D('12000')
    journal,original=request('resume_drawdown',{})
    service.step_once();done=journal.status(original.proof.operation_id,original.intent.device_id)
    assert done.phase=='APPLIED' and done.result['entry_authority_granted'] is False
    assert service.peak_equity==service.adapter.sync_account().equity==D('10000')
    assert service._ledger.count(EventKind.ORDER_COMMAND)==0


def test_signed_account_loss_reset_does_not_erase_a_later_loss_on_replay(book):
    service,clock,review,request=book;sid='FX-TREND-PULLBACK-01'
    def loss(identity):
        service._ledger.append(make_event(EventKind.TRADE_REVIEW,'vati-account-lifecycle',
            {'strategy_id':sid,'account_alias':service.cfg.account_alias,'pnl':'-1'},
            event_time_ms=clock['now'],received_time_ms=clock['now'],correlation_id=identity))
        service.lifecycle.streaks.on_close(sid,D('-1'),clock['now'])
    loss('original-loss');journal,original=request('reset_loss_streak',{'scope':'*ACCOUNT*'})
    service.step_once();assert journal.status(original.proof.operation_id,original.intent.device_id).phase=='APPLIED'
    assert service.lifecycle.streaks._scopes['*ACCOUNT*'].losses==0
    loss('later-loss');service.step_once()
    assert journal.enqueue(original.intent,original.proof,{}).phase=='APPLIED'
    assert service.lifecycle.streaks._scopes['*ACCOUNT*'].losses==1


def test_owner_key_retirement_cannot_acknowledge_during_a_recovery_effect(book,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from vati.app.runtime_control_actor import process_recovery_requests
    from vati.authority_registry import owner_key_id,revocation_record,revoke_owner_key
    service,clock,review,request=book
    halt(service);service._observe_owner_halt(clock['now']);journal,original=request()
    pem=original.public_key_pem;kid=owner_key_id(pem);record=revocation_record('source-s24',kid)
    effect,started,retired=Event(),Event(),Event();append=service._ledger.append
    def revoke():
        assert effect.wait(3);started.set()
        try:
            return revoke_owner_key(service.cfg.owner_authority_keys,device_id='source-s24',key_id=kid,
                public_key_pem=pem,operation_id=record['operation_id'])
        finally:retired.set()
    def guarded_append(event):
        if event.kind is EventKind.KILL_SWITCH and event.payload.get('cleared') is True:
            effect.set();assert started.wait(2)
            assert not retired.wait(.2),'native key retirement acknowledged before the approved recovery effect committed'
        return append(event)
    monkeypatch.setattr(service._ledger,'append',guarded_append)
    with ThreadPoolExecutor(max_workers=1) as pool:
        retiring=pool.submit(revoke)
        try:process_recovery_requests(service)
        finally:effect.set()
        assert retiring.result(timeout=5)['phase']=='APPLIED'
    assert journal.status(original.proof.operation_id,original.intent.device_id).phase=='APPLIED'


def test_equivalent_pem_format_keeps_the_same_approved_recovery_key(book):
    service,clock,review,request=book
    halt(service);service._observe_owner_halt(clock['now']);journal,original=request()
    Path(service.cfg.owner_authority_keys).write_text(json.dumps({'keys':{
        original.proof.key_id:original.public_key_pem.replace('\n','\r\n')}}))
    service.step_once()
    assert journal.status(original.proof.operation_id,original.intent.device_id).phase=='APPLIED'


def unconfirmed_order(service):
    from dataclasses import asdict
    from vati.execution.base import OrderCommand,StopMode
    from vati.risk.contracts import Direction,LossModel
    command=OrderCommand('original-unconfirmed','d'*64,'original-unconfirmed',service.cfg.account_alias,
        'paper','EURUSD',Direction.LONG,'MARKET',D('.1'),D('1.1'),D('1.09'),
        StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
    service._ledger.append(make_event(EventKind.ORDER_COMMAND,'vati-execution-router',asdict(command),
        event_time_ms=service.clock(),received_time_ms=service.clock(),correlation_id=command.trade_intent_id))
    return command


def native_receipt(service,command,status,quantity,price=None):
    from dataclasses import asdict
    from vati.execution.base import ExecutionReceipt
    receipt=ExecutionReceipt(command.trade_intent_id,command.decision_hash,command.venue,status,
        quantity,price,command.entry_price,command.entry_price,command.entry_price,True,
        service.clock(),service.clock()).sealed()
    payload=asdict(receipt)
    payload['native_entry_observation']={'schema':'vati.native-entry-observation/1',
        'command_hash':command.command_hash,'source':'ORIGINAL_NATIVE_RESULT'}
    service._ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-cycle',payload,
        event_time_ms=service.clock(),received_time_ms=service.clock(),correlation_id=command.trade_intent_id))


def test_unconfirmed_original_native_order_blocks_account_recovery_without_a_resend(book):
    service,clock,review,request=book
    command=unconfirmed_order(service);halt(service);service._observe_owner_halt(clock['now'])
    assert review()['state']['unresolved_entry_ids']==[command.trade_intent_id]
    journal,original=request();service.step_once()
    done=journal.status(original.proof.operation_id,original.intent.device_id)
    assert done.phase=='REFUSED' and done.result['reason_code']=='PRECONDITION_UNMET'
    assert KillSwitchTrigger.OWNER_HALT in service.kill.active
    assert service._ledger.count(EventKind.ORDER_COMMAND)==1


def test_unconfirmed_native_order_is_not_a_healthy_account_risk_snapshot(book):
    from types import SimpleNamespace
    service,clock,review,request=book
    candidate=SimpleNamespace(symbol='EURUSD',strategy_id='FX-TREND-PULLBACK-01')
    assert service._snapshot_for(candidate).reconciliation_ok
    unconfirmed_order(service)
    assert service._snapshot_for(candidate).reconciliation_ok is False


def test_original_zero_effect_readback_allows_a_fresh_account_recovery_without_resending(book):
    service,clock,review,request=book;command=unconfirmed_order(service)
    halt(service);service._observe_owner_halt(clock['now'])
    journal,original=request();service.step_once()
    assert journal.status(original.proof.operation_id,original.intent.device_id).phase=='REFUSED'
    native_receipt(service,command,'REJECTED',D('0'))
    assert review()['state']['unresolved_entry_ids']==[]
    journal,fresh=request();service.step_once()
    assert journal.status(fresh.proof.operation_id,fresh.intent.device_id).phase=='APPLIED'
    assert service._ledger.count(EventKind.ORDER_COMMAND)==1


def test_late_zero_quantity_refusal_cannot_erase_an_original_positive_partial_fill(book):
    service,clock,review,request=book;command=unconfirmed_order(service)
    native_receipt(service,command,'PARTIAL',D('.05'),D('1.1'))
    native_receipt(service,command,'REJECTED',D('0'))
    assert review()['state']['unresolved_entry_ids']==[command.trade_intent_id]


@pytest.mark.parametrize('price',[None,D('0'),D('-1'),D('NaN')])
def test_invalid_original_fill_money_cannot_clear_native_uncertainty(book,price):
    service,clock,review,request=book;command=unconfirmed_order(service)
    native_receipt(service,command,'FILLED',command.quantity,price)
    assert review()['state']['unresolved_entry_ids']==[command.trade_intent_id]


@pytest.mark.parametrize('ack_lost',[False,True])
def test_account_recovery_effect_and_original_outcome_are_one_real_pg_commit(book,monkeypatch,ack_lost):
    from contextlib import contextmanager
    from vati.app.runtime_control_actor import process_recovery_requests
    service,clock,review,request=book
    halt(service);service._observe_owner_halt(clock['now']);journal,original=request()
    ledger=service._ledger;append=ledger.append;atomic=ledger.atomic;effect_written=[];fired=[]
    def observed(event):
        result=append(event)
        if event.kind is EventKind.KILL_SWITCH and event.payload.get('cleared') is True:
            effect_written.append(True)
            if not ack_lost:raise OSError('fixture failure before actual PostgreSQL commit')
        return result
    @contextmanager
    def lost_committed_reply():
        outer=ledger._atomic_depth==0
        with atomic():yield ledger
        if outer and effect_written and not fired:
            fired.append(True)
            raise OSError('fixture reply lost after actual PostgreSQL commit')
    with monkeypatch.context() as scoped:
        scoped.setattr(ledger,'append',observed)
        if ack_lost:
            scoped.setattr(ledger,'atomic',lost_committed_reply)
            process_recovery_requests(service)
        else:
            with pytest.raises(OSError,match='before actual PostgreSQL commit'):
                process_recovery_requests(service)
    done=journal.status(original.proof.operation_id,original.intent.device_id)
    assert done.phase==('APPLIED' if ack_lost else 'REQUESTED')
    effects=[e for e in ledger.iter(EventKind.KILL_SWITCH) if e.payload.get('cleared') is True]
    assert len(effects)==(1 if ack_lost else 0)
    process_recovery_requests(service)
    assert journal.status(original.proof.operation_id,original.intent.device_id).phase=='APPLIED'
    assert len([e for e in ledger.iter(EventKind.KILL_SWITCH) if e.payload.get('cleared') is True])==1
