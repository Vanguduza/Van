"""Conversation history/lifecycle is durable presentation, never work authority."""
import asyncio
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from van_gateway.conversations.service import ConversationService,ConversationServiceError
from van_gateway.conversations.models import ThreadStatus
from van_gateway.storage.db import Store


async def service(tmp_path):
    store=Store(str(tmp_path/'threads.sqlite'));await store.migrate()
    return ConversationService(store)


@pytest.mark.asyncio
async def test_concurrent_main_thread_getters_return_one_main_instead_of_an_error(tmp_path):
    s=await service(tmp_path)
    outcomes=await asyncio.gather(*(s.ensure_main() for _ in range(5)),return_exceptions=True)
    assert all(not isinstance(result,Exception) for result in outcomes),[type(result).__name__ for result in outcomes]
    assert len({result.thread_id for result in outcomes})==1
    assert len(await s.store.fetchall("SELECT * FROM conversation_threads WHERE kind='MAIN'"))==1


@pytest.mark.asyncio
async def test_bounded_thread_restore_contains_the_latest_messages(tmp_path):
    s=await service(tmp_path);thread=await s.create('History',now_ms=1000)
    for number in range(6):await s.append_message(thread.thread_id,role='OWNER',body=f'Turn {number}',now_ms=2000+number)
    restored=await s.get(thread.thread_id,message_limit=2)
    assert [message.body for message in restored.messages]==['Turn 4','Turn 5']


@pytest.mark.asyncio
async def test_failed_thread_touch_does_not_leave_an_unacknowledged_message(tmp_path):
    s=await service(tmp_path);thread=await s.create('Atomic message',now_ms=1000)
    await s.store.execute("CREATE TRIGGER fixture_no_thread_update BEFORE UPDATE ON conversation_threads BEGIN SELECT RAISE(ABORT,'thread unavailable'); END")
    with pytest.raises(Exception,match='thread unavailable'):
        await s.append_message(thread.thread_id,role='OWNER',body='Do not partially save this',now_ms=2000)
    assert not await s.store.fetchall('SELECT * FROM conversation_messages WHERE thread_id=?',(thread.thread_id,))


@pytest.mark.asyncio
async def test_racing_followup_decisions_do_not_both_report_success(tmp_path):
    s=await service(tmp_path);thread=await s.create('Queued intent');followup=await s.queue_followup(thread.thread_id,'Ask later')
    outcomes=await asyncio.gather(s.decide_followup(thread.thread_id,followup.followup_id,'promote',command_id='caller-reference'),
        s.decide_followup(thread.thread_id,followup.followup_id,'dismiss'),return_exceptions=True)
    accepted=[result for result in outcomes if not isinstance(result,Exception)]
    refused=[result for result in outcomes if isinstance(result,ConversationServiceError)]
    assert len(accepted)==1 and len(refused)==1
    assert refused[0].code=='FOLLOWUP_ALREADY_DECIDED'
    row=await s.store.fetchone('SELECT status,command_id FROM conversation_followups WHERE followup_id=?',(followup.followup_id,))
    assert row['status']==accepted[0].status.value and row['command_id']==accepted[0].command_id


@pytest.mark.asyncio
async def test_original_projection_key_cannot_be_rebound_to_another_thread(tmp_path):
    s=await service(tmp_path);first=await s.create('Original');other=await s.create('Different scope')
    await s.append_projection(first.thread_id,projection_key='command:original:terminal',role='VAN',body='Original outcome',terminal=True)
    with pytest.raises(ConversationServiceError,match='MESSAGE_PROJECTION_SCOPE_CONFLICT'):
        await s.append_projection(other.thread_id,projection_key='command:original:terminal',role='VAN',body='Original outcome',terminal=True)
    assert (await s.get(other.thread_id)).messages==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['draft','projection'])
async def test_thread_change_time_includes_its_draft_and_result_updates(tmp_path,operation):
    s=await service(tmp_path);thread=await s.create('Visible update',now_ms=1000)
    if operation=='draft':await s.save_draft(thread.thread_id,'Saved owner draft',now_ms=2000)
    else:await s.append_projection(thread.thread_id,projection_key='command:one:result',role='VAN',body='Actual stored result',now_ms=2000)
    assert (await s.get(thread.thread_id)).updated_at_ms==2000


@pytest.mark.asyncio
async def test_owner_archive_cannot_be_ignored_by_a_stale_followup_enqueue(tmp_path,monkeypatch):
    s=await service(tmp_path);thread=await s.create('Archive race');connection=s.store.connection;attempted=committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'SELECT * FROM conversation_threads WHERE thread_id' not in sql:return cursor
                async def fetchone():
                    nonlocal attempted,committed
                    row=await cursor.fetchone()
                    if not attempted:
                        attempted=True
                        with sqlite3.connect(s.store.path,timeout=0) as owner:
                            try:
                                owner.execute("UPDATE conversation_threads SET status='ARCHIVED' WHERE thread_id=?",(thread.thread_id,));owner.commit();committed=True
                            except sqlite3.OperationalError as exc:assert 'locked' in str(exc)
                    return row
                return SimpleNamespace(fetchone=fetchone)
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def execute(self,sql,params=()):return await execute(sql,params)
            yield Connection()
    monkeypatch.setattr(s.store,'connection',interleaved)
    try:result=await s.queue_followup(thread.thread_id,'Stale enqueue')
    except Exception as exc:result=exc
    assert attempted
    if committed:
        assert isinstance(result,ConversationServiceError) and result.code=='THREAD_ARCHIVED'
        assert not await s.store.fetchall('SELECT * FROM conversation_followups WHERE thread_id=?',(thread.thread_id,))
    else:
        assert not isinstance(result,Exception)
        await s.set_status(thread.thread_id,ThreadStatus.ARCHIVED)
    assert (await s.get(thread.thread_id)).status is ThreadStatus.ARCHIVED


@pytest.mark.asyncio
async def test_archived_thread_still_preserves_an_unsent_owner_draft(tmp_path):
    s=await service(tmp_path);thread=await s.create('Keep unsent input')
    await s.set_status(thread.thread_id,ThreadStatus.ARCHIVED)
    stored=await s.save_draft(thread.thread_id,'Preserve this unsent draft')
    assert stored.status is ThreadStatus.ARCHIVED and stored.draft_text=='Preserve this unsent draft'
    restored=await s.set_status(thread.thread_id,ThreadStatus.ACTIVE)
    assert restored.draft_text=='Preserve this unsent draft'


@pytest.mark.asyncio
async def test_pagination_returns_all_history_once_including_same_timestamp_messages(tmp_path):
    s=await service(tmp_path);thread=await s.create('Complete history')
    original=[]
    for number in range(7):
        original.append(await s.append_message(thread.thread_id,role='OWNER',body=f'Equal-time {number}',now_ms=2000))
    restored=await s.get(thread.thread_id,message_limit=2)
    assert [m.message_id for m in restored.messages]==[m.message_id for m in original[-2:]]
    assert restored.message_count==7 and restored.messages_has_more is True
    assert restored.messages_next_before_id==original[-2].message_id
    seen=[];cursor=None
    while True:
        page=await s.messages_page(thread.thread_id,limit=2,before_message_id=cursor)
        assert page.total_count==7
        seen=page.messages+seen
        if not page.has_more:
            assert page.next_before_message_id is None
            break
        assert page.next_before_message_id not in {None,cursor}
        cursor=page.next_before_message_id
    assert [m.message_id for m in seen]==[m.message_id for m in original]


@pytest.mark.asyncio
async def test_unknown_deleted_or_foreign_history_cursor_is_refused(tmp_path):
    s=await service(tmp_path);first=await s.create('Original');other=await s.create('Other')
    message=await s.append_message(first.thread_id,role='OWNER',body='Original message')
    with pytest.raises(ConversationServiceError,match='MESSAGE_CURSOR_INVALID'):
        await s.messages_page(other.thread_id,before_message_id=message.message_id)
    await s.store.execute('DELETE FROM conversation_messages WHERE message_id=?',(message.message_id,))
    with pytest.raises(ConversationServiceError,match='MESSAGE_CURSOR_INVALID'):
        await s.messages_page(first.thread_id,before_message_id=message.message_id)


@pytest.mark.asyncio
async def test_late_canonical_projection_is_retained_without_restoring_archived_thread(tmp_path):
    s=await service(tmp_path);thread=await s.create('Original execution')
    await s.set_status(thread.thread_id,ThreadStatus.ARCHIVED,now_ms=2000)
    first=await s.append_projection(thread.thread_id,projection_key='mission:original:terminal',role='VAN',body='Observed terminal result',mission_id='original',terminal=True,now_ms=3000)
    replay=await s.append_projection(thread.thread_id,projection_key='mission:original:terminal',role='VAN',body='Presentation changed later',mission_id='original',terminal=True,now_ms=4000)
    assert replay==first
    result=await s.get(thread.thread_id)
    assert result.status is ThreadStatus.ARCHIVED and result.updated_at_ms==3000
    assert [m.message_id for m in result.messages]==[first.message_id]


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['draft','followup','decision','projection'])
async def test_failed_parent_touch_rolls_back_each_conversation_child_mutation(tmp_path,operation):
    s=await service(tmp_path);thread=await s.create('Rollback',now_ms=1000)
    followup=await s.queue_followup(thread.thread_id,'Existing queued prompt',now_ms=1001) if operation=='decision' else None
    await s.store.execute("CREATE TRIGGER fixture_no_parent BEFORE UPDATE ON conversation_threads BEGIN SELECT RAISE(ABORT,'parent unavailable'); END")
    with pytest.raises(Exception,match='parent unavailable'):
        if operation=='draft':await s.save_draft(thread.thread_id,'Not acknowledged')
        elif operation=='followup':await s.queue_followup(thread.thread_id,'Not acknowledged')
        elif operation=='decision':await s.decide_followup(thread.thread_id,followup.followup_id,'promote')
        else:await s.append_projection(thread.thread_id,projection_key='result:pending',role='VAN',body='Not acknowledged')
    current=await s.get(thread.thread_id)
    assert current.draft_text=='' and current.messages==[]
    if followup is not None:assert current.followups[0].status.value=='QUEUED'
    else:assert current.followups==[]


@pytest.mark.asyncio
async def test_thread_fields_and_draft_share_one_actual_read_snapshot(tmp_path,monkeypatch):
    s=await service(tmp_path);thread=await s.create('Before');await s.save_draft(thread.thread_id,'Before draft')
    connection=s.store.connection;changed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'SELECT * FROM conversation_threads WHERE thread_id' not in sql:return cursor
                async def fetchone():
                    nonlocal changed
                    row=await cursor.fetchone()
                    if not changed:
                        changed=True
                        with sqlite3.connect(s.store.path) as owner:
                            owner.execute("UPDATE conversation_threads SET title='After' WHERE thread_id=?",(thread.thread_id,))
                            owner.execute("UPDATE conversation_drafts SET draft_text='After draft' WHERE thread_id=?",(thread.thread_id,));owner.commit()
                    return row
                return SimpleNamespace(fetchone=fetchone)
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def execute(self,sql,params=()):return await execute(sql,params)
            yield Connection()
    monkeypatch.setattr(s.store,'connection',interleaved)
    result=await s.get(thread.thread_id)
    assert changed and (result.title,result.draft_text) in {('Before','Before draft'),('After','After draft')}
    current=await s.get(thread.thread_id)
    assert (current.title,current.draft_text)==('After','After draft')


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['message','followup'])
async def test_archived_thread_refuses_new_owner_work_but_preserves_history(tmp_path,operation):
    s=await service(tmp_path);thread=await s.create('Archived owner work')
    await s.set_status(thread.thread_id,ThreadStatus.ARCHIVED)
    with pytest.raises(ConversationServiceError,match='THREAD_ARCHIVED'):
        if operation=='message':await s.append_message(thread.thread_id,role='OWNER',body='New message')
        else:await s.queue_followup(thread.thread_id,'New queued intent')
    loaded=await s.get(thread.thread_id)
    assert loaded.messages==[] and loaded.followups==[] and loaded.status is ThreadStatus.ARCHIVED


@pytest.mark.asyncio
async def test_two_fresh_main_reads_are_safe_at_a_controlled_creation_race(tmp_path,monkeypatch):
    s=await service(tmp_path);fetchone=s.store.fetchone;gate=asyncio.Event();observed=0
    async def concurrent_read(sql,*args):
        nonlocal observed
        row=await fetchone(sql,*args)
        if 'FROM conversation_threads' in sql and 'MAIN' in sql and row is None:
            observed+=1
            if observed==2:gate.set()
            await asyncio.wait_for(gate.wait(),5)
        return row
    monkeypatch.setattr(s.store,'fetchone',concurrent_read)
    results=await asyncio.gather(s.ensure_main(),s.ensure_main(),return_exceptions=True)
    assert observed==2 and all(not isinstance(item,Exception) for item in results),[type(item).__name__ for item in results]
    assert results[0].thread_id==results[1].thread_id


@pytest.mark.asyncio
async def test_followup_decision_observes_an_actual_competing_owner_decision(tmp_path,monkeypatch):
    s=await service(tmp_path);thread=await s.create('Decision race');followup=await s.queue_followup(thread.thread_id,'Original queued intent')
    connection=s.store.connection;attempted=committed=False
    @asynccontextmanager
    async def interleaved():
        async with connection() as db:
            async def execute(sql,params=()):
                cursor=await db.execute(sql,params)
                if 'SELECT * FROM conversation_followups WHERE thread_id' not in sql:return cursor
                async def fetchone():
                    nonlocal attempted,committed
                    row=await cursor.fetchone()
                    if not attempted:
                        attempted=True
                        with sqlite3.connect(s.store.path,timeout=0) as owner:
                            try:
                                owner.execute("UPDATE conversation_followups SET status='DISMISSED',command_id=NULL WHERE followup_id=?",(followup.followup_id,));owner.commit();committed=True
                            except sqlite3.OperationalError as exc:assert 'locked' in str(exc)
                    return row
                return SimpleNamespace(fetchone=fetchone)
            class Connection:
                def __getattr__(self,name):return getattr(db,name)
                async def execute(self,sql,params=()):return await execute(sql,params)
            yield Connection()
    monkeypatch.setattr(s.store,'connection',interleaved)
    try:result=await s.decide_followup(thread.thread_id,followup.followup_id,'promote')
    except Exception as exc:result=exc
    assert attempted
    row=await s.store.fetchone('SELECT status FROM conversation_followups WHERE followup_id=?',(followup.followup_id,))
    if committed:
        assert isinstance(result,ConversationServiceError) and result.code=='FOLLOWUP_ALREADY_DECIDED'
        assert row['status']=='DISMISSED'
    else:
        assert not isinstance(result,Exception) and result.status.value=='PROMOTED' and row['status']=='PROMOTED'
        with pytest.raises(ConversationServiceError,match='FOLLOWUP_ALREADY_DECIDED'):
            await s.decide_followup(thread.thread_id,followup.followup_id,'dismiss')
