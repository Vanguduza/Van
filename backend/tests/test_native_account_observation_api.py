"""Original bound native account facts through authenticated existing routes."""
import pytest
from httpx import ASGITransport, AsyncClient
from test_trading_api import client, _env
from test_native_account_observation import observed_owner
from vati.accounts import Account, AccountRegistry
from vati.accounts.registry import CredentialRef


@pytest.mark.asyncio
@pytest.mark.parametrize('credit', ['known', None, -10.0])
async def test_owner_account_routes_preserve_original_facts_without_unknown_credit_as_capital(client, tmp_path, credit):
    ac, app = client
    sdk, adapter, ledger, original = observed_owner(tmp_path, credit=credit)
    registry = AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='native', broker='MT5', mode='DEMO_TRADER', currency='USD', demo=True,
        login='12345678', server='Broker-Demo',
        credential_ref=CredentialRef(env_var='UNREAD_FIXTURE_CREDENTIAL_REFERENCE')))
    app.state.trading.ledger_path=ledger.path; app.state.trading.accounts_registry=str(registry.path)
    app.state.trading.reporting_currency='USD'; before=ledger.count()
    response=await ac.get('/v1/trading/accounts')
    assert response.status_code==200, response.text
    row=response.json()['accounts'][0]; observed=row['native_account_observation']
    assert observed['state']=='OBSERVED' and observed['snapshot_ref']==original.hash
    assert observed['execution_authority'] is False and observed['reported_equity']=='10250.5'
    assert row['funding']['state']=='UNSUPPORTED' and row['funding']['execution_authority'] is False
    if credit=='known':
        assert row['equity']=='10000.0' and observed['risk_equity']=='10000.0'
        assert row['margin']['state']=='OBSERVED'
    else:
        assert row['equity'] is None and row['floating_pnl'] is None
        assert observed['risk_equity'] is None and row['margin']['state']=='UNAVAILABLE'
    portfolio=await ac.get('/v1/trading/portfolio'); assert portfolio.status_code==200
    assert portfolio.json()['accounts'][0]['native_account_observation']==observed
    assert ledger.count()==before and not sdk.sent
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as unpaired:
        assert (await unpaired.get('/v1/trading/accounts')).status_code in {401,403}
