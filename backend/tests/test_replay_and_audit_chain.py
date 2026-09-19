"""P1-SEC-005 replay and concurrency, P1-SEC-006 tamper-evident audit.

Three defects, all found by the whole-system audit:

  * the command nonce was covered by the v2 signature and then never stored, so a captured
    command could be replayed inside its validity window with a fresh idempotency key;
  * the idempotency claim did a SELECT on one connection and an INSERT on another with no
    transaction, so two concurrent identical commands could both proceed;
  * the owner-authority audit log was a flat table with a random UUID and no ordering, so
    rows could be inserted, altered or deleted undetectably.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from van_gateway.audit.service import GENESIS_HASH, AuditService
from van_gateway.command.nonce import CommandNonceService, NonceReplay
from van_gateway.config import get_settings
from van_gateway.idempotency.service import IdempotencyInFlight, IdempotencyService
from van_gateway.storage.db import Store


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "replay.sqlite3"))
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(str(tmp_path / "replay.sqlite3"))
    await s.migrate()
    return s


@pytest.mark.asyncio
class TestNonceReplay:
    async def test_a_nonce_can_only_be_consumed_once(self, store):
        nonces = CommandNonceService(store)
        await nonces.consume(device_id="dev-1", nonce="n-abc", command_id="cmd-1")

        with pytest.raises(NonceReplay) as caught:
            await nonces.consume(device_id="dev-1", nonce="n-abc", command_id="cmd-2")

        assert caught.value.original_command_id == "cmd-1", (
            "the refusal should name the command that first used the nonce"
        )

    async def test_nonces_are_scoped_per_device(self, store):
        """One device must not be able to exhaust or probe another's nonce space."""
        nonces = CommandNonceService(store)
        await nonces.consume(device_id="dev-1", nonce="shared", command_id="cmd-1")
        await nonces.consume(device_id="dev-2", nonce="shared", command_id="cmd-2")

    async def test_concurrent_replays_of_one_nonce_yield_exactly_one_winner(self, store):
        """The race is settled by the database, not by a read-then-write both can win."""
        nonces = CommandNonceService(store)

        async def attempt(n: int):
            try:
                await nonces.consume(device_id="dev-race", nonce="same", command_id=f"cmd-{n}")
                return "accepted"
            except NonceReplay:
                return "refused"

        outcomes = await asyncio.gather(*(attempt(i) for i in range(8)))
        assert outcomes.count("accepted") == 1, f"expected exactly one winner, got {outcomes}"

    async def test_retention_window_exceeds_the_widest_replay_window(self):
        """A nonce pruned while its command is still valid would become replayable again."""
        assert CommandNonceService.RETENTION_SECONDS > 24 * 3600

    async def test_prune_removes_only_expired_nonces(self, store):
        nonces = CommandNonceService(store)
        now = int(time.time())
        await nonces.consume(device_id="d", nonce="old", command_id="c1",
                             now=now - CommandNonceService.RETENTION_SECONDS - 10)
        await nonces.consume(device_id="d", nonce="fresh", command_id="c2", now=now)

        removed = await nonces.prune(now=now)
        assert removed == 1
        with pytest.raises(NonceReplay):
            await nonces.consume(device_id="d", nonce="fresh", command_id="c3")


@pytest.mark.asyncio
class TestIdempotencyAtomicity:
    async def test_concurrent_identical_claims_produce_one_winner(self, store):
        """Two concurrent identical signed commands must not both execute."""
        idem = IdempotencyService(store)
        payload = {"command_id": "c", "text": "do the thing"}

        async def claim():
            try:
                await idem.begin("race-key", payload)
                return "claimed"
            except IdempotencyInFlight:
                return "in_flight"
            except Exception as exc:  # a raw IntegrityError would be a 500 to the owner
                return f"error:{type(exc).__name__}"

        outcomes = await asyncio.gather(*(claim() for _ in range(6)))
        assert outcomes.count("claimed") == 1, f"expected one claim, got {outcomes}"
        assert not any(o.startswith("error:") for o in outcomes), (
            f"a contended claim surfaced as an unhandled error: {outcomes}"
        )


@pytest.mark.asyncio
class TestAuditChain:
    async def test_chain_starts_at_genesis_and_advances(self, store):
        audit = AuditService(store)
        await audit.record(result="accepted", command_id="c1", device_id="d1")
        await audit.record(result="denied", command_id="c2", device_id="d1")

        rows = await store.fetchall(
            "SELECT chain_seq, prev_hash, entry_hash FROM audit ORDER BY chain_seq"
        )
        assert [int(r["chain_seq"]) for r in rows] == [1, 2]
        assert rows[0]["prev_hash"] == GENESIS_HASH
        assert rows[1]["prev_hash"] == rows[0]["entry_hash"], "entries must link"

    async def test_an_intact_chain_verifies(self, store):
        audit = AuditService(store)
        for i in range(5):
            await audit.record(result="accepted", command_id=f"c{i}", device_id="d")
        report = await audit.verify_chain()
        assert report["ok"] is True
        assert report["checked"] == 5

    async def test_altering_a_row_breaks_verification(self, store):
        """The defect: anyone with write access could change an audit row undetectably."""
        audit = AuditService(store)
        for i in range(4):
            await audit.record(result="accepted", command_id=f"c{i}", device_id="d")

        await store.execute("UPDATE audit SET result = ? WHERE chain_seq = ?", ("denied", 2))

        report = await audit.verify_chain()
        assert report["ok"] is False
        assert report["broken_at"] == 2
        assert "hash" in report["reason"]

    async def test_deleting_a_row_breaks_verification(self, store):
        audit = AuditService(store)
        for i in range(4):
            await audit.record(result="accepted", command_id=f"c{i}", device_id="d")

        await store.execute("DELETE FROM audit WHERE chain_seq = ?", (2,))

        report = await audit.verify_chain()
        assert report["ok"] is False
        assert report["broken_at"] == 3
        assert "sequence gap" in report["reason"]

    async def test_tampering_with_an_early_row_invalidates_every_later_row(self, store):
        """prev_hash is inside the digest, so the break propagates forward."""
        audit = AuditService(store)
        for i in range(5):
            await audit.record(result="accepted", command_id=f"c{i}", device_id="d")

        await store.execute(
            "UPDATE audit SET failure_reason = ? WHERE chain_seq = ?", ("rewritten", 1)
        )

        report = await audit.verify_chain()
        assert report["ok"] is False
        assert report["broken_at"] == 1, "the earliest altered row should be named"

    async def test_concurrent_writers_do_not_fork_the_chain(self, store):
        audit = AuditService(store)
        await asyncio.gather(*(
            audit.record(result="accepted", command_id=f"c{i}", device_id="d")
            for i in range(10)
        ))
        report = await audit.verify_chain()
        assert report["ok"] is True, f"concurrent writes forked the chain: {report}"
        assert report["checked"] == 10
