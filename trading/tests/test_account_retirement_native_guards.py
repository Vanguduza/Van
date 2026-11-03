"""Real Commander/registry/files/lease; controlled readonly venue observations."""
from dataclasses import asdict,replace
from decimal import Decimal as D
from types import SimpleNamespace as NS
import time
from backend.tests.test_trading_api import client,_env
from backend.tests.test_account_update_review import isolate,immediate_challenge
from van_gateway.trading.accounts import LocalAccountControl

import pytest
from fastapi import HTTPException
from commander.accounts import AccountControlSettings,build_account_handlers,_write_secrets
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.app.account_lease import AccountRuntimeLease
from vati.app.account_lease import LeaseStoreUnavailable
from vati.app.sqlite_lease import SQLiteLeaseStore
from vati.core import Ledger,EventKind,make_event
from vati.execution.base import AccountState,Health,OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel
from vati.execution.exit_journal import ExitJournal


@pytest.fixture
def native(tmp_path,monkeypatch,client):
    path=tmp_path/'accounts.json';secrets=tmp_path/'secrets';secrets.mkdir()
    secret=secrets/'fx_primary.env';_write_secrets(secret,{'BRIDGE_SIGNING_KEY':'test-fixture-never-owner'})
    registry=AccountRegistry(path)
    account=Account('fx_primary','MT5','OBSERVE','USD',login='12345678',server='Broker-Demo',
        bridge_url='https://fixture.invalid:9443',credential_ref=CredentialRef(secrets_file=str(secret)))
    registry.add(account);ledger_path=tmp_path/'authority.sqlite';ledger=Ledger(str(ledger_path));ledger.close()
    view={'positions':[],'orders':[],'balance':D('100.25'),'equity':D('100.25'),'connected':True}
    adapter=NS(sync_account=lambda:AccountState('fx_primary',view['equity'],view['balance'],'USD',True,
        server_time_unix_ms=int(time.time()*1000)),
        positions=lambda:view['positions'],orders=lambda:view['orders'],
        heartbeat=lambda **kw:Health(view['connected'],0,kw['now_ms']))
    monkeypatch.setattr('vati.app.service.build_adapter',lambda *a,**k:adapter)
    ac,app=client
    app.state.onboarding.control=LocalAccountControl(str(path),str(secrets),operation_ledger=str(ledger_path))
    app.state.account_lifecycle.bind_local_admission_verifier()
    return NS(handlers=app.state.onboarding.control.handlers,ac=ac,path=path,secret=secret,ledger=ledger_path,view=view)


async def disconnect(native,*,expected=200):
    issued=await immediate_challenge(native.ac,'fx_primary',expected_status=expected)
    if expected!=200:return issued
    body,_=issued
    return await native.ac.post('/v1/trading/accounts/action',json=body)

@pytest.mark.parametrize('obstruction',['position','pending','funds','unavailable','lease','original-unknown'])
@pytest.mark.asyncio
async def test_native_unlink_retains_profile_and_protection_credentials_when_not_safe(native,obstruction):
    lease=None;store=None
    if obstruction=='position':native.view['positions']=[NS(position_id='42')]
    elif obstruction=='pending':native.view['orders']=[{'ticket':'11'}]
    elif obstruction=='funds':native.view['balance']=D('NaN')
    elif obstruction=='unavailable':native.view['connected']=False
    elif obstruction=='lease':
        store=SQLiteLeaseStore(native.ledger);lease=AccountRuntimeLease(store,account_alias='fx_primary',instance_id='actual-source-runtime')
        assert lease.acquire().permits_orders
    else:
        command=OrderCommand('original','d'*64,'key','fx_primary','mt5','EURUSD',Direction.LONG,
            'MARKET',D('.1'),D('1.1'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
        ledger=Ledger(str(native.ledger));now=int(time.time()*1000)
        ledger.append(make_event(EventKind.ORDER_COMMAND,'vati-execution-router',asdict(command),
            event_time_ms=now,received_time_ms=now,correlation_id='original'));ledger.close()
    before=native.secret.read_bytes()
    try:
        rejected=await disconnect(native,expected=409)
        assert rejected.status_code==409 and 'attestation required' not in rejected.text
        assert AccountRegistry(native.path).get('fx_primary')
        assert native.secret.read_bytes()==before
    finally:
        if lease:lease.release()
        if store:store.close()


@pytest.mark.asyncio
async def test_known_nonzero_funds_are_retained_remotely_not_reported_closed(native):
    response=await disconnect(native)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['removed'] is True and result['remote_account_closed'] is False
    assert result['historical_data_retained'] is True
    assert result['retained_remote_funds']=={'balance':'100.25','equity':'100.25','currency':'USD'}
    assert 'fx_primary' not in AccountRegistry(native.path).accounts and not native.secret.exists()
    assert native.ledger.exists()


@pytest.mark.asyncio
async def test_unbound_original_protective_exit_cannot_be_assumed_to_belong_to_another_account(native):
    ledger=Ledger(str(native.ledger))
    ExitJournal(ledger,'vati-execution-router').begin(venue='mt5',position_id='42',
        trade_intent_id='unbound-legacy-intent',action='FULL_CLOSE',quantity=None,
        reason='protective',now_ms=int(time.time()*1000))
    ledger.close();before=native.secret.read_bytes()
    response=await disconnect(native,expected=409)
    assert response.status_code==409 and 'protective' in response.text.lower()
    assert AccountRegistry(native.path).get('fx_primary') and native.secret.read_bytes()==before


@pytest.mark.parametrize('settled',[False,True])
@pytest.mark.asyncio
async def test_actual_paper_order_and_cash_close_need_settled_history_before_local_unlink(tmp_path,eurusd,settled,client):
    from test_single_session_recovery import opened_service
    service,cfg,clock=opened_service(tmp_path,eurusd)
    try:
        position=service.adapter.positions()[0]
        service.adapter.last_price[position.symbol]=position.entry_price+D('.001')
        receipt=service.adapter.close(position.position_id,None,now_ms=clock['now'],reason='LOCAL_UNLINK_RECONCILIATION')
        if settled:
            service.runner.cycle._on_close(position.trade_intent_id,receipt.average_fill,
                'LOCAL_UNLINK_RECONCILIATION',clock['now'])
        before=service._ledger.count(EventKind.TRADE_REVIEW)
        service.close()
        ac,app=client
        app.state.onboarding.control=LocalAccountControl(cfg.registry_path,str(tmp_path/'managed'),operation_ledger=cfg.ledger)
        app.state.account_lifecycle.bind_local_admission_verifier()
        if settled:
            body,_=await immediate_challenge(ac,cfg.account_alias)
            response=await ac.post('/v1/trading/accounts/action',json=body)
            assert response.status_code==200,response.text
            result=response.json()
            assert result['removed'] is True and result['retained_remote_funds'] is None
            assert cfg.account_alias not in AccountRegistry(cfg.registry_path).accounts
        else:
            blocked=await immediate_challenge(ac,cfg.account_alias,expected_status=409)
            assert 'unsettled' in blocked.text.lower()
            assert AccountRegistry(cfg.registry_path).get(cfg.account_alias)
        assert service._ledger.count(EventKind.TRADE_REVIEW)==before
    finally:service.close();service._ledger.close()


@pytest.mark.asyncio
async def test_unlink_does_not_destroy_credentials_shared_with_another_native_account(native):
    registry=AccountRegistry(native.path);account=registry.get('fx_primary')
    registry.replace(replace(account,broker='CTRADER',login='12345',server='demo'))
    registry=AccountRegistry(native.path);account=registry.get('fx_primary')
    registry.add(replace(account,alias='other_account',login='67890'))
    before=native.secret.read_bytes()
    # Deliberate canonical correction: removing a local reference is not
    # per-account credential revocation/destruction; shared access must HOLD.
    response=await disconnect(native,expected=409)
    assert 'destruction cannot be proven' in response.text
    assert AccountRegistry(native.path).get('fx_primary')
    assert native.secret.read_bytes()==before
    assert AccountRegistry(native.path).get('other_account')


@pytest.mark.asyncio
async def test_unmanaged_credential_reference_does_not_authorize_deleting_another_alias_file(native,tmp_path):
    registry=AccountRegistry(native.path);account=registry.get('fx_primary')
    external=tmp_path/'external'/'private.env';_write_secrets(external,{'BRIDGE_SIGNING_KEY':'fixture-external'})
    registry.add(replace(account,alias='other_account',login='98765'))
    registry=AccountRegistry(native.path);registry.replace(replace(account,credential_ref=CredentialRef(secrets_file=str(external))))
    before=native.secret.read_bytes();external_before=external.read_bytes()
    response=await disconnect(native,expected=409)
    assert 'destruction cannot be proven' in response.text
    assert AccountRegistry(native.path).get('fx_primary')
    assert native.secret.read_bytes()==before and external.read_bytes()==external_before


@pytest.mark.asyncio
async def test_a_shared_reference_added_after_native_readback_is_rechecked_before_deletion(native,monkeypatch):
    import commander.account_retirement as module
    from commander.account_effects import _effect_started
    inspect=module.inspect_retirement;inserted=[]
    def shared_after_facts(*args,**kwargs):
        facts=inspect(*args,**kwargs)
        # Fresh challenge/readback calls are readonly. Add the competing owner
        # once, at the admitted native effect's final ownership boundary.
        if _effect_started.get() is not None and kwargs.get('inside_removal') and not inserted:
            registry=AccountRegistry(native.path)
            registry.add(replace(registry.get('fx_primary'),alias='late_reference',login='98765'))
            inserted.append(True)
        return facts
    monkeypatch.setattr(module,'inspect_retirement',shared_after_facts)
    before=native.secret.read_bytes()
    body,_=await immediate_challenge(native.ac,'fx_primary')
    blocked=await native.ac.post('/v1/trading/accounts/action',json=body)
    assert inserted and blocked.status_code==409 and 'destruction cannot be proven' in blocked.text
    assert native.secret.read_bytes()==before
    registry=AccountRegistry(native.path)
    assert registry.get('fx_primary') and registry.get('late_reference')


@pytest.mark.asyncio
async def test_unreachable_authority_is_not_reported_as_observed_lease_exclusion(native,monkeypatch):
    def unavailable(*args):raise LeaseStoreUnavailable('controlled source fixture outage')
    monkeypatch.setattr('commander.account_retirement.lease_store',
        lambda *a:NS(read=unavailable,close=lambda:None))
    before=native.secret.read_bytes()
    blocked=await disconnect(native,expected=503)
    assert 'store is unreachable' in blocked.text and 'runtime is active' not in blocked.text
    assert native.secret.read_bytes()==before and AccountRegistry(native.path).get('fx_primary')
