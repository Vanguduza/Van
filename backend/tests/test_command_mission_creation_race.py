"""A database uniqueness fence must return the winning mission to racing retries."""
import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from van_gateway.command.mission_link import CommandMissionLink
from van_gateway.mission.models import MissionEventType
from van_gateway.mission.service import MissionService
from van_gateway.models import ActionClass, CommandRequest, OriginChannel, PrincipalType
from van_gateway.storage.db import Store


def request(command_id="one-command"):
    return CommandRequest(command_id=command_id, idempotency_key="one-key", device_id="owner-phone",
                          issued_at_unix=1, signature="fixture-only", text="read the result",
                          principal_type=PrincipalType.OWNER_DEVICE, origin_channel=OriginChannel.UI,
                          action_class=ActionClass.A1)


@pytest.mark.asyncio
async def test_racing_links_return_one_durable_mission_without_a_constraint_error(tmp_path, monkeypatch):
    database = str(tmp_path / "racing.sqlite3")
    store = Store(database)
    await store.migrate()
    links = [CommandMissionLink(MissionService(Store(database))) for _ in range(2)]
    both_read = asyncio.Event()
    initial_reads = 0

    def delay_initial_read(original):
        async def lookup(command_id):
            nonlocal initial_reads
            result = await original(command_id)
            initial_reads += 1
            ordinal = initial_reads
            if ordinal == 2:
                both_read.set()
            if ordinal <= 2:
                assert result is None
                await asyncio.wait_for(both_read.wait(), timeout=5)
            return result
        return lookup

    for link in links:
        monkeypatch.setattr(link, "existing_for_command", delay_initial_read(link.existing_for_command))
    results = await asyncio.wait_for(asyncio.gather(*[
        link.open(request(), effective_action_class=ActionClass.A1, owner_approved=False)
        for link in links
    ], return_exceptions=True), timeout=10)
    assert not any(isinstance(result, BaseException) for result in results), results
    assert results[0].mission_id == results[1].mission_id
    missions = await store.fetchall("SELECT mission_id FROM missions")
    assert [row["mission_id"] for row in missions] == [results[0].mission_id]
    events = await store.fetchall("SELECT mission_id FROM mission_events WHERE event_type = ?",
                                  (MissionEventType.MISSION_CREATED.value,))
    assert [row["mission_id"] for row in events] == [results[0].mission_id]
    # Recovery after the winning insert has committed retains the same identity too.
    restarted = CommandMissionLink(MissionService(Store(database)))
    restored = await restarted.open(request(), effective_action_class=ActionClass.A1, owner_approved=False)
    assert restored.mission_id == results[0].mission_id


@pytest.mark.asyncio
async def test_an_unrelated_integrity_failure_is_not_disguised_as_a_duplicate_command(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "other-constraint.sqlite3"))
    await store.migrate()
    link = CommandMissionLink(MissionService(store))
    # Force a real primary-key collision belonging to a different source command.
    monkeypatch.setattr("van_gateway.mission.service.uuid.uuid4", lambda: SimpleNamespace(hex="fixed"))
    first = await link.open(request("first-command"), effective_action_class=ActionClass.A1, owner_approved=False)
    with pytest.raises(sqlite3.IntegrityError):
        await link.open(request("different-command"), effective_action_class=ActionClass.A1, owner_approved=False)
    rows = await store.fetchall("SELECT mission_id FROM missions")
    assert [row["mission_id"] for row in rows] == [first.mission_id]


@pytest.mark.asyncio
async def test_a_post_insert_integrity_failure_is_not_reported_as_successful_duplicate_recovery(tmp_path):
    store = Store(str(tmp_path / "post-insert.sqlite3"))
    await store.migrate()

    class BrokenNativeEvent(MissionService):
        async def record_event(self, **kwargs):
            # A canonical mission event is required; optional learning is not. A
            # post-insert native write failure must not become duplicate recovery.
            await store.execute("INSERT INTO missions(mission_id) VALUES (?)", ("incomplete-row",))

    link = CommandMissionLink(BrokenNativeEvent(store))
    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL constraint failed"):
        await link.open(request(), effective_action_class=ActionClass.A1, owner_approved=False)
    assert len(await store.fetchall("SELECT mission_id FROM missions")) == 1
