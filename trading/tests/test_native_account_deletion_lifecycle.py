"""Native owned credential/safety/unknown/CAS controls; SOURCE fixtures only."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib,json,time
import pytest
from fastapi import HTTPException
from commander.accounts import AccountControlSettings,build_account_handlers,_write_secrets
from commander.account_lifecycle import NativeLifecycle,selected_sessions
from vati.accounts import AccountRegistry,Account,CredentialRef
from vati.accounts.resource_version import resource_snapshot
from vati.core import Ledger,EventKind
from vati.core.canonical import canonical_hash
from trading.tests.test_account_strategy_detachment import detached


def service(tmp_path,account=None):
    path=tmp_path/'vati.sqlite';Ledger(path).close()
    reg=AccountRegistry(tmp_path/'accounts.json')
    reg.add(account or Account('paper_owner','PAPER','OBSERVE','USD'))
    config=tmp_path/'session.json';config.write_text(json.dumps({'account_alias':'paper_owner','symbol':'EURUSD','base':'EUR','quote':'USD','timeframe':'M5','contract':{},'mandate':{},'capsules':['a-v1'],'registry_path':str(reg.path)}))
    st=AccountControlSettings(str(reg.path),str(tmp_path/'secrets'),operation_ledger=str(path),
        lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    return st,config,build_account_handlers(st)

def native_review(handlers,args):return handlers['account_review']({'action':'account_remove','args':args,'owner_device_id':'source-device','_account_dispatch_guard':lambda:None})

def admitted(handlers,args):
    review=native_review(handlers,args)
    return args|{'_expected_resource_version':review['resource_version'],'_expected_review_digest':review['review_digest'],
        '_expected_lifecycle_context_digest':review['context_digest'],
        '_expected_account_control_domain':handlers['account_revision']({})['account_control_domain'],
        '_native_operation':{'operation_id':'source_original_deletion_00000001','device_id':'source-device',
            'request_digest':canonical_hash(args),'authority_ref':'SOURCE_INTERNAL_NOT_OWNER::review:'+review['review_digest'],
            'expires_at_unix':int(time.time())+300},'_account_dispatch_guard':lambda:None,
        '_lifecycle_oauth':{'digest':args['oauth_discard_digest'],'request_digest':canonical_hash(args)}}

def delete_args():return {'alias':'paper_owner','variant':'DELETE_GRACE','grace_seconds':600,'oauth_discard_digest':'5'*64}


def test_retained_cash_view_current_original_device_and_post_read_guard(tmp_path):
    st,_,handlers=service(tmp_path)
    result=handlers['account_remove'](admitted(handlers,delete_args()))
    row=result['lifecycle']
    args={'view':'FINANCIAL_HISTORY','alias':row['alias'],'lifecycle_id':row['operation_id']}
    def read(device='source-device',guard=lambda:None,body=None):
        return handlers['account_review']({'action':'account_lifecycle_read','args':args if body is None else body,
            'owner_device_id':device,'_account_dispatch_guard':guard})
    result=read()
    for _ in range(100):
        if result['state']!='IN_PROGRESS':break
        result=read(body=args | {'cursor':result['next_cursor']})
    assert result['state']=='UNOBSERVED'
    with pytest.raises(HTTPException) as refused:read(device='another-paired-device')
    assert refused.value.status_code==403
    with pytest.raises(HTTPException) as malformed:read(body={'view':'FINANCIAL_HISTORY'})
    assert malformed.value.status_code==422
    calls=[]
    def revoke_after_read():
        calls.append(True)
        if len(calls)==2:raise HTTPException(403,'source device revoked after source read')
    with pytest.raises(HTTPException) as revoked:read(guard=revoke_after_read)
    assert revoked.value.status_code==403 and len(calls)==2

def test_native_missing_current_actor_refuses_before_any_data_or_secret_effect(tmp_path):
    st,_,handlers=service(tmp_path)
    args=admitted(handlers,delete_args());args.pop('_account_dispatch_guard')
    with pytest.raises(HTTPException,match='Current lifecycle actor'):handlers['account_remove'](args)
    assert AccountRegistry(st.registry_path).get('paper_owner')

def test_actual_native_hard_readonly_source_scope_no_filesystem_scan_or_config_rewrite(tmp_path):
    st,config,handlers=service(tmp_path)
    before=config.read_bytes();review=native_review(handlers,delete_args())
    assert review['view']['strategies']==['a-v1']
    assert review['view']['session_sources'][0]['sha256']==hashlib.sha256(before).hexdigest()
    assert str(config) not in json.dumps(review)
    result=handlers['account_remove'](admitted(handlers,delete_args()))
    assert result['removed'] and config.read_bytes()==before
    assert AccountRegistry(st.registry_path)._lifecycles['paper_owner']['phase']=='PENDING_ARCHIVE'

def test_no_unsigned_or_expired_native_original_can_start_delete(tmp_path):
    st,_,handlers=service(tmp_path);args=admitted(handlers,delete_args())
    args['_native_operation']['expires_at_unix']=int(time.time())-1
    with pytest.raises(HTTPException):handlers['account_remove'](args)
    assert AccountRegistry(st.registry_path).get('paper_owner')
    assert not AccountRegistry(st.registry_path)._lifecycles

@pytest.mark.parametrize('fault',['after_prepare','after_unlink'])
def test_original_partial_delete_retains_unknown_null_and_never_ages_to_success(tmp_path,monkeypatch,fault):
    st,_,handlers=service(tmp_path);args=admitted(handlers,delete_args());update=AccountRegistry.lifecycle_update;calls=[]
    def fail(self,*a,**kw):
        result=update(self,*a,**kw);calls.append(True)
        # Retain the original physical-removal/completion windows even when a
        # new guarded DATA reservation precedes those actual replacements.
        phase=self._lifecycles.get('paper_owner',{}).get('phase')
        if 'paper_owner' not in self.accounts and phase==('DELETING' if fault=='after_prepare' else 'PENDING_ARCHIVE'):
            raise OSError('SOURCE postreplace lost acknowledgement')
        return result
    monkeypatch.setattr(AccountRegistry,'lifecycle_update',fail)
    with pytest.raises(Exception):handlers['account_remove'](args)
    from commander.account_effects import AccountEffectJournal
    with closing(Ledger(st.operation_ledger)) as led:
        original=AccountEffectJournal(led).status(args['_native_operation']['operation_id'],'source-device')
        assert original.phase=='UNKNOWN' and original.result is None
    cold=AccountRegistry(st.registry_path);assert 'paper_owner' not in cold.accounts
    row=cold._lifecycles['paper_owner'];assert row['phase']==('DELETING' if fault=='after_prepare' else 'PENDING_ARCHIVE')
    with pytest.raises(HTTPException):handlers['account_remove'](args) # original never gets blindly resent
    with closing(Ledger(st.operation_ledger)) as led:
        assert AccountEffectJournal(led).status(args['_native_operation']['operation_id'],'source-device').result is None

@pytest.mark.parametrize('value',[None,(),(('missing', '1'*64),)])
def test_missing_incomplete_or_wrong_exact_config_source_holds(tmp_path,value):
    st,_,handlers=service(tmp_path);handlers=build_account_handlers(replace(st,lifecycle_session_sources=value))
    with pytest.raises(HTTPException):native_review(handlers,delete_args())
    assert AccountRegistry(st.registry_path).get('paper_owner')


def test_real_native_configuration_file_binding_is_data_not_an_approval_label(tmp_path,monkeypatch):
    st,config,_=service(tmp_path)
    manifest=tmp_path/'scope.json'
    manifest.write_text(json.dumps({'schema':'vati.account-session-scope/1','registry_path':st.registry_path,
        'sources':[{'path':str(config),'sha256':hashlib.sha256(config.read_bytes()).hexdigest()}]}))
    manifest.chmod(0o600);monkeypatch.setenv('VAN_ACCOUNT_LIFECYCLE_SESSION_SCOPE_FILE',str(manifest))
    loaded=AccountControlSettings(st.registry_path,st.secrets_dir,operation_ledger=st.operation_ledger)
    assert loaded.lifecycle_session_sources==st.lifecycle_session_sources
    native_review(build_account_handlers(loaded),delete_args())
    manifest.chmod(0o644)
    with pytest.raises(ValueError,match='private owner configuration'):
        AccountControlSettings(st.registry_path,st.secrets_dir)


def _dying_native(settings,args):
    import os
    update=AccountRegistry.lifecycle_update
    def die(self,*a,**kw):
        result=update(self,*a,**kw)
        if args['alias'] not in self.accounts and self._lifecycles.get(args['alias'],{}).get('phase')=='DELETING':os._exit(23)
        return result
    AccountRegistry.lifecycle_update=die
    build_account_handlers(settings)['account_remove'](args)


def test_actual_process_death_after_native_prepare_cold_read_keeps_original_unknown(tmp_path):
    import multiprocessing
    st,_,handlers=service(tmp_path);args=admitted(handlers,delete_args())
    child=multiprocessing.get_context('fork').Process(target=_dying_native,args=(st,args))
    child.start();child.join(10)
    try:assert child.exitcode==23
    finally:
        if child.is_alive():child.terminate();child.join(5)
        assert not child.is_alive()
    cold=AccountRegistry(st.registry_path);row=cold._lifecycles['paper_owner']
    assert row['phase']=='DELETING' and 'paper_owner' not in cold.accounts
    from commander.account_effects import AccountEffectJournal
    with closing(Ledger(st.operation_ledger)) as led:
        original=AccountEffectJournal(led).status(args['_native_operation']['operation_id'],'source-device')
        assert original.phase in {'IN_FLIGHT','UNKNOWN'} and original.result is None and led.verify_chain()[0]
    # Metadata archive cannot convert an incomplete deletion into success.
    with closing(Ledger(st.operation_ledger)) as led:
        native=NativeLifecycle(st,led,lambda _:row['account_control_domain'],None,
            lambda alias:resource_snapshot(AccountRegistry(st.registry_path),alias)['resource_version'],clock=lambda:row['archive_at_unix']+100)
        assert native.archive_due('paper_owner') is False
    assert AccountRegistry(st.registry_path)._lifecycles['paper_owner']['phase']=='DELETING'


def _archive_worker(settings,when,ready,go,queue):
    with closing(Ledger(settings.operation_ledger)) as led:
        handlers=build_account_handlers(settings)
        native=NativeLifecycle(settings,led,lambda _:handlers['account_revision']({})['account_control_domain'],None,
            lambda alias:resource_snapshot(AccountRegistry(settings.registry_path),alias)['resource_version'],clock=lambda:when)
        ready.set();go.wait(5)
        try:queue.put(('archive',native.archive_due('paper_owner')))
        except HTTPException as error:queue.put(('archive',error.status_code))


def _cancel_worker(settings,args,when,ready,go,queue):
    with closing(Ledger(settings.operation_ledger)) as led:
        handlers=build_account_handlers(settings)
        native=NativeLifecycle(settings,led,lambda _:handlers['account_revision']({})['account_control_domain'],None,
            lambda alias:resource_snapshot(AccountRegistry(settings.registry_path),alias)['resource_version'],clock=lambda:when)
        ready.set();go.wait(5)
        try:native.execute(args,lambda:None);queue.put(('cancel','applied'))
        except HTTPException as error:queue.put(('cancel',error.status_code))


def test_actual_two_process_cancel_archive_have_one_cas_winner(tmp_path):
    import multiprocessing
    st,_,handlers=service(tmp_path);handlers['account_remove'](admitted(handlers,delete_args()))
    row=AccountRegistry(st.registry_path)._lifecycles['paper_owner']
    with closing(Ledger(st.operation_ledger)) as led:
        native=NativeLifecycle(st,led,lambda _:row['account_control_domain'],None,
            lambda alias:resource_snapshot(AccountRegistry(st.registry_path),alias)['resource_version'],clock=lambda:row['archive_at_unix']-1)
        args={'alias':'paper_owner','variant':'CANCEL_DELETE','lifecycle_id':row['operation_id'],
            'expected_revision':row['revision'],'expected_digest':canonical_hash(row)}
        review=native.review(args,'source-device',lambda:None)
    args|={'_expected_resource_version':review['resource_version'],'_expected_review_digest':review['review_digest'],
        '_expected_lifecycle_context_digest':review['context_digest'],
        '_expected_account_control_domain':row['account_control_domain'],
        '_native_operation':{'operation_id':'source_cancel_boundary_00000001','device_id':'source-device','request_digest':canonical_hash(args),
            'authority_ref':'SOURCE_INTERNAL_NOT_OWNER::review:'+review['review_digest'],'expires_at_unix':int(time.time())+300}}
    ctx=multiprocessing.get_context('fork');go=ctx.Event();a=ctx.Event();b=ctx.Event();queue=ctx.Queue()
    workers=[ctx.Process(target=_archive_worker,args=(st,row['archive_at_unix']+1,a,go,queue)),
             ctx.Process(target=_cancel_worker,args=(st,args,row['archive_at_unix']-1,b,go,queue))]
    for worker in workers:worker.start()
    try:
        assert a.wait(5) and b.wait(5);go.set()
        for worker in workers:worker.join(10);assert worker.exitcode==0
        observations=[queue.get(timeout=2),queue.get(timeout=2)]
    finally:
        for worker in workers:
            if worker.is_alive():worker.terminate();worker.join(5)
        queue.close();queue.join_thread()
    cold=AccountRegistry(st.registry_path);final=cold._lifecycles['paper_owner']
    assert final['phase'] in {'ARCHIVED','RELINK_REQUIRED'} and final['restore'] is None and final['revision']==3
    assert ('paper_owner' in cold.accounts)==(final['phase']=='RELINK_REQUIRED')
    assert final['detached'] is True
    with closing(Ledger(st.operation_ledger)) as led:assert led.verify_chain()[0]


def test_actual_service_parser_consumes_exact_hashed_bytes_not_a_second_source_read(tmp_path,monkeypatch):
    st,config,_=service(tmp_path);original=config.read_bytes();read=Path.read_bytes;seen=[]
    def swapped(path):
        value=read(path)
        if path==config and not seen:
            seen.append(True);changed=json.loads(value);changed['capsules']=['swapped-v1'];config.write_text(json.dumps(changed))
        return value
    monkeypatch.setattr(Path,'read_bytes',swapped)
    strategies,sources=selected_sessions(st,AccountRegistry(st.registry_path).get('paper_owner'))
    assert strategies==['a-v1'] and sources[0]['sha256']==hashlib.sha256(original).hexdigest()
    with pytest.raises(HTTPException,match='configuration changed'):
        selected_sessions(st,AccountRegistry(st.registry_path).get('paper_owner'))

@pytest.mark.parametrize('forged',['dict','callback','transport_label','constructed_marker'])
def test_immediate_direct_helper_cannot_mint_gateway_authority(forged):
    from commander.account_lifecycle import _GatewayLifecycleAdmission
    service=NativeLifecycle.__new__(NativeLifecycle)
    service.st=NS(lifecycle_admission_verifier=None,lifecycle_transport_binding=None)
    args={'variant':'IMMEDIATE_DISCONNECT','_lifecycle_admission':{'label':'not an owner proof'}}
    if forged=='dict':args['_lifecycle_admission_guard']={'approved':True}
    elif forged=='callback':args['_lifecycle_admission_guard']=lambda:None
    elif forged=='transport_label':args['_lifecycle_admission_guard']='van-gateway'
    else:args['_lifecycle_admission_guard']=_GatewayLifecycleAdmission(args['_lifecycle_admission'],lambda:None,object())
    with pytest.raises(HTTPException,match='two-proof attestation required'):
        service.require_admission(args)

@pytest.mark.parametrize('corruption',['grace','deadline','phase','request','null_request'])
def test_immediate_lifecycle_data_corruption_holds_in_memory(corruption):
    from vati.accounts.lifecycle import validate_records
    row={'schema':'vati.account-lifecycle/1','alias':'paper_owner','operation_id':'controlled_original_00001','device_id':'source-device',
        'account_control_domain':'1'*64,'incarnation':'2'*64,'revision':2,'phase':'DISCONNECTED','created_at_unix':10,
        'archive_at_unix':None,'grace_seconds':None,'restore':None,'strategies':['a-v1'],'session_sources':[],
        'history_ref':'3'*64,'credential_disposition':'NONE','unlink_ref':'4'*64,'oauth_discard_ref':'5'*64,
        'original_request':{'alias':'paper_owner','variant':'IMMEDIATE_DISCONNECT','oauth_discard_digest':'5'*64},
        'detached':True,'link_intent':'RELINK_REQUIRED','remote_account_closed':False}
    assert validate_records({'paper_owner':row})['paper_owner']['phase']=='DISCONNECTED'
    if corruption=='grace':row['grace_seconds']=7
    elif corruption=='deadline':row['archive_at_unix']=17
    elif corruption=='phase':row['phase']='PENDING_ARCHIVE'
    elif corruption=='request':row['original_request']['grace_seconds']=None
    else:row['original_request']=None
    with pytest.raises(ValueError,match='HOLD'):validate_records({'paper_owner':row})


@pytest.mark.parametrize('waits',[1,2,3])
def test_final_source_binding_follows_all_current_authority_waits_in_memory(waits):
    from commander.account_lifecycle import _check_source_after_waits
    state={'source':0,'effects':0};events=[]
    def authority():
        events.append('authority');state['source']+=1
    def source():
        events.append('source')
        if state['source']!=0:raise HTTPException(409,'ordinary metadata source changed while authority waited')
    def final_effect():state['effects']+=1
    with pytest.raises(HTTPException,match='source changed'):
        _check_source_after_waits([authority]*waits,source,final_effect)
    assert events==['authority']*waits+['source'] and state['effects']==0
