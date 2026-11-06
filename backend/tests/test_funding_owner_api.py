"""Original native cash facts through the existing authenticated owner API."""
import pytest
from httpx import ASGITransport,AsyncClient
from test_trading_api import client,_env
from test_funding_runtime import setup
from test_funding_owner_reports import snapshot
from vati.accounts import Account,AccountRegistry
from vati.accounts.registry import CredentialRef
from vati.core.events import EventKind
from vati.funding.runtime import capture_funding

@pytest.mark.asyncio
async def test_native_cash_history_reaches_accounts_and_portfolio_without_profit_or_effect_authority(client,tmp_path):
    ac,app=client
    ledger,_,adapter=setup(tmp_path);account=adapter.sync_account()
    funding=capture_funding(ledger,adapter,account,now_ms=3000)
    snapshot(ledger,funding_observation=funding)
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='ctrader_primary',broker='CTRADER',mode='DEMO_TRADER',currency='EUR',login='12345',
        credential_ref=CredentialRef(env_var='UNREAD_FIXTURE_CREDENTIAL_REFERENCE')))
    app.state.trading.ledger_path=ledger.path;app.state.trading.accounts_registry=str(registry.path)
    app.state.trading.reporting_currency='EUR'
    before=ledger.count()
    response=await ac.get('/v1/trading/accounts')
    assert response.status_code==200,response.text
    row=response.json()['accounts'][0]
    assert row['day_pnl'] is None and row['performance_state']=='UNMEASURED'
    assert row['funding']['state']=='OBSERVED' and row['funding']['return_qualification']=='NOT_ISSUED'
    movement=row['funding']['movements'][0]
    assert movement['movement']['delta']=='0.01234567'
    assert movement['classification']['category']=='EXTERNAL_CAPITAL'
    assert row['funding']['execution_authority'] is False
    portfolio=(await ac.get('/v1/trading/portfolio')).json()
    assert portfolio['totals']['day_pnl'] is None
    assert portfolio['accounts'][0]['funding']['statement_ref']==funding['statement']['statement_ref']
    assert ledger.count()==before and ledger.count(EventKind.FUNDING_STATEMENT)==1
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as unpaired:
        assert (await unpaired.get('/v1/trading/accounts')).status_code in {401,403}


@pytest.mark.asyncio
async def test_signed_mt5_cash_query_reaches_owner_api_without_credit_as_profit(client,tmp_path):
    from dataclasses import replace
    from test_mt5_funding_runtime import setup as mt5_setup, publish
    from test_mt5_funding_contract import cash
    from vati.funding.mt5 import Mt5CashFact
    from vati.funding.mt5_runtime import capture_cached_mt5
    ac,app=client
    ledger,adapter,account=mt5_setup(tmp_path)
    account=replace(account,funding_mark=replace(account.funding_mark,movements=(Mt5CashFact.from_body(cash()),)))
    funding=capture_cached_mt5(ledger,account,now_ms=10000);publish(ledger,account,funding)
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='native',broker='MT5',mode='DEMO_TRADER',currency='USD',demo=True,
        login='12345678',server='Broker-Demo',credential_ref=CredentialRef(env_var='UNREAD_FIXTURE_CREDENTIAL_REFERENCE')))
    app.state.trading.ledger_path=ledger.path;app.state.trading.accounts_registry=str(registry.path)
    app.state.trading.reporting_currency='USD';before=ledger.count()
    response=await ac.get('/v1/trading/accounts');assert response.status_code==200,response.text
    row=response.json()['accounts'][0]
    assert row['equity']=='10000' and row['floating_pnl']=='0' and row['day_pnl'] is None
    observed=row['funding'];assert observed['query_ref']==funding['query_ref']
    assert observed['return_qualification']=='NOT_ISSUED' and observed['execution_authority'] is False
    cash_row=observed['movements'][0]['movement']
    assert cash_row['native_id']==9007199254740993 and cash_row['fee']=='-1.3E-7' and 'delta' not in cash_row
    portfolio=(await ac.get('/v1/trading/portfolio')).json()
    assert portfolio['totals']['day_pnl'] is None and portfolio['totals']['floating_pnl']=='0'
    assert ledger.count()==before
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as unpaired:
        assert (await unpaired.get('/v1/trading/accounts')).status_code in {401,403}
