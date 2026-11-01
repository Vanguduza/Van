"""Original permission revoke journal survives existing owner-state maintenance."""
import pytest

from test_owner_permission_revocation_recovery import client, _settings, grant, explicit_request
from van_gateway.capability.owner_permissions import REVOCATION_PREFIX
from van_gateway.context.forget import OwnerMemory
from van_gateway.ops.retention import RetentionService

pytestmark=pytest.mark.asyncio


async def test_original_revoke_receipt_survives_age_prune_and_inferred_memory_forget(client):
    ac,app,_=client
    grant_id,_=await grant(ac,app,idem='retention-original-revoke')
    request=await explicit_request(ac,grant_id)
    path='/v1/permissions/'+grant_id+'/revoke'
    original=await ac.post(path,json=request)
    assert original.status_code==200 and original.json()['state']=='APPLIED'
    key=REVOCATION_PREFIX+request['operation_id']
    before=await app.state.store.fetchone('SELECT * FROM runtime_meta WHERE key=?',(key,))
    assert before is not None
    await RetentionService(app.state.store).prune(now_ms=10**15,tables=('runtime_meta',))
    report=await OwnerMemory(app.state.store).forget_all()
    assert 'runtime_meta' not in report['removed']
    after=await app.state.store.fetchone('SELECT * FROM runtime_meta WHERE key=?',(key,))
    assert dict(after)==dict(before)
    recovered=await ac.get('/v1/permissions/'+grant_id+'/revocations/'+request['operation_id'])
    assert recovered.status_code==200 and recovered.json()==original.json()
    assert (await ac.post(path,json=request)).json()==original.json()
