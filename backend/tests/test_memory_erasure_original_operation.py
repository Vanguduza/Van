"""A completed erase is an original effect, not authority to erase future memory."""
import asyncio
import json

import pytest

from tests.test_owner_memory_erasure import client,_settings,_pair,_approve,_fact
from van_gateway.context.memory_erasure import erase_memory,WITNESS_PREFIX,MemoryErasureDenied

pytestmark=pytest.mark.asyncio


async def test_completed_erase_replays_original_result_without_deleting_new_facts(client):
    ac,app,_=client;key=await _pair(ac,app);first=await _fact(app)
    body,result=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','original-erasure')
    assert result['local_execution']['removed_counts']=={'owner_facts':1}
    later=await _fact(app)
    another=await app.state.owner_fact_author.state(device_id='dev-erasure',subject='owner',
        predicate='later_memory',value='new owner instruction',scope='global')
    assert first.fact_id!=later.fact_id
    replay=await erase_memory(app.state.store,'owner_facts',body['command_id'],device_id='dev-erasure')
    assert replay=={'owner_facts':1}
    assert await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))
    assert await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(another.fact_id,))


async def test_original_erasure_witness_and_context_revision_survive_duplicate_execution(client):
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','stable-witness')
    store=app.state.store
    before=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],))
    revision=await app.state.owner_runtime.context.kernel_revision()
    rows=await asyncio.gather(*(erase_memory(store,'owner_facts',body['command_id'],device_id='dev-erasure') for _ in range(2)))
    assert rows==[{'owner_facts':1},{'owner_facts':1}]
    after=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],))
    assert before['value']==after['value']
    assert await app.state.owner_runtime.context.kernel_revision()==revision


@pytest.mark.parametrize('defect',['invalid_ids','bool_schema','foreign_device'])
async def test_unreadable_original_witness_refuses_another_erase(client,defect):
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','corrupt-original')
    store=app.state.store;later=await _fact(app)
    row=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],))
    witness=json.loads(row['value'])
    if defect=='invalid_ids':witness['tables']['owner_facts']['before_ids']=['invalid']
    elif defect=='bool_schema':witness['schema_version']=True
    else:witness['device_id']='another-device'
    raw=store.dumps(witness)
    await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(raw,WITNESS_PREFIX+body['command_id']))
    with pytest.raises(MemoryErasureDenied,match='original_witness_unreadable'):
        await erase_memory(store,'owner_facts',body['command_id'],device_id='dev-erasure')
    assert await store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))
    assert (await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],)))['value']==raw


async def test_original_record_receipt_survives_its_rows_absence(client):
    from van_gateway.understanding.records import OwnerRecords
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    target=(await OwnerRecords(app.state.store).list('owner_facts'))['records'][0]
    body,_=await _approve(ac,app,key,target['erasure']['command_text'],'original-record')
    later=await _fact(app)
    result=await erase_memory(app.state.store,'owner_facts',body['command_id'],device_id='dev-erasure',
        record_id=target['record_id'],expected_sha256=target['revision_sha256'])
    assert result=={'owner_facts':1}
    assert await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))


async def test_expired_original_receipt_is_read_only_and_never_renews_erasure_authority(client,monkeypatch):
    from van_gateway.command.authority import CommandAuthorityService
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','expired-original')
    later=await _fact(app)
    authority=await CommandAuthorityService(app.state.store).get(body['command_id'])
    monkeypatch.setattr('van_gateway.context.memory_erasure._now_ms',lambda:(authority.expires_at_unix+1)*1000)
    assert await erase_memory(app.state.store,'owner_facts',body['command_id'],device_id='dev-erasure')=={'owner_facts':1}
    assert await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))


async def test_lost_domain_reply_uses_original_commit_instead_of_erasing_later_memory(client,monkeypatch):
    ac,app,_=client;key=await _pair(ac,app);first=await _fact(app)
    async def lose_reply(*args,**kwargs):
        await erase_memory(*args,**kwargs)
        raise RuntimeError('lost domain reply after actual commit')
    monkeypatch.setattr('van_gateway.command.local_executors.erase_memory',lose_reply)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','lost-domain-reply')
    assert not await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(first.fact_id,))
    assert await app.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],))
    later=await _fact(app)
    assert await erase_memory(app.state.store,'owner_facts',body['command_id'],device_id='dev-erasure')=={'owner_facts':1}
    assert await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))


async def test_new_explicit_owner_erasure_is_separate_from_replaying_the_old_one(client):
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    first,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','first-erasure')
    later=await _fact(app)
    second,result=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','new-explicit-erasure')
    assert first['command_id']!=second['command_id']
    assert result['local_execution']['removed_counts']=={'owner_facts':1}
    assert not await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))


async def test_revoked_device_cannot_read_original_through_the_erasure_executor(client):
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','revoked-original')
    later=await _fact(app)
    await app.state.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='dev-erasure'")
    with pytest.raises(MemoryErasureDenied,match='device_revoked'):
        await erase_memory(app.state.store,'owner_facts',body['command_id'],device_id='dev-erasure')
    assert await app.state.store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))


async def test_legacy_witness_uses_its_existing_sealed_device_authority_without_reerasing(client):
    ac,app,_=client;key=await _pair(ac,app);await _fact(app)
    body,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','legacy-original')
    store=app.state.store;later=await _fact(app)
    row=await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],))
    witness=json.loads(row['value']);witness.pop('device_id')
    raw=store.dumps(witness)
    await store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(raw,WITNESS_PREFIX+body['command_id']))
    assert await erase_memory(store,'owner_facts',body['command_id'],device_id='dev-erasure')=={'owner_facts':1}
    assert await store.fetchone('SELECT fact_id FROM owner_facts WHERE fact_id=?',(later.fact_id,))
    assert (await store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(WITNESS_PREFIX+body['command_id'],)))['value']==raw
