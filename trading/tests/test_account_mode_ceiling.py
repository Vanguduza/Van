"""Both real service builders refuse mandates that widen registry authority."""
from types import SimpleNamespace

import pytest

from vati.accounts import Account, AccountRegistry
from vati.accounts.access import validate_mode
from vati.app.service import SessionService
from vati.app.account_service import AccountCoordinatorService
from conftest import mandate_dict


@pytest.mark.parametrize('builder',[SessionService,AccountCoordinatorService])
@pytest.mark.parametrize('configured,mandate,demo',[
    ('OBSERVE','DEMO_TRADER',True),('ADVISOR','DEMO_TRADER',True),
    ('SHADOW_TRADER','DEMO_TRADER',True),('DEMO_TRADER','DEMO_TRADER',False),
    ('LIMITED_LIVE','AUTONOMOUS_LIVE',False),('DEMO_TRADER','LIMITED_LIVE',True),
])
def test_real_builder_refuses_authority_widening_before_runtime_or_network(tmp_path,monkeypatch,builder,configured,mandate,demo):
    registry=AccountRegistry(tmp_path/'accounts.json')
    registry.add(Account(alias='paper_lab',broker='PAPER',mode=configured,currency='USD',
        demo=demo,mandate_ref='fixture-owner-mandate' if not demo else ''))
    cfg=SimpleNamespace(account_alias='paper_lab',registry_path=str(registry.path),
        mandate=mandate_dict(venue='paper',mode=mandate,account_alias='paper_lab'),
        ledger='postgresql://fixture-not-opened')
    import vati.app.service as single
    import vati.app.account_service as multi
    def entry_boundary(*args, **kwargs):
        raise AssertionError('authority widening reached native adapter construction')
    monkeypatch.setattr(single,'build_adapter',entry_boundary)
    monkeypatch.setattr(multi,'build_adapter',entry_boundary)
    if builder is SessionService:
        service=builder(cfg,lambda now:[])
    else:
        service=builder(cfg)
        monkeypatch.setattr(service,'_load_specs',lambda:None)
    with pytest.raises(RuntimeError,match='mode|safety identity'):
        service.build()


@pytest.mark.parametrize('configured,mandate,demo',[
    ('DEMO_TRADER','DEMO_TRADER',True),('LIMITED_LIVE','LIMITED_LIVE',False),
    ('AUTONOMOUS_LIVE','LIMITED_LIVE',False),('AUTONOMOUS_LIVE','AUTONOMOUS_LIVE',False),
    ('OBSERVE','OBSERVE',False),('OBSERVE','SHADOW_TRADER',False),
])
def test_narrower_or_non_sending_mandates_remain_available(configured,mandate,demo):
    validate_mode(Account(alias='paper_lab',broker='PAPER',mode=configured,currency='USD',demo=demo,
        mandate_ref='fixture-owner-mandate' if not demo else ''),mandate)
