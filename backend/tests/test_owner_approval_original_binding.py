"""Historical commitment reads cannot issue, renew or consume A4 permission."""
import json
import pytest
from conftest_automation import make_store
from van_gateway.approval.service import OwnerApprovalService, OwnerApprovalError

@pytest.mark.asyncio
async def test_exact_expired_original_fact_is_read_only_and_cannot_be_used_as_permission(tmp_path):
    service=OwnerApprovalService(await make_store(tmp_path))
    identity=dict(device_id='owner',source_command_id='account:deriv_oauth_link',action_id='trading.account.deriv_oauth_link',text='exact committed original version and domain',parameters={'alias':'original'})
    challenge=await service.issue(**identity,turn_id=None,project_id=None,now_unix=1000)
    key=service.PREFIX+challenge.challenge_id
    before=await service.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
    fact=await service.original_binding_fact(challenge_id=challenge.challenge_id,**identity)
    assert fact['historical_only'] is True and fact['execution_authority'] is False
    assert fact['expires_at_unix']==challenge.expires_at_unix
    assert (await service.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,)))['value']==before['value']
    for changed in ({'device_id':'other'},{'text':'different version'},{'parameters':{'alias':'other'}},{'action_id':'other'}):
        with pytest.raises(OwnerApprovalError):await service.original_binding_fact(challenge_id=challenge.challenge_id,**{**identity,**changed})
    with pytest.raises(OwnerApprovalError,match='expired'):
        await service.verify_and_consume(**identity,turn_id=None,project_id=None,challenge_id=challenge.challenge_id,signature_b64='unused',now_unix=challenge.expires_at_unix)
    with pytest.raises(OwnerApprovalError,match='unavailable'):
        await service.original_binding_fact(challenge_id=challenge.challenge_id,**identity)
