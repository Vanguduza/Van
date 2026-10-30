"""A previously admitted policy is not current authority after signer retirement."""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal as D
import json

import pytest

from conftest import owner_authority,mandate_dict,intent,snapshot
from conftest_owner_authority import OWNER_KEY_ID,OwnerAuthorityHarness
from vati.authority import OwnerAuthorityVerifier,load_owner_keys
from vati.authority_registry import owner_key_id,revocation_record,revoke_owner_key
from vati.core import Ledger
from vati.execution import ExecutionRouter,PaperAdapter,ProtectionManager,RouterError
from vati.risk import TradingMandate,RiskAuthority,Decision,StrategyState,KillSwitch


def live_policy(tmp_path,monkeypatch):
    path=tmp_path/'current-owner.json';path.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}))
    monkeypatch.setenv('VAN_OWNER_AUTHORITY_KEYS',str(path))
    raw=mandate_dict(venue='paper',mode='DEMO_TRADER')
    return path,raw,TradingMandate.from_mapping(raw)


def retire(path,pem=None,device='owner-s24'):
    pem=pem or owner_authority().pem;kid=owner_key_id(pem);op=revocation_record(device,kid)['operation_id']
    return revoke_owner_key(path,device_id=device,key_id=kid,public_key_pem=pem,operation_id=op)


def decision(policy,eurusd):
    trade=intent(venue='paper',strategy_state=StrategyState.DEMO)
    result=RiskAuthority(policy).evaluate_safe(trade,snapshot(replace(eurusd,venue='paper')))
    return trade,result


def sender(policy,**kwargs):
    paper=PaperAdapter(account_alias=policy.account_alias)
    router=ExecutionRouter(ledger=Ledger(),adapters={'paper':paper},kill_switch=KillSwitch(),protection=ProtectionManager(),**kwargs)
    return router,paper


def test_key_retirement_rejects_new_risk_under_an_already_admitted_policy(tmp_path,monkeypatch,eurusd):
    path,_,policy=live_policy(tmp_path,monkeypatch)
    assert decision(policy,eurusd)[1].decision in {Decision.APPROVED,Decision.REDUCED}
    retire(path)
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_key_retirement_invalidates_an_old_risk_approval_before_actual_send(tmp_path,monkeypatch,eurusd):
    path,_,policy=live_policy(tmp_path,monkeypatch);trade,approved=decision(policy,eurusd)
    assert approved.decision in {Decision.APPROVED,Decision.REDUCED}
    router,paper=sender(policy);retire(path)
    with pytest.raises(RouterError,match='(?i)signer|owner.*key|owner.*authority'):
        router.execute(trade,approved,policy,now_ms=1800000000000)
    assert not paper.positions()


def test_signer_retirement_inside_submission_guard_still_prevents_native_send(tmp_path,monkeypatch,eurusd):
    path,_,policy=live_policy(tmp_path,monkeypatch);trade,approved=decision(policy,eurusd)
    @contextmanager
    def guard(epoch):
        retire(path)
        yield True
    router,paper=sender(policy,lease_submission_guard=guard)
    with pytest.raises(RouterError,match='(?i)signer|owner.*key|owner.*authority'):
        router.execute(trade,approved,policy,now_ms=1800000000000)
    assert not paper.positions()


def test_replacing_key_material_under_the_same_label_does_not_keep_old_policy_authority(tmp_path,monkeypatch,eurusd):
    path,_,policy=live_policy(tmp_path,monkeypatch)
    path.write_text(json.dumps({'keys':{OWNER_KEY_ID:OwnerAuthorityHarness().pem}}))
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_verified_signature_binds_the_key_used_before_a_concurrent_registry_change(tmp_path,monkeypatch,eurusd):
    path,raw,_=live_policy(tmp_path,monkeypatch);verify=OwnerAuthorityVerifier.verify
    other=OwnerAuthorityHarness()
    def changed_after_verification(self,*args,**kwargs):
        verified=verify(self,*args,**kwargs)
        if kwargs.get('act')=='mandate-admit':path.write_text(json.dumps({'keys':{OWNER_KEY_ID:other.pem}}))
        return verified
    monkeypatch.setattr(OwnerAuthorityVerifier,'verify',changed_after_verification)
    policy=TradingMandate.from_mapping(raw)
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_unavailable_or_unreadable_current_issuer_never_allows_new_risk(tmp_path,monkeypatch,eurusd):
    path,_,policy=live_policy(tmp_path,monkeypatch)
    path.write_text('not-json')
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED
    path.unlink()
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_equivalent_pem_and_unrelated_key_retirement_preserve_approved_authority(tmp_path,monkeypatch,eurusd):
    path,_,policy=live_policy(tmp_path,monkeypatch);other=OwnerAuthorityHarness()
    path.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem.replace('\n','\r\n'),'unrelated-key':other.pem}}))
    retire(path,pem=other.pem,device='unrelated-device')
    trade,approved=decision(policy,eurusd);assert approved.decision in {Decision.APPROVED,Decision.REDUCED}
    router,paper=sender(policy)
    assert router.execute(trade,approved,policy,now_ms=1800000000000).status=='FILLED'
    assert paper.positions()


def test_explicit_archived_trust_view_preserves_historical_paper_research(tmp_path,monkeypatch,eurusd):
    path,raw,current=live_policy(tmp_path,monkeypatch)
    historical=TradingMandate.from_mapping(raw,authority=OwnerAuthorityVerifier(load_owner_keys(path)))
    retire(path)
    assert decision(current,eurusd)[1].decision is Decision.REJECTED
    trade,approved=decision(historical,eurusd);assert approved.decision in {Decision.APPROVED,Decision.REDUCED}
    router,paper=sender(historical)
    assert router.execute(trade,approved,historical,now_ms=1800000000000).status=='FILLED'


def test_optional_temperament_signer_is_current_independently_of_the_base_policy(tmp_path,monkeypatch,eurusd):
    from vati.authority import sign_token
    from vati.risk.mandate import mandate_subject,trading_temperament_subject
    base=owner_authority();profile=OwnerAuthorityHarness();path=tmp_path/'two-issuers.json'
    path.write_text(json.dumps({'keys':{OWNER_KEY_ID:base.pem,'profile-owner':profile.pem}}))
    monkeypatch.setenv('VAN_OWNER_AUTHORITY_KEYS',str(path))
    raw=mandate_dict(venue='paper',mode='DEMO_TRADER',trading_temperament='NORMAL')
    raw['owner_signature_ref']=base.token(act='mandate-admit',subject=mandate_subject(raw),
        issued_at_unix=raw['signed_at_unix'],lifetime_seconds=raw['expires_at_unix']-raw['signed_at_unix'])
    raw['temperament_owner_signature_ref']=sign_token(profile.key,act='trading-temperament-admit',
        subject=trading_temperament_subject(raw),key_id='profile-owner',issued_at_unix=raw['signed_at_unix'],
        lifetime_seconds=raw['expires_at_unix']-raw['signed_at_unix'])
    policy=TradingMandate.from_mapping(raw)
    assert policy.owner_keys_current()
    retire(path,pem=profile.pem,device='profile-owner-device')
    assert OWNER_KEY_ID in load_owner_keys(path)
    assert not policy.owner_keys_current()
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_key_guard_serializes_native_submission_before_acknowledged_retirement(tmp_path,monkeypatch,eurusd):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    path,_,policy=live_policy(tmp_path,monkeypatch);trade,approved=decision(policy,eurusd)
    entered,released,retired=Event(),Event(),Event()
    paper=PaperAdapter(account_alias=policy.account_alias);submit=paper.submit
    def blocked(command,*,now_ms):
        entered.set()
        assert released.wait(3)
        return submit(command,now_ms=now_ms)
    paper.submit=blocked
    def send():
        ledger=Ledger(tmp_path/'native-send.sqlite')
        try:
            router=ExecutionRouter(ledger=ledger,adapters={'paper':paper},
                kill_switch=KillSwitch(),protection=ProtectionManager())
            return router.execute(trade,approved,policy,now_ms=1800000000000)
        finally:ledger.close()
    def revoke():
        try:return retire(path)
        finally:retired.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        sending=pool.submit(send)
        if not entered.wait(2):
            released.set()
            sending.result(timeout=5)
            pytest.fail('native submission did not reach the guarded adapter')
        revoking=pool.submit(revoke)
        try:assert not retired.wait(.2),'native revocation acknowledged before admitted send released its key-source guard'
        finally:released.set()
        assert sending.result(timeout=5).status=='FILLED'
        assert revoking.result(timeout=5)['phase']=='APPLIED'
    # The one already admitted operation is retained. A later decision cannot add risk.
    assert len(paper.positions())==1
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_runtime_trust_handles_do_not_change_signed_policy_or_risk_wire_hashes(tmp_path,monkeypatch):
    from dataclasses import asdict
    from vati.risk.serde import mandate_binding_hash
    path,_,policy=live_policy(tmp_path,monkeypatch)
    before=mandate_binding_hash(policy);encoded=asdict(policy)
    assert not any('binding' in k or 'registry_path' in k for k in encoded)
    retire(path)
    assert not policy.owner_keys_current()
    assert mandate_binding_hash(policy)==before and asdict(policy)==encoded
    assert not replace(policy).owner_keys_current()  # A replacement is not a new signed admission.


def test_current_admission_keeps_the_actual_verified_source_when_the_verifier_is_reconfigured(tmp_path,monkeypatch,eurusd):
    path,raw,_=live_policy(tmp_path,monkeypatch)
    verifier=OwnerAuthorityVerifier()
    policy=TradingMandate.from_mapping(raw,authority=verifier)
    replacement=tmp_path/'replacement.json';replacement.write_bytes(path.read_bytes())
    verifier.registry_path=str(replacement)
    retire(path)
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_in_memory_signer_retirement_also_invalidates_explicit_trust_admission(tmp_path,monkeypatch,eurusd):
    path,raw,_=live_policy(tmp_path,monkeypatch)
    verifier=OwnerAuthorityVerifier(load_owner_keys(path))
    policy=TradingMandate.from_mapping(raw,authority=verifier)
    assert policy.owner_keys_current()
    verifier.revoked_key_ids=verifier.revoked_key_ids|{OWNER_KEY_ID}
    assert decision(policy,eurusd)[1].decision is Decision.REJECTED


def test_signer_retirement_does_not_prevent_protective_exit_of_existing_exposure(tmp_path,monkeypatch,eurusd):
    from vati.execution.base import StopMode
    path,_,policy=live_policy(tmp_path,monkeypatch);trade,approved=decision(policy,eurusd)
    router,paper=sender(policy)
    opened=router.execute(trade,approved,policy,now_ms=1800000000000,stop_mode=StopMode.SOFTWARE)
    assert opened.status=='FILLED'
    stop=router.protection.stop_of(opened.broker_position_id)
    retire(path)
    assert not policy.owner_keys_current()
    assert router.protection.stop_of(opened.broker_position_id)==stop
    closed=router.apply_exits('paper',trade.symbol,trade.stop-D('.001'),trade.stop-D('.0009'),now_ms=1800000000001)
    assert any(r.status=='FILLED' for r in closed)
    assert not paper.positions()
    router.ledger.close()


def test_running_session_exposes_owner_signer_hold_without_erasing_position_protection(tmp_path,monkeypatch,eurusd):
    from pathlib import Path
    from test_single_session_recovery import opened_service
    source=tmp_path/'session-owner.json'
    source.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}))
    monkeypatch.setenv('VAN_OWNER_AUTHORITY_KEYS',str(source))
    service,cfg,clock=opened_service(tmp_path,eurusd)
    try:
        cycle=service.runner.cycle;position=service.adapter.positions()[0]
        stop=cycle.protection.stop_of(position.position_id)
        source=cycle.mandate._verified_owner_key_bindings[0].registry_path
        assert source is not None
        retire(Path(source))
        clock['now']+=1;service.step_once()
        heartbeat=json.loads(Path(cfg.heartbeat_path).read_text())
        assert heartbeat['permit_new_orders'] is False and heartbeat['owner_policy_current'] is False
        assert not service._entry_permitted()
        assert cycle.protection.stop_of(position.position_id)==stop
        assert service.adapter.positions()[0].position_id==position.position_id
    finally:
        service.close();service._ledger.close()


def test_actual_account_coordinator_reports_the_current_signer_hold(tmp_path,monkeypatch,eurusd):
    import os,uuid
    from pathlib import Path
    from test_single_session_lease import config
    from vati.accounts import AccountRegistry
    from vati.app.account_service import AccountCoordinatorService
    from vati.core import EventKind
    from vati.risk.serde import contract_to_dict
    if not os.environ.get('VATI_TEST_PG_DSN'):pytest.skip('requires real isolated PostgreSQL fixture')
    source=tmp_path/'book-owner.json'
    source.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}))
    monkeypatch.setenv('VAN_OWNER_AUTHORITY_KEYS',str(source))
    cfg=config(tmp_path,eurusd,ledger=os.environ['VATI_TEST_PG_DSN'])
    registry=AccountRegistry(cfg.registry_path);account=registry.get(cfg.account_alias)
    cfg.account_alias='signer_book_'+uuid.uuid4().hex[:12]
    registry.add(replace(account,alias=cfg.account_alias))
    cfg.mandate=mandate_dict(venue='paper',mode='DEMO_TRADER',account_alias=cfg.account_alias,
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    cfg.lake_root=str(tmp_path/'lake')
    cfg.instruments=[{'symbol':'GBPUSD','base':'GBP','quote':'USD',
        'contract':contract_to_dict(replace(eurusd,symbol='GBPUSD',base_currency='GBP'))}]
    service=AccountCoordinatorService(cfg,clock=lambda:1800000000000).build()
    try:
        service.start()
        assert json.loads(Path(cfg.heartbeat_path).read_text())['owner_policy_current'] is True
        retire(source)
        service.step_once()
        assert json.loads(Path(cfg.heartbeat_path).read_text())['owner_policy_current'] is False
        service._account_snapshot(1800000000001)
        latest=list(service._ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[-1]
        assert latest.payload['owner_policy_current'] is False
        assert not service.mandate.owner_keys_current()
    finally:
        service.lease.release(now_ms=1800000000001)
        service._lease_store.close();service._ledger.close()
