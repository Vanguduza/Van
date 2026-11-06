"""OBL-002 / OBS-002 SOURCE: original HTTP → mission → real local effect owner.

SQLite/HTTP and local owner writes are real. Scheduling/crash injection and the
Hermes transport are explicitly fixtures; no native Hermes/phone qualification.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import time

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.context.models import ContextRequirement
from van_gateway.idempotency.service import IdempotencyConflict
from van_gateway.models import CommandRequest, OriginChannel
from test_ingress_trust_boundary import TestGatewayEnforcement as _Signer


class SourceCrash(BaseException):
    """Interrupt an awaited boundary; not a claim of native process death."""


@pytest.fixture(autouse=True)
def configured(tmp_path, monkeypatch):
    values = {'VAN_DATABASE_PATH': str(tmp_path/'original.sqlite3'),
        'VAN_VATI_LEDGER_PATH': str(tmp_path/'vati.sqlite3'),
        'VAN_HERMES_BASE_URL': 'http://SOURCE.invalid',
        'VAN_GOOGLE_TOKEN_FERNET_KEY': Fernet.generate_key().decode(),
        'VAN_DEVICE_SECRET_FERNET_KEY': Fernet.generate_key().decode(),
        'VAN_INGRESS_TOKEN': 'SOURCE-original-ingress-0123456789',
        'VAN_INTERNAL_CONTROL_TOKEN': 'SOURCE-internal',
        'VAN_DEVICE_ENROLMENT_TOKEN': 'SOURCE-enrol', 'VAN_SCHEDULER_ENABLED':'false'}
    for k,v in values.items(): monkeypatch.setenv(k,v)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@asynccontextmanager
async def running(monkeypatch, token=None, posts=None):
    app=create_app()
    async def health(): return {'ok': True, 'profile':'van'}
    async def dispatch(text, metadata=None):
        if posts is not None: posts.append(metadata)
        return {'id': 'SOURCE-original-run'}
    monkeypatch.setattr(app.state.orchestrator.hermes,'health',health)
    monkeypatch.setattr(app.state.orchestrator.hermes,'create_run',dispatch)
    async with app.router.lifespan_context(app):
        headers={'X-Van-Ingress-Token':'SOURCE-original-ingress-0123456789'}
        if token: headers['X-Van-Device-Token']=token
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://SOURCE',headers=headers) as client:
            yield client,app


async def pair(client,app,device='SOURCE-original-device'):
    ticket=await app.state.auth.create_pairing_ticket(device)
    p=await app.state.auth.pair_device(ticket.token,device,'SOURCE-secret','PEM','SOURCE')
    client.headers['X-Van-Device-Token']=p.access_token
    return p.access_token


async def signed(app, text='help organize my work',suffix=''):
    return await _Signer()._signed(app,'SOURCE-original-device','SOURCE-secret',text=text,channel=OriginChannel.UI,suffix=suffix)


async def age(app,body):
    await app.state.store.execute('UPDATE idempotency SET updated_at_unix=? WHERE idempotency_key=?',
        (int(time.time())-1000,body['idempotency_key']))


@pytest.mark.asyncio
@pytest.mark.parametrize('late',[False,True])
async def test_live_stale_contender_preserves_original_receipt_and_one_dispatch(monkeypatch,late):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c1,a1):
        token=await pair(c1,a1);body=await signed(a1)
        async with running(monkeypatch,token,posts) as (c2,a2):
            assert a1.state.store is not a2.state.store
            both=asyncio.Event();first=asyncio.Event();reads=0
            for app in (a1,a2):
                original=app.state.orchestrator.missions.existing_for_command
                def lookup(fn):
                    async def read(cid):
                        nonlocal reads
                        result=await fn(cid)
                        if cid==body['command_id']:
                            reads+=1
                            if reads<=2:
                                assert result is None
                                first.set()
                                if reads==2: both.set()
                                await asyncio.wait_for(both.wait(),10)
                        return result
                    return read
                monkeypatch.setattr(app.state.orchestrator.missions,'existing_for_command',lookup(original))
                if late:
                    seal=app.state.orchestrator.authority.seal
                    def delay(fn,store):
                        async def wrapped(record):
                            try:return await fn(record)
                            except Exception:
                                async with asyncio.timeout(10):
                                    while True:
                                        row=await store.fetchone('SELECT status,response_json FROM idempotency WHERE idempotency_key=?',(body['idempotency_key'],))
                                        if row and row['status']=='COMPLETED' and json.loads(row['response_json'])['status']=='accepted':break
                                        await asyncio.sleep(.01)
                                raise
                        return wrapped
                    monkeypatch.setattr(app.state.orchestrator.authority,'seal',delay(seal,app.state.store))
            t=asyncio.create_task(c1.post('/v1/commands',json=body))
            await asyncio.wait_for(first.wait(),10);await age(a1,body)
            responses=await asyncio.wait_for(asyncio.gather(t,c2.post('/v1/commands',json=body)),30)
            results=[r.json() for r in responses]
            assert all(r.status_code==200 for r in responses)
            assert {x['status'] for x in results} <= {'accepted','in_flight'}
            original=next(x for x in results if x['status']=='accepted')
            assert len({x['mission_id'] for x in results})==1
            assert len({x['context_snapshot_id'] for x in results})==1
            assert len(posts)==1
            assert (await c1.post('/v1/commands',json=body)).json()==original
            assert len(await a1.state.store.fetchall('SELECT mission_id FROM missions'))==1
            assert (await a1.state.store.fetchone('SELECT claim_count FROM idempotency'))['claim_count']==2


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary',['written','verified'])
async def test_real_memory_effect_survives_restart_without_a_second_owner_write(monkeypatch,boundary):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        token=await pair(c,a);body=await signed(a,'remember that my accountant is Thandi')
        if boundary=='written':
            write=a.state.owner_fact_author.state
            async def interrupted(**kwargs):
                await write(**kwargs)
                raise SourceCrash('after committed OwnerFactAuthor write before execution receipt')
            monkeypatch.setattr(a.state.owner_fact_author,'state',interrupted)
        else:
            publish=a.state.orchestrator._publish_original
            async def interrupted(req,result,**kwargs):
                if result.status=='accepted':raise SourceCrash('after owned verification/audit before gateway result publication')
                return await publish(req,result,**kwargs)
            monkeypatch.setattr(a.state.orchestrator,'_publish_original',interrupted)
        with pytest.raises((SourceCrash, BaseExceptionGroup)) as raised:
            await c.post('/v1/commands',json=body)
        def leaves(error):
            return [leaf for child in error.exceptions for leaf in leaves(child)] if isinstance(error,BaseExceptionGroup) else [error]
        # Starlette also reports the exact missing-response collateral from the
        # deliberately interrupted ASGI request; no other failure is accepted.
        errors=leaves(raised.value)
        assert sum(isinstance(error,SourceCrash) for error in errors)==1
        assert all(isinstance(error,SourceCrash) or
            (type(error) is RuntimeError and str(error)=="No response returned.") for error in errors)
        facts=await a.state.store.fetchall('SELECT * FROM owner_facts')
        assert len(facts)==1
        original_fact=dict(facts[0]);mission=await a.state.orchestrator.missions.existing_for_command(body['command_id'])
        execution=await a.state.store.fetchone('SELECT execution_id FROM action_executions WHERE command_id=?',(body['command_id'],))
        await age(a,body)
    # New app, AuthService, Store and mission/action owners read the original file.
    async with running(monkeypatch,token,posts) as (c,a):
        recovered=(await c.post('/v1/commands',json=body)).json()
        assert recovered['status']==('outcome_unknown' if boundary=='written' else 'accepted')
        assert recovered['mission_id']==mission.mission_id
        if boundary=='verified':assert recovered['execution_id']==execution['execution_id']
        assert [dict(x) for x in await a.state.store.fetchall('SELECT * FROM owner_facts')]==[original_fact]
        independent=await a.state.owner_runtime.context.current_candidates(ContextRequirement(subject='OWNER',predicate='accountant',scope='global'))
        assert len(independent)==1 and independent[0].fact_id==original_fact['fact_id'] and independent[0].value=='Thandi'
        assert (await c.post('/v1/commands',json=body)).json()==recovered
        read=(await c.get('/v1/commands/'+body['command_id'])).json()
        assert read['mission_id']==mission.mission_id
        assert len(await a.state.store.fetchall('SELECT mission_id FROM missions'))==1
        assert len(await a.state.store.fetchall('SELECT execution_id FROM action_executions'))==1
        assert posts==[]


@pytest.mark.asyncio
async def test_late_denial_unknown_and_failure_cannot_replace_accepted_history(monkeypatch):
    async with running(monkeypatch) as (c,a):
        await pair(c,a);body=await signed(a);original=(await c.post('/v1/commands',json=body)).json()
        payload=CommandRequest(**body).model_dump()
        for state in ('denied','in_flight','outcome_unknown'):
            late=dict(original,status=state,hermes_run_id=None,context_snapshot_id='foreign-snapshot')
            assert await a.state.orchestrator.idempotency.publish_original(body['idempotency_key'],payload,late)==original
            assert await a.state.orchestrator.idempotency.publish_original(body['idempotency_key'],payload,late,failed=True)==original
        assert (await c.post('/v1/commands',json=body)).json()==original
        with pytest.raises(IdempotencyConflict):
            await a.state.orchestrator.idempotency.publish_original(body['idempotency_key'],dict(payload,text='different intent'),original)


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['command_id','context_snapshot_id','hermes_run_id','json'])
async def test_corrupt_original_receipt_is_held_not_replaced(monkeypatch,field):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        await pair(c,a);body=await signed(a);response=(await c.post('/v1/commands',json=body)).json()
        response[field]='foreign'
        corrupt='broken-json' if field=='json' else json.dumps(response)
        await a.state.store.execute('UPDATE idempotency SET response_json=? WHERE idempotency_key=?',(corrupt,body['idempotency_key']))
        payload=CommandRequest(**body).model_dump()
        with pytest.raises(IdempotencyConflict):await a.state.orchestrator.idempotency.read_original(body['idempotency_key'],payload)
        unresolved=await c.post('/v1/commands',json=body)
        assert unresolved.status_code==200 and unresolved.json()['status']=='outcome_unknown'
        assert unresolved.json()['command_id']==body['command_id']
        assert (await a.state.store.fetchone('SELECT response_json FROM idempotency'))['response_json']==corrupt
        assert len(posts)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['fact','audit'])
async def test_missing_original_local_evidence_holds_without_fabricating_denial(monkeypatch,damage):
    async with running(monkeypatch) as (c,a):
        token=await pair(c,a);body=await signed(a,'remember that my accountant is Thandi')
        original=(await c.post('/v1/commands',json=body)).json()
        assert original['status']=='accepted'
        await a.state.store.execute("UPDATE idempotency SET status='IN_FLIGHT',response_json=NULL WHERE idempotency_key=?",(body['idempotency_key'],))
        if damage=='fact':await a.state.store.execute("UPDATE owner_facts SET value_json=?",(json.dumps('corrupted-value'),))
        else:await a.state.store.execute('DELETE FROM audit WHERE id=?',(original['evidence_id'],))
        await age(a,body)
        facts=[dict(x) for x in await a.state.store.fetchall('SELECT * FROM owner_facts')]
    async with running(monkeypatch,token) as (c,a):
        held=(await c.post('/v1/commands',json=body)).json()
        assert held['status']=='outcome_unknown' and held['mission_id']==original['mission_id']
        assert [dict(x) for x in await a.state.store.fetchall('SELECT * FROM owner_facts')]==facts
        assert len(await a.state.store.fetchall('SELECT execution_id FROM action_executions'))==1


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['revoke','cancel','expire'])
async def test_current_owner_mission_and_expiry_rechecked_after_health_before_dispatch(monkeypatch,change):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        await pair(c,a);body=await signed(a)
        async def health():
            if change=='revoke':await a.state.auth.revoke(body['device_id'])
            elif change=='cancel':
                mission=await a.state.orchestrator.missions.existing_for_command(body['command_id'])
                assert (await c.post('/v1/missions/'+mission.mission_id+'/cancel')).status_code==200
            else:
                future=body['issued_at_unix']+a.state.orchestrator.owner_intent_max_age_seconds+1
                monkeypatch.setattr('van_gateway.orchestrator.time.time',lambda:future)
            return {'ok':True,'profile':'van'}
        monkeypatch.setattr(a.state.orchestrator.hermes,'health',health)
        result=(await c.post('/v1/commands',json=body)).json()
        assert result['status']==('expired' if change=='expire' else 'denied')
        assert posts==[]
        assert await a.state.store.fetchone('SELECT key FROM runtime_meta WHERE key=?',('command_run_receipt:'+body['command_id'],)) is None


@pytest.mark.asyncio
async def test_current_foreign_device_cannot_retarget_original_command_history(monkeypatch):
    async with running(monkeypatch) as (c,a):
        await pair(c,a);body=await signed(a)
        original=(await c.post('/v1/commands',json=body)).json()
        await pair(c,a,'SOURCE-other-device')
        denied=await c.post('/v1/commands',json=body)
        assert denied.status_code in {401,403}
        payload=CommandRequest(**body).model_dump()
        assert await a.state.orchestrator.idempotency.read_original(body['idempotency_key'],payload)==original


@pytest.mark.asyncio
async def test_two_safe_recoveries_use_one_atomic_dispatch_claim(monkeypatch):
    from van_gateway.hermes.bridge import HermesBridgeError
    posts=[]
    async with running(monkeypatch,posts=posts) as (c1,a1):
        token=await pair(c1,a1);body=await signed(a1)
        async def rejected(text,metadata=None):raise HermesBridgeError('hermes_reject','SOURCE definitive no acceptance',retry_safe=True)
        monkeypatch.setattr(a1.state.orchestrator.hermes,'create_run',rejected)
        assert (await c1.post('/v1/commands',json=body)).json()['status']=='degraded'
        async with running(monkeypatch,token,posts) as (c2,a2):
            both=asyncio.Event();first=asyncio.Event();observations=0
            async def health():
                nonlocal observations
                observations+=1;first.set()
                if observations==2:both.set()
                await asyncio.wait_for(both.wait(),10)
                return {'ok':True,'profile':'van'}
            async def accepted(text,metadata=None):
                posts.append(metadata)
                return {'id':'SOURCE-original-run'}
            for a in (a1,a2):
                monkeypatch.setattr(a.state.orchestrator.hermes,'health',health)
                monkeypatch.setattr(a.state.orchestrator.hermes,'create_run',accepted)
            t=asyncio.create_task(c1.post('/v1/commands',json=body))
            await asyncio.wait_for(first.wait(),10);await age(a1,body)
            responses=await asyncio.wait_for(asyncio.gather(t,c2.post('/v1/commands',json=body)),30)
            values=[x.json() for x in responses]
            assert all(x.status_code==200 for x in responses)
            assert {x['status'] for x in values}<={'accepted','outcome_unknown'}
            assert len(posts)==1
            assert len({x['mission_id'] for x in values})==len({x['context_snapshot_id'] for x in values})==1
            assert (await c1.post('/v1/commands',json=body)).json()['status']=='accepted'
            assert (await a1.state.store.fetchone('SELECT claim_count FROM idempotency'))['claim_count']==3


@pytest.mark.asyncio
async def test_verified_live_memory_worker_and_recovery_publish_the_same_original(monkeypatch):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c1,a1):
        token=await pair(c1,a1);body=await signed(a1,'remember that my accountant is Thandi')
        reached=asyncio.Event();release=asyncio.Event();publish=a1.state.orchestrator._publish_original
        async def pause(req,result,**kwargs):
            if result.status=='accepted':
                reached.set();await asyncio.wait_for(release.wait(),15)
            return await publish(req,result,**kwargs)
        monkeypatch.setattr(a1.state.orchestrator,'_publish_original',pause)
        first=asyncio.create_task(c1.post('/v1/commands',json=body))
        try:
            await asyncio.wait_for(reached.wait(),15);await age(a1,body)
            async with running(monkeypatch,token,posts) as (c2,a2):
                recovered=(await c2.post('/v1/commands',json=body)).json()
                assert recovered['status']=='accepted'
                release.set();original=(await asyncio.wait_for(first,15)).json()
                assert original==recovered
                facts=await a2.state.owner_runtime.context.current_candidates(ContextRequirement(subject='OWNER',predicate='accountant',scope='global'))
                assert len(facts)==1 and facts[0].value=='Thandi'
                assert len(await a2.state.store.fetchall('SELECT execution_id FROM action_executions'))==1
                assert len(await a2.state.store.fetchall('SELECT mission_id FROM missions'))==1
                assert posts==[]
        finally:
            release.set()
            if not first.done():await asyncio.gather(first,return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['json','missing','foreign'])
async def test_ambiguous_original_run_evidence_cannot_become_authority(monkeypatch,bad):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        await pair(c,a);body=await signed(a);original=(await c.post('/v1/commands',json=body)).json()
        await a.state.store.execute("UPDATE idempotency SET status='IN_FLIGHT',response_json=NULL WHERE idempotency_key=?",(body['idempotency_key'],))
        data='broken-json' if bad=='json' else json.dumps({} if bad=='missing' else {'id':'SOURCE-foreign-run'})
        await a.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(data,'command_run_receipt:'+body['command_id']))
        await age(a,body)
        result=(await c.post('/v1/commands',json=body)).json()
        assert result['status']=='outcome_unknown' and result['mission_id']==original['mission_id']
        assert (await a.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('command_run_receipt:'+body['command_id'],)))['value']==data
        assert len(posts)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['owner', 'source', 'envelope', 'mission_scope', 'snapshot_source', 'snapshot_digest'])
async def test_r2_dispatch_writer_binds_exact_original_subject_after_health(monkeypatch, damage):
    posts=[]
    async with running(monkeypatch, posts=posts) as (c,a):
        await pair(c,a); body=await signed(a)
        async def health():
            if damage=='owner':
                await a.state.store.execute("UPDATE missions SET owner_principal_id='device:foreign'")
            elif damage in {'source','envelope','mission_scope'}:
                row=await a.state.store.fetchone('SELECT authority_envelope_json FROM missions')
                value=json.loads(row['authority_envelope_json'])
                if damage=='mission_scope': value['requires_owner_presence']=not value['requires_owner_presence']
                else: value['source_command_id']='foreign'
                await a.state.store.execute('UPDATE missions SET authority_envelope_json=?',
                    ('[]' if damage=='envelope' else json.dumps(value),))
            elif damage=='snapshot_source':
                await a.state.store.execute("UPDATE context_snapshots SET command_id='foreign'")
            else:
                await a.state.store.execute("UPDATE context_snapshots SET digest='foreign'")
            return {'ok':True,'profile':'van'}
        monkeypatch.setattr(a.state.orchestrator.hermes,'health',health)
        response=await c.post('/v1/commands',json=body)
        assert response.status_code==200 and response.json()['status'] in {'denied','outcome_unknown'}
        assert posts==[]
        assert not await a.state.store.fetchall('SELECT * FROM hermes_run_bindings')


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['mission_array', 'mission_source', 'run_array', 'run_identity'])
async def test_r2_completed_nested_corruption_retains_original_bytes_without_dispatch(monkeypatch, damage):
    posts=[]
    async with running(monkeypatch, posts=posts) as (c,a):
        await pair(c,a); body=await signed(a)
        original=(await c.post('/v1/commands',json=body)).json(); assert original['status']=='accepted'
        if damage.startswith('mission'):
            row=await a.state.store.fetchone('SELECT authority_envelope_json FROM missions')
            value=json.loads(row['authority_envelope_json']); value['source_command_id']='foreign'
            raw='[]' if damage=='mission_array' else json.dumps(value)
            await a.state.store.execute('UPDATE missions SET authority_envelope_json=?',(raw,))
            table,column='missions','authority_envelope_json'
        else:
            raw='[]' if damage=='run_array' else json.dumps({'id':[]})
            await a.state.store.execute("UPDATE runtime_meta SET value=? WHERE key=?",(raw,'command_run_receipt:'+body['command_id']))
            table,column='runtime_meta','value'
        cached=(await a.state.store.fetchone('SELECT response_json FROM idempotency'))['response_json']
        response=await c.post('/v1/commands',json=body)
        assert response.status_code==200 and response.json()['status']=='outcome_unknown'
        assert (await a.state.store.fetchone('SELECT response_json FROM idempotency'))['response_json']==cached
        if table=='missions': assert (await a.state.store.fetchone('SELECT authority_envelope_json FROM missions'))[column]==raw
        else: assert (await a.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',('command_run_receipt:'+body['command_id'],)))['value']==raw
        assert len(posts)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['observation_array','fact_identity','audit_array','audit_local'])
async def test_r2_verified_memory_nested_corruption_survives_restart_without_second_write(monkeypatch, damage):
    async with running(monkeypatch) as (c,a):
        token=await pair(c,a); body=await signed(a,'remember that my accountant is Thandi')
        publish=a.state.orchestrator._publish_original
        async def interrupted(req,result,**kwargs):
            if result.status=='accepted': raise SourceCrash('verified original before publication')
            return await publish(req,result,**kwargs)
        monkeypatch.setattr(a.state.orchestrator,'_publish_original',interrupted)
        with pytest.raises((SourceCrash,BaseExceptionGroup)): await c.post('/v1/commands',json=body)
        if damage.startswith('observation') or damage=='fact_identity':
            raw='[]' if damage=='observation_array' else json.dumps({'fact_id':[]})
            await a.state.store.execute('UPDATE action_receipts SET observed_postcondition_json=?',(raw,))
        else:
            row=await a.state.store.fetchone("SELECT after_json FROM audit WHERE result='accepted' AND model_delegate='gateway:local'")
            value=json.loads(row['after_json']); value['local_execution']=[]
            raw='[]' if damage=='audit_array' else json.dumps(value)
            await a.state.store.execute("UPDATE audit SET after_json=? WHERE result='accepted' AND model_delegate='gateway:local'",(raw,))
        facts=[dict(row) for row in await a.state.store.fetchall('SELECT * FROM owner_facts')]
        await age(a,body)
    async with running(monkeypatch,token) as (c,a):
        response=await c.post('/v1/commands',json=body)
        assert response.status_code==200 and response.json()['status']=='outcome_unknown'
        assert [dict(row) for row in await a.state.store.fetchall('SELECT * FROM owner_facts')]==facts
        assert len(await a.state.store.fetchall('SELECT * FROM action_executions'))==1
        if damage.startswith('observation') or damage=='fact_identity':
            assert (await a.state.store.fetchone('SELECT observed_postcondition_json FROM action_receipts'))['observed_postcondition_json']==raw
        else:
            assert (await a.state.store.fetchone("SELECT after_json FROM audit WHERE result='accepted' AND model_delegate='gateway:local'"))['after_json']==raw


@pytest.mark.asyncio
async def test_r2_explicit_missionless_constructor_preserves_supported_dispatch(monkeypatch):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        await pair(c,a); a.state.orchestrator.missions=None
        body=await signed(a); response=await c.post('/v1/commands',json=body)
        assert response.status_code==200 and response.json()['status']=='accepted'
        assert response.json()['mission_id'] is None and len(posts)==1
        assert not await a.state.store.fetchall('SELECT * FROM missions')


@pytest.mark.asyncio
async def test_r2_legacy_original_run_binding_uses_existing_owned_event(monkeypatch):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        await pair(c,a); body=await signed(a)
        original=(await c.post('/v1/commands',json=body)).json(); assert original['status']=='accepted'
        await a.state.store.execute('DELETE FROM hermes_run_bindings')
        assert (await c.post('/v1/commands',json=body)).json()==original
        assert len(posts)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['authority_array','resolution_array','context_subject','authority_subject'])
async def test_r2_completed_authority_corruption_never_rewrites_original_receipt(monkeypatch, damage):
    posts=[]
    async with running(monkeypatch,posts=posts) as (c,a):
        await pair(c,a); body=await signed(a)
        original=(await c.post('/v1/commands',json=body)).json(); assert original['status']=='accepted'
        key='command_authority:'+body['command_id']
        row=await a.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,))
        value=json.loads(row['value'])
        if damage=='resolution_array': value['dispatch_metadata']['typed_resolution']=[]
        elif damage=='context_subject': value['dispatch_metadata']['canonical_context']['snapshot_id']='foreign'
        elif damage=='authority_subject': value['command_id']='foreign'
        raw='[]' if damage=='authority_array' else json.dumps(value)
        await a.state.store.execute('UPDATE runtime_meta SET value=? WHERE key=?',(raw,key))
        cached=(await a.state.store.fetchone('SELECT response_json FROM idempotency'))['response_json']
        response=await c.post('/v1/commands',json=body)
        assert response.status_code==200 and response.json()['status']=='outcome_unknown'
        assert (await a.state.store.fetchone('SELECT value FROM runtime_meta WHERE key=?',(key,)))['value']==raw
        assert (await a.state.store.fetchone('SELECT response_json FROM idempotency'))['response_json']==cached
        assert len(posts)==1
