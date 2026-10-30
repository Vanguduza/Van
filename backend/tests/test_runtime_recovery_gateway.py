"""Paired gateway + A4 CryptoObject + signed Commander + actual session.

Only transport is in-process. Both authenticated HTTP applications, native
SQLite journal/lease, real P256 signatures and the running actor are exercised.
"""
import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from test_trading_api import client, _env, DEVICE_KEY, _approval_proof
from test_single_session_lease import config
from conftest import mandate_dict, owner_authority
from commander.app import create_app as commander_app, CommanderSettings
from commander.auth import sign_headers
from vati.app.service import SessionService
from vati.core import EventKind
from vati.risk.contracts import SymbolContract, KillSwitchTrigger

BASE = '/v1/trading/runtime/recovery'
GATEWAY_TOKEN = 'g'*40
HERMES_TOKEN = 'h'*40


@pytest.fixture
def session_control(client, tmp_path, monkeypatch):
    _, app = client
    from decimal import Decimal as D
    contract = SymbolContract(symbol='EURUSD', venue='paper', base_currency='EUR', quote_currency='USD',
        account_currency='USD', contract_size=D('100000'), tick_size=D('0.00001'), tick_value=D('1'),
        volume_min=D('0.01'), volume_step=D('0.01'), volume_max=D('100'), min_stop_distance=D('0.00030'))
    cfg = config(tmp_path, contract)
    now = int(time.time())
    policy_keys = tmp_path/'policy-keys.json'
    from conftest_owner_authority import OWNER_KEY_ID
    policy_keys.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}))
    monkeypatch.setenv('VAN_OWNER_AUTHORITY_KEYS', str(policy_keys))
    cfg.mandate = mandate_dict(account_alias=cfg.account_alias, venue='paper', mode='DEMO_TRADER',
        allowed_strategies=['FX-TREND-PULLBACK-01'], signed_at_unix=now-1, expires_at_unix=now+86400)
    cfg.owner_authority_keys = str(tmp_path/'native-owner.json')
    cfg.heartbeat_path = str(tmp_path/'heartbeats'/'current.json')
    Path(cfg.heartbeat_path).parent.mkdir()
    service = SessionService(cfg, lambda now: []).build(); service.start()
    service.runner.authority = owner_authority().verifier
    service.runner.owner_halt(now_ms=service.clock(), owner_signature_ref=owner_authority().token(
        act='owner-halt', subject=service.runner.cycle.cfg.session_id))
    service._heartbeat('RUNNING')
    settings = CommanderSettings(tokens={'van-gateway':GATEWAY_TOKEN,'hermes':HERMES_TOKEN},
        ledger=cfg.ledger, heartbeat_dir=str(Path(cfg.heartbeat_path).parent),
        owner_authority_keys=cfg.owner_authority_keys, accounts_registry=cfg.registry_path,
        log_dir=str(tmp_path/'logs'), secrets_dir=str(tmp_path/'secrets'))
    native = TestClient(commander_app(settings))
    class NativeTransport:
        calls = []
        lose_after_enqueue = False
        fail_before_enqueue = False
        def run(self, name, args):
            self.calls.append(name)
            if name=='runtime_recovery_request' and self.fail_before_enqueue:
                self.fail_before_enqueue = False
                raise HTTPException(502, 'fixture lost connection before native enqueue')
            body = json.dumps({'args':args, 'requested_by':'van-gateway'}).encode()
            path = '/v1/cmd/'+name
            response = native.post(path, content=body, headers={**sign_headers(GATEWAY_TOKEN,'POST',path,body),
                'Content-Type':'application/json'})
            if response.status_code >= 400:
                raise HTTPException(response.status_code, response.json()['detail'])
            if name=='runtime_recovery_request' and self.lose_after_enqueue:
                self.lose_after_enqueue = False
                raise HTTPException(502, 'fixture lost successful native response')
            return response.json()['result']
    transport = NativeTransport()
    app.state.strategy_promotions.control = transport
    yield service, transport, native
    native.close(); service.close(); service._ledger.close()


async def prepare(ac, service):
    target = {'account_alias':service.cfg.account_alias, 'session_id':service.runner.cycle.cfg.session_id}
    review = await ac.get(BASE+'/state', params=target)
    assert review.status_code==200, review.text
    intent = {'schema':'vati.runtime-recovery/1','device_id':'test-device', **target,
        'action':'clear_kill_switch','state_ref':review.json()['state_ref'],
        'issued_at_unix':int(time.time()),'args':{'trigger':'OWNER_HALT'}}
    response = await ac.post(BASE+'/challenge', json={'intent':intent})
    assert response.status_code==200, response.text
    challenge = response.json()
    proof = {**_approval_proof(challenge), 'expires_at_unix':challenge['approval_expires_at_unix']}
    return {'intent':intent,'approval_proof':proof}


@pytest.mark.asyncio
async def test_real_owner_recovery_round_trip_and_exact_original_replay(client, session_control):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service)
    accepted = await ac.post(BASE+'/request', json=body)
    assert accepted.status_code==200 and accepted.json()['phase']=='REQUESTED', accepted.text
    op = body['approval_proof']['challenge_id']
    assert accepted.json()['operation_id']==op
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active
    service.step_once()
    read = await ac.get(BASE+'/operations/'+op)
    assert read.status_code==200 and read.json()['phase']=='APPLIED', read.text
    assert not service.runner.cycle.kill.halted
    assert service._entry_permitted()
    count = service._ledger.count(EventKind.KILL_SWITCH)
    again = await ac.post(BASE+'/request', json=body)
    assert again.json()==read.json()
    assert service._ledger.count(EventKind.KILL_SWITCH)==count
    assert transport.calls.count('runtime_recovery_request')==1
    assert service._ledger.count(EventKind.ORDER_COMMAND)==0
    receipt = await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?', ('owner_approval_receipt:'+op,))
    assert receipt is not None and json.loads(receipt['value'])['context']['intent']==body['intent']


@pytest.mark.asyncio
@pytest.mark.parametrize('lost', ['before','after'])
async def test_lost_dispatch_response_resumes_original_operation_without_a_second_effect(client, session_control, lost):
    ac, app = client; service, transport, _ = session_control
    body = await prepare(ac, service); op = body['approval_proof']['challenge_id']
    if lost=='before': transport.fail_before_enqueue = True
    else: transport.lose_after_enqueue = True
    first = await ac.post(BASE+'/request', json=body)
    assert first.status_code==503 and first.json()['phase']=='UNKNOWN', first.text
    read = await ac.get(BASE+'/operations/'+op)
    assert read.json()['phase']==('PENDING_DISPATCH' if lost=='before' else 'REQUESTED')
    retried = await ac.post(BASE+'/request', json=body)
    assert retried.status_code==200 and retried.json()['operation_id']==op, retried.text
    service.step_once()
    assert (await ac.get(BASE+'/operations/'+op)).json()['phase']=='APPLIED'
    clears = [e for e in service._ledger.iter(EventKind.KILL_SWITCH) if e.payload.get('cleared')]
    assert len(clears)==1


@pytest.mark.asyncio
async def test_biometric_proof_cannot_clear_a_changed_native_target(client, session_control):
    ac, _ = client; service, _, _ = session_control
    body = await prepare(ac, service)
    body['intent']['args']['trigger']='VENUE_DISCONNECT'
    refused = await ac.post(BASE+'/request', json=body)
    assert refused.status_code==403
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active
    assert service._ledger.count(EventKind.ORDER_COMMAND)==0


@pytest.mark.asyncio
async def test_concurrent_original_posts_enqueue_only_one_native_request(client, session_control):
    ac, _ = client; service, _, _ = session_control
    body = await prepare(ac, service)
    responses = await asyncio.gather(*(ac.post(BASE+'/request',json=body) for _ in range(3)))
    assert all(r.status_code==200 for r in responses), [r.text for r in responses]
    originals = [e for e in service._ledger.iter(EventKind.SESSION) if e.producer=='vati-runtime-recovery-control']
    assert len(originals)==1
    service.step_once()
    assert not service.runner.cycle.kill.halted


@pytest.mark.asyncio
async def test_no_agent_principal_can_enqueue_recovery_or_see_hidden_tools(client, session_control):
    service, _, native = session_control
    path = '/v1/cmd/runtime_recovery_request'; body = b'{"args":{}}'
    response = native.post(path, content=body, headers=sign_headers(HERMES_TOKEN, 'POST', path, body))
    assert response.status_code==403
    tools = native.get('/v1/tools', headers=sign_headers(HERMES_TOKEN,'GET','/v1/tools',b''))
    assert not any(x['name'].startswith('runtime_recovery_') for x in tools.json()['tools'])
    assert KillSwitchTrigger.OWNER_HALT in service.runner.cycle.kill.active


@pytest.mark.asyncio
async def test_owner_catalog_and_openapi_describe_inputs_outputs_and_uncertainty(client, session_control):
    ac, app = client
    catalog = await ac.get(BASE+'/catalog')
    assert catalog.status_code==200, catalog.text
    assert set(catalog.json()['actions'])=={'clear_kill_switch','reset_loss_streak','resume_drawdown'}
    schema = app.openapi()
    operations = {('/catalog','get'),('/state','get'),('/challenge','post'),('/request','post'),('/operations/{operation_id}','get')}
    for suffix, method in operations:
        response = schema['paths'][BASE+suffix][method]['responses']['200']['content']['application/json']['schema']
        assert response.get('$ref') or response.get('anyOf')
    unknown = schema['paths'][BASE+'/request']['post']['responses']['503']['content']['application/json']['schema']
    assert unknown['$ref'].endswith('/RuntimeRecoveryUnknown')
    assert schema['components']['schemas']['RuntimeRecoveryResult']['properties']['entry_authority_granted']['const'] is False
