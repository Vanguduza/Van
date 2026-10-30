import asyncio
import pytest
from conftest_automation import make_store
from van_gateway.attention.engine import AttentionEngine
from van_gateway.models import AttentionSeverity


@pytest.mark.asyncio
async def test_concurrent_reports_share_one_attention_identity_and_preserve_owner_ack(tmp_path):
    store=await make_store(tmp_path)
    async def report():
        return await AttentionEngine(store).upsert(title='Actual reminder',severity=AttentionSeverity.FOLLOW_UP,
            source='reminder',dedupe_key='reminder:one',project_id='project-alpha')
    results=await asyncio.gather(*(report() for _ in range(4)),return_exceptions=True)
    assert all(not isinstance(r,Exception) for r in results),[type(r).__name__ for r in results]
    assert len({r.id for r in results})==1
    await AttentionEngine(store).acknowledge(results[0].id)
    await asyncio.gather(*(report() for _ in range(4)))
    row=await store.fetchone("SELECT * FROM attention WHERE dedupe_key='reminder:one'")
    assert row['state']=='ACKNOWLEDGED' and row['project_id']=='project-alpha'
    assert (await store.fetchone('SELECT count(*) AS n FROM attention'))['n']==1


@pytest.mark.asyncio
async def test_attention_update_returns_the_same_project_and_source_it_persisted(tmp_path):
    store=await make_store(tmp_path);engine=AttentionEngine(store)
    await engine.upsert(title='Original',severity=AttentionSeverity.FOLLOW_UP,source='reminder',dedupe_key='same')
    updated=await engine.upsert(title='Observed',severity=AttentionSeverity.FOLLOW_UP,source='reminder-recovery',dedupe_key='same',project_id='project-alpha')
    row=await store.fetchone("SELECT * FROM attention WHERE dedupe_key='same'")
    assert row['source']==updated.source and row['project_id']==updated.project_id


@pytest.mark.asyncio
async def test_owner_ack_survives_an_actual_report_read_write_interleaving(tmp_path,monkeypatch):
    """Independent SQLite owner write, not a guessed scheduling delay.

    An acknowledgement either commits in the read/write gap and must survive,
    or is excluded by the report transaction and commits after it. A safe CAS
    implementation would also pass; the test does not demand a particular lock.
    """
    import sqlite3
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    store=await make_store(tmp_path);engine=AttentionEngine(store)
    item=await engine.upsert(title='Original',severity=AttentionSeverity.FOLLOW_UP,source='reminder',dedupe_key='same')
    connection=store.connection;attempted=False;committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'FROM attention WHERE dedupe_key = ?' not in sql:return cursor
                async def fetchone():
                    nonlocal attempted,committed
                    row=await cursor.fetchone()
                    if not attempted:
                        attempted=True
                        with sqlite3.connect(store.path,timeout=0) as owner:
                            try:
                                owner.execute("UPDATE attention SET state='ACKNOWLEDGED' WHERE id=?",(item.id,));owner.commit();committed=True
                            except sqlite3.OperationalError as exc:
                                assert 'locked' in str(exc)
                    return row
                return SimpleNamespace(fetchone=fetchone)
            yield SimpleNamespace(execute=execute,commit=db.commit)
    monkeypatch.setattr(store,'connection',interleaved)
    updated=await engine.upsert(title='Re-report',severity=AttentionSeverity.FOLLOW_UP,source='reminder',dedupe_key='same')
    assert attempted and updated.id==item.id
    if not committed:await engine.acknowledge(item.id)
    row=await store.fetchone('SELECT state FROM attention WHERE id=?',(item.id,))
    assert row['state']=='ACKNOWLEDGED'
