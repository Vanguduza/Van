from __future__ import annotations

import pytest

from van_gateway.conversations.models import ThreadStatus
from van_gateway.conversations.service import ConversationService,ConversationServiceError
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_main_thread_is_stable_and_cannot_archive(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=ConversationService(store)
    first=await service.ensure_main(now_ms=1)
    second=await service.ensure_main(now_ms=2)
    assert first.thread_id==second.thread_id
    with pytest.raises(ConversationServiceError,match="MAIN_THREAD_CANNOT_ARCHIVE"):
        await service.set_status(first.thread_id,ThreadStatus.ARCHIVED)


@pytest.mark.asyncio
async def test_side_thread_archive_restore_replay_is_non_executing(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=ConversationService(store)
    thread=await service.create("Research",now_ms=1)
    message=await service.append_message(
        thread.thread_id,role="VAN",body="Completed",command_id="cmd1",mission_id="m1",
        artifact_refs=["art1"],terminal=True,now_ms=2,
    )
    assert message.terminal is True
    await service.save_draft(thread.thread_id,"next question",now_ms=3)
    archived=await service.set_status(thread.thread_id,ThreadStatus.ARCHIVED,now_ms=4)
    assert archived.status is ThreadStatus.ARCHIVED
    restored=await service.set_status(thread.thread_id,ThreadStatus.ACTIVE,now_ms=5)
    assert restored.messages[0].message_id==message.message_id
    assert restored.messages[0].terminal is True
    assert restored.draft_text=="next question"


@pytest.mark.asyncio
async def test_followup_queue_never_executes_by_itself(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3")); await store.migrate()
    service=ConversationService(store)
    thread=await service.create("Follow-ups",now_ms=1)
    item=await service.queue_followup(thread.thread_id,"Check the supplier reply",now_ms=2)
    assert item.status.value=="QUEUED"
    assert item.command_id is None
    loaded=await service.get(thread.thread_id)
    assert loaded is not None and loaded.followups[0].followup_id==item.followup_id

    promoted=await service.decide_followup(
        thread.thread_id,item.followup_id,"promote",now_ms=4
    )
    assert promoted.status.value=="PROMOTED"
    assert promoted.command_id is None
    with pytest.raises(ConversationServiceError,match="FOLLOWUP_ALREADY_DECIDED"):
        await service.decide_followup(thread.thread_id,item.followup_id,"dismiss",now_ms=5)
