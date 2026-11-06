"""Two real approval proofs -> native deletion -> cold retained cash HTTP read."""
import hashlib
import json
from dataclasses import replace
from contextlib import closing

import pytest
from httpx import ASGITransport,AsyncClient
from backend.tests.test_account_deletion_lifecycle import configure,deletion
from backend.tests.test_account_unlink_review import native_funds,client,_env,isolate
from commander.accounts import build_account_handlers
from vati.core import Ledger,EventKind,make_event
from vati.accounts import AccountRegistry
from vati.funding.mt5 import Mt5CashFact
from vati.funding.mt5_journal import Mt5FundingBook
from trading.tests.test_mt5_funding_contract import frame,cash


async def retained(client,tmp_path,monkeypatch,*,later_missing=False,later_bad_query=False,later_unattributed=False,later_valid_snapshot=False):
    ac,app,settings,config=await configure(client,tmp_path)
    _,secret,account=native_funds(tmp_path,monkeypatch)
    data=json.loads(config.read_text());data['account_alias']=account.alias;config.write_text(json.dumps(data))
    settings=replace(settings,lifecycle_session_sources=((str(config),hashlib.sha256(config.read_bytes()).hexdigest()),))
    app.state.onboarding.control.settings=settings
    app.state.onboarding.control.handlers=build_account_handlers(settings,retained_jobs=app.state.onboarding.control.retained_jobs)
    app.state.account_lifecycle.bind_local_admission_verifier()
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        f=replace(frame(),account_alias=account.alias,
            movements=tuple(Mt5CashFact.from_body(cash(native_id=i)) for i in range(1,104)))
        query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(f)
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':account.alias,
            'native_account_mark':f.mark_body(),'funding_observation':{'query_ref':query,'statement':receipt,'scope_hash':f.scope_hash}},
            event_time_ms=11000,received_time_ms=11000))
        if later_missing:
            ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':account.alias,
                'native_account_mark':f.mark_body(),'funding_observation':{'query_ref':'f'*64,'statement':receipt,'scope_hash':f.scope_hash}},
                event_time_ms=11001,received_time_ms=11001))
        if later_bad_query:
            from copy import deepcopy
            q=next(e for e in ledger.iter(EventKind.FUNDING_MT5_QUERY) if e.hash==query)
            bad=deepcopy(q.payload);bad['cash_statement_ref']='f'*64
            ledger.append(make_event(q.kind,q.producer,bad,event_time_ms=q.event_time_ms,received_time_ms=q.received_time_ms,correlation_id=q.correlation_id))
        if later_valid_snapshot:
            newer=replace(f,observed_at_ms=12000,source_nonce='later-original-snapshot',
                movements=(Mt5CashFact.from_body(cash(native_id=999)),))
            # Generate independently valid journal events before appending them after the unavailable lineage.
            with closing(Ledger(tmp_path/'independent-newer.sqlite')) as newer_ledger:
                later_query,later_receipt=Mt5FundingBook(newer_ledger,clock=lambda:12000).capture(newer)
                newer_events=[event for _,event,_,_ in newer_ledger.read_page(0,10)]
            for event in newer_events:ledger.append(event)
            ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':account.alias,
                'native_account_mark':newer.mark_body(),'funding_observation':{'query_ref':later_query,'statement':later_receipt,'scope_hash':newer.scope_hash}},
                event_time_ms=12000,received_time_ms=12000))
        if later_unattributed:
            ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':account.alias,
                'funding_observation':{'scope_hash':f.scope_hash,'statement':receipt}},event_time_ms=11002,received_time_ms=11002))
    body=await deletion(ac,alias=account.alias)
    response=await ac.post('/v1/trading/accounts/action',json=body)
    assert response.status_code==200 and response.json()['effect_state']=='APPLIED',response.text
    assert not secret.exists()
    operation=body['approval_proof']['challenge_id']
    return ac,app,settings,account,operation,receipt


@pytest.mark.asyncio
async def test_actual_original_native_owner_pages_after_destroyed_credentials_and_cold_restart(client,tmp_path,monkeypatch):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    before=AccountRegistry(settings.registry_path).path.read_bytes()
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:count=ledger.count()
    monkeypatch.setattr('vati.app.service.build_adapter',lambda *a,**k:pytest.fail('retained read attempted provider/credential access'))
    async def finish(headers=None):
        headers=dict(headers or {}); progress=0
        for _ in range(200):
            response=await ac.get(path,headers=headers)
            assert response.status_code==200,response.text
            value=response.json()
            if value['state']!='IN_PROGRESS':return response,progress
            progress+=1;headers['X-Van-History-Cursor']=value['next_cursor']
        pytest.fail('retained history failed to finish bounded work')
    first,progress=await finish();assert progress>=2
    data=first.json();assert data['state']=='OBSERVED' and data['movement_count'] is None
    assert data['statement_ref']==receipt['statement_ref'] and data['generation_provenance']=='UNKNOWN'
    assert data['execution_authority'] is False and data['truncated']
    assert first.headers['cache-control']=='no-store'
    assert all(text not in first.text for text in ('fixture.invalid','Broker-Demo','12345678','BRIDGE_SIGNING_KEY','credential_ref'))
    from vati.funding.retained_history import RetainedHistoryJobs
    app.state.onboarding.control.retained_jobs.close()
    app.state.onboarding.control.retained_jobs=RetainedHistoryJobs()
    app.state.onboarding.control.handlers=build_account_handlers(settings,retained_jobs=app.state.onboarding.control.retained_jobs)
    second,_=await finish({'X-Van-History-Cursor':data['next_cursor']})
    assert second.status_code==200,second.text
    assert [r['movement']['native_id'] for r in second.json()['movements']]==[101,102,103]
    assert second.json()['truncated'] is False
    restarted,_=await finish()
    assert restarted.json()==data
    assert AccountRegistry(settings.registry_path).path.read_bytes()==before
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:assert ledger.count()==count and ledger.verify_chain()[0]
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as unpaired:
        assert (await unpaired.get(path,headers={'X-Van-History-Cursor':data['next_cursor']})).status_code in {401,403}
    assert (await ac.get(path,headers={'X-Van-Account-Control-Domain':'f'*64})).status_code==409
    assert (await ac.get(path,headers={'X-Van-History-Limit':'101'})).status_code==422
    assert (await ac.get(path,params={'cursor':data['next_cursor']})).status_code==422


@pytest.mark.asyncio
async def test_paper_original_history_is_truthfully_unobserved_not_zero_or_permission(client,tmp_path):
    ac,app,settings,config=await configure(client,tmp_path)
    b=await deletion(ac);response=await ac.post('/v1/trading/accounts/action',json=b)
    assert response.json()['effect_state']=='APPLIED'
    path=f"/v1/trading/accounts/lifecycle/records/paper_owner/{b['approval_proof']['challenge_id']}/financial-history"
    response=await ac.get(path);assert response.status_code==200,response.text
    for _ in range(100):
        if response.json()['state']!='IN_PROGRESS':break
        response=await ac.get(path,headers={'X-Van-History-Cursor':response.json()['next_cursor']})
        assert response.status_code==200,response.text
    assert response.json()['state']=='UNOBSERVED' and response.json()['movements']==[]
    assert response.json()['return_qualification']=='NOT_ISSUED'


@pytest.mark.asyncio
async def test_later_missing_lineage_returns_verified_prefix_and_reconciliation_over_http(client,tmp_path,monkeypatch):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch,later_missing=True)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    headers={}
    for _ in range(200):
        response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
        data=response.json()
        if data['state']!='IN_PROGRESS':break
        headers['X-Van-History-Cursor']=data['next_cursor']
    assert data['state']=='RECONCILIATION_REQUIRED' and data['reason']=='ORIGINAL_LATER_LINEAGE_UNAVAILABLE'
    assert data['original_prefix_state']=='OBSERVED' and data['movement_count'] is None
    assert data['statement_ref']==receipt['statement_ref'] and len(data['movements'])==100
    assert data['execution_authority'] is False and data['truncated'] is True


@pytest.mark.asyncio
async def test_gateway_shutdown_drains_inflight_http_guard_without_blocking_event_loop(tmp_path,monkeypatch):
    import asyncio
    from backend.tests.test_trading_api import HDR, DEVICE_PEM, OWNER
    from van_gateway.app import create_app
    app=create_app();lifespan=app.router.lifespan_context(app);await lifespan.__aenter__()
    exited=False
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as ac:
            ticket=await ac.post('/v1/devices/pairing-ticket',json={'label':'test','ttl_seconds':600},headers=HDR)
            paired=await ac.post('/v1/devices/pair',json={'pairing_token':ticket.json()['pairing_token'],'device_id':'test-device',
                'device_secret':'test-device-secret','public_key_pem':DEVICE_PEM,'label':'test'})
            ac.headers.update({'X-Van-Ingress-Token':paired.json()['ingress_token'],'X-Van-Device-Token':paired.json()['device_access_token']})
            app.state.trading.owner_authority=OWNER.verifier
            ac,app,settings,account,operation,receipt=await retained((ac,app),tmp_path,monkeypatch)
            path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
            original_authorize=app.state.account_lifecycle.authorize
            entered=asyncio.Event();release=asyncio.Event();completed=asyncio.Event();calls=[0]
            async def gated(db,caller,write):
                calls[0]+=1
                if calls[0]==4:
                    entered.set();await release.wait()
                    try:return await original_authorize(db,caller,write)
                    finally:completed.set()
                return await original_authorize(db,caller,write)
            monkeypatch.setattr(app.state.account_lifecycle,'authorize',gated)
            request=asyncio.create_task(ac.get(path));await asyncio.wait_for(entered.wait(),5)
            manager=app.state.onboarding.control.retained_jobs
            shutdown=asyncio.create_task(lifespan.__aexit__(None,None,None))
            def wait_closed():
                with manager._condition:return manager._condition.wait_for(lambda:manager._closed,timeout=5)
            assert await asyncio.to_thread(wait_closed)
            assert not shutdown.done()
            release.set();await asyncio.wait_for(completed.wait(),5)
            response=await asyncio.wait_for(request,10)
            assert response.status_code in {403,409}
            await asyncio.wait_for(shutdown,10);exited=True
    finally:
        if not exited:await lifespan.__aexit__(None,None,None)


@pytest.mark.asyncio
async def test_signed_commander_preserves_original_history_job_across_http_calls(client,tmp_path,monkeypatch):
    import io
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from van_gateway.trading.accounts import CommanderAccountControl
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    token='owned-source-history-test-token-'*3
    token_file=tmp_path/'commander-token';token_file.write_text(token);token_file.chmod(0o600)
    native=TestClient(create_app(CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'vati.sqlite'),
        log_dir=str(tmp_path/'native-log'),units=(),account_control=settings)))
    calls=[]
    class Reply:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return self.data
    def signed_http(request,**kwargs):
        path=urlsplit(request.full_url).path
        response=native.post(path,content=request.data,headers=dict(request.header_items()));calls.append(path)
        if response.status_code>=400:raise HTTPError(request.full_url,response.status_code,'native refusal',{},io.BytesIO(response.content))
        return Reply(response.content)
    monkeypatch.setattr('van_gateway.trading.accounts.urlopen',signed_http)
    app.state.onboarding.control=CommanderAccountControl('https://native.fixture',str(token_file))
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    with native:
        headers={};progress=0
        for _ in range(200):
            response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
            data=response.json()
            if data['state']!='IN_PROGRESS':break
            progress+=1;headers['X-Van-History-Cursor']=data['next_cursor']
        assert progress>=2 and data['state']=='OBSERVED' and data['statement_ref']==receipt['statement_ref']
        assert data['movement_count'] is None and len(data['movements'])==100 and data['truncated']
        assert len([p for p in calls if p.endswith('/account_review')])>=3


@pytest.mark.asyncio
async def test_original_http_continuation_excludes_later_same_physical_activity(client,tmp_path,monkeypatch):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    first=await ac.get(path);assert first.status_code==200 and first.json()['state']=='IN_PROGRESS'
    headers={'X-Van-History-Cursor':first.json()['next_cursor']}
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        later=replace(frame(),account_alias=account.alias,observed_at_ms=12000,source_nonce='later-physical-activity',
            movements=(Mt5CashFact.from_body(cash(native_id=999)),))
        query,new_receipt=Mt5FundingBook(ledger,clock=lambda:13000).capture(later)
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':account.alias,
            'native_account_mark':later.mark_body(),'funding_observation':{'query_ref':query,'statement':new_receipt,'scope_hash':later.scope_hash}},
            event_time_ms=12000,received_time_ms=13000))
    observed=[];tokens=[]
    for _ in range(400):
        response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
        data=response.json()
        if data['state']=='IN_PROGRESS':headers['X-Van-History-Cursor']=data['next_cursor'];continue
        assert data['state']=='OBSERVED' and data['statement_ref']==receipt['statement_ref']
        observed.extend(row['movement']['native_id'] for row in data['movements'])
        if not data['truncated']:break
        headers['X-Van-History-Cursor']=data['next_cursor'];tokens.append(data['next_cursor'])
    assert observed==list(range(1,104)) and 999 not in observed and len(tokens)==1


@pytest.mark.asyncio
async def test_signed_commander_shutdown_drains_inflight_original_read(client,tmp_path,monkeypatch):
    import asyncio,io,threading
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from van_gateway.trading.accounts import CommanderAccountControl
    from vati.funding.retained_history import RetainedHistoryJobs,RetainedHistoryReadJob
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    token='owned-source-shutdown-test-token-'*3
    token_file=tmp_path/'native-shutdown-token';token_file.write_text(token);token_file.chmod(0o600)
    native=TestClient(create_app(CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'vati.sqlite'),
        log_dir=str(tmp_path/'native-log'),units=(),account_control=settings)))
    class Reply:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return self.data
    def signed_http(request,**kwargs):
        path=urlsplit(request.full_url).path
        response=native.post(path,content=request.data,headers=dict(request.header_items()))
        if response.status_code>=400:raise HTTPError(request.full_url,response.status_code,'native refusal',{},io.BytesIO(response.content))
        return Reply(response.content)
    monkeypatch.setattr('van_gateway.trading.accounts.urlopen',signed_http)
    app.state.onboarding.control=CommanderAccountControl('https://native.fixture',str(token_file))
    entered=threading.Event();release=threading.Event();closing=threading.Event()
    original_advance=RetainedHistoryReadJob.advance;original_close=RetainedHistoryJobs.close
    def blocked_advance(self,*args,**kwargs):
        entered.set();assert release.wait(8)
        return original_advance(self,*args,**kwargs)
    def notify_close(self):closing.set();return original_close(self)
    monkeypatch.setattr(RetainedHistoryReadJob,'advance',blocked_advance)
    monkeypatch.setattr(RetainedHistoryJobs,'close',notify_close)
    native.__enter__();exited=False
    try:
        path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
        request=asyncio.create_task(ac.get(path));assert await asyncio.to_thread(entered.wait,5)
        shutdown=asyncio.create_task(asyncio.to_thread(native.__exit__,None,None,None))
        assert await asyncio.to_thread(closing.wait,5) and not shutdown.done()
        release.set();response=await asyncio.wait_for(request,10)
        assert response.status_code in {403,409,503}
        await asyncio.wait_for(shutdown,10);exited=True
    finally:
        release.set()
        if not exited:await asyncio.to_thread(native.__exit__,None,None,None)


@pytest.mark.asyncio
async def test_revoked_device_is_checked_before_signed_commander_history_advance(client,tmp_path,monkeypatch):
    import io,time
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from fastapi.testclient import TestClient
    from commander.app import CommanderSettings,create_app
    from van_gateway.trading.accounts import CommanderAccountControl
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    token='owned-history-revocation-test-token-'*3
    token_file=tmp_path/'native-revocation-token';token_file.write_text(token);token_file.chmod(0o600)
    native=TestClient(create_app(CommanderSettings(tokens={'van-gateway':token},ledger=str(tmp_path/'vati.sqlite'),
        log_dir=str(tmp_path/'native-log'),units=(),account_control=settings)))
    calls=[]
    class Reply:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return self.data
    def signed_http(request,**kwargs):
        path=urlsplit(request.full_url).path;calls.append(path)
        response=native.post(path,content=request.data,headers=dict(request.header_items()))
        if response.status_code>=400:raise HTTPError(request.full_url,response.status_code,'native refusal',{},io.BytesIO(response.content))
        return Reply(response.content)
    monkeypatch.setattr('van_gateway.trading.accounts.urlopen',signed_http)
    app.state.onboarding.control=CommanderAccountControl('https://native.fixture',str(token_file))
    original_context=app.state.account_lifecycle.read_context
    async def revoke_after_context(request):
        result=await original_context(request)
        async with app.state.store.connection() as db:
            await db.execute('UPDATE devices SET revoked_at_unix=? WHERE device_id=?',(int(time.time()),'test-device'))
            await db.commit()
        return result
    monkeypatch.setattr(app.state.account_lifecycle,'read_context',revoke_after_context)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    with native:
        response=await ac.get(path)
        assert response.status_code==403,response.text
        assert not any(path.endswith('/account_review') for path in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['later_bad_query','later_unattributed'])
async def test_original_http_prefix_survives_later_unproven_native_lineage(client,tmp_path,monkeypatch,fault):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch,**{fault:True})
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history';headers={}
    for _ in range(300):
        response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
        data=response.json()
        if data['state']!='IN_PROGRESS':break
        headers['X-Van-History-Cursor']=data['next_cursor']
    assert data['state']=='RECONCILIATION_REQUIRED' and data['reason']=='ORIGINAL_LATER_LINEAGE_UNAVAILABLE'
    assert data['original_prefix_state']=='OBSERVED' and data['movement_count'] is None
    assert data['statement_ref']==receipt['statement_ref'] and len(data['movements'])==100
    assert data['execution_authority'] is False and data['truncated']


@pytest.mark.asyncio
async def test_original_http_gap_never_promotes_later_valid_snapshot(client,tmp_path,monkeypatch):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch,later_bad_query=True,later_valid_snapshot=True)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history';headers={};rows=[]
    for _ in range(500):
        response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
        data=response.json()
        if data['state']=='IN_PROGRESS':headers['X-Van-History-Cursor']=data['next_cursor'];continue
        assert data['state']=='RECONCILIATION_REQUIRED' and data['reason']=='ORIGINAL_LATER_LINEAGE_UNAVAILABLE'
        assert data['original_prefix_state']=='OBSERVED' and data['movement_count'] is None
        assert data['statement_ref']==receipt['statement_ref'] and data['execution_authority'] is False
        rows.extend(row['movement']['native_id'] for row in data['movements'])
        if not data['truncated']:break
        headers['X-Van-History-Cursor']=data['next_cursor']
    else:pytest.fail('retained history did not complete')
    assert rows==list(range(1,104)) and 999 not in rows


@pytest.mark.asyncio
async def test_real_gateway_all_history_collections_finish_with_bounded_continuations(client,tmp_path,monkeypatch):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    fields={'MOVEMENTS':'movements','COVERAGE':'coverage_windows','CONFLICT':'conflicts'}; results={}
    for collection,field in fields.items():
        headers={'X-Van-History-Collection':collection,'X-Van-History-Limit':'37'};rows=[]
        for _ in range(1000):
            response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
            data=response.json();assert data['collection']==collection
            if data['state']=='IN_PROGRESS':headers['X-Van-History-Cursor']=data['next_cursor'];continue
            assert data['state']=='OBSERVED' and data['movement_count'] is None and data['execution_authority'] is False
            rows.extend(data[field])
            if not data['truncated']:break
            headers['X-Van-History-Cursor']=data['next_cursor']
        else:pytest.fail('collection did not finish bounded continuations')
        results[collection]=rows
    assert [row['movement']['native_id'] for row in results['MOVEMENTS']]==list(range(1,104))
    assert any(row['statement_ref']==receipt['statement_ref'] for row in results['COVERAGE'])
    assert results['CONFLICT']==[]


@pytest.mark.asyncio
async def test_relinked_same_alias_never_extends_original_http_history(client,tmp_path,monkeypatch):
    ac,app,settings,account,operation,receipt=await retained(client,tmp_path,monkeypatch)
    path=f'/v1/trading/accounts/lifecycle/records/{account.alias}/{operation}/financial-history'
    first=await ac.get(path);assert first.status_code==200 and first.json()['state']=='IN_PROGRESS'
    headers={'X-Van-History-Cursor':first.json()['next_cursor']}
    registry=AccountRegistry(settings.registry_path);assert account.alias not in registry.accounts
    registry.add(account)
    assert AccountRegistry(settings.registry_path).get(account.alias).login==account.login
    with closing(Ledger(tmp_path/'vati.sqlite')) as ledger:
        later=replace(frame(),account_alias=account.alias,observed_at_ms=12000,source_nonce='relinked-account-activity',
            movements=(Mt5CashFact.from_body(cash(native_id=999)),))
        query,later_receipt=Mt5FundingBook(ledger,clock=lambda:13000).capture(later)
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':account.alias,'native_account_mark':later.mark_body(),
            'funding_observation':{'query_ref':query,'statement':later_receipt,'scope_hash':later.scope_hash}},event_time_ms=12000,received_time_ms=13000))
    rows=[]
    for _ in range(500):
        response=await ac.get(path,headers=headers);assert response.status_code==200,response.text
        data=response.json()
        if data['state']=='IN_PROGRESS':headers['X-Van-History-Cursor']=data['next_cursor'];continue
        assert data['state']=='OBSERVED' and data['statement_ref']==receipt['statement_ref'] and data['movement_count'] is None
        rows.extend(row['movement']['native_id'] for row in data['movements'])
        if not data['truncated']:break
        headers['X-Van-History-Cursor']=data['next_cursor']
    else:pytest.fail('original history did not finish')
    assert rows==list(range(1,104)) and 999 not in rows
