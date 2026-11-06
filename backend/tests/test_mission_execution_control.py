"""Actual SQLite recovery, ordering and admission boundaries of mission control."""

from __future__ import annotations

import asyncio
import sqlite3
import sys

import pytest

from van_gateway.mission.control import (
    MissionControlError,
    MissionExecutionControlService,
    require_mission_dispatch,
)
from van_gateway.mission.models import TERMINAL_STATES
from van_gateway.storage.db import Store

MISSION = "mission-control-test"
RUN = "actual-create-receipt-run"
OWNER = "device:owner-control-test"


@pytest.fixture
async def controls(tmp_path):
    store = Store(str(tmp_path / "mission-control.sqlite3"))
    await store.migrate()
    await store.execute(
        "INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES (?,?,?)",
        (OWNER[7:], "test owner public key", 1),
    )
    await store.execute(
        "INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,"
        "authority_envelope_json,created_at_ms,updated_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (MISSION, "owner", "OWNER_UI", "UI", "Control test", "Complete existing mission", "RUNNING",
         '{"max_action_class":"A2"}', 1, 1),
    )
    return MissionExecutionControlService(store)


async def bind(service, mission_id=MISSION, run_id=RUN):
    await service.store.execute(
        "INSERT INTO hermes_run_bindings(hermes_run_id,mission_id,bound_at_ms) VALUES (?,?,?)",
        (run_id, mission_id, 1),
    )


async def request(service, operation="PAUSE", generation=0, request_id="owner-request-1", **kwargs):
    return await service.request(mission_id=MISSION, request_id=request_id, operation=operation,
                                 expected_generation=generation, requested_by=OWNER, **kwargs)


async def ack(service, receipt, *, generation=None, **kwargs):
    body = dict(mission_id=MISSION, hermes_run_id=RUN, control_id=receipt["control_id"],
                generation=receipt["generation"] if generation is None else generation,
                payload_digest=receipt["payload_digest"], checkpoint_ref="checkpoint://safe-boundary/1")
    body.update(kwargs)
    return await service.acknowledge(**body)


def refuses(code):
    return pytest.raises(MissionControlError, match=code)


async def test_default_dispatch_is_running_and_does_not_claim_a_worker_report(controls):
    state = await controls.read(MISSION)
    assert state["generation"] == 0
    assert state["desired_execution"] == "RUNNING" and state["dispatch_allowed"]
    assert state["hermes_run_id"] is None
    assert state["latest_worker_report"] is None and state["pending_directions"] == []
    await require_mission_dispatch(controls.store, MISSION)


async def test_pause_resume_fence_is_independent_of_lifecycle_and_authority(controls):
    initial = await controls.store.fetchone("SELECT state,authority_envelope_json FROM missions WHERE mission_id=?", (MISSION,))
    pause = await request(controls)
    assert pause["status"] == "CONTROL_RECORDED" and pause["generation"] == 1
    assert pause["hermes_run_id"] is None
    with refuses("MISSION_DISPATCH_PAUSED") as caught:
        await require_mission_dispatch(controls.store, MISSION)
    assert caught.value.reason == caught.value.code
    assert (await controls.read(MISSION))["latest_worker_report"] is None
    await request(controls, "DIRECTION", 1, "owner-direction-1", direction="Keep the existing authority.")
    with refuses("MISSION_DISPATCH_PAUSED"):
        await require_mission_dispatch(controls.store, MISSION)
    await request(controls, "RESUME", 2, "owner-resume-1")
    await require_mission_dispatch(controls.store, MISSION)
    final = await controls.store.fetchone("SELECT state,authority_envelope_json FROM missions WHERE mission_id=?", (MISSION,))
    assert tuple(initial) == tuple(final)


async def test_writer_connection_helper_does_not_open_or_commit_another_transaction(controls, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("supplied writer must be used")

    monkeypatch.setattr(controls.store, "fetchone", forbidden)
    async with controls.store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute("UPDATE missions SET title='uncommitted admission' WHERE mission_id=?", (MISSION,))
        await require_mission_dispatch(controls.store, MISSION, db=db)
        assert db.in_transaction
        await db.rollback()
    row = await Store(controls.store.path).fetchone("SELECT title FROM missions WHERE mission_id=?", (MISSION,))
    assert row["title"] == "Control test"


async def test_pause_serializes_after_admitted_effect_and_fences_next_effect(controls):
    await controls.store.execute("CREATE TABLE admitted_test_effects(effect_id TEXT PRIMARY KEY)")
    async with controls.store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        await require_mission_dispatch(controls.store, MISSION, db=db)
        await db.execute("INSERT INTO admitted_test_effects VALUES ('already-admitted')")
        pending_pause = asyncio.create_task(request(controls))
        # A competing writer cannot commit PAUSE through the effect admission's
        # lock. The admitted operation may finish; the following one is fenced.
        done, _ = await asyncio.wait({pending_pause}, timeout=0.02)
        assert done == set()
        await db.commit()
    await pending_pause
    async with controls.store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        with refuses("MISSION_DISPATCH_PAUSED"):
            await require_mission_dispatch(controls.store, MISSION, db=db)
        await db.rollback()
    assert len(await controls.store.fetchall("SELECT * FROM admitted_test_effects")) == 1


async def test_lost_owner_reply_exact_retry_and_receipt_read_survive_restart(controls):
    first = await request(controls, now_ms=10)
    restarted = MissionExecutionControlService(Store(controls.store.path))
    retry = await request(restarted, now_ms=20)
    assert retry == first == await restarted.get_request(MISSION, "owner-request-1")
    await request(restarted, "RESUME", 1, "owner-resume-2", now_ms=30)
    assert await request(restarted, now_ms=40) == first
    assert (await restarted.read(MISSION))["generation"] == 2
    assert len(await restarted.store.fetchall("SELECT * FROM mission_control_requests")) == 2


@pytest.mark.parametrize("changed", [
    {"operation": "RESUME"}, {"expected_generation": 1},
    {"operation": "DIRECTION", "direction": "altered body"}, {"requested_by": "device:other-owner"},
])
async def test_same_request_id_with_different_canonical_body_conflicts(controls, changed):
    original = await request(controls)
    await controls.store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES (?,?,?)",
                                 ("other-owner", "test", 1))
    body = dict(mission_id=MISSION, request_id="owner-request-1", operation="PAUSE",
                expected_generation=0, requested_by=OWNER)
    body.update(changed)
    with refuses("MISSION_CONTROL_REQUEST_CONFLICT"):
        await controls.request(**body)
    assert await controls.get_request(MISSION, "owner-request-1") == original
    assert (await controls.read(MISSION))["generation"] == 1


async def test_direction_exact_whitespace_and_unicode_are_bound_in_digest(controls):
    first = await request(controls, "DIRECTION", direction="  résumé\nKeep order.  ")
    assert await request(controls, "DIRECTION", direction="  résumé\nKeep order.  ") == first
    with refuses("MISSION_CONTROL_REQUEST_CONFLICT"):
        await request(controls, "DIRECTION", direction="résumé\nKeep order.")
    assert (await controls.read(MISSION))["pending_directions"][0]["direction"] == "  résumé\nKeep order.  "


async def test_pause_reason_is_preserved_and_changed_reason_cannot_reuse_receipt(controls):
    first = await request(controls, reason="  Wait for the owner's review.\n")
    assert first["reason"] == "  Wait for the owner's review.\n"
    assert await request(controls, reason="  Wait for the owner's review.\n") == first
    with refuses("MISSION_CONTROL_REQUEST_CONFLICT"):
        await request(controls, reason="Wait for the owner's review.")
    assert await controls.get_request(MISSION, "owner-request-1") == first


async def test_optimistic_generation_refuses_stale_new_request(controls):
    await request(controls)
    with refuses("MISSION_CONTROL_GENERATION_CONFLICT"):
        await request(controls, "RESUME", 0, "stale-resume")
    assert (await controls.read(MISSION))["desired_execution"] == "PAUSED"
    assert len(await controls.store.fetchall("SELECT * FROM mission_control_requests")) == 1


async def test_concurrent_exact_owner_retries_commit_one_control(controls):
    receipts = await asyncio.gather(*(request(controls) for _ in range(8)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert len(await controls.store.fetchall("SELECT * FROM mission_control_requests")) == 1
    assert (await controls.read(MISSION))["generation"] == 1


async def test_concurrent_distinct_requests_same_generation_have_one_winner(controls):
    receipts = await asyncio.gather(
        request(controls, request_id="concurrent-pause-a"),
        request(controls, "RESUME", request_id="concurrent-resume-b"), return_exceptions=True,
    )
    assert sum(isinstance(receipt, dict) for receipt in receipts) == 1
    failures = [receipt for receipt in receipts if isinstance(receipt, MissionControlError)]
    assert len(failures) == 1 and failures[0].code == "MISSION_CONTROL_GENERATION_CONFLICT"
    assert (await controls.read(MISSION))["generation"] == 1


async def test_insert_failure_rolls_back_fence_and_retry_can_commit(controls):
    await controls.store.execute("CREATE TRIGGER fail_control_receipt BEFORE INSERT ON mission_control_requests "
                                 "BEGIN SELECT RAISE(ABORT,'receipt persistence failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="receipt persistence failed"):
        await request(controls)
    assert (await controls.read(MISSION))["generation"] == 0
    assert await controls.store.fetchone("SELECT * FROM mission_execution_controls") is None
    await controls.store.execute("DROP TRIGGER fail_control_receipt")
    assert (await request(controls))["generation"] == 1


async def test_final_fence_update_failure_rolls_back_inserted_owner_receipt(controls):
    await controls.store.execute("CREATE TRIGGER fail_fence_update BEFORE UPDATE OF generation ON mission_execution_controls "
                                 "BEGIN SELECT RAISE(ABORT,'fence persistence failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="fence persistence failed"):
        await request(controls)
    assert await controls.store.fetchall("SELECT * FROM mission_control_requests") == []
    assert (await controls.read(MISSION))["generation"] == 0
    await controls.store.execute("DROP TRIGGER fail_fence_update")
    assert (await request(controls))["generation"] == 1


@pytest.mark.parametrize("crash_phase", ["before-final-write", "after-commit"])
async def test_real_process_crash_before_or_after_commit_has_one_recoverable_outcome(controls, crash_phase):
    # Terminate a separate local service process at the actual transaction
    # boundary. No mock database or staged caller response supplies recovery.
    script = r'''
import asyncio, os, sys
import aiosqlite
from van_gateway.mission.control import MissionExecutionControlService
from van_gateway.storage.db import Store
phase, path = sys.argv[1:]
original_execute = aiosqlite.Connection.execute
original_commit = aiosqlite.Connection.commit
def execute(self, sql, parameters=()):
    if phase == "before-final-write" and sql.startswith("UPDATE mission_execution_controls SET generation="):
        os._exit(73)
    return original_execute(self, sql, parameters)
async def commit(self):
    await original_commit(self)
    if phase == "after-commit":
        os._exit(74)
aiosqlite.Connection.execute = execute
aiosqlite.Connection.commit = commit
async def run():
    await MissionExecutionControlService(Store(path)).request(
        mission_id="mission-control-test", request_id="owner-request-1", operation="PAUSE",
        expected_generation=0, requested_by="device:owner-control-test", now_ms=17)
asyncio.run(run())
'''
    child = await asyncio.create_subprocess_exec(sys.executable, "-c", script, crash_phase, controls.store.path,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await asyncio.wait_for(child.communicate(), timeout=10)
    assert child.returncode == (73 if crash_phase == "before-final-write" else 74), (stdout, stderr)
    restarted = MissionExecutionControlService(Store(controls.store.path))
    state = await restarted.read(MISSION)
    assert state["generation"] == (0 if crash_phase == "before-final-write" else 1)
    recovered = await request(restarted, now_ms=99)
    assert recovered["generation"] == 1
    assert recovered["created_at_ms"] == (99 if crash_phase == "before-final-write" else 17)
    assert await restarted.get_request(MISSION, "owner-request-1") == recovered
    assert len(await restarted.store.fetchall("SELECT * FROM mission_control_requests")) == 1


async def test_unbound_controls_fence_locally_and_only_actual_binding_allows_poll_ack(controls):
    pause = await request(controls)
    direction = await request(controls, "DIRECTION", 1, "pending-direction", direction="Read this at the next checkpoint.")
    with refuses("MISSION_CONTROL_RUN_UNBOUND"):
        await controls.poll(mission_id=MISSION, hermes_run_id=RUN)
    with refuses("MISSION_CONTROL_RUN_UNBOUND"):
        await ack(controls, pause, generation=2)
    await bind(controls)
    state = await controls.poll(mission_id=MISSION, hermes_run_id=RUN)
    assert state["generation"] == 2 and state["desired_execution"] == "PAUSED"
    assert state["latest_fence_control"]["control_id"] == pause["control_id"]
    assert state["pending_directions"][0]["control_id"] == direction["control_id"]
    assert state["pending_directions"][0]["hermes_run_id"] == RUN
    assert (await controls.get_request(MISSION, "owner-request-1"))["hermes_run_id"] is None
    assert (await ack(controls, pause, generation=2))["status"] == "CHECKPOINT_RECORDED"


async def test_poll_and_ack_cannot_select_wrong_run_or_different_mission(controls):
    await bind(controls)
    pause = await request(controls)
    with refuses("MISSION_CONTROL_RUN_MISMATCH"):
        await controls.poll(mission_id=MISSION, hermes_run_id="unrelated-run")
    with refuses("MISSION_CONTROL_RUN_MISMATCH"):
        await ack(controls, pause, hermes_run_id="unrelated-run")
    await controls.store.execute(
        "INSERT INTO missions(mission_id,owner_principal_id,origin,origin_channel,title,goal,state,created_at_ms,updated_at_ms) "
        "VALUES ('other-mission','owner','OWNER_UI','UI','other','other','RUNNING',1,1)")
    await bind(controls, "other-mission", "other-run")
    with refuses("MISSION_CONTROL_UNKNOWN"):
        await ack(controls, pause, mission_id="other-mission", hermes_run_id="other-run")


async def test_pinned_binding_cannot_be_replaced_or_removed(controls):
    await bind(controls)
    await request(controls)
    await controls.store.execute("UPDATE hermes_run_bindings SET hermes_run_id='replacement-run' WHERE mission_id=?", (MISSION,))
    with refuses("MISSION_CONTROL_BINDING_CONFLICT"):
        await controls.poll(mission_id=MISSION, hermes_run_id="replacement-run")
    with refuses("MISSION_CONTROL_BINDING_CONFLICT"):
        await request(controls, "RESUME", 1, "replacement-resume")
    await controls.store.execute("DELETE FROM hermes_run_bindings WHERE mission_id=?", (MISSION,))
    with refuses("MISSION_CONTROL_BINDING_CONFLICT"):
        await controls.read(MISSION)


async def test_worker_receipt_reports_checkpoint_without_claiming_process_stop(controls):
    await bind(controls)
    pause = await request(controls)
    worker = await ack(controls, pause, now_ms=30)
    assert worker["status"] == "CHECKPOINT_RECORDED"
    assert worker["process_stopped_verified"] is False and worker["authority_granted"] is False
    assert worker["original_control_generation"] == worker["generation"] == 1
    state = await controls.read(MISSION)
    assert state["latest_worker_report"] == worker
    assert state["desired_execution"] == "PAUSED" and not state["dispatch_allowed"]
    assert (await controls.store.fetchone("SELECT state FROM missions WHERE mission_id=?", (MISSION,)))["state"] == "RUNNING"


async def test_worker_lost_reply_recovers_immutable_historical_receipt_after_restart_and_resume(controls):
    await bind(controls)
    pause = await request(controls)
    first = await ack(controls, pause, now_ms=100)
    restarted = MissionExecutionControlService(Store(controls.store.path))
    await request(restarted, "RESUME", 1, "later-resume", now_ms=200)
    assert await ack(restarted, pause, now_ms=300) == first
    assert (await restarted.read(MISSION))["desired_execution"] == "RUNNING"
    await require_mission_dispatch(restarted.store, MISSION)


@pytest.mark.parametrize("changed,code", [
    ({"generation": 0}, "MISSION_CONTROL_GENERATION_CONFLICT"),
    ({"payload_digest": "sha256:" + "0" * 64}, "MISSION_CONTROL_DIGEST_MISMATCH"),
    ({"control_id": "mctl_unknown"}, "MISSION_CONTROL_UNKNOWN"),
    ({"checkpoint_ref": ""}, "MISSION_CONTROL_INVALID"),
])
async def test_bad_worker_report_never_records_acknowledgement(controls, changed, code):
    await bind(controls)
    pause = await request(controls)
    with refuses(code):
        await ack(controls, pause, **changed)
    assert (await controls.read(MISSION))["latest_worker_report"] is None


async def test_changed_duplicate_ack_conflicts_without_overwriting_original_receipt(controls):
    await bind(controls)
    pause = await request(controls)
    first = await ack(controls, pause)
    with refuses("MISSION_CONTROL_ACK_CONFLICT"):
        await ack(controls, pause, checkpoint_ref="checkpoint://different")
    with refuses("MISSION_CONTROL_ACK_CONFLICT"):
        await ack(controls, pause, generation=2)
    assert (await controls.read(MISSION))["latest_worker_report"] == first


async def test_new_owner_control_makes_old_poll_snapshot_stale(controls):
    await bind(controls)
    pause = await request(controls)
    await controls.poll(mission_id=MISSION, hermes_run_id=RUN)
    await request(controls, "DIRECTION", 1, "new-direction", direction="Newer direction")
    with refuses("MISSION_CONTROL_GENERATION_CONFLICT"):
        await ack(controls, pause)
    assert (await ack(controls, pause, generation=2))["original_control_generation"] == 1


async def test_superseded_fence_cannot_get_fresh_ack_but_directions_remain_pending(controls):
    await bind(controls)
    pause = await request(controls)
    direction = await request(controls, "DIRECTION", 1, "older-direction", direction="Keep this direction")
    resume = await request(controls, "RESUME", 2, "new-resume")
    with refuses("MISSION_CONTROL_SUPERSEDED"):
        await ack(controls, pause, generation=3)
    adoption = await ack(controls, direction, generation=3)
    assert adoption["status"] == "DIRECTION_ADOPTION_RECORDED"
    assert adoption["original_control_generation"] == 2
    assert (await ack(controls, resume))["status"] == "CHECKPOINT_RECORDED"
    assert (await controls.read(MISSION))["pending_directions"] == []


async def test_directions_adopt_in_original_order_across_pause_resume(controls):
    await bind(controls)
    first = await request(controls, "DIRECTION", direction="First")
    second = await request(controls, "DIRECTION", 1, "second-direction", direction="Second")
    await request(controls, "PAUSE", 2, "queue-pause")
    await request(controls, "RESUME", 3, "queue-resume")
    with refuses("MISSION_CONTROL_DIRECTION_ORDER"):
        await ack(controls, second, generation=4)
    one = await ack(controls, first, generation=4)
    two = await ack(controls, second, generation=4)
    assert [one["original_control_generation"], two["original_control_generation"]] == [1, 2]
    assert (await controls.read(MISSION))["pending_directions"] == []
    assert await ack(controls, first, generation=4) == one


async def test_concurrent_exact_acknowledgements_commit_one_immutable_report(controls):
    await bind(controls)
    pause = await request(controls)
    reports = await asyncio.gather(*(ack(controls, pause) for _ in range(8)))
    assert all(report == reports[0] for report in reports)
    assert len(await controls.store.fetchall("SELECT * FROM mission_control_requests WHERE worker_ack_json IS NOT NULL")) == 1


async def test_concurrent_conflicting_acknowledgements_have_one_winner(controls):
    await bind(controls)
    pause = await request(controls)
    reports = await asyncio.gather(
        ack(controls, pause, checkpoint_ref="checkpoint://a"),
        ack(controls, pause, checkpoint_ref="checkpoint://b"), return_exceptions=True,
    )
    assert sum(isinstance(report, dict) for report in reports) == 1
    failure = next(report for report in reports if isinstance(report, MissionControlError))
    assert failure.code == "MISSION_CONTROL_ACK_CONFLICT"


async def test_acknowledgement_write_failure_rolls_back_and_retry_succeeds(controls):
    await bind(controls)
    pause = await request(controls)
    await controls.store.execute("CREATE TRIGGER fail_worker_receipt BEFORE UPDATE OF worker_ack_json ON mission_control_requests "
                                 "BEGIN SELECT RAISE(ABORT,'worker persistence failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="worker persistence failed"):
        await ack(controls, pause)
    assert (await controls.read(MISSION))["latest_worker_report"] is None
    await controls.store.execute("DROP TRIGGER fail_worker_receipt")
    assert (await ack(controls, pause))["status"] == "CHECKPOINT_RECORDED"


@pytest.mark.parametrize("terminal", sorted(state.value for state in TERMINAL_STATES))
async def test_terminal_missions_cannot_resume_or_adopt_new_controls(controls, terminal):
    await bind(controls)
    pause = await request(controls)
    await controls.store.execute("UPDATE missions SET state=? WHERE mission_id=?", (terminal, MISSION))
    with refuses("MISSION_CONTROL_TERMINAL"):
        await request(controls, "RESUME", 1, "terminal-resume")
    with refuses("MISSION_CONTROL_TERMINAL"):
        await ack(controls, pause)
    with refuses("MISSION_CONTROL_TERMINAL"):
        await require_mission_dispatch(controls.store, MISSION)
    assert await request(controls) == pause
    assert (await controls.read(MISSION))["dispatch_allowed"] is False


async def test_historical_worker_ack_recovery_after_cancel_cannot_reopen_mission(controls):
    await bind(controls)
    pause = await request(controls)
    worker = await ack(controls, pause)
    await controls.store.execute("UPDATE missions SET state='CANCELLED' WHERE mission_id=?", (MISSION,))
    assert await ack(controls, pause) == worker
    assert (await controls.read(MISSION))["mission_state"] == "CANCELLED"
    assert not (await controls.read(MISSION))["dispatch_allowed"]


async def test_unknown_mission_and_missing_receipt_refuse(controls):
    with refuses("MISSION_UNKNOWN"):
        await controls.read("absent-mission")
    with refuses("MISSION_UNKNOWN"):
        await require_mission_dispatch(controls.store, "absent-mission")
    with refuses("MISSION_CONTROL_UNKNOWN"):
        await controls.get_request(MISSION, "absent-request")


async def test_revoked_owner_cannot_write_or_replay_control(controls):
    pause = await request(controls)
    await controls.store.execute("UPDATE devices SET revoked_at_unix=2 WHERE device_id=?", (OWNER[7:],))
    with refuses("MISSION_CONTROL_DEVICE_REVOKED"):
        await request(controls, "RESUME", 1, "revoked-resume")
    with refuses("MISSION_CONTROL_DEVICE_REVOKED"):
        await request(controls)
    assert await controls.get_request(MISSION, "owner-request-1") == pause


@pytest.mark.parametrize("changed", [
    {"expected_generation": True}, {"expected_generation": -1}, {"expected_generation": 0.0},
    {"request_id": ""}, {"request_id": " request"}, {"operation": []},
    {"operation": "DIRECTION", "direction": ""}, {"operation": "DIRECTION", "direction": "\ud800"},
    {"direction": "unexpected"}, {"requested_by": "owner"}, {"now_ms": -1},
    {"reason": None}, {"reason": "a" * 2001}, {"reason": "\ud800"},
])
async def test_malformed_requests_cannot_advance_fence(controls, changed):
    body = dict(mission_id=MISSION, request_id="invalid-request", operation="PAUSE",
                expected_generation=0, requested_by=OWNER)
    body.update(changed)
    with refuses("MISSION_CONTROL_INVALID"):
        await controls.request(**body)
    assert (await controls.read(MISSION))["generation"] == 0
