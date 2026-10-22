"""Actual Commander writers, real private files, isolated native authorize replies."""
from dataclasses import replace
import json

import pytest
from fastapi import HTTPException

from commander.accounts import AccountControlSettings, build_account_handlers
from vati.accounts import AccountRegistry
from test_deriv_native_identity import Socket, native


def handlers(tmp_path,profile):
    def connector(url):
        return Socket(profile)
    controls=build_account_handlers(AccountControlSettings(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),deriv_connector=connector))
    controls['account_upsert']({'alias':'deriv_demo','broker':'DERIV','login':'VRTC900'})
    path=tmp_path/'secrets'/'deriv_demo.env'
    path.write_text('DERIV_API_TOKEN=fixture-old\nDERIV_APP_ID=1089\n');path.chmod(0o600)
    return controls,path


@pytest.mark.parametrize('patch',[{'loginid':'VRTC999'},{'is_virtual':0},{'currency':'EUR'},{'scopes':['read']}])
def test_unverified_rotation_keeps_the_previous_private_credential(tmp_path,patch):
    controls,path=handlers(tmp_path,native(**patch));before=path.read_bytes()
    with pytest.raises(HTTPException) as exc:
        controls['account_credentials']({'alias':'deriv_demo','secrets':{'DERIV_API_TOKEN':'fixture-replacement'}})
    assert exc.value.status_code==409
    assert path.read_bytes()==before
    assert AccountRegistry(tmp_path/'accounts.json').get('deriv_demo').login=='VRTC900'


def test_first_native_verified_credential_pins_an_unbound_account(tmp_path):
    controls,path=handlers(tmp_path,native())
    registry=AccountRegistry(tmp_path/'accounts.json');registry.replace(replace(registry.get('deriv_demo'),login=''))
    result=controls['account_credentials']({'alias':'deriv_demo','secrets':{'DERIV_API_TOKEN':'fixture-replacement'}})
    assert result=={'alias':'deriv_demo','stored_keys':['DERIV_API_TOKEN']}
    assert AccountRegistry(tmp_path/'accounts.json').get('deriv_demo').login=='VRTC900'
    assert 'DERIV_API_TOKEN=fixture-replacement' in path.read_text()


def test_oauth_link_checks_native_identity_before_creating_files(tmp_path):
    controls,path=handlers(tmp_path,native(loginid='VRTC999'))
    before=(tmp_path/'accounts.json').read_bytes()
    with pytest.raises(HTTPException) as exc:
        controls['deriv_oauth_link']({'alias':'other_alias','loginid':'VRTC900','token':'fixture-token','currency':'USD'})
    assert exc.value.status_code==409
    assert (tmp_path/'accounts.json').read_bytes()==before
    assert not (path.parent/'other_alias.env').exists()


def test_oauth_alias_collision_does_not_overwrite_a_different_registered_binding(tmp_path):
    controls,path=handlers(tmp_path,native());before=path.read_bytes()
    with pytest.raises(HTTPException) as exc:
        controls['deriv_oauth_link']({'alias':'deriv_demo','loginid':'VRTC900','token':'fixture-token','currency':'USD'})
    assert exc.value.status_code==409
    assert path.read_bytes()==before


def test_read_only_oauth_token_retains_a_real_observe_link(tmp_path):
    controls,path=handlers(tmp_path,native(scopes=['read']))
    result=controls['deriv_oauth_link']({'alias':'observe_link','loginid':'VRTC900','token':'fixture-readonly','currency':'USD'})
    account=result['account']
    assert account['mode']=='OBSERVE' and account['demo'] is True and account['login']=='VRTC900'
    assert account['safety_identity']=='READ ONLY'
    assert 'fixture-readonly' not in json.dumps(result)
    assert AccountRegistry(tmp_path/'accounts.json').credentials('observe_link')['DERIV_API_TOKEN']=='fixture-readonly'


def test_demo_alias_collision_is_checked_before_the_remote_creation_request(tmp_path):
    requests=[]
    def connector(url):
        requests.append(url);return Socket(native())
    controls=build_account_handlers(AccountControlSettings(str(tmp_path/'accounts.json'),str(tmp_path/'secrets'),deriv_connector=connector))
    controls['account_upsert']({'alias':'deriv_demo','broker':'DERIV','login':'VRTC900'})
    with pytest.raises(HTTPException) as exc:
        controls['deriv_create_demo']({'alias':'deriv_demo','verification_code':'fixture-code','client_password':'fixture-password','residence':'zw'})
    assert exc.value.status_code==409 and requests==[]
