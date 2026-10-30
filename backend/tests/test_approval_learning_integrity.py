"""Approval learning requires actual sealed source identity, never a requirement flag."""
import asyncio,time
import pytest
from conftest_automation import make_store
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.service import MissionService
from van_gateway.mission.models import MissionOrigin,AuthorityEnvelope
from van_gateway.models import ActionClass,OriginChannel,PrincipalType
from van_gateway.command.authority import CommandAuthorityRecord,CommandAuthorityService

async def native_mission(store,source='cmd-approval-source'):
    return await MissionService(store).create(owner_principal_id='device:dev-source',origin=MissionOrigin.OWNER_UI,
        origin_channel=OriginChannel.UI,title='Review owner choice',goal='Keep the account disabled',
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4,requires_owner_presence=True,source_command_id=source))

async def seal(store,**changes):
    from van_gateway.context.service import OwnerContextService
    snapshot=await OwnerContextService(store).compile_snapshot(changes.get('command_id','cmd-approval-source'),[])
    now=int(time.time())
    fields=dict(command_id='cmd-approval-source',device_id='dev-source',principal_type=PrincipalType.OWNER_DEVICE,
        requested_by='owner',origin_channel=OriginChannel.UI,signed_action_class=ActionClass.A4,effective_action_class=ActionClass.A4,
        snapshot_id=snapshot.snapshot_id,context_digest=snapshot.digest,issued_at_unix=now,sealed_at_unix_ms=now*1000,
        owner_approved=True,request_hash='d'*64)
    fields.update(changes);record=CommandAuthorityRecord(**fields)
    return await CommandAuthorityService(store).seal(record)

@pytest.mark.asyncio
async def test_owner_presence_requirement_does_not_prove_an_approval(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);feed=LearningFeed(store)
    await feed.record_mission_opened(mission)
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')

@pytest.mark.asyncio
async def test_replaying_one_native_approved_source_cannot_create_extra_decisions(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store);feed=LearningFeed(store)
    await feed.record_mission_opened(mission)
    await feed.record_mission_opened(mission)
    await feed.record_mission_opened(mission)
    rows=await store.fetchall('SELECT * FROM decision_fingerprints')
    assert len(rows)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('changes',[
    {'owner_approved':False},{'device_id':'different-device'},{'principal_type':PrincipalType.HERMES_AGENT},
    {'effective_action_class':ActionClass.A2},{'origin_channel':OriginChannel.SYSTEM_EVENT},{'request_hash':None},
    {'authority_source':'STANDING_AUTOMATION'},
])
async def test_unapproved_foreign_or_automation_sources_cannot_become_owner_choices(tmp_path,changes):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store,**changes)
    assert await LearningFeed(store).record_owner_approval(mission) is None
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')

@pytest.mark.asyncio
async def test_one_source_is_projected_once_under_concurrent_reads_and_after_original_outcome(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store)
    feed=LearningFeed(store)
    ids=await asyncio.gather(*(feed.record_owner_approval(mission) for _ in range(6)))
    assert len(set(ids))==1 and ids[0] is not None
    await feed.fingerprints.record_outcome(ids[0],outcome='failed',reassessment='Observed task failure')
    again=await feed.record_owner_approval(mission,now_ms=1)
    assert again==ids[0]
    rows=await store.fetchall('SELECT * FROM decision_fingerprints')
    assert len(rows)==1 and rows[0]['outcome']=='failed' and rows[0]['reassessment']=='Observed task failure'
    assert rows[0]['inferred_reason'] is None

@pytest.mark.asyncio
async def test_stale_or_fabricated_caller_presentation_is_not_canonical_owner_evidence(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store)
    fake=mission.model_copy(update={'goal':'Invented instruction','mission_class':'INVENTED'})
    result=await LearningFeed(store).record_owner_approval(fake)
    row=await store.fetchone('SELECT * FROM decision_fingerprints WHERE decision_id=?',(result,))
    assert row['owner_choice']=='approved: Keep the account disabled'
    assert 'INVENTED' not in row['context_json']

@pytest.mark.asyncio
async def test_typed_escalation_keeps_original_signed_class_without_discarding_verified_approval(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store,signed_action_class=ActionClass.A1)
    result=await LearningFeed(store).record_owner_approval(mission)
    assert result is not None
    row=await store.fetchone('SELECT * FROM decision_fingerprints WHERE decision_id=?',(result,))
    assert '"signed_action_class":"A1"' in row['context_json']

@pytest.mark.asyncio
@pytest.mark.parametrize('defect',['missing','different_command','different_digest'])
async def test_owner_choice_requires_the_exact_native_sealed_context(tmp_path,defect):
    store=await make_store(tmp_path);mission=await native_mission(store);record=await seal(store)
    if defect=='missing':await store.execute('DELETE FROM context_snapshots WHERE snapshot_id=?',(record.snapshot_id,))
    elif defect=='different_command':await store.execute('UPDATE context_snapshots SET command_id=? WHERE snapshot_id=?',('foreign-source',record.snapshot_id))
    else:await store.execute('UPDATE context_snapshots SET digest=? WHERE snapshot_id=?',('e'*64,record.snapshot_id))
    assert await LearningFeed(store).record_owner_approval(mission) is None
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')

@pytest.mark.asyncio
async def test_authorized_command_join_observes_approval_after_capture_and_seal(tmp_path):
    from van_gateway.command.mission_link import CommandMissionLink
    store=await make_store(tmp_path);feed=LearningFeed(store);missions=MissionService(store,learning=feed)
    mission=await native_mission(store)
    await feed.record_mission_opened(mission)
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')
    await seal(store)
    join=CommandMissionLink(missions)
    mission=await join.understood(mission,summary='fixture interpretation')
    mission=await join.planned(mission,summary='fixture plan')
    mission=await join.authorized(mission,summary='actual native seal observed')
    await join.authorized(mission,summary='same original seal observed again')
    rows=await store.fetchall('SELECT * FROM decision_fingerprints')
    assert len(rows)==1 and rows[0]['mission_id']==mission.mission_id

@pytest.mark.asyncio
async def test_failed_projection_rolls_back_without_changing_sealed_authority_and_recovers(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);record=await seal(store);feed=LearningFeed(store)
    await store.execute("CREATE TRIGGER fixture_no_approval_projection BEFORE INSERT ON decision_fingerprints BEGIN SELECT RAISE(ABORT,'projection unavailable'); END")
    with pytest.raises(Exception,match='projection unavailable'):await feed.record_owner_approval(mission)
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')
    assert await CommandAuthorityService(store).get(record.command_id)==record
    await store.execute('DROP TRIGGER fixture_no_approval_projection')
    assert await feed.record_owner_approval(mission) is not None

@pytest.mark.asyncio
async def test_lost_projection_commit_ack_replays_original_without_resetting_outcome(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store);feed=LearningFeed(store)
    connection=store.connection;armed=True
    @asynccontextmanager
    async def uncertain():
        async with connection() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def commit(self):
                    nonlocal armed
                    await db.commit()
                    if armed:armed=False;raise OSError('projection commit acknowledgement lost')
            yield Connection()
    monkeypatch.setattr(store,'connection',uncertain)
    with pytest.raises(OSError,match='projection commit acknowledgement lost'):await feed.record_owner_approval(mission)
    original=await store.fetchone('SELECT * FROM decision_fingerprints');assert original is not None
    await feed.fingerprints.record_outcome(original['decision_id'],outcome='failed')
    assert await feed.record_owner_approval(mission)==original['decision_id']
    rows=await store.fetchall('SELECT * FROM decision_fingerprints')
    assert len(rows)==1 and rows[0]['outcome']=='failed'

@pytest.mark.asyncio
@pytest.mark.parametrize('witness',['{}','[]','{','{"tables":{"decision_fingerprints":{}}}'])
async def test_unreadable_native_erasure_witness_cannot_be_ignored_to_relearn(tmp_path,witness):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store)
    await store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES('memory_erasure_witness:fixture',?,0)",(witness,))
    with pytest.raises(ValueError,match='memory_erasure_source_witness_unreadable'):
        await LearningFeed(store).record_owner_approval(mission)
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')

@pytest.mark.asyncio
async def test_changed_native_goal_cannot_relabel_an_original_approval_projection(tmp_path):
    store=await make_store(tmp_path);mission=await native_mission(store);await seal(store);feed=LearningFeed(store)
    identity=await feed.record_owner_approval(mission)
    original=dict(await store.fetchone('SELECT * FROM decision_fingerprints WHERE decision_id=?',(identity,)))
    await store.execute('UPDATE missions SET goal=? WHERE mission_id=?',('Changed owner instruction',mission.mission_id))
    with pytest.raises(ValueError,match='DECISION_PROJECTION_SCOPE_CONFLICT'):await feed.record_owner_approval(mission)
    assert dict(await store.fetchone('SELECT * FROM decision_fingerprints WHERE decision_id=?',(identity,)))==original
