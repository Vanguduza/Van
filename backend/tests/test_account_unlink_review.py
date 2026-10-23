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
        rows=[e for e in ledger.iter(EventKind.ACCOUNT_OPERATION) if e.payload['intent']['command']=='account_remove']
        assert len(rows)==2 and [e.payload['phase'] for e in rows]==['IN_FLIGHT','APPLIED']
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
