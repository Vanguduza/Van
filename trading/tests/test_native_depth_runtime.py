"""Actual runtime lifecycle/reader/archive join with owned SQLite and native sockets.

Coordinator fixture explicitly injects its store constructors; it is not a
PostgreSQL shared-authority qualification or a deployment configuration.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import mandate_dict
from test_native_depth_worker import depth_service
from vati.app.service import ServiceConfig, SessionService
from vati.market_data.native_depth import NativeDepthArchive
from vati.risk.serde import contract_to_dict


def depth_reads(s):
    return sum(name=='ProtoOASubscribeDepthQuotesReq' for peer in [s.test.primary,*s.test.peers] for name,_ in peer.requests)


def runtime_config(s, tmp_path, eurusd):
    return ServiceConfig(account_alias=s.cfg.account_alias,symbol='EURUSD',base='EUR',quote='USD',
        timeframe='H1',contract=contract_to_dict(eurusd),
        mandate=mandate_dict(venue='ctrader',mode='OBSERVE',account_alias=s.cfg.account_alias),
        capsules=[],registry_path=s.cfg.registry_path,ledger=str(tmp_path/'runtime.sqlite'),
        lake_root=str(tmp_path/'bars'),heartbeat_path=str(tmp_path/'heartbeat.json'),
        depth_capture=deepcopy(s.cfg.depth_capture))


def build_runtime(s,cfg,eurusd,monkeypatch,kind):
    if kind=='session':
        runtime=SessionService(cfg,lambda now:[],clock=s.clock,adapter=s.adapter).build()
    else:
        import vati.app.account_service as module
        from vati.app.sqlite_lease import SQLiteLeaseStore
        from vati.core.ledger_pg import open_ledger
        # Same actual lifecycle and SQL owner interfaces; no PG server is
        # provisioned, and the production shared-store guard remains unchanged.
        sql=cfg.ledger;cfg.ledger='postgresql://source-fixture-not-connected'
        cfg.instruments=[{'symbol':'XAUUSD','base':'XAU','quote':'USD',
            'contract':contract_to_dict(replace(eurusd,symbol='XAUUSD',base_currency='XAU'))}]
        monkeypatch.setattr(module,'open_ledger',lambda _:open_ledger(sql))
        monkeypatch.setattr(module,'PostgresLeaseStore',lambda _:SQLiteLeaseStore(sql))
        runtime=module.AccountCoordinatorService(cfg,clock=s.clock,adapter=s.adapter).build()
    return runtime


@pytest.mark.parametrize('kind',['session','coordinator'])
def test_actual_runtime_start_step_close_collects_once_and_recovers_original(depth_service,tmp_path,eurusd,monkeypatch,kind):
    s=depth_service;cfg=runtime_config(s,tmp_path,eurusd)
    runtime=build_runtime(s,cfg,eurusd,monkeypatch,kind)
    assert depth_reads(s)==0 and not hasattr(runtime,'_depth_capture_worker')
    try:
        runtime.start()
        w=runtime._depth_capture_worker
        assert w.wait_idle(3)
        assert w.snapshot()['requests']['original']['state']=='CAPTURED'
        assert depth_reads(s)==1
        receipt=w.snapshot()['requests']['original']['receipt']
        assert runtime.step_once() is None
        assert runtime._depth_capture_worker is w and depth_reads(s)==1
        cold=NativeDepthArchive(cfg.depth_capture['archive_root'])
        assert cold.lookup(s.test.contract.native_scope,'DEPTH','original')==receipt
        assert receipt['provider_qualified'] is False
        assert not any(name in {'ProtoOANewOrderReq','ProtoOAAmendPositionSLTPReq','ProtoOAClosePositionReq'}
            for peer in [s.test.primary,*s.test.peers] for name,_ in peer.requests)
    finally:
        runtime.close()
        runtime._ledger.close()
    assert w.wait_idle(0) and w.snapshot()['state']=='STOPPED'


def test_default_off_runtime_constructor_and_read_model_do_not_open_reader(depth_service,tmp_path,eurusd):
    s=depth_service;cfg=runtime_config(s,tmp_path,eurusd);cfg.depth_capture=None
    runtime=SessionService(cfg,lambda now:[],clock=s.clock,adapter=s.adapter).build()
    try:
        assert not s.test.peers
        runtime.start();runtime.step_once()
        assert depth_reads(s)==0 and not hasattr(runtime,'_depth_capture_worker')
    finally:
        runtime.close();runtime._ledger.close()
    assert not Path(s.cfg.depth_capture['archive_root']).exists()


from backend.tests.test_trading_api import client,_env


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['session','coordinator'])
async def test_each_actual_runtime_produces_same_original_paired_http_receipt(client,depth_service,tmp_path,eurusd,monkeypatch,kind):
    s=depth_service;cfg=runtime_config(s,tmp_path,eurusd)
    runtime=build_runtime(s,cfg,eurusd,monkeypatch,kind)
    ac,app=client
    app.state.trading.native_source_root=cfg.depth_capture['archive_root']
    try:
        runtime.start();w=runtime._depth_capture_worker
        assert w.wait_idle(3)
        receipt=w.snapshot()['requests']['original']['receipt']
        assert receipt is not None and depth_reads(s)==1
        scope=s.test.contract.native_scope
        query={k:str(scope[k]) for k in ('environment','native_account_id','native_symbol_id')}
        query['revision']='1'
        result=await ac.get('/v1/trading/market/depth-history',params=query)
        assert result.status_code==200,result.text
        assert result.json()['snapshot']['receipt']==receipt
        query.pop('revision');query['as_of_ms']=str(receipt['available_at_ms'])
        bytime=await ac.get('/v1/trading/market/depth-history',params=query)
        assert bytime.status_code==200 and bytime.json()['snapshot']==result.json()['snapshot']
        assert depth_reads(s)==1
        assert NativeDepthArchive(cfg.depth_capture['archive_root']).lookup(scope,'DEPTH','original')==receipt
    finally:
        runtime.close();runtime._ledger.close()
