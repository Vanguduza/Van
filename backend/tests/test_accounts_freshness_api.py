"""Paired actual account/portfolio routes over owned native SQLite stores."""
import json
from types import SimpleNamespace
import pytest
from test_trading_api import client,_env,EventKind,make_event,Ledger
from van_gateway.trading.service import TradingService,LEDGER_STALENESS_MS
from vati.accounts import Account,AccountRegistry

NOW=2_000_000_000_000
BOUND=LEDGER_STALENESS_MS


def seed(app,tmp_path,rows):
    registry=AccountRegistry(tmp_path/'accounts.json')
    ledger=Ledger(tmp_path/'vati.sqlite');events={}
    for alias,source,connected in rows:
        registry.add(Account(alias=alias,broker='PAPER',mode='DEMO_TRADER',currency='USD'))
        if source is not None:
            e=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':alias,
                'mode':'DEMO_TRADER','currency':'USD','connected':connected,
                'balance':'12000.00','equity':'12345.67'},event_time_ms=source,
                received_time_ms=source,correlation_id=alias)
            ledger.append(e);events[alias]=e
    app.state.trading.accounts_registry=str(registry.path)
    return registry,ledger,events


@pytest.mark.asyncio
@pytest.mark.parametrize('age,connected,state,reason',[
    (0,True,'LIVE','SOURCE_SNAPSHOT_WITHIN_DISPLAY_BOUND'),
    (BOUND,True,'LIVE','SOURCE_SNAPSHOT_WITHIN_DISPLAY_BOUND'),
    (BOUND+1,True,'STALE','STALE_SOURCE_SNAPSHOT'),
    (-1,True,'STALE','FUTURE_SOURCE_TIME'),
    (NOW,True,'STALE','INVALID_SOURCE_TIME'),
    (0,False,'OFFLINE','SOURCE_SNAPSHOT_WITHIN_DISPLAY_BOUND'),
    (None,False,'NEVER_SYNCED','NO_ACCOUNT_SNAPSHOT'),
])
async def test_actual_paired_accounts_and_portfolio_keep_original_age_and_revision(client,tmp_path,monkeypatch,age,connected,state,reason):
    ac,app=client
    registry,ledger,events=seed(app,tmp_path,[('paper_one',None if age is None else NOW-age,connected)])
    monkeypatch.setattr('van_gateway.trading.service.time',SimpleNamespace(time=lambda:NOW/1000))
    before=ledger.count(),ledger.head()
    try:
        responses=[await ac.get(path) for path in ['/v1/trading/accounts','/v1/trading/portfolio','/v1/trading/accounts']]
        assert all(r.status_code==200 for r in responses),[r.text for r in responses]
        assert all(r.json()['ledger_available'] is True for r in responses)
        rows=[r.json()['accounts'][0] for r in responses]
        assert rows[0]==rows[1]==rows[2]
        row=rows[0];meta=row['snapshot_readback']
        assert row['connection_state']==state and meta['reason']==reason
        assert meta['read_at_ms']==NOW and meta['staleness_threshold_ms']==BOUND and meta['execution_authority'] is False
        assert meta['source_revision']==(events['paper_one'].hash if events else None)
        if events:
            assert row['equity']=='12345.67' and row['balance']=='12000.00'
            original=list(ledger.iter(EventKind.ACCOUNT_SNAPSHOT))[0]
            assert original.hash==meta['source_revision'] and original.event_time_ms==meta['source_event_time_ms']
        assert (ledger.count(),ledger.head())==before
        assert registry.public()==AccountRegistry(registry.path).public()
        assert all(word not in json.dumps(row).lower() for word in ['client_password','verification_code','secrets_file'])
    finally:ledger.close()


@pytest.mark.asyncio
async def test_two_accounts_unrelated_fresh_session_restart_and_current_scope_denial(client,tmp_path,monkeypatch):
    ac,app=client
    registry,ledger,events=seed(app,tmp_path,[('stale_one',NOW-BOUND-1,True),('fresh_two',NOW,True)])
    ledger.append(make_event(EventKind.SESSION,'vati-service',{'event':'HEARTBEAT'},event_time_ms=NOW,received_time_ms=NOW,correlation_id='unrelated'))
    monkeypatch.setattr('van_gateway.trading.service.time',SimpleNamespace(time=lambda:NOW/1000))
    before=ledger.count(),ledger.head()
    try:
        first=(await ac.get('/v1/trading/accounts')).json()['accounts']
        status=await ac.get('/v1/trading/status')
        assert status.status_code==200 and status.json()['ledger_stale'] is False
        assert {row['alias']:row['connection_state'] for row in first}=={'stale_one':'STALE','fresh_two':'LIVE'}
        # Reconstruct read owner from actual persisted registry/SQLite, not a
        # cached response. A process-death probe separately covers fresh import.
        restarted=TradingService(str(tmp_path/'vati.sqlite'),accounts_registry=str(registry.path))
        assert restarted.accounts()['accounts']==first
        assert restarted.portfolio()['accounts']==first
        denied=await ac.get('/v1/trading/accounts',headers={'X-Van-Device-Token':'wrong-scope-token'})
        assert denied.status_code in {401,403}
        assert (ledger.count(),ledger.head())==before
    finally:ledger.close()


@pytest.mark.asyncio
async def test_missing_and_corrupt_sources_remain_explicit(client,tmp_path,monkeypatch):
    ac,app=client
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='never_one',broker='PAPER',mode='DEMO_TRADER',currency='USD'))
    app.state.trading.accounts_registry=str(registry.path)
    app.state.trading.ledger_path=str(tmp_path/'absent.sqlite')
    monkeypatch.setattr('van_gateway.trading.service.time',SimpleNamespace(time=lambda:NOW/1000))
    for path in ['/v1/trading/accounts','/v1/trading/portfolio']:
        response=await ac.get(path);assert response.status_code==200,response.text
        assert response.json()['ledger_available'] is False
        row=response.json()['accounts'][0]
        assert row['connection_state']=='UNAVAILABLE' and row['snapshot_readback']['state']=='UNAVAILABLE'
        assert row['snapshot_readback']['reason']=='LEDGER_UNAVAILABLE' and row['equity'] is None
    assert not (tmp_path/'absent.sqlite').exists()
    # A malformed registry is not overwritten or relabelled an empty healthy list.
    registry.path.write_text('{broken')
    from vati.accounts.registry import AccountRegistryError
    with pytest.raises(AccountRegistryError):app.state.trading.accounts()
    assert registry.path.read_text()=='{broken'
    registry.path.write_text(json.dumps({'schema_version':1,'accounts':[]}))
    corrupt=tmp_path/'corrupt.sqlite';corrupt.write_bytes(b'owned-invalid-sqlite-source')
    app.state.trading.ledger_path=str(corrupt)
    import sqlite3
    with pytest.raises(sqlite3.DatabaseError):app.state.trading.accounts()
    assert corrupt.read_bytes()==b'owned-invalid-sqlite-source'
