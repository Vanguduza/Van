"""Factory defaults must not replace the registered owner's account identity."""
from decimal import Decimal

import pytest

from vati.accounts import Account,AccountRegistry
from vati.app.service import build_adapter


@pytest.mark.parametrize('currency',['EUR','GBP','ZiG'])
def test_paper_factory_preserves_the_registered_currency(tmp_path,currency):
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='paper_owner',broker='PAPER',mode='DEMO_TRADER',currency=currency))
    adapter=build_adapter(account,registry,equity_hint=Decimal('9000'))
    state=adapter.sync_account()
    assert state.currency==currency
    assert state.account_alias=='paper_owner' and state.balance==Decimal('9000')


def test_owner_ticket_factory_preserves_alias_venue_and_currency_without_inventing_verification(tmp_path):
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='vfex_owner',broker='ZSE_OWNER_TICKET',venue='vfex',mode='OBSERVE',currency='USD',demo=False))
    adapter=build_adapter(account,registry,equity_hint=Decimal('1200'))
    state=adapter.sync_account()
    assert (state.account_alias,adapter.venue,state.currency)==('vfex_owner','vfex','USD')
    assert state.balance==Decimal('1200') and state.verified is False
