"""The real paired-owner routes expose native period evidence without effect authority."""
import pytest
from decimal import Decimal
from test_trading_api import client,_env
from test_native_balance_runtime import native_runtime_book
from vati.accounts import Account,AccountRegistry
from vati.accounts.registry import CredentialRef

@pytest.mark.asyncio
async def test_native_balance_reconciliation_is_available_through_both_existing_owner_routes(client,tmp_path):
    ac,app=client;ledger=native_runtime_book(tmp_path)
    registry=AccountRegistry(tmp_path/'accounts.json');registry.add(Account(alias='ctrader_primary',broker='CTRADER',mode='DEMO_TRADER',currency='EUR',login='12345',
        credential_ref=CredentialRef(env_var='UNREAD_FIXTURE_CREDENTIAL_REFERENCE')))
    app.state.trading.ledger_path=ledger.path;app.state.trading.accounts_registry=str(registry.path);app.state.trading.reporting_currency='EUR'
    before=ledger.count()
    for path in ['/v1/trading/accounts','/v1/trading/portfolio']:
        response=await ac.get(path);assert response.status_code==200,response.text
        row=response.json()['accounts'][0];period=row['funding']['period']
        assert row['day_pnl'] is None and row['funding']['native_deals']['deal_count']==1
        assert period['state']=='MEASURED' and period['balance_state']=='RECONCILED'
        assert period['return_qualification']=='NOT_ISSUED' and period['trade_alpha_claimed'] is False
        assert Decimal(period['performance']['net_account_pnl'])==Decimal('10') and period['execution_authority'] is False
    assert ledger.count()==before
