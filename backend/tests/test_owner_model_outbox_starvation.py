"""No row can starve another target's delivery (reviewer D, outbox starvation).

`drain_outbox` read `ORDER BY created_at LIMIT 100` across every target. D's probe: 60
events x 3 targets, a handler only for HINDSIGHT_OWNER, and five drains still left 10
HINDSIGHT rows PENDING, because the unhandled targets' rows filled each batch.
"""

from __future__ import annotations

from conftest_automation import make_store

from van_gateway.understanding.owner_model_outbox import (
    OutboxEventKind,
    OutboxTarget,
    backoff_ms,
    drain_outbox,
    write_outbox,
)

H = OutboxTarget.HINDSIGHT_OWNER


async def _events(store, n: int, targets=tuple(OutboxTarget)) -> list[str]:
    ids = []
    async with store.connection() as db:
        for i in range(n):
            ids.append(await write_outbox(
                db, owner_principal_id="owner", owner_model_revision=i + 1,
                event_kind=OutboxEventKind.REJECTED, payload={}, now_ms=i, targets=targets))
        await db.commit()
    return ids


async def _pending(store, target: OutboxTarget) -> int:
    row = await store.fetchone(
        "SELECT COUNT(*) AS n FROM owner_model_outbox WHERE target = ? AND status = 'PENDING'",
        (target.value,))
    return int(row["n"])


async def test_unhandled_targets_do_not_starve_a_handled_one(tmp_path):
    """D's probe O5, asserted: one drain clears the handled target."""
    store = await make_store(tmp_path)
    await _events(store, 60)

    async def ok(event):
        return f"r:{event.outbox_id}"

    report = await drain_outbox(store, {H: ok}, now_ms=100)
    assert len(report.delivered) == 60 and report.failed == []
    assert await _pending(store, H) == 0
    # Still reported, still untouched.
    assert {t for _, t in report.unhandled} == {
        "OPENVIKING_OWNER_PROJECTION", "PERSONAL_CONTEXT_CACHE"}
    row = await store.fetchone(
        "SELECT MAX(attempts) AS a FROM owner_model_outbox WHERE target != 'HINDSIGHT_OWNER'")
    assert row["a"] == 0


async def test_poison_rows_back_off_and_are_dead_lettered(tmp_path):
    """100 oldest rows always fail. They must not occupy every batch, and after the attempt
    budget they are parked for good."""
    store = await make_store(tmp_path)
    ids = await _events(store, 150, targets=(H,))
    poison = set(ids[:100])

    async def handler(event):
        if event.outbox_id in poison:
            raise ValueError("poison")
        return f"r:{event.outbox_id}"

    first = await drain_outbox(store, {H: handler}, now_ms=1_000, max_attempts=3)
    assert len(first.failed) == 100 and first.delivered == []
    # Same instant: every poison row is backing off, so the batch reaches the good rows.
    second = await drain_outbox(store, {H: handler}, now_ms=1_000, max_attempts=3)
    assert len(second.delivered) == 50 and second.failed == []
    assert await _pending(store, H) == 100

    now = 1_000
    for failures in (1, 2):
        now += backoff_ms(failures)
        report = await drain_outbox(store, {H: handler}, now_ms=now, max_attempts=3)
        assert len(report.failed) == 100
    assert len(report.dead_lettered) == 100
    rows = await store.fetchall(
        "SELECT attempts, last_error, dead_lettered_at_ms, status FROM owner_model_outbox "
        "WHERE status = 'PENDING'")
    assert len(rows) == 100 and all(
        r["attempts"] == 3 and r["last_error"] == "ValueError"
        and r["dead_lettered_at_ms"] == now and r["status"] == "PENDING" for r in rows)
    # Parked: never selected again, however late the drain.
    later = await drain_outbox(store, {H: handler}, now_ms=now + 10**9, max_attempts=3)
    assert later.failed == [] and later.delivered == [] and later.dead_lettered == []


async def test_a_failed_row_is_retried_once_its_backoff_elapses(tmp_path):
    store = await make_store(tmp_path)
    await _events(store, 1, targets=(H,))
    calls = []

    async def flaky(event):
        calls.append(event.attempts)
        if len(calls) == 1:
            raise ConnectionError
        return "ok"

    await drain_outbox(store, {H: flaky}, now_ms=0)
    assert (await drain_outbox(store, {H: flaky}, now_ms=backoff_ms(1) - 1)).delivered == []
    done = await drain_outbox(store, {H: flaky}, now_ms=backoff_ms(1))
    assert len(done.delivered) == 1 and calls == [0, 1]
    assert backoff_ms(1) == 1_000 and backoff_ms(3) == 4_000 and backoff_ms(40) == 15 * 60_000


async def test_undecodable_payload_row_is_an_attempt_not_a_drain_abort(tmp_path):
    """A-MIN-VAN (reviewer D2): `json.loads(payload_json)` ran outside the try, so one
    oldest row with a corrupt payload raised JSONDecodeError out of every drain and the
    five good rows behind it stayed PENDING forever (10 drains, bad row attempts 0)."""
    from van_gateway.understanding.owner_model_outbox import DEFAULT_MAX_ATTEMPTS

    store = await make_store(tmp_path)
    good = await _events(store, 5, targets=(H,))
    await store.execute(
        "INSERT INTO owner_model_outbox(outbox_id, target, owner_principal_id, owner_model_revision, "
        "event_kind, payload_json, created_at_ms) "
        "VALUES ('bad', 'HINDSIGHT_OWNER', 'owner', 1, 'REJECTED', '{not json', -1)")
    seen: list[str] = []

    async def ok(event):
        seen.append(event.outbox_id)
        return f"r:{event.outbox_id}"

    first = await drain_outbox(store, {H: ok}, now_ms=100)
    assert sorted(k for k, _ in first.delivered) == sorted(good)
    assert first.failed == [("bad", H.value, "OUTBOX_PAYLOAD_UNDECODABLE")]
    assert "bad" not in seen
    assert await _pending(store, H) == 1
    now = 100
    for _ in range(DEFAULT_MAX_ATTEMPTS - 1):
        now += 10**9
        report = await drain_outbox(store, {H: ok}, now_ms=now)
    assert report.dead_lettered == [("bad", H.value, "OUTBOX_PAYLOAD_UNDECODABLE")]
    bad = await store.fetchone(
        "SELECT attempts, dead_lettered_at_ms, last_error FROM owner_model_outbox WHERE outbox_id = 'bad'")
    assert bad["attempts"] == DEFAULT_MAX_ATTEMPTS and bad["dead_lettered_at_ms"] == now
    assert bad["last_error"] == "OUTBOX_PAYLOAD_UNDECODABLE"
    after = await drain_outbox(store, {H: ok}, now_ms=now + 10**9)
    assert after.failed == [] and after.delivered == []
