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
