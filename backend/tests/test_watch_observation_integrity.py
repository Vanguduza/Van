"""Owner watch controls and alerts must survive concurrency and lost replies."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from van_gateway.attention.engine import AttentionEngine
from van_gateway.goals.models import WatchCreate,WatchObservation,WatchSourceKind,WatchStatus
from van_gateway.goals.service import GoalService,GoalServiceError
from van_gateway.storage.db import Store


async def service(tmp_path):
    store=Store(str(tmp_path/'watches.sqlite'));await store.migrate()
    return GoalService(store,AttentionEngine(store))


async def watch(s,kind='BOOLEAN_TRUE'):
    return await s.create_watch(WatchCreate(title='Owner watch',source_kind=WatchSourceKind.PROVIDER,
        target='fixture:owner',condition={'kind':kind,**({'threshold':'100'} if kind=='NUMERIC_ABOVE' else {})},interval_seconds=60),now_ms=1000)


@pytest.mark.asyncio
async def test_string_false_is_not_boolean_watch_evidence(tmp_path):
    s=await service(tmp_path);w=await watch(s)
    with pytest.raises(GoalServiceError):
        await s.record_observation(w.watch_id,WatchObservation(observation='false'),now_ms=2000)
    assert (await s.get_watch(w.watch_id)).last_observation is None


@pytest.mark.asyncio
@pytest.mark.parametrize('value',[float('nan'),float('inf'),True])
async def test_invalid_numeric_observations_do_not_poison_current_watch_state(tmp_path,value):
    s=await service(tmp_path);w=await watch(s,'NUMERIC_ABOVE')
    with pytest.raises(GoalServiceError):
        await s.record_observation(w.watch_id,WatchObservation(observation=value),now_ms=2000)
    assert (await s.get_watch(w.watch_id)).last_observation is None


@pytest.mark.asyncio
async def test_failed_run_insert_rolls_back_the_watch_projection(tmp_path,monkeypatch):
    s=await service(tmp_path);w=await watch(s);execute=s.store.execute;connection=s.store.connection
    async def fail_execute(sql,*args,**kwargs):
        if 'INSERT INTO watch_runs' in sql:raise RuntimeError('run write failed')
        return await execute(sql,*args,**kwargs)
    class Connection:
        def __init__(self,db):self.db=db
        def __getattr__(self,name):return getattr(self.db,name)
        async def execute(self,sql,*args,**kwargs):
            if 'INSERT INTO watch_runs' in sql:raise RuntimeError('run write failed')
            return await self.db.execute(sql,*args,**kwargs)
    @asynccontextmanager
    async def fail_connection():
        async with connection() as db:yield Connection(db)
    monkeypatch.setattr(s.store,'execute',fail_execute);monkeypatch.setattr(s.store,'connection',fail_connection)
    with pytest.raises(RuntimeError,match='run write failed'):
        await s.record_observation(w.watch_id,WatchObservation(observation=True),now_ms=2000)
    current=await s.get_watch(w.watch_id)
    assert current.last_observation is None and current.last_success_at_ms is None and current.next_run_at_ms==1000


@pytest.mark.asyncio
async def test_two_concurrent_failure_observations_are_both_counted(tmp_path):
    s=await service(tmp_path);w=await watch(s)
    await asyncio.gather(*(s.record_observation(w.watch_id,WatchObservation(success=False,error_code='offline'),now_ms=2000) for _ in range(2)))
    assert (await s.get_watch(w.watch_id)).consecutive_failures==2


@pytest.mark.asyncio
async def test_same_boolean_edge_creates_one_trigger_across_independent_connections(tmp_path):
    s=await service(tmp_path);w=await watch(s)
    await asyncio.gather(*(s.record_observation(w.watch_id,WatchObservation(observation=True),now_ms=2000) for _ in range(2)))
    rows=await s.store.fetchall('SELECT changed FROM watch_runs WHERE watch_id=?',(w.watch_id,))
    assert sum(r['changed'] for r in rows)==1


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [False, True])
async def test_lost_attention_reply_preserves_a_recoverable_watch_publication(tmp_path,monkeypatch,committed):
    s=await service(tmp_path);w=await watch(s); original=s.attention.upsert
    async def lost(**kwargs):
        if committed:await original(**kwargs)
        raise RuntimeError('attention unavailable')
    monkeypatch.setattr(s.attention,'upsert',lost)
    result=await s.record_observation(w.watch_id,WatchObservation(observation=True),now_ms=2000)
    assert result['triggered'] and result['notification_state']=='PENDING'
    assert (await s.get_watch(w.watch_id)).last_observation is True
    # A new process/service uses the original stored intent, without another edge.
    recovered=GoalService(s.store,AttentionEngine(s.store))
    assert await recovered.publish_pending()==1
    assert await recovered.publish_pending()==0
    runs=await s.store.fetchall('SELECT run_id FROM watch_runs WHERE watch_id=?',(w.watch_id,))
    alerts=await s.store.fetchall("SELECT * FROM attention WHERE source='watch'")
    assert [r['run_id'] for r in runs]==[result['run_id']]
    assert len(alerts)==1 and alerts[0]['dedupe_key'].endswith(result['run_id'])


@pytest.mark.asyncio
async def test_delayed_failure_publication_cannot_downgrade_paused_blocker(tmp_path,monkeypatch):
    import json
    s=await service(tmp_path);w=await watch(s); original=s.attention.upsert
    async def offline(**kwargs):raise RuntimeError('offline')
    monkeypatch.setattr(s.attention,'upsert',offline)
    first=await s.record_observation(w.watch_id,WatchObservation(success=False),now_ms=2000)
    await s.record_observation(w.watch_id,WatchObservation(success=False),now_ms=3000)
    monkeypatch.setattr(s.attention,'upsert',original)
    third=await s.record_observation(w.watch_id,WatchObservation(success=False),now_ms=4000)
    assert third['paused'] and first['notification_state']=='PENDING'
    alert=await s.store.fetchone("SELECT * FROM attention WHERE source='watch'")
    await s.attention.acknowledge(alert['id'])
    assert await s.publish_pending()==2
    updated=await s.store.fetchone("SELECT * FROM attention WHERE source='watch'")
    assert updated['severity']=='BLOCKER' and updated['state']=='ACKNOWLEDGED'
    assert json.loads(updated['payload_json'])['failures']==3


@pytest.mark.asyncio
async def test_owner_pause_survives_actual_observation_read_write_interleaving(tmp_path,monkeypatch):
    import sqlite3
    from types import SimpleNamespace
    s=await service(tmp_path);w=await watch(s);connection=s.store.connection
    attempted=committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'FROM watches WHERE watch_id' not in sql:return cursor
                async def fetchone():
                    nonlocal attempted,committed
                    row=await cursor.fetchone()
                    if not attempted:
                        attempted=True
                        with sqlite3.connect(s.store.path,timeout=0) as owner:
                            try:
                                owner.execute("UPDATE watches SET status='PAUSED' WHERE watch_id=?",(w.watch_id,));owner.commit();committed=True
                            except sqlite3.OperationalError as exc:assert 'locked' in str(exc)
                    return row
                return SimpleNamespace(fetchone=fetchone)
            yield SimpleNamespace(execute=execute,commit=db.commit)
    monkeypatch.setattr(s.store,'connection',interleaved)
    await s.record_observation(w.watch_id,WatchObservation(success=False),now_ms=2000)
    assert attempted
    if not committed:await s.set_watch_status(w.watch_id,WatchStatus.PAUSED)
    assert (await s.get_watch(w.watch_id)).status is WatchStatus.PAUSED


@pytest.mark.asyncio
async def test_one_bad_publication_does_not_starve_a_different_watch(tmp_path,monkeypatch):
    s=await service(tmp_path);first=await watch(s);second=await watch(s);original=s.attention.upsert
    async def offline(**kwargs):raise RuntimeError('offline')
    monkeypatch.setattr(s.attention,'upsert',offline)
    await s.record_observation(first.watch_id,WatchObservation(observation=True),now_ms=2000)
    await s.record_observation(second.watch_id,WatchObservation(observation=True),now_ms=2001)
    async def one_bad(**kwargs):
        if kwargs['payload']['watch_id']==first.watch_id:raise RuntimeError('one source unavailable')
        return await original(**kwargs)
    monkeypatch.setattr(s.attention,'upsert',one_bad)
    assert await s.publish_pending()==1
    assert await s.publish_pending()==0
    monkeypatch.setattr(s.attention,'upsert',original)
    assert await s.publish_pending()==1


@pytest.mark.asyncio
async def test_owner_pause_during_read_discards_observation_and_other_watches_continue(tmp_path):
    from test_goals_watches import _FakeHarness
    from van_gateway.browser.service import BrowserSessionBroker,BrowserTaskService
    from van_gateway.goals.watch_runner import WatchRunner
    s=await service(tmp_path)
    first=await s.create_watch(WatchCreate(title='pause me',source_kind=WatchSourceKind.BROWSER,
        target='https://example.com/first',condition={'kind':'TEXT_CONTAINS','text':'ready'},interval_seconds=60),now_ms=1000)
    second=await s.create_watch(WatchCreate(title='keep checking',source_kind=WatchSourceKind.BROWSER,
        target='https://example.com/second',condition={'kind':'TEXT_CONTAINS','text':'ready'},interval_seconds=60),now_ms=1001)
    class Harness(_FakeHarness):
        async def navigate(self,task,url):
            if url.endswith('/first'):await s.set_watch_status(first.watch_id,WatchStatus.PAUSED)
            return await super().navigate(task,url)
    broker=BrowserSessionBroker(s.store);tasks=BrowserTaskService(s.store,broker)
    runner=WatchRunner(s,tasks=tasks,broker=broker,harness=Harness('ready'))
    try:
        result=await runner.run(now_ms=2000)
    except Exception as exc:
        result=exc
    assert isinstance(result,dict),f"one owner-paused watch aborted scheduler: {type(result).__name__}"
    assert result['checked']==1 and result['triggered']==1
    assert (await s.get_watch(first.watch_id)).status is WatchStatus.PAUSED
    assert (await s.get_watch(first.watch_id)).last_observation is None
    assert (await s.get_watch(second.watch_id)).last_observation=='ready'
    assert not await s.store.fetchall('SELECT * FROM watch_runs WHERE watch_id=?',(first.watch_id,))
    assert not await s.store.fetchall("SELECT * FROM browser_tasks WHERE status IN ('QUEUED','RUNNING')")


@pytest.mark.asyncio
async def test_nonfinite_nested_changed_observation_is_not_stored(tmp_path):
    s=await service(tmp_path);w=await watch(s,'CHANGED')
    with pytest.raises(GoalServiceError,match='WATCH_OBSERVATION_INVALID'):
        await s.record_observation(w.watch_id,WatchObservation(observation={'nested':[float('nan')]}),now_ms=2000)
    assert (await s.get_watch(w.watch_id)).last_observation is None


@pytest.mark.asyncio
async def test_watch_alert_revision_survives_run_history_retention(tmp_path):
    import json
    s=await service(tmp_path);w=await watch(s)
    await s.record_observation(w.watch_id,WatchObservation(success=False),now_ms=2000)
    # Real SQLite rowids may restart after history is pruned. Alert versions may not.
    await s.store.execute('DELETE FROM watch_runs WHERE watch_id=?',(w.watch_id,))
    await s.record_observation(w.watch_id,WatchObservation(success=False),now_ms=3000)
    row=await s.store.fetchone("SELECT payload_json FROM attention WHERE source='watch'")
    assert json.loads(row['payload_json'])['failures']==2


@pytest.mark.asyncio
async def test_failed_publication_intent_insert_rolls_back_the_run_and_projection(tmp_path):
    s=await service(tmp_path);w=await watch(s)
    await s.store.execute("CREATE TRIGGER fixture_no_intent BEFORE INSERT ON runtime_meta WHEN NEW.key LIKE 'watch_publication:%' BEGIN SELECT RAISE(ABORT,'intent unavailable'); END")
    with pytest.raises(Exception,match='intent unavailable'):
        await s.record_observation(w.watch_id,WatchObservation(observation=True),now_ms=2000)
    assert (await s.get_watch(w.watch_id)).last_observation is None
    assert not await s.store.fetchall('SELECT * FROM watch_runs WHERE watch_id=?',(w.watch_id,))
    assert not await s.store.fetchall("SELECT * FROM runtime_meta WHERE key LIKE 'watch_publication%'")


@pytest.mark.asyncio
async def test_corrupt_publication_counter_refuses_observation_without_partial_commit(tmp_path):
    s=await service(tmp_path);w=await watch(s)
    await s.store.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
        ('watch_publication_revision:'+w.watch_id,'true',1000))
    with pytest.raises(GoalServiceError,match='WATCH_PUBLICATION_STATE_INVALID'):
        await s.record_observation(w.watch_id,WatchObservation(observation=True),now_ms=2000)
    assert (await s.get_watch(w.watch_id)).last_observation is None
    assert not await s.store.fetchall('SELECT * FROM watch_runs WHERE watch_id=?',(w.watch_id,))
