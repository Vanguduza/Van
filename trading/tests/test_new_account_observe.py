"""Initial mode policy via real pure resolver and PAPER CLI metadata only."""
from pathlib import Path
import pytest
from fastapi import HTTPException
from commander.account_config import resolve_account_config
from vati.accounts import Account,AccountRegistry,CredentialRef
from vati.accounts.initial_mode import InitialAccountModeError,require_initial_account_mode
from vati.__main__ import main


@pytest.mark.parametrize('demo',[True,False])
def test_omitted_initial_mode_is_observe_for_both_account_environments(tmp_path,demo):
    candidate=resolve_account_config({'alias':'fresh_paper','broker':'PAPER','demo':demo},
        alias='fresh_paper',current=None,secret_path=tmp_path/'unused.env')
    assert candidate.mode=='OBSERVE' and candidate.demo is demo
    assert candidate.credential_ref==CredentialRef() and not list(tmp_path.iterdir())


@pytest.mark.parametrize('mode',['DEMO_TRADER','LIMITED_LIVE','AUTONOMOUS_LIVE','ADVISOR','SHADOW_TRADER',None,True,''])
def test_explicit_initial_mode_cannot_widen_the_default_before_any_write(tmp_path,mode):
    with pytest.raises(InitialAccountModeError) as direct:require_initial_account_mode(mode)
    assert direct.value.code=='NEW_ACCOUNT_OBSERVE_REQUIRED'
    with pytest.raises(HTTPException) as error:
        resolve_account_config({'alias':'fresh_paper','broker':'PAPER','mode':mode},
            alias='fresh_paper',current=None,secret_path=tmp_path/'unused.env')
    assert error.value.status_code==422 and not list(tmp_path.iterdir())
    if isinstance(mode,str):assert error.value.detail['code']=='NEW_ACCOUNT_OBSERVE_REQUIRED'
    else:assert error.value.detail=='mode must be text'


@pytest.mark.parametrize('mode,demo',[('OBSERVE',True),('DEMO_TRADER',True),('LIMITED_LIVE',False),('AUTONOMOUS_LIVE',False)])
def test_existing_admitted_mode_and_mandate_survive_ordinary_metadata_edits(tmp_path,mode,demo):
    original=Account('admitted_paper','PAPER',mode,'USD',demo=demo,mandate_ref='existing-admitted-control')
    changed=resolve_account_config({'alias':original.alias,'label':'Current owner label'},
        alias=original.alias,current=original,secret_path=tmp_path/'unused.env')
    assert changed.mode==mode and changed.mandate_ref==original.mandate_ref
    assert changed.credential_ref==original.credential_ref and changed.demo is demo
    assert not list(tmp_path.iterdir())


def test_real_paper_cli_defaults_observe_and_refuses_explicit_initial_trading_mode(tmp_path,capsys):
    registry=tmp_path/'accounts.json'
    assert main(['accounts','add','--registry',str(registry),'--alias','cli_paper','--broker','PAPER'])==0
    assert AccountRegistry(registry).get('cli_paper').mode=='OBSERVE'
    before=registry.read_bytes();capsys.readouterr()
    assert main(['accounts','add','--registry',str(registry),'--alias','other_paper','--broker','PAPER',
        '--mode','DEMO_TRADER'])==2
    assert 'NEW_ACCOUNT_OBSERVE_REQUIRED' in capsys.readouterr().out and registry.read_bytes()==before
    assert set(AccountRegistry(registry).accounts)=={'cli_paper'}
