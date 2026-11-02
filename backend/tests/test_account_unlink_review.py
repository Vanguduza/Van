"""Paired device -> P256 review -> actual native journal/local unlink/readback."""
import time
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest
from test_trading_api import client,_env
from test_account_update_review import isolate,challenge
from test_trading_oauth_scope import act
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.account_lease import AccountRuntimeLease
from vati.app.sqlite_lease import SQLiteLeaseStore
from vati.core import Ledger,EventKind
from vati.core.canonical import canonical_hash
from commander.accounts import _write_secrets
from vati.execution.base import AccountState,Health


async def paper(ac):
    response=await act(ac,'account_upsert',{'alias':'paper_owner','broker':'PAPER'})
    assert response.status_code==200,response.text


def native_funds(tmp_path,monkeypatch):
    path=tmp_path/'secrets'/'fx_primary.env';_write_secrets(path,{'BRIDGE_SIGNING_KEY':'isolated-fixture-only'})
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account('fx_primary','MT5','OBSERVE','USD',login='12345678',server='Broker-Demo',
        bridge_url='https://fixture.invalid:9443',credential_ref=CredentialRef(secrets_file=str(path))))
    Ledger(str(tmp_path/'vati.sqlite')).close();view={'balance':D('100.25')}
    adapter=NS(sync_account=lambda:AccountState('fx_primary',view['balance'],view['balance'],'USD',True,
            server_time_unix_ms=int(time.time()*1000)),positions=lambda:[],orders=lambda:[],
        heartbeat=lambda **kw:Health(True,0,kw['now_ms']))
    monkeypatch.setattr('vati.app.service.build_adapter',lambda *a,**k:adapter)
    return view,path,account


@pytest.mark.asyncio
async def test_signed_unlink_keeps_native_history_and_never_reports_broker_closure(client,tmp_path):
    ac,app=client;await paper(ac)
    body,issued=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    review=issued['resolved_review']
    assert review['after'] is None and review['before']['alias']=='paper_owner'
    assert review['retirement']['remote_account_closed'] is False
    assert review['retirement']['retained_remote_funds'] is None
    assert review['review_digest']==canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==200,response.text
    result=response.json();assert result['effect_state']=='APPLIED' and result['removed'] is True
    assert result['remote_account_closed'] is False and result['historical_data_retained'] is True
    assert 'paper_owner' not in AccountRegistry(tmp_path/'accounts.json').accounts
    status=await ac.get('/v1/trading/accounts/operations/'+result['operation_id'])
    assert status.status_code==200 and status.json()['effect_state']=='APPLIED',status.text
    assert status.json()['result']['remote_account_closed'] is False
    ledger=Ledger(str(tmp_path/'vati.sqlite'))
    try:
        assert ledger.verify_chain()[0]
        from commander.account_effects import AccountEffectJournal
        rows=[e for e in AccountEffectJournal(ledger).business_events() if e.payload['intent']['command']=='account_remove']
        assert len(rows)==2 and [e.payload['phase'] for e in rows]==['IN_FLIGHT','APPLIED']
        internal=[e for e in ledger.iter(EventKind.ACCOUNT_OPERATION) if AccountEffectJournal.internal_namespace_metadata(e)]
        assert len(internal)==1 and 'phase' not in internal[0].payload and 'intent' not in internal[0].payload
    finally:ledger.close()


@pytest.mark.asyncio
async def test_lost_native_reply_after_unlink_is_recovered_by_original_read_without_repetition(client,tmp_path,monkeypatch):
    ac,app=client;await paper(ac)
    body,_=await challenge(ac,'account_remove',{'alias':'paper_owner'});native=app.state.onboarding.control.run
    def lost_reply(command,args):
        result=native(command,args)
        if command=='account_remove':raise ConnectionError('induced lost native completion reply')
        return result
    monkeypatch.setattr(app.state.onboarding.control,'run',lost_reply)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==409 and response.json()['effect_state']=='UNKNOWN',response.text
    assert 'paper_owner' not in AccountRegistry(tmp_path/'accounts.json').accounts
    status=await ac.get('/v1/trading/accounts/operations/'+response.json()['operation_id'])
    assert status.status_code==200 and status.json()['effect_state']=='APPLIED',status.text
    assert status.json()['result']['historical_data_retained'] is True


@pytest.mark.asyncio
async def test_active_runtime_refuses_unlink_before_an_owner_challenge_is_issued(client,tmp_path):
    ac,app=client;await paper(ac)
    store=SQLiteLeaseStore(tmp_path/'vati.sqlite')
    lease=AccountRuntimeLease(store,account_alias='paper_owner',instance_id='actual-running-runtime')
    assert lease.acquire().permits_orders
    try:
        response=await act(ac,'account_remove',{'alias':'paper_owner'},expected_challenge_status=409)
        assert 'runtime' in response.json()['detail'].lower()
        assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
    finally:lease.release();store.close()


@pytest.mark.asyncio
async def test_runtime_starting_after_proof_is_consumed_refuses_original_without_shredding(client,tmp_path,monkeypatch):
    ac,app=client;await paper(ac);body,_=await challenge(ac,'account_remove',{'alias':'paper_owner'})
    store=SQLiteLeaseStore(tmp_path/'vati.sqlite');lease=AccountRuntimeLease(store,account_alias='paper_owner',instance_id='raced-runtime')
    native=app.state.onboarding.control.run
    def raced(command,args):
        if command=='account_remove':assert lease.acquire().permits_orders
        return native(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',raced)
    try:
        response=await ac.post('/v1/trading/accounts/action',json=body)
        assert response.status_code==409 and response.json()['effect_state']=='REFUSED',response.text
        assert AccountRegistry(tmp_path/'accounts.json').get('paper_owner')
        status=await ac.get('/v1/trading/accounts/operations/'+body['approval_proof']['challenge_id'])
        assert status.status_code==200 and status.json()['effect_state']=='REFUSED',status.text
    finally:lease.release();store.close()


@pytest.mark.asyncio
async def test_catalog_requires_the_same_native_review_for_local_unlink(client):
    ac,_=client;catalog=(await ac.get('/v1/trading/accounts/catalog')).json()
    item=next(r for r in catalog['actions'] if r['action']=='account_remove')
    assert item['requires_resolved_review'] is True and item['requires_owner_approval'] is True


@pytest.mark.asyncio
async def test_exact_nonzero_native_funds_are_in_the_signed_owner_review(client,tmp_path,monkeypatch):
    ac,app=client;view,path,account=native_funds(tmp_path,monkeypatch)
    body,issued=await challenge(ac,'account_remove',{'alias':account.alias})
    assert issued['resolved_review']['retirement']['retained_remote_funds']=={'balance':'100.25','equity':'100.25','currency':'USD'}
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==200,response.text
    assert response.json()['retained_remote_funds']['balance']=='100.25'
    assert response.json()['remote_account_closed'] is False and not path.exists()


@pytest.mark.asyncio
async def test_native_funds_changing_after_gateway_preflight_requires_fresh_review(client,tmp_path,monkeypatch):
    ac,app=client;view,path,account=native_funds(tmp_path,monkeypatch)
    body,_=await challenge(ac,'account_remove',{'alias':account.alias});before=path.read_bytes()
    native=app.state.onboarding.control.run
    def changed(command,args):
        if command=='account_remove':view['balance']+=D('1')
        return native(command,args)
    monkeypatch.setattr(app.state.onboarding.control,'run',changed)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==409 and response.json()['effect_state']=='REFUSED',response.text
    assert path.read_bytes()==before and AccountRegistry(tmp_path/'accounts.json').get(account.alias)==account


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('remote_account_closed',True),('retained_remote_funds',None)])
async def test_incomplete_or_broker_closing_native_review_is_refused_before_signature(client,tmp_path,monkeypatch,field,value):
    ac,app=client;native_funds(tmp_path,monkeypatch);native=app.state.onboarding.control.review
    def broken(action,args):
        review=native(action,args);review['retirement'][field]=value
        review['review_digest']=canonical_hash({k:v for k,v in review.items() if k!='review_digest'})
        return review
    monkeypatch.setattr(app.state.onboarding.control,'review',broken)
    response=await act(ac,'account_remove',{'alias':'fx_primary'},expected_challenge_status=409)
    assert response.status_code==409


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['resolution','fsync','namespace','version','readback_age','future_clock','lease'])
async def test_final_unlink_writer_rechecks_original_scope_and_fresh_native_facts(client,tmp_path,monkeypatch,fault):
    import os
    from dataclasses import replace
    import commander.accounts as native
    import commander.account_effects as effects
    import commander.account_retirement as retirement
    import vati.accounts.registry as storage
    ac,app=client;view,secret,account=native_funds(tmp_path,monkeypatch)
    body,issued=await challenge(ac,'account_remove',{'alias':account.alias})
    identity=body['approval_proof']['challenge_id'];expiry=issued['approval_expires_at_unix']
    path=tmp_path/'accounts.json';before=path.read_bytes();secret_before=secret.read_bytes();version=app.state.onboarding.control.resource_version(account.alias)['resource_version']
    clock=[int(time.time())];offset=[0];seen=[]
    monkeypatch.setattr(effects,'time',NS(time=lambda:clock[0]))
    monkeypatch.setattr(retirement,'time',NS(time=lambda:time.time()+offset[0]))
    if fault=='readback_age':
        adapter=NS(sync_account=lambda:AccountState(account.alias,view['balance'],view['balance'],'USD',True,server_time_unix_ms=int(time.time()*1000)),
            positions=lambda:[],orders=lambda:[],heartbeat=lambda **kw:Health(True,0,kw['now_ms']-29999))
        monkeypatch.setattr('vati.app.service.build_adapter',lambda *a,**k:adapter)
    if fault=='resolution':
        inspect=retirement.inspect_retirement
        def delayed(*a,**kw):
            value=inspect(*a,**kw)
            if effects._effect_started.get() is not None:clock[0]=expiry;seen.append(True)
            return value
        monkeypatch.setattr(retirement,'inspect_retirement',delayed)
    fsync=storage.os.fsync
    def delayed_fsync(fd):
        fsync(fd);marker=effects._effect_started.get()
        if marker is None or marker[1].command!='account_remove' or '.accounts.json.' not in os.readlink('/proc/self/fd/'+str(fd)):return
        if seen:return
        seen.append(True);assert marker[0] is False
        if fault=='fsync':clock[0]=expiry
        elif fault=='namespace':(tmp_path/'secrets/.account-control-domain.env').write_text('owned-current-namespace-malformed')
        elif fault=='version':
            writer=AccountRegistry(path);writer.replace(replace(writer.get(account.alias),label='Concurrent owner edit'))
        elif fault=='readback_age':offset[0]=.01
        elif fault=='future_clock':offset[0]=-60
        elif fault=='lease':
            store=SQLiteLeaseStore(tmp_path/'vati.sqlite')
            try:
                held=store.read(account.alias);assert held is not None
                assert store.write_if(held,replace(held,expires_at_ms=int(time.time()*1000)-1))
            finally:store.close()
    monkeypatch.setattr(storage.os,'fsync',delayed_fsync)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert seen and result.status_code==(403 if fault in {'resolution','fsync'} else 409),result.text
    assert secret.read_bytes()==secret_before
    if fault=='version':assert AccountRegistry(path).get(account.alias).label=='Concurrent owner edit'
    else:
        assert path.read_bytes()==before
        # Corrupt namespace is a deliberate test fault; the registry generation
        # itself is unchanged and must not be inferred through that bad scope.
        if fault!='namespace':assert app.state.onboarding.control.resource_version(account.alias)['resource_version']==version
    ledger=Ledger(tmp_path/'vati.sqlite')
    from commander.account_effects import AccountEffectJournal
    try:state=AccountEffectJournal(ledger).status(identity,'test-device')
    finally:ledger.close()
    assert state.phase=='REFUSED'
    if fault!='namespace':
        original=await ac.get('/v1/trading/accounts/operations/'+identity)
        assert original.json()['effect_state']=='REFUSED' and not original.json()['reconciliation_required']
    assert list(tmp_path.glob('.accounts.json.*.tmp'))==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['before_shred','before_shred_missing','after_overwrite_expiry','after_overwrite_io'])
async def test_partial_unlink_stays_original_unknown_without_cleanup_or_resend_authority(client,tmp_path,monkeypatch,fault):
    import os
    import commander.accounts as native
    import commander.account_effects as effects
    ac,app=client;_,secret,account=native_funds(tmp_path,monkeypatch)
    body,issued=await challenge(ac,'account_remove',{'alias':account.alias});identity=body['approval_proof']['challenge_id']
    before=secret.read_bytes();clock=[int(time.time())];calls=[];shred=native._shred
    monkeypatch.setattr(effects,'time',NS(time=lambda:clock[0]))
    def observed(path,**kw):
        calls.append(True)
        if fault=='before_shred':clock[0]=issued['approval_expires_at_unix']
        elif fault=='before_shred_missing':path.unlink()
        return shred(path,**kw)
    monkeypatch.setattr(native,'_shred',observed);fsync=os.fsync
    def delayed(fd):
        fsync(fd);marker=effects._effect_started.get()
        if marker is not None and marker[1].command=='account_remove' and os.readlink('/proc/self/fd/'+str(fd))==str(secret):
            if fault=='after_overwrite_expiry':clock[0]=issued['approval_expires_at_unix']
            elif fault=='after_overwrite_io':raise OSError('owned interrupted credential flush')
    monkeypatch.setattr(native.os,'fsync',delayed)
    result=await ac.post('/v1/trading/accounts/action',json=body)
    assert result.status_code==409 and result.json()['effect_state']=='UNKNOWN',result.text
    assert len(calls)==1 and account.alias not in AccountRegistry(tmp_path/'accounts.json').accounts
    if fault=='before_shred_missing':assert not secret.exists()
    else:
        assert secret.exists()
        assert (secret.read_bytes()==before)==(fault=='before_shred')
    for _ in range(2):
        original=await ac.get('/v1/trading/accounts/operations/'+identity)
        assert original.status_code==200 and original.json()['effect_state']=='UNKNOWN'
        assert original.json()['operation_id']==identity and original.json()['result'] is None
    assert len(calls)==1
    clock[0]=int(time.time())
    blocked=await act(ac,'account_upsert',{'alias':account.alias,'broker':'MT5','server':'Broker-Demo','login':'12345678'})
    assert blocked.status_code==409 and len(calls)==1
    assert (await act(ac,'account_upsert',{'alias':'disjoint_owner','broker':'PAPER'})).status_code==200
    # SOURCE observations are separate from the original UNKNOWN receipt and
    # confer no authority to finish the still-pending shred after restart.
    from pathlib import Path
    import json
    Path('/tmp/van-be004-unlink-r1-partial-'+fault+'-'+tmp_path.parent.name+'-observation-20261101.json').write_text(json.dumps({
        'kind':'CURRENT_SOURCE_OBSERVATION_NOT_ORIGINAL_COMPLETION_OR_AUTHORITY','observed_at_unix':int(time.time()),
        'operation_id':identity,'registry_alias_absent':True,'managed_file_present':secret.exists(),
        'file_unchanged':secret.read_bytes()==before if secret.exists() else None,'original_phase':'UNKNOWN','original_result':None,
        'cleanup_authority_or_resend':False,'cold_fixture':str(tmp_path)},indent=2))
