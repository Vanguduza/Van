"""Paired gateway -> signed Commander HTTP -> real PG multi-instrument actor."""
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from test_trading_api import client,_env,_approval_proof
from test_account_runtime_recovery import book,halt
from conftest import eurusd
from commander.app import create_app,CommanderSettings
from commander.auth import sign_headers
from vati.core import EventKind
from vati.risk.contracts import KillSwitchTrigger


@pytest.mark.asyncio
async def test_paired_owner_recovers_the_actual_account_actor_and_reads_the_same_original(client,book,tmp_path):
    ac,app=client;service,clock,review,request=book
    # The paired phone's real P256 key is enrolled by the existing gateway-only
    # native handshake. The financial policy keeps its independent issuer.
    Path(service.cfg.owner_authority_keys).write_text(json.dumps({'keys':{}}))
    halt(service);service._observe_owner_halt(clock['now']);state=review()
    token='g'*40;heartbeat_dir=Path(service.cfg.heartbeat_path).parent
    settings=CommanderSettings(tokens={'van-gateway':token},ledger=service.cfg.ledger,
        heartbeat_dir=str(heartbeat_dir),owner_authority_keys=service.cfg.owner_authority_keys,
        accounts_registry=service.cfg.registry_path,log_dir=str(tmp_path/'logs'),secrets_dir=str(tmp_path/'secrets'))
    calls=[]
    with TestClient(create_app(settings)) as native:
        class NativeTransport:
            def run(self,name,args):
                calls.append(name);path='/v1/cmd/'+name
                body=json.dumps({'args':args,'requested_by':'van-gateway'}).encode()
                result=native.post(path,content=body,headers={**sign_headers(token,'POST',path,body),
                    'Content-Type':'application/json'})
                if result.status_code>=400:raise HTTPException(result.status_code,result.json()['detail'])
                return result.json()['result']
        app.state.strategy_promotions.control=NativeTransport()
        base='/v1/trading/runtime/recovery'
        catalog=await ac.get(base+'/catalog')
        assert catalog.status_code==200 and catalog.json()['supported_runtime']=='single-session-and-account'
        target={'account_alias':service.cfg.account_alias,'session_id':state['state']['session_id']}
        observed=await ac.get(base+'/state',params=target)
        assert observed.status_code==200,observed.text
        intent={'schema':'vati.runtime-recovery/1','device_id':'test-device',**target,
            'action':'clear_kill_switch','state_ref':observed.json()['state_ref'],
            'issued_at_unix':clock['now']//1000,'args':{'trigger':'OWNER_HALT'}}
        response=await ac.post(base+'/challenge',json={'intent':intent})
        assert response.status_code==200,response.text
        challenge=response.json();proof={**_approval_proof(challenge),
            'expires_at_unix':challenge['approval_expires_at_unix']}
        body={'intent':intent,'approval_proof':proof}
        accepted=await ac.post(base+'/request',json=body)
        assert accepted.status_code==200 and accepted.json()['phase']=='REQUESTED',accepted.text
        original=proof['challenge_id'];assert accepted.json()['operation_id']==original
        assert KillSwitchTrigger.OWNER_HALT in service.kill.active
        service.step_once()
        done=await ac.get(base+'/operations/'+original)
        assert done.status_code==200 and done.json()['phase']=='APPLIED',done.text
        assert done.json()['result']['entry_authority_granted'] is False
        assert KillSwitchTrigger.OWNER_HALT not in service.kill.active
        count=service._ledger.count(EventKind.KILL_SWITCH)
        again=await ac.post(base+'/request',json=body)
        assert again.json()==done.json()
        assert service._ledger.count(EventKind.KILL_SWITCH)==count
        assert calls.count('runtime_recovery_request')==1
        assert service._ledger.count(EventKind.ORDER_COMMAND)==0
