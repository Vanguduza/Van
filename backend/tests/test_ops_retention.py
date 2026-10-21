"""P3-OPS-001 — every unbounded store has a retention class, and the sweep honours it.

The first test is the one that keeps this true: it reads the *live* schema and
fails if any table is unassigned. The reason the system had exactly one retention
setting in it was that nothing ever compared the policy to the schema.
"""

from __future__ import annotations

import time

import pytest

from conftest_automation import make_store
from van_gateway.audit.service import AuditService
from van_gateway.ops.retention import (
    BY_TABLE,
    POLICIES,
    RETENTION_DAYS,
    RetentionClass,
    RetentionService,
    TimeUnit,
)

DAY_MS = 86_400_000


async def _tables(store) -> set[str]:
    rows = await store.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return {str(row["name"]) for row in rows}


@pytest.mark.asyncio
async def test_every_table_in_the_live_schema_has_a_retention_class(tmp_path):
    store = await make_store(tmp_path)
    tables = await _tables(store)
    unassigned = sorted(tables - set(BY_TABLE))
    assert not unassigned, (
        f"{len(unassigned)} tables have no retention class: {unassigned}. "
        "A new table must be assigned one; see van_gateway/ops/retention.py."
    )
    stale = sorted(set(BY_TABLE) - tables)
    assert not stale, f"policy names tables that no longer exist: {stale}"


def test_a_pruned_class_must_name_the_column_that_says_how_old_a_row_is():
    for policy in POLICIES:
        days = RETENTION_DAYS[policy.retention]
        if days is not None and policy.retention is not RetentionClass.CHILD:
            assert policy.column, policy.table


def test_the_classes_that_never_delete_say_why():
    """OWNER_STATE and CHILD are exemptions, and an exemption without a reason is
    indistinguishable from an oversight."""
    for policy in POLICIES:
        if policy.retention is RetentionClass.OWNER_STATE and not policy.note:
            # A note is not required on every owner table — "it is the owner's" is
            # the whole reason — but the class itself must be one that never prunes.
            assert RETENTION_DAYS[RetentionClass.OWNER_STATE] is None
        if policy.retention is RetentionClass.CHILD:
            assert policy.parent is not None, policy.table


@pytest.mark.asyncio
async def test_a_row_past_its_horizon_goes_and_one_inside_it_stays(tmp_path):
    store = await make_store(tmp_path)
    now_ms = int(time.time() * 1000)
    now_s = now_ms // 1000
    # `events` is DERIVED: 30 days.
    await store.execute(
        "INSERT INTO events(event_type, payload_json, created_at_unix) VALUES (?, ?, ?)",
        ("old.event", "{}", now_s - 40 * 86_400),
    )
    await store.execute(
        "INSERT INTO events(event_type, payload_json, created_at_unix) VALUES (?, ?, ?)",
        ("fresh.event", "{}", now_s - 3 * 86_400),
    )
    results = {r.table: r for r in await RetentionService(store).prune(now_ms=now_ms)}
    assert results["events"].deleted == 1
    remaining = await store.fetchall("SELECT event_type FROM events")
    assert [row["event_type"] for row in remaining] == ["fresh.event"]


@pytest.mark.asyncio
async def test_owner_state_is_never_pruned_however_old_it_is(tmp_path):
    """A mission from two years ago is the owner's record of what they asked for.
    The system does not get to decide it expired."""
    store = await make_store(tmp_path)
    now_ms = int(time.time() * 1000)
    ancient = now_ms - 900 * DAY_MS
    await store.execute(
        "INSERT INTO missions(mission_id, owner_principal_id, origin, origin_channel, "
        "title, goal, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-old", "owner", "OWNER_VOICE", "VOICE", "old", "old", ancient, ancient),
    )
    await RetentionService(store).prune(now_ms=now_ms)
    rows = await store.fetchall("SELECT mission_id FROM missions")
    assert [row["mission_id"] for row in rows] == ["m-old"]


@pytest.mark.asyncio
async def test_recovery_authority_survives_age_pruning_and_tracks_its_parent(tmp_path):
    """A timer must not erase delayed lifecycle reports or earned pairing recovery."""
    store = await make_store(tmp_path)
    now_ms = int(time.time() * 1000)
    ancient = now_ms - 900 * DAY_MS
    await store.execute(
        "INSERT INTO missions(mission_id, owner_principal_id, origin, origin_channel, "
        "title, goal, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-recovery", "owner", "OWNER_VOICE", "VOICE", "t", "g", ancient, ancient),
    )
    await store.execute(
        "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix) VALUES (?, ?, ?)",
        ("d-recovery", "synthetic test key", ancient // 1000),
    )
    await store.execute(
        "INSERT INTO hermes_run_bindings(hermes_run_id, mission_id, bound_at_ms) VALUES (?, ?, ?)",
        ("run-recovery", "m-recovery", ancient),
    )
    await store.execute(
        "INSERT INTO hermes_result_inbox(hermes_run_id, outcome, summary, received_at_ms) "
        "VALUES (?, ?, ?, ?)", ("run-before-bind", "COMPLETED", "delayed report", ancient),
    )
    await store.execute(
        "INSERT INTO pairing_attempts(pairing_ticket_hash, device_id, request_hash, "
        "access_token_hash, created_at_unix) VALUES (?, ?, ?, ?, ?)",
        ("ticket-hash", "d-recovery", "body-hash", "token-hash", ancient // 1000),
    )
    await RetentionService(store).prune(now_ms=now_ms)
    assert len(await store.fetchall("SELECT * FROM hermes_run_bindings")) == 1
    assert len(await store.fetchall("SELECT * FROM hermes_result_inbox")) == 1
    assert len(await store.fetchall("SELECT * FROM pairing_attempts")) == 1

    # Restore/owner deletion can leave old-schema orphans; the existing child sweep
    # removes correlation records only when their authoritative parent is absent.
    async with store.connection() as db:
        await db.execute("PRAGMA foreign_keys = OFF")
        await db.execute("DELETE FROM missions WHERE mission_id = 'm-recovery'")
        await db.execute("DELETE FROM devices WHERE device_id = 'd-recovery'")
        await db.commit()
    await RetentionService(store).prune(now_ms=now_ms)
    assert await store.fetchall("SELECT * FROM hermes_run_bindings") == []
    assert await store.fetchall("SELECT * FROM pairing_attempts") == []
    assert len(await store.fetchall("SELECT * FROM hermes_result_inbox")) == 1


@pytest.mark.asyncio
async def test_session_retirement_preserves_live_admission_then_removes_grant_producer_and_transfer(tmp_path):
    from van_gateway.browser.control_lease import ControlLeaseService
    from van_gateway.browser.interactive_models import Viewport
    from van_gateway.browser.interactive_service import InteractiveSessionService
    from van_gateway.browser.producer_service import BrowserProducerService, credential_principal
    from van_gateway.browser.service import BrowserSessionBroker
    from van_gateway.browser.stream_grants import StreamGrantService, StreamGrantSigner, generate_signing_key

    store = await make_store(tmp_path)
    now = int(time.time() * 1000)
    old = now - 91 * DAY_MS
    await store.execute("INSERT INTO devices(device_id,public_key_pem,enrolled_at_unix) VALUES('phone','test-key',?)", (old // 1000,))
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="public_research", now_ms=old)
    sessions = InteractiveSessionService(store, broker, ControlLeaseService(store))
    session = await sessions.create(owner_device_id="phone", profile_alias="public_research",
        viewport=Viewport(width=1080, height=1920, device_scale_factor=1), now_ms=old)
    grants = StreamGrantService(store, StreamGrantSigner(generate_signing_key("retention-test")))
    token, _ = await grants.mint(session_id=session.session_id, device_id="phone", profile_alias="public_research",
        scope=["browser.view", "webrtc.signal", "browser.owner_input"], max_width=1080, max_height=1920,
        max_fps=60, now_ms=old)
    producer = BrowserProducerService(store=store, sessions=sessions, grants=grants)
    await producer.redeem(stream_grant=token, producer_session_id="producer_retention_0123456789",
                          principal=credential_principal("retention-machine-token"), now_ms=old)
    await store.execute("""INSERT INTO browser_owner_transfer_grants(
        transfer_id,token_sha256,producer_session_id,session_id,owner_device_id,operation,resource_id,target_id,
        profile_lease_id,profile_generation,control_lease_id,control_generation,viewport_revision,metadata_json,
        created_at_ms,expires_at_ms) VALUES('transfer','hash','producer_retention_0123456789',?,'phone','upload','chooser','target',
        'profile-lease',1,'control-lease',1,1,'{}',?,?)""", (session.session_id, old, old + 60_000))
    # A renewed live session retains its canonical producer mint row even though
    # the original short redemption window and age horizon have elapsed.
    await store.execute("UPDATE browser_interactive_sessions SET expires_at_ms=? WHERE session_id=?", (now + 60_000, session.session_id))
    await RetentionService(store).prune(now_ms=now)
    assert len(await store.fetchall("SELECT * FROM browser_stream_grants")) == 1
    assert len(await store.fetchall("SELECT * FROM browser_stream_producers")) == 1
    assert len(await store.fetchall("SELECT * FROM browser_owner_transfer_grants")) == 1
    await store.execute("UPDATE browser_interactive_sessions SET expires_at_ms=? WHERE session_id=?", (now - 1, session.session_id))
    # Its independently retained event evidence outlives the live episode. Do
    # not silently erase that evidence or fail the sweep on its foreign key.
    await RetentionService(store).prune(now_ms=now)
    assert len(await store.fetchall("SELECT * FROM browser_stream_producers")) == 1
    await store.execute("UPDATE browser_session_events SET occurred_at_ms=?", (now - 400 * DAY_MS,))
    await RetentionService(store).prune(now_ms=now)
    results = {row.table: row for row in await RetentionService(store).prune(now_ms=now)}
    assert results["browser_stream_grants"].deleted == 1
    assert results["browser_stream_producers"].deleted == 1
    assert results["browser_owner_transfer_grants"].deleted == 1
    assert await store.fetchall("SELECT * FROM browser_stream_producers") == []
    assert await store.fetchall("SELECT * FROM browser_owner_transfer_grants") == []
    assert await store.fetchone("SELECT session_id FROM browser_interactive_sessions") is None


@pytest.mark.asyncio
async def test_an_orphaned_child_row_is_swept(tmp_path):
    """The foreign key stops an orphan being *created*, which is why the sweep is
    a floor rather than the mechanism. It still has to hold, because a database
    restored from before the constraint existed, or edited by hand, can contain
    orphans the constraint will never notice — and a mission_events row pointing
    at a mission that is gone is a timeline entry nothing can render."""
    store = await make_store(tmp_path)
    now_ms = int(time.time() * 1000)
    await store.execute(
        "INSERT INTO missions(mission_id, owner_principal_id, origin, origin_channel, "
        "title, goal, created_at_ms, updated_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-1", "owner", "OWNER_VOICE", "VOICE", "t", "g", now_ms, now_ms),
    )
    await store.execute(
        "INSERT INTO mission_events(event_id, mission_id, event_type, actor, occurred_at_ms) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e-1", "m-1", "MISSION_CREATED", "van", now_ms),
    )
    async with store.connection() as db:
        await db.execute("PRAGMA foreign_keys = OFF")
        await db.execute("DELETE FROM missions WHERE mission_id = 'm-1'")
        await db.commit()

    results = {r.table: r for r in await RetentionService(store).prune(now_ms=now_ms)}
    assert results["mission_events"].deleted == 1
    assert await store.fetchall("SELECT event_id FROM mission_events") == []


@pytest.mark.asyncio
async def test_the_audit_log_is_not_touched_by_the_ordinary_sweep(tmp_path):
    """A `DELETE ... WHERE created_at < ?` on a hash-chained table is exactly the
    operation that breaks the chain silently."""
    store = await make_store(tmp_path)
    audit = AuditService(store)
    await audit.record(result="accepted", command_id="c1")
    tables = {r.table for r in await RetentionService(store).prune()}
    assert "audit" not in tables
    assert (await audit.verify_chain())["ok"] is True


@pytest.mark.asyncio
async def test_pruning_the_audit_prefix_leaves_a_chain_that_still_verifies(tmp_path):
    store = await make_store(tmp_path)
    audit = AuditService(store)
    now_ms = int(time.time() * 1000)
    for index in range(6):
        await audit.record(result="accepted", command_id=f"c{index}")
    # Age the first three rows past the two-year horizon.
    old = (now_ms // 1000) - 800 * 86_400
    await store.execute(
        "UPDATE audit SET created_at_unix = ? WHERE chain_seq <= 3", (old,)
    )
    # Re-hash them so the chain is still internally consistent before the prune;
    # otherwise this test would be proving the prune fixed a break it introduced.
    rows = await store.fetchall(
        "SELECT id, command_id, device_id, result, failure_reason, before_json, "
        "after_json, created_at_unix, chain_seq, prev_hash FROM audit ORDER BY chain_seq"
    )
    prev = "0" * 64
    for row in rows:
        digest = AuditService.entry_digest(
            seq=int(row["chain_seq"]), prev_hash=prev, audit_id=str(row["id"]),
            command_id=row["command_id"], device_id=row["device_id"],
            result=str(row["result"]), failure_reason=row["failure_reason"],
            before_json=row["before_json"], after_json=row["after_json"],
            created_at_unix=int(row["created_at_unix"]),
        )
        await store.execute(
            "UPDATE audit SET prev_hash = ?, entry_hash = ? WHERE chain_seq = ?",
            (prev, digest, int(row["chain_seq"])),
        )
        prev = digest
    assert (await audit.verify_chain())["ok"] is True

    report = await RetentionService(store).prune_audit_prefix(now_ms=now_ms)
    assert report["pruned"] == 3
    assert report["anchor_seq"] == 3

    verified = await audit.verify_chain()
    assert verified["ok"] is True, verified
    assert verified["checked"] == 3
    assert verified["anchor_seq"] == 3
    assert verified["pruned_rows"] == 3


@pytest.mark.asyncio
async def test_a_tampered_row_after_an_anchor_is_still_caught(tmp_path):
    """The point of anchoring rather than resetting: pruning must not buy
    tamper-evidence back by forgetting what the chain used to be."""
    store = await make_store(tmp_path)
    audit = AuditService(store)
    await store.execute(
        "INSERT INTO audit_chain_anchors(anchor_seq, anchor_hash, pruned_rows, created_at_unix) "
        "VALUES (?, ?, ?, ?)", (10, "a" * 64, 10, 1),
    )
    await store.execute(
        "INSERT INTO audit(id, result, created_at_unix, chain_seq, prev_hash, entry_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("x", "accepted", 2, 11, "a" * 64, "wrong-hash"),
    )
    verified = await audit.verify_chain()
    assert verified["ok"] is False
    assert verified["broken_at"] == 11


@pytest.mark.asyncio
async def test_a_prune_is_visible_afterwards(tmp_path):
    """An anchor that recorded nothing would make a prune indistinguishable from
    somebody deleting rows by hand."""
    store = await make_store(tmp_path)
    audit = AuditService(store)
    await audit.record(result="accepted", command_id="c1")
    await store.execute("UPDATE audit SET created_at_unix = ?", (1,))
    await RetentionService(store).prune_audit_prefix()
    anchor = await audit.chain_anchor()
    assert anchor is not None
    assert anchor["pruned_rows"] == 1


def test_seconds_and_millisecond_columns_are_not_confused():
    """A cutoff computed in the wrong unit deletes everything or nothing."""
    service = RetentionService.cutoff_for
    now_ms = 1_700_000_000_000
    ms_policy = BY_TABLE["context_snapshots"]
    s_policy = BY_TABLE["events"]
    assert ms_policy.unit is TimeUnit.MS
    assert s_policy.unit is TimeUnit.SECONDS
    assert service(ms_policy, now_ms) == now_ms - 365 * DAY_MS
    assert service(s_policy, now_ms) == now_ms // 1000 - 30 * 86_400
