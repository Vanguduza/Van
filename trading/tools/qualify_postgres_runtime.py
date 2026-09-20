"""Destructive-safe PostgreSQL qualification canary for VATI authority primitives.

The tool refuses to run unless current_database() begins with vati_pr49_qual_.
It exercises real PostgreSQL transactions with independent OS processes:

* shared account-lease arbitration and stale-epoch fencing;
* SELECT FOR UPDATE submission fencing across process takeover;
* database row-lock release when the holder process dies;
* concurrent writers against one VATI hash-chain head.

It never creates or drops a database. The caller owns disposable-database
lifecycle and passes its DSN explicitly.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import time

import psycopg

from vati.app.account_lease import (
    AccountRuntimeLease,
    LeaseOutcome,
    PostgresLeaseStore,
)
from vati.core.events import EventKind, make_event
from vati.core.ledger_pg import PostgresLedger

SAFE_DB_PREFIX = "vati_pr49_qual_"


def _require_disposable_database(dsn: str) -> str:
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            name = str(cur.fetchone()[0])
            if not name.startswith(SAFE_DB_PREFIX):
                raise RuntimeError(
                    f"refusing qualification against non-disposable database {name!r}; "
                    f"name must start with {SAFE_DB_PREFIX!r}"
                )
            cur.execute("CREATE SCHEMA IF NOT EXISTS vati")
            cur.execute("SELECT to_regclass('vati.events')")
            existing = cur.fetchone()[0]
            if existing is not None:
                cur.execute("SELECT COUNT(*) FROM vati.events")
                if int(cur.fetchone()[0]) != 0:
                    raise RuntimeError(
                        "qualification database already contains VATI events; "
                        "use a new disposable database"
                    )
    return name


def _acquire_worker(
    dsn: str,
    alias: str,
    instance: str,
    now_ms: int,
    ttl_ms: int,
    queue,
    ready=None,
) -> None:
    store = PostgresLeaseStore(dsn)
    try:
        lease = AccountRuntimeLease(
            store,
            account_alias=alias,
            instance_id=instance,
            ttl_ms=ttl_ms,
        )
        if ready is not None:
            ready.set()
        started = time.monotonic()
        result = lease.acquire(now_ms=now_ms)
        queue.put(
            {
                "outcome": result.outcome.value,
                "epoch": result.lease.lease_epoch if result.lease else None,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        )
    finally:
        store.close()


def _hold_guard_worker(dsn: str, alias: str, ready) -> None:
    store = PostgresLeaseStore(dsn)
    try:
        lease = AccountRuntimeLease(
            store,
            account_alias=alias,
            instance_id="crash-holder",
            ttl_ms=1_000,
        )
        result = lease.acquire(now_ms=1_000)
        if result.outcome is not LeaseOutcome.GRANTED:
            raise RuntimeError(
                f"crash holder could not acquire lease: {result.outcome.value}"
            )
        with lease.submission_guard(lease.epoch, now_ms=1_500) as allowed:
            if not allowed:
                raise RuntimeError("crash-holder submission guard refused")
            ready.set()
            time.sleep(30)
    finally:
        store.close()


def _append_worker(dsn: str, producer: str, count: int, queue) -> None:
    ledger = PostgresLedger(dsn, ledger_name="vati")
    try:
        for idx in range(count):
            stamp = 10_000 + idx
            ledger.append(
                make_event(
                    EventKind.SESSION,
                    producer,
                    {"event": "QUAL_APPEND", "writer": producer, "i": idx},
                    event_time_ms=stamp,
                    received_time_ms=stamp,
                    correlation_id=f"{producer}-{idx}",
                )
            )
        queue.put({"producer": producer, "count": count})
    finally:
        ledger.close()


def qualify(dsn: str) -> dict[str, object]:
    db_name = _require_disposable_database(dsn)
    ctx = mp.get_context("spawn")

    bootstrap = PostgresLedger(dsn, ledger_name="vati")
    bootstrap.close()

    store_a = PostgresLeaseStore(dsn)
    store_b = PostgresLeaseStore(dsn)
    try:
        a = AccountRuntimeLease(
            store_a,
            account_alias="qual-account",
            instance_id="host-a",
            ttl_ms=5_000,
        )
        b = AccountRuntimeLease(
            store_b,
            account_alias="qual-account",
            instance_id="host-b",
            ttl_ms=5_000,
        )
        assert a.acquire(now_ms=1_000).outcome is LeaseOutcome.GRANTED
        assert (
            b.acquire(now_ms=2_000).outcome
            is LeaseOutcome.REFUSED_HELD_BY_OTHER
        )
        stale_epoch = a.epoch
        assert a.fence(stale_epoch, now_ms=2_000, min_validity_ms=0)
        takeover = b.acquire(now_ms=7_000)
        assert takeover.outcome is LeaseOutcome.GRANTED
        assert takeover.lease is not None and takeover.lease.lease_epoch == 2
        assert not a.fence(stale_epoch, now_ms=7_001, min_validity_ms=0)
    finally:
        store_a.close()
        store_b.close()

    guard_store = PostgresLeaseStore(dsn)
    holder = AccountRuntimeLease(
        guard_store,
        account_alias="guard-account",
        instance_id="guard-holder",
        ttl_ms=1_000,
    )
    assert holder.acquire(now_ms=1_000).outcome is LeaseOutcome.GRANTED
    queue = ctx.Queue()
    contender_ready = ctx.Event()
    with holder.submission_guard(holder.epoch, now_ms=1_500) as allowed:
        assert allowed
        contender = ctx.Process(
            target=_acquire_worker,
            args=(
                dsn,
                "guard-account",
                "guard-contender",
                3_000,
                5_000,
                queue,
                contender_ready,
            ),
        )
        contender.start()
        assert contender_ready.wait(5), "contender did not reach acquire boundary"
        time.sleep(0.6)
        assert contender.is_alive(), (
            "takeover completed while the submission row lock was held"
        )
    contender.join(5)
    assert contender.exitcode == 0
    guarded = queue.get(timeout=2)
    assert guarded["outcome"] == LeaseOutcome.GRANTED.value
    assert guarded["epoch"] == 2
    assert int(guarded["elapsed_ms"]) >= 450
    guard_store.close()

    ready = ctx.Event()
    crashed_holder = ctx.Process(
        target=_hold_guard_worker,
        args=(dsn, "crash-account", ready),
    )
    crashed_holder.start()
    assert ready.wait(5), "crash holder never acquired submission guard"

    crash_queue = ctx.Queue()
    crash_contender_ready = ctx.Event()
    crash_contender = ctx.Process(
        target=_acquire_worker,
        args=(
            dsn,
            "crash-account",
            "crash-contender",
            3_000,
            5_000,
            crash_queue,
            crash_contender_ready,
        ),
    )
    crash_contender.start()
    assert crash_contender_ready.wait(5), "crash contender did not reach acquire boundary"
    time.sleep(0.6)
    assert crash_contender.is_alive(), (
        "contender did not block while crash holder owned row lock"
    )
    crashed_holder.terminate()
    crashed_holder.join(5)
    crash_contender.join(5)
    assert crash_contender.exitcode == 0
    crash_result = crash_queue.get(timeout=2)
    assert crash_result["outcome"] == LeaseOutcome.GRANTED.value
    assert crash_result["epoch"] == 2
    assert int(crash_result["elapsed_ms"]) >= 450

    ledger_queue = ctx.Queue()
    writer_a = ctx.Process(
        target=_append_worker,
        args=(dsn, "writer-a", 20, ledger_queue),
    )
    writer_b = ctx.Process(
        target=_append_worker,
        args=(dsn, "writer-b", 20, ledger_queue),
    )
    writer_a.start()
    writer_b.start()
    writer_a.join(10)
    writer_b.join(10)
    assert writer_a.exitcode == 0 and writer_b.exitcode == 0
    write_a = ledger_queue.get(timeout=2)
    write_b = ledger_queue.get(timeout=2)
    assert sorted([write_a["count"], write_b["count"]]) == [20, 20]

    verifier = PostgresLedger(dsn, ledger_name="vati")
    try:
        chain_ok, checked = verifier.verify_chain()
        session_events = verifier.count(EventKind.SESSION)
    finally:
        verifier.close()
    assert chain_ok
    assert checked == 40
    assert session_events == 40

    return {
        "database": db_name,
        "lease_arbitration": "GRANTED/REFUSED_HELD_BY_OTHER/TAKEOVER_EPOCH_2",
        "submission_guard": "TWO_PROCESS_ROW_LOCK_BLOCKED_TAKEOVER",
        "crash_release": "PROCESS_TERMINATION_RELEASED_ROW_LOCK",
        "ledger_chain": "OK",
        "ledger_events": checked,
        "ledger_writers": 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    result = qualify(args.dsn)
    print("POSTGRES_CANARY_OK")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
