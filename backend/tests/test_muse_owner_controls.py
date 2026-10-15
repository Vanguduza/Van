import pytest
from van_gateway.muse.tasks import validate_task_call
from van_gateway.muse.models import MuseError

@pytest.mark.parametrize('operation', ['dial_owner_discover','dial_owner_profiles','dial_owner_route','dial_owner_status','dial_owner_session','dial_owner_artifact'])
def test_owner_read_keeps_existing_signed_task_transport(operation):
    args={'context_ref':'fixture-native-context','input':{'method':'inspect'} if operation=='dial_owner_session' else {}}
    validate_task_call(operation,args)

def test_context_discovery_cannot_accept_client_authority():
    validate_task_call('dial_owner_contexts',{})
    with pytest.raises(MuseError):validate_task_call('dial_owner_contexts',{'owner_verified':True})

@pytest.mark.parametrize('changes',[{'actor':'owner'},{'scope':{'profile_id':'other'}},{'owner_verified':True}])
def test_scope_and_authority_stay_server_owned(changes):
    with pytest.raises(MuseError):validate_task_call('dial_owner_status',{'context_ref':'fixture-native-context','input':{},**changes})

def test_control_requires_original_native_request_and_closed_action():
    args={'context_ref':'fixture-native-context','input':{'action':'pause','request_id':'fixture-request-1'}}
    validate_task_call('dial_owner_control',args)
    with pytest.raises(MuseError):validate_task_call('dial_owner_control',{'context_ref':args['context_ref'],'input':{'action':'approve_all','request_id':'fixture-request-1'}})
    with pytest.raises(MuseError):validate_task_call('dial_owner_control',{'context_ref':args['context_ref'],'input':{'action':'pause'}})
