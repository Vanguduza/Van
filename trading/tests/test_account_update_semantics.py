"""Owner metadata edits must preserve connection identity and explicit controls."""
from dataclasses import asdict

import pytest
from fastapi import HTTPException

from commander.accounts import AccountControlSettings,build_account_handlers
from vati.accounts import Account,AccountRegistry,CredentialRef


def existing(tmp_path):
    registry=AccountRegistry(tmp_path/'accounts.json')
    account=registry.add(Account(alias='owner_account',broker='DERIV',mode='OBSERVE',currency='EUR',
        label='Old label',server='8123',login='CR900',venue='deriv-owner',
        bridge_url='wss://ws.derivws.com/websockets/v3',credential_ref=CredentialRef(env_var='FIXTURE_OWNER_ACCOUNT_SECRET'),
        demo=False,enabled=False,mandate_ref='owner-policy-reference',notes='Keep owner notes'))
    h=build_account_handlers(AccountControlSettings(str(registry.path),str(tmp_path/'secrets')))
    return registry,account,h


@pytest.mark.parametrize('field',['mode','currency','server','login','venue','bridge_url','credential_ref','demo','enabled','mandate_ref','notes'])
def test_an_approved_label_edit_cannot_reset_unsupplied_native_fields(tmp_path,field):
    registry,account,h=existing(tmp_path)
    h['account_upsert']({'alias':account.alias,'broker':account.broker,'label':'New label'})
    current=AccountRegistry(registry.path).get(account.alias)
    assert getattr(current,field)==getattr(account,field)
    assert current.label=='New label'


def test_metadata_edit_does_not_create_a_new_empty_vault_or_drop_existing_reference(tmp_path):
    registry,account,h=existing(tmp_path)
    result=h['account_upsert']({'alias':account.alias,'broker':account.broker,'label':'New label'})
    assert not (tmp_path/'secrets/owner_account.env').exists()
    assert AccountRegistry(registry.path).get(account.alias).credential_ref==account.credential_ref
    assert result['secrets_file'] is None


def test_owner_can_disable_and_reenable_without_resupplying_or_rebinding_account_identity(tmp_path):
    registry,account,h=existing(tmp_path)
    h['account_upsert']({'alias':account.alias,'enabled':True})
    assert AccountRegistry(registry.path).get(account.alias).enabled is True
    h['account_upsert']({'alias':account.alias,'enabled':False})
    current=AccountRegistry(registry.path).get(account.alias)
    assert current.enabled is False and current.login==account.login and current.mode=='OBSERVE'


@pytest.mark.parametrize('value',['false',0,None])
def test_ambiguous_enabled_values_are_refused_before_any_native_write(tmp_path,value):
    registry,account,h=existing(tmp_path); before=registry.path.read_bytes()
    with pytest.raises(HTTPException) as error:
        h['account_upsert']({'alias':account.alias,'broker':account.broker,'enabled':value})
    assert error.value.status_code==422 and registry.path.read_bytes()==before
    assert not (tmp_path/'secrets/owner_account.env').exists()


def test_unsupported_control_is_never_reported_as_applied(tmp_path):
    registry,account,h=existing(tmp_path); before=registry.path.read_bytes()
    with pytest.raises(HTTPException) as error:
        h['account_upsert']({'alias':account.alias,'broker':account.broker,'max_daily_loss':'1.0'})
    assert error.value.status_code==422 and registry.path.read_bytes()==before


@pytest.mark.parametrize('endpoint',['wss://ws.derivws.com.evil.invalid/websockets/v3',
    'wss://ws.derivws.com@evil.invalid/websockets/v3','ws://ws.derivws.com/websockets/v3'])
def test_registration_cannot_redirect_future_deriv_credentials_to_an_untrusted_endpoint(tmp_path,endpoint):
    registry=AccountRegistry(tmp_path/'accounts.json')
    h=build_account_handlers(AccountControlSettings(str(registry.path),str(tmp_path/'secrets')))
    with pytest.raises(HTTPException) as error:
        h['account_upsert']({'alias':'new_account','broker':'DERIV','bridge_url':endpoint})
    assert error.value.status_code==422
    assert not registry.path.exists() and not (tmp_path/'secrets/new_account.env').exists()


def test_existing_untrusted_connection_can_be_disabled_without_first_repairing_identity(tmp_path):
    registry,account,h=existing(tmp_path)
    from dataclasses import replace
    bad=replace(account,bridge_url='wss://legacy-untrusted.invalid/websockets/v3',enabled=True)
    registry.replace(bad)
    result=h['account_upsert']({'alias':account.alias,'enabled':False})
    assert result['account']['enabled'] is False
    assert AccountRegistry(registry.path).get(account.alias)==replace(bad,enabled=False)


def test_provider_link_cannot_rebind_an_existing_alias_or_replace_its_secret_reference(tmp_path):
    registry,account,h=existing(tmp_path);before=registry.path.read_bytes()
    with pytest.raises(HTTPException) as error:
        h['ctrader_link']({'alias':account.alias,'ctid_trader_account_id':12345,
            'client_id':'fixture-app','client_secret':'fixture-secret','access_token':'fixture-token'})
    assert error.value.status_code==409 and registry.path.read_bytes()==before
    assert not (tmp_path/'secrets/owner_account.env').exists()
