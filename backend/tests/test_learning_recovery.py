"""Learning recovery uses one real native outcome, never delivery count or caller claims."""
from __future__ import annotations
import asyncio
import pytest
from conftest_automation import make_store
from van_gateway.learning.feed import LearningFeed
from van_gateway.mission.models import AuthorityEnvelope,MissionOrigin,MissionState
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass,OriginChannel

async def failed_mission(store, *, goal='Original native work'):
    service=MissionService(store)
    mission=await service.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_UI,
        origin_channel=OriginChannel.UI,title='Learning source',goal=goal,mission_class='NATIVE_TASK',
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2))
    for state in [MissionState.UNDERSTOOD,MissionState.PLANNED,MissionState.AUTHORIZED,MissionState.RUNNING]:
        mission=await service.transition(mission.mission_id,target=state)
    await service.add_activity(mission_id=mission.mission_id,activity_type='WORK',capability_id='native-task',executor='HERMES')
    return await service.transition(mission.mission_id,target=MissionState.FAILED)

@pytest.mark.asyncio
async def test_replayed_original_strategy_outcome_is_one_sample(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store);feed=LearningFeed(store)
    first=await feed.record_strategy_outcome(mission,state=mission.state)
    second=await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
    rows=await store.fetchall('SELECT * FROM execution_strategies')
    assert first==second and len(rows)==1 and rows[0]['failure_count']==1

@pytest.mark.asyncio
async def test_concurrent_original_strategy_delivery_has_one_identity_and_one_sample(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store)
    ids=await asyncio.gather(*(LearningFeed(store).record_strategy_outcome(mission,state=mission.state) for _ in range(6)))
    rows=await store.fetchall('SELECT * FROM execution_strategies')
    assert len(set(ids))==1 and len(rows)==1 and rows[0]['failure_count']==1

@pytest.mark.asyncio
async def test_a_claimed_success_cannot_replace_the_native_failed_outcome(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store)
    with pytest.raises(ValueError,match='LEARNING_NATIVE_OUTCOME_CONFLICT'):
        await LearningFeed(store).record_strategy_outcome(mission,state=MissionState.VERIFIED_SUCCESS)
    assert not await store.fetchall('SELECT * FROM execution_strategies')

@pytest.mark.asyncio
async def test_a_caller_cannot_replace_the_original_native_strategy_class_or_ceiling(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store)
    stale=mission.model_copy(update={'mission_class':'FAKE_TASK','authority_envelope':AuthorityEnvelope(max_action_class=ActionClass.A5)})
    await LearningFeed(store).record_strategy_outcome(stale,state=mission.state)
    row=await store.fetchone('SELECT * FROM execution_strategies')
    assert row['mission_class']=='NATIVE_TASK' and row['max_action_class']=='A2'


@pytest.mark.asyncio
async def test_a_restart_repairs_all_original_terminal_learning_without_rerunning_work(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store)
    assert len(await store.fetchall("SELECT * FROM mission_learning_outbox")) == 4
    restarted=MissionService(type(store)(store.path), learning=LearningFeed(type(store)(store.path)))
    assert await restarted.reconcile_learning_projections() == 4
    assert await restarted.reconcile_learning_projections() == 0
    outcome=await store.fetchone("SELECT * FROM learning_outcomes WHERE mission_id=?", (mission.mission_id,))
    assert outcome['outcome_kind']=='failed' and outcome['recorded_at_ms']==mission.updated_at_ms
    strategy=await store.fetchone("SELECT * FROM execution_strategies")
    assert strategy['failure_count']==1 and strategy['success_count']==0
    assert not await store.fetchall("SELECT * FROM mission_learning_outbox")
    assert (await restarted.get(mission.mission_id)).state is MissionState.FAILED

@pytest.mark.asyncio
async def test_a_lost_strategy_delivery_ack_retries_the_original_sample_once(tmp_path,monkeypatch):
    store=await make_store(tmp_path);mission=await failed_mission(store)
    service=MissionService(store,learning=LearningFeed(store));original=service._ack_learning
    async def lost(mission_id,stage,**kw):
        if stage=='STRATEGY_OUTCOME':raise OSError('fixture-private-lost-ack')
        await original(mission_id,stage,**kw)
    monkeypatch.setattr(service,'_ack_learning',lost)
    await service.reconcile_learning_projections()
    pending=await store.fetchall("SELECT * FROM mission_learning_outbox")
    assert len(pending)==1 and pending[0]['stage']=='STRATEGY_OUTCOME'
    assert pending[0]['last_failure']=='OSError' and pending[0]['attempts']==1
    restarted=MissionService(type(store)(store.path),learning=LearningFeed(type(store)(store.path)))
    assert await restarted.reconcile_learning_projections()==1
    assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==1

@pytest.mark.asyncio
async def test_receipt_failure_rolls_back_the_strategy_identity_and_counter(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store)
    await store.execute("CREATE TRIGGER reject_strategy_source BEFORE INSERT ON mission_strategy_observations BEGIN SELECT RAISE(ABORT,'original source unavailable'); END")
    with pytest.raises(Exception,match='original source unavailable'):
        await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
    assert not await store.fetchall('SELECT * FROM execution_strategies')
    assert not await store.fetchall('SELECT * FROM mission_strategy_observations')
    await store.execute('DROP TRIGGER reject_strategy_source')
    await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
    assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==1

@pytest.mark.asyncio
async def test_replayed_native_outcome_preserves_a_later_owner_reassessment(tmp_path):
    from van_gateway.understanding.memory import DecisionFingerprints
    store=await make_store(tmp_path);mission=await failed_mission(store);feed=LearningFeed(store)
    identity=await DecisionFingerprints(store).record(owner_choice='original choice',mission_id=mission.mission_id)
    await feed.record_decision_outcome(mission,state=mission.state)
    await DecisionFingerprints(store).record_outcome(identity,outcome='failed',reassessment='The owner corrected the interpretation',now_ms=mission.updated_at_ms+100)
    await feed.record_decision_outcome(mission,state=mission.state)
    row=await store.fetchone('SELECT * FROM decision_fingerprints WHERE decision_id=?',(identity,))
    assert row['reassessment']=='The owner corrected the interpretation' and row['updated_at_ms']==mission.updated_at_ms+100

@pytest.mark.asyncio
async def test_a_failed_original_source_cannot_starve_other_learning_work(tmp_path,monkeypatch):
    store=await make_store(tmp_path);first=await failed_mission(store);second=await failed_mission(store)
    feed=LearningFeed(store);original=feed.record_mission_opened
    async def unavailable(mission,**kw):
        if mission.mission_id==first.mission_id:raise RuntimeError('fixture-private-source')
        return await original(mission,**kw)
    monkeypatch.setattr(feed,'record_mission_opened',unavailable);service=MissionService(store,learning=feed)
    assert await service.reconcile_learning_projections(limit=1)==0
    assert await service.reconcile_learning_projections(limit=1)==1
    for _ in range(8):await service.reconcile_learning_projections(limit=1)
    pending=await store.fetchall('SELECT * FROM mission_learning_outbox')
    assert len(pending)==1 and pending[0]['mission_id']==first.mission_id and pending[0]['stage']=='OPENED'
    assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==2

@pytest.mark.asyncio
async def test_learning_repair_cancellation_keeps_the_original_delivery_pending(tmp_path,monkeypatch):
    store=await make_store(tmp_path);await failed_mission(store);feed=LearningFeed(store)
    async def cancelled(*a,**kw):raise asyncio.CancelledError()
    monkeypatch.setattr(feed,'record_mission_opened',cancelled)
    with pytest.raises(asyncio.CancelledError):await MissionService(store,learning=feed).reconcile_learning_projections()
    assert len(await store.fetchall('SELECT * FROM mission_learning_outbox'))==4


@pytest.mark.asyncio
async def test_capture_and_original_learning_delivery_commit_atomically(tmp_path):
    store=await make_store(tmp_path)
    await store.execute("CREATE TRIGGER reject_capture_delivery BEFORE INSERT ON mission_learning_outbox BEGIN SELECT RAISE(ABORT,'delivery unavailable'); END")
    with pytest.raises(Exception,match='delivery unavailable'):await failed_mission(store)
    assert not await store.fetchall('SELECT * FROM missions')
    assert not await store.fetchall('SELECT * FROM mission_events')

@pytest.mark.asyncio
async def test_terminal_state_and_original_learning_deliveries_commit_atomically(tmp_path):
    store=await make_store(tmp_path);service=MissionService(store)
    mission=await service.create(owner_principal_id='owner',origin=MissionOrigin.OWNER_UI,origin_channel=OriginChannel.UI,title='t',goal='g')
    for state in [MissionState.UNDERSTOOD,MissionState.PLANNED,MissionState.AUTHORIZED,MissionState.RUNNING]:
        mission=await service.transition(mission.mission_id,target=state)
    await store.execute("CREATE TRIGGER reject_terminal_learning BEFORE INSERT ON mission_learning_outbox WHEN NEW.stage='STRATEGY_OUTCOME' BEGIN SELECT RAISE(ABORT,'terminal delivery unavailable'); END")
    with pytest.raises(Exception,match='terminal delivery unavailable'):
        await service.transition(mission.mission_id,target=MissionState.FAILED)
    assert (await service.get(mission.mission_id)).state is MissionState.RUNNING
    assert not await store.fetchall("SELECT * FROM mission_events WHERE event_type='mission.failed'")
    assert not await store.fetchall("SELECT * FROM mission_projection_outbox")
    assert [r['stage'] for r in await store.fetchall('SELECT * FROM mission_learning_outbox')]==['OPENED']

@pytest.mark.asyncio
async def test_lost_strategy_database_commit_ack_reads_original_receipt(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    store=await make_store(tmp_path);mission=await failed_mission(store);original=store.connection;armed=True
    @asynccontextmanager
    async def uncertain():
        async with original() as db:
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def commit(self):
                    nonlocal armed
                    await db.commit()
                    if armed:armed=False;raise OSError('strategy commit acknowledgement lost')
            yield Connection()
    monkeypatch.setattr(store,'connection',uncertain)
    with pytest.raises(OSError,match='strategy commit acknowledgement lost'):
        await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
    receipt=await store.fetchone('SELECT * FROM mission_strategy_observations')
    identity=await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
    assert identity==receipt['strategy_id']
    assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==1

@pytest.mark.asyncio
async def test_changed_original_strategy_source_is_refused_instead_of_becoming_another_sample(tmp_path):
    store=await make_store(tmp_path);mission=await failed_mission(store);feed=LearningFeed(store)
    identity=await feed.record_strategy_outcome(mission,state=mission.state)
    await store.execute("UPDATE mission_activities SET capability_id='different-native-work' WHERE mission_id=?",(mission.mission_id,))
    with pytest.raises(ValueError,match='LEARNING_NATIVE_SOURCE_CONFLICT'):
        await feed.record_strategy_outcome(mission,state=mission.state)
    rows=await store.fetchall('SELECT * FROM execution_strategies')
    assert len(rows)==1 and rows[0]['strategy_id']==identity and rows[0]['failure_count']==1

@pytest.mark.asyncio
async def test_upgrade_does_not_guess_that_legacy_terminal_missions_are_new_samples(tmp_path,monkeypatch):
    import van_gateway.storage.db as storage
    from van_gateway.evolution.radar import StrategyLearning,StrategyOutcome
    database=tmp_path/'legacy.sqlite3';store=storage.Store(str(database))
    async def legacy_no_outbox(*a,**kw):pass
    with monkeypatch.context() as old:
        old.setattr(storage,'MIGRATIONS',{k:v for k,v in storage.MIGRATIONS.items() if k<=56})
        old.setattr(storage,'SCHEMA_VERSION',56)
        old.setattr(MissionService,'_enqueue_learning',legacy_no_outbox)
        await store.migrate()
        mission=await failed_mission(store)
        strategies=StrategyLearning(store)
        identity=await strategies.find_or_register(mission_class=mission.mission_class,capability_sequence=['native-task'],max_action_class=ActionClass.A2)
        await strategies.record_outcome(identity,outcome=StrategyOutcome.FAILURE)
    await store.migrate()
    assert await LearningFeed(store).record_strategy_outcome(mission,state=mission.state) is None
    assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==1
    baseline=await store.fetchone('SELECT * FROM mission_strategy_observations')
    assert baseline['state']=='LEGACY_UNRECONCILED' and baseline['strategy_id'] is None
    assert not await store.fetchall('SELECT * FROM mission_learning_outbox')


@pytest.mark.asyncio
async def test_gateway_startup_and_real_scheduler_are_wired_to_original_learning_delivery(tmp_path,monkeypatch):
    from cryptography.fernet import Fernet
    from van_gateway.app import create_app
    from van_gateway.config import get_settings
    database=tmp_path/'gateway.sqlite3'
    from van_gateway.storage.db import Store
    store=Store(str(database));await store.migrate();first=await failed_mission(store)
    monkeypatch.setenv('VAN_DATABASE_PATH',str(database))
    monkeypatch.setenv('VAN_GOOGLE_TOKEN_FERNET_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('VAN_DEVICE_SECRET_FERNET_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('VAN_SCHEDULER_ENABLED','false')
    get_settings.cache_clear()
    try:
        app=create_app()
        async with app.router.lifespan_context(app):
            assert await store.fetchone('SELECT * FROM learning_outcomes WHERE mission_id=?',(first.mission_id,))
            assert not await store.fetchall('SELECT * FROM mission_learning_outbox')
            second=await failed_mission(store)
            job=app.state.scheduler.jobs.get('learning.repair_missions')
            assert job is not None
            result=await app.state.scheduler.run_job(job)
            assert result['outcome']=='OK' and result['detail']=={'repaired':4,'pending':0,'retry_pending':0}
            assert await store.fetchone('SELECT * FROM learning_outcomes WHERE mission_id=?',(second.mission_id,))
            assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==2
    finally:get_settings.cache_clear()

@pytest.mark.asyncio
async def test_late_opened_delivery_also_restores_the_original_terminal_decision_outcome(tmp_path,monkeypatch):
    from test_owner_memory_has_a_producer import _open
    store=await make_store(tmp_path);native=MissionService(store)
    mission=await _open(native,goal='A real owner choice with delayed memory',approved=True)
    for state in [MissionState.UNDERSTOOD,MissionState.PLANNED,MissionState.AUTHORIZED,MissionState.RUNNING,MissionState.FAILED]:
        mission=await native.transition(mission.mission_id,target=state)
    feed=LearningFeed(store);original=feed.record_mission_opened
    async def unavailable(*a,**kw):raise OSError('source delivery temporarily unavailable')
    monkeypatch.setattr(feed,'record_mission_opened',unavailable)
    service=MissionService(store,learning=feed)
    assert await service.reconcile_learning_projections()==3
    assert not await store.fetchall('SELECT * FROM decision_fingerprints')
    monkeypatch.setattr(feed,'record_mission_opened',original)
    assert await service.reconcile_learning_projections()==1
    row=await store.fetchone('SELECT * FROM decision_fingerprints')
    assert row['outcome']=='failed' and row['inferred_reason'] is None

from tests.test_owner_memory_erasure import client,_settings,_pair,_approve

@pytest.mark.asyncio
async def test_repair_of_original_owner_sources_cannot_undo_native_erasure(client,monkeypatch):
    ac,app,_=client;key=await _pair(ac,app);original=LearningFeed.record_mission_opened
    async def unavailable_after_native_seal(self,mission,**kw):
        from van_gateway.command.authority import CommandAuthorityService
        source=mission.authority_envelope.source_command_id
        if source and await CommandAuthorityService(self.store).get(source):raise OSError('fixture-private-delayed-memory')
        return await original(self,mission,**kw)
    monkeypatch.setattr(LearningFeed,'record_mission_opened',unavailable_after_native_seal)
    first,_=await _approve(ac,app,key,'forget owner-derived memory store owner_facts','repair-source-before-erasure')
    await _approve(ac,app,key,'forget owner-derived memory store intent_nodes','repair-intent-erasure')
    await _approve(ac,app,key,'forget owner-derived memory store decision_fingerprints','repair-choice-erasure')
    assert await app.state.store.fetchall("SELECT * FROM mission_learning_outbox WHERE stage='OPENED'")
    monkeypatch.setattr(LearningFeed,'record_mission_opened',original)
    service=MissionService(app.state.store,learning=LearningFeed(app.state.store))
    await service.reconcile_learning_projections(limit=100)
    first_mission=await app.state.store.fetchone("SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?",(first['command_id'],))
    assert not await app.state.store.fetchall('SELECT * FROM intent_missions WHERE mission_id=?',(first_mission['mission_id'],))
    assert not await app.state.store.fetchall('SELECT * FROM intent_nodes WHERE owner_goal=?',(first['text'],))
    # The later instruction to erase decisions was issued after intent erasure. It
    # remains fresh consent, even though the earlier original source stays forgotten.
    fresh=await app.state.store.fetchall('SELECT * FROM intent_nodes')
    assert len(fresh)==1 and fresh[0]['owner_goal']=='forget owner-derived memory store decision_fingerprints'
    assert not await app.state.store.fetchall('SELECT * FROM decision_fingerprints')
    assert not await app.state.store.fetchall('SELECT * FROM mission_learning_outbox')


@pytest.mark.asyncio
async def test_retention_preserves_pending_delivery_original_sample_identity_and_owner_chart_state(tmp_path):
    from test_chart_workspace_persistence import state
    from van_gateway.trading.chart_models import CreateWorkspace
    from van_gateway.trading.chart_workspaces import ChartWorkspaceService
    from van_gateway.ops.retention import RetentionService
    store=await make_store(tmp_path);mission=await failed_mission(store)
    identity=await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
    charts=ChartWorkspaceService(store)
    workspace=await charts.create('owner',CreateWorkspace(request_id='owner-original-chart',state=state()))
    await RetentionService(store).prune(now_ms=mission.updated_at_ms+400*86400000)
    assert len(await store.fetchall('SELECT * FROM mission_learning_outbox'))==4
    assert (await store.fetchone('SELECT * FROM mission_strategy_observations'))['strategy_id']==identity
    assert (await charts.get('owner',workspace.workspace_id)).state==state()
    assert await charts.operation('owner','owner-original-chart')==workspace
    # A telemetry retention sweep must not turn an old delivery into new evidence.
    assert not await store.fetchall('SELECT * FROM execution_strategies')
    await MissionService(store,learning=LearningFeed(store)).reconcile_learning_projections()
    assert not await store.fetchall('SELECT * FROM execution_strategies')

@pytest.mark.asyncio
@pytest.mark.parametrize('invalid',[0,101,True,1.0,'5'])
async def test_learning_repair_refuses_unbounded_or_ambiguous_batch_limits(tmp_path,invalid):
    store=await make_store(tmp_path)
    with pytest.raises(ValueError,match='learning_repair_limit_invalid'):
        await MissionService(store,learning=LearningFeed(store)).reconcile_learning_projections(limit=invalid)

@pytest.mark.asyncio
async def test_recovery_reads_the_exact_original_native_verification_receipt(tmp_path):
    from test_learning_records_and_bounds import _svc,_run_mission
    store=await make_store(tmp_path);native=_svc(store);native.learning=None
    mission=await _run_mission(native,mission_class='PROVEN_TASK',capabilities=['native-task'],terminal=MissionState.VERIFIED_SUCCESS)
    original=await native.verification_record(mission.mission_id)
    assert original is not None and original.evidence_refs
    await MissionService(store,learning=LearningFeed(store)).reconcile_learning_projections()
    row=await store.fetchone('SELECT * FROM learning_outcomes WHERE mission_id=?',(mission.mission_id,))
    import json
    assert row['outcome_kind']=='verified_success' and row['verification_status']==original.status.value
    assert json.loads(row['evidence_refs_json'])==sorted(set(original.evidence_refs))
    assert row['recorded_at_ms']==mission.updated_at_ms

@pytest.mark.asyncio
@pytest.mark.parametrize('after_strategy',[False,True])
async def test_process_death_recovery_retains_the_same_native_mission_and_sample(tmp_path,after_strategy):
    import json,os,subprocess,sys
    from pathlib import Path
    from van_gateway.storage.db import Store
    database=tmp_path/'crashed.sqlite3'
    code="""
import asyncio,json,os,sys
from van_gateway.storage.db import Store
from van_gateway.learning.feed import LearningFeed
from test_learning_recovery import failed_mission
async def work():
 store=Store(sys.argv[1]);await store.migrate();mission=await failed_mission(store)
 if sys.argv[2]=='True':await LearningFeed(store).record_strategy_outcome(mission,state=mission.state)
 print(json.dumps({'mission_id':mission.mission_id}),flush=True)
asyncio.run(work());os._exit(31)
"""
    root=Path(__file__).resolve().parents[2]
    result=await asyncio.to_thread(subprocess.run,[sys.executable,'-B','-c',code,str(database),str(after_strategy)],cwd=root,
        env=dict(os.environ,PYTHONPATH='backend:backend/tests:.:trading'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    assert result.returncode==31,result.stderr
    identity=json.loads(result.stdout)['mission_id'];store=Store(str(database))
    assert len(await store.fetchall('SELECT * FROM missions'))==1
    assert len(await store.fetchall('SELECT * FROM mission_learning_outbox'))==4
    service=MissionService(store,learning=LearningFeed(store))
    events_before=await store.fetchall('SELECT * FROM mission_events')
    assert await service.reconcile_learning_projections()==4
    assert (await service.get(identity)).state is MissionState.FAILED
    assert (await store.fetchone('SELECT * FROM execution_strategies'))['failure_count']==1
    assert [dict(x) for x in await store.fetchall('SELECT * FROM mission_events')]==[dict(x) for x in events_before]
    assert not await store.fetchall('SELECT * FROM mission_learning_outbox')

@pytest.mark.asyncio
async def test_failed_schema_version_marker_rolls_back_new_learning_tables_and_can_retry(tmp_path,monkeypatch):
    import van_gateway.storage.db as storage
    store=storage.Store(str(tmp_path/'marker.sqlite3'))
    with monkeypatch.context() as old:
        old.setattr(storage,'MIGRATIONS',{k:v for k,v in storage.MIGRATIONS.items() if k<=56})
        old.setattr(storage,'SCHEMA_VERSION',56)
        await store.migrate()
    await store.execute("CREATE TRIGGER reject_learning_schema_version BEFORE INSERT ON schema_migrations WHEN NEW.version=57 BEGIN SELECT RAISE(ABORT,'schema marker unavailable'); END")
    with pytest.raises(Exception,match='schema marker unavailable'):await store.migrate()
    names=[r['name'] for r in await store.fetchall("SELECT name FROM sqlite_master WHERE type='table'")]
    assert 'mission_learning_outbox' not in names and 'mission_strategy_observations' not in names
    assert (await store.fetchone('SELECT MAX(version) AS version FROM schema_migrations'))['version']==56
    await store.execute('DROP TRIGGER reject_learning_schema_version')
    await store.migrate()
    assert (await store.fetchone('SELECT MAX(version) AS version FROM schema_migrations'))['version']==storage.SCHEMA_VERSION
    assert not await store.fetchall('SELECT * FROM mission_learning_outbox')

@pytest.mark.asyncio
async def test_process_death_before_schema_marker_leaves_a_retryable_original_database(tmp_path,monkeypatch):
    import json,os,subprocess,sys
    from pathlib import Path
    import van_gateway.storage.db as storage
    database=tmp_path/'migration-crash.sqlite3';store=storage.Store(str(database))
    with monkeypatch.context() as old:
        old.setattr(storage,'MIGRATIONS',{k:v for k,v in storage.MIGRATIONS.items() if k<=56})
        old.setattr(storage,'SCHEMA_VERSION',56)
        await store.migrate()
    code="""
import asyncio,os,sys
from contextlib import asynccontextmanager
from van_gateway.storage.db import Store
original=Store.connection
@asynccontextmanager
async def crashing(self):
 async with original(self) as db:
  class Connection:
   def __getattr__(self,name):return getattr(db,name)
   async def execute(self,sql,params=()):
    if 'INSERT INTO schema_migrations(' in sql and params and params[0]==57:os._exit(32)
    return await db.execute(sql,params)
  yield Connection()
Store.connection=crashing
asyncio.run(Store(sys.argv[1]).migrate())
"""
    root=Path(__file__).resolve().parents[2]
    result=await asyncio.to_thread(subprocess.run,[sys.executable,'-B','-c',code,str(database)],cwd=root,
        env=dict(os.environ,PYTHONPATH='backend:backend/tests:.:trading'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    assert result.returncode==32,result.stderr
    names=[r['name'] for r in await store.fetchall("SELECT name FROM sqlite_master WHERE type='table'")]
    assert 'mission_learning_outbox' not in names and 'mission_strategy_observations' not in names
    assert (await store.fetchone('SELECT MAX(version) AS version FROM schema_migrations'))['version']==56
    await store.migrate()
    assert (await store.fetchone('SELECT MAX(version) AS version FROM schema_migrations'))['version']==storage.SCHEMA_VERSION

@pytest.mark.asyncio
@pytest.mark.parametrize('old_failure',[False,True])
async def test_an_old_delivery_ack_cannot_erase_newly_authorized_owner_feedback(tmp_path,monkeypatch,old_failure):
    from test_owner_memory_has_a_producer import _seal_fixture_choice
    from van_gateway.command.mission_link import CommandMissionLink
    store=await make_store(tmp_path);native=MissionService(store)
    source='cmd-native-learning-generation-race'
    mission=await native.create(owner_principal_id='device:dev-memory-owner',origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,title='Real owner request',goal='Preserve the newly sealed choice',
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A4,requires_owner_presence=True,source_command_id=source))
    for state in [MissionState.UNDERSTOOD,MissionState.PLANNED]:
        mission=await native.transition(mission.mission_id,target=state)
    feed=LearningFeed(store);original=feed.record_mission_opened;entered=asyncio.Event();release=asyncio.Event()
    async def delayed_old_snapshot(snapshot,**kw):
        if snapshot.state is MissionState.AUTHORIZED:raise OSError('new owner publication temporarily unavailable')
        result=await original(snapshot,**kw)
        assert result=={'intent_id':None,'decision_id':None}
        entered.set();await asyncio.wait_for(release.wait(),timeout=5)
        if old_failure:raise OSError('the obsolete source delivery failed')
        return result
    monkeypatch.setattr(feed,'record_mission_opened',delayed_old_snapshot)
    service=MissionService(store,learning=feed)
    repair=asyncio.create_task(service.reconcile_learning_projections(limit=1))
    await asyncio.wait_for(entered.wait(),timeout=5)
    await _seal_fixture_choice(store,source)
    await CommandMissionLink(service).authorized(mission,summary='Native owner command sealed')
    release.set();assert await repair==(0 if old_failure else 1)
    pending=await store.fetchall("SELECT * FROM mission_learning_outbox WHERE stage='OPENED'")
    assert len(pending)==1, 'The old unsealed snapshot must not acknowledge the newly authorized delivery'
    assert pending[0]['attempts']==0 and pending[0]['last_failure'] is None
    monkeypatch.setattr(feed,'record_mission_opened',original)
    assert await service.reconcile_learning_projections()==1
    assert (await store.fetchone('SELECT * FROM intent_nodes'))['observation_count']==1
    assert len(await store.fetchall('SELECT * FROM decision_fingerprints'))==1
