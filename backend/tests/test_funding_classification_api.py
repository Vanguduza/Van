"""Actual paired HTTP -> Auth writer -> existing SQLite Ledger, no provider effects."""
import asyncio
from contextlib import closing,contextmanager
import hashlib
import json
import threading

import pytest
import pytest_asyncio
from httpx import ASGITransport,AsyncClient
from test_device_proof_enforcement import _settings,_paired,_base_headers,_bind,_proof_headers
from test_funding_classification_journal import original
from van_gateway.app import create_app
from van_gateway.context.forget import OwnerMemory
from vati.core.ledger import Ledger
from vati.core.events import EventKind

PATH='/v1/trading/funding/classifications'

@pytest_asyncio.fixture
async def label_client(_settings,tmp_path):
    path=tmp_path/'funding.sqlite';statement,body=original(path)
    app=create_app();await app.state.store.migrate();device=await _paired(app)
    app.state.trading.ledger_path=str(path)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as ac:
        yield ac,app,device,statement,body,path
    assert not app.state.funding_classifications.tasks

async def post(client,body=None,key=None):
    ac,app,device,statement,default,path=client;body=body or default
    headers=_base_headers(device)
    if key:
        raw=json.dumps(body).encode();headers.update(_proof_headers(key,method='POST',path=PATH,device_id=device.device.device_id,body=raw));headers['Content-Type']='application/json'
        return await ac.post(PATH,content=raw,headers=headers)
    return await ac.post(PATH,json=body,headers=headers)

@pytest.mark.asyncio
async def test_paired_http_complete_lifecycle_independent_readback_and_retention_disclosure(label_client):
    ac,app,device,statement,body,path=label_client
    result=await post(label_client);assert result.status_code==200,result.text
    receipt=result.json();assert receipt['state']=='ASSERTED'
    read=await ac.get(PATH+'/'+body['operation_id'],headers=_base_headers(device))
    assert read.status_code==200 and read.json()['receipt']==receipt
    assert read.headers['cache-control']=='no-store'
    assert (await post(label_client)).json()==receipt
    corrected=body|{'operation_id':'correct_http_00002','expected_revision':1,'label':'FEE'}
    assert (await post(label_client,corrected)).status_code==200
    withdrawal=body|{'operation_id':'withdraw_http_0003','expected_revision':2,'action':'WITHDRAW','label':None}
    assert (await post(label_client,withdrawal)).json()['state']=='WITHDRAWN'
    from vati.funding.classification_journal import ClassificationBook
    with closing(Ledger(path)) as ledger:
        assert ClassificationBook(ledger).lookup(body['operation_id'])['receipt']==receipt
        assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==3
        assert ledger.count(EventKind.FINANCIAL_MOVEMENT)==0
    inventory=await OwnerMemory(app.state.store).inventory()
    assert 'funding_owner_classifications' in inventory['kept_deliberately']
    await OwnerMemory(app.state.store).forget_all()
    assert (await ac.get(PATH+'/'+body['operation_id'],headers=_base_headers(device))).json()['receipt']==receipt
    assert not await app.state.store.fetchall('SELECT * FROM missions')

@pytest.mark.asyncio
async def test_current_real_bound_proof_required_valid_and_single_use(label_client):
    ac,app,device,statement,body,path=label_client
    key=await _bind(app,device.device.device_id)
    assert (await post(label_client)).status_code==401
    raw=json.dumps(body).encode();headers={**_base_headers(device),**_proof_headers(key,method='POST',path=PATH,device_id=device.device.device_id,body=raw),'Content-Type':'application/json'}
    result=await ac.post(PATH,content=raw,headers=headers);assert result.status_code==200,result.text
    assert (await ac.post(PATH,content=raw,headers=headers)).status_code==401
    assert (await ac.get(PATH+'/'+body['operation_id'],headers=_base_headers(device))).status_code==200

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('owner_id','foreign'),('password','secret-value'),('delta','9.0'),('profile_id','fake'),('expires_at_ms',999999999),('label','private-note')])
async def test_unknown_secret_or_source_override_fields_not_retained(label_client,field,value):
    result=await post(label_client,label_client[4]|{field:value})
    assert result.status_code==422 and str(value) not in result.text
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==0

@pytest.mark.asyncio
async def test_duplicate_and_oversized_input_never_echoed(label_client):
    ac,app,device,_,body,path=label_client
    for raw,status in [(json.dumps(body)[:-1]+',"label":"FEE"}',422),('{"password":"'+'private-'*1000+'"}',413),('[]',422)]:
        r=await ac.post(PATH,content=raw,headers={**_base_headers(device),'Content-Type':'application/json'})
        assert r.status_code==status and 'private-' not in r.text

@pytest.mark.asyncio
async def test_same_id_parallel_http_exactly_one_event(label_client):
    results=await asyncio.gather(post(label_client),post(label_client))
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert results[0].json()==results[1].json()
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==1

@pytest.mark.asyncio
async def test_actual_commit_ack_loss_resolves_original_not_replacement(label_client,monkeypatch):
    app=label_client[1];open_original=app.state.trading._open;lost=False
    def opened():
        nonlocal lost
        kind,make,ledger=open_original();atomic=ledger.atomic
        @contextmanager
        def ack():
            nonlocal lost
            outer=not ledger._conn.in_transaction
            with atomic() as tx:yield tx
            if outer and not lost and ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION):
                lost=True;raise OSError('fixture secret ACK')
        ledger.atomic=ack;return kind,make,ledger
    monkeypatch.setattr(app.state.trading,'_open',opened)
    result=await post(label_client)
    assert lost and result.status_code==200,result.text
    assert (await post(label_client)).json()==result.json()
    with closing(Ledger(label_client[5])) as ledger:assert ledger.count(EventKind.FUNDING_OWNER_CLASSIFICATION)==1


@pytest.mark.asyncio
async def test_real_original_http_accounts_read_selection_to_assertion_to_owner_report(label_client,tmp_path,monkeypatch):
    from test_funding_runtime import setup
    from test_funding_owner_reports import profile,snapshot
    from vati.funding.runtime import capture_funding
    from vati.core.canonical import canonical_hash
    ac,app,device,_,_,_=label_client
    source=tmp_path/'source';source.mkdir()
    ledger,transport,adapter=setup(source)
    with closing(ledger):
        observation=capture_funding(ledger,adapter,adapter.sync_account(),now_ms=3000)
        snapshot(ledger,funding_observation=observation)
    registry=tmp_path/'accounts.json'
    registry.write_text(json.dumps({'schema_version':1,'accounts':[profile()|{'credential_ref':{'env_var':'FIXTURE_NOT_RESOLVED'}}]}))
    app.state.trading.accounts_registry=str(registry);app.state.trading.ledger_path=str(source/'facts.sqlite')
    import van_gateway.trading.service as service_module
    from types import SimpleNamespace
    monkeypatch.setattr(service_module,'time',SimpleNamespace(time=lambda:3))  # fixed report as-of, not Auth clock
    before=await ac.get('/v1/trading/accounts',headers=_base_headers(device))
    assert before.status_code==200,before.text
    funding=before.json()['accounts'][0]['funding'];row=funding['movements'][0]
    body={'operation_id':'native_http_label_0001','scope_hash':funding['scope_hash'],'native_id':row['movement']['native_id'],
          'statement_ref':row['original_statement_ref'],'row_digest':canonical_hash(row['movement']),
          'expected_revision':0,'action':'SET','label':'FEE'}
    receipt=await post(label_client,body);assert receipt.status_code==200,receipt.text
    after=await ac.get('/v1/trading/accounts',headers=_base_headers(device));assert after.status_code==200
    a=after.json()['accounts'][0];b=before.json()['accounts'][0]
    overlay=a['funding'].pop('owner_classification');b['funding'].pop('owner_classification')
    assert a==b
    assert overlay['assertions'][0]['receipt']==receipt.json()
    assert overlay['descriptive_totals'][0]['delta']==row['movement']['delta']
    assert not any(name in {'ProtoOANewOrderReq','ProtoOAWithdrawReq'} for name,_ in transport.requests)
