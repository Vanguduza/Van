"""Real PostgreSQL in explicitly opted-in disposable fixture databases only."""
import os
import uuid
import hashlib

import pytest

from vati.core.canonical import canonical_json
from vati.core.events import EventKind, make_event
from vati.core.ledger import GENESIS, LedgerError
from vati.core.ledger_pg import PostgresLedger


@pytest.fixture
def pg_dsn():
    if os.environ.get("VATI_TEST_PG_ISOLATED_FIXTURE") != "1":
        pytest.skip("requires explicit disposable PostgreSQL fixture opt-in")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    spec = os.environ["VATI_TEST_PG_DSN"]
    name = "van_ledger_fixture_"+uuid.uuid4().hex
    with psycopg.connect(spec, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = psycopg.conninfo.make_conninfo(spec, dbname=name)
    try:
        with psycopg.connect(dsn,autocommit=True) as conn:
            conn.execute("CREATE SCHEMA vati")
        yield dsn
    finally:
        with psycopg.connect(spec,autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (name,))
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def event(number):
    return make_event(EventKind.SESSION,"isolated-fixture",{"observation":number},
        event_time_ms=number,received_time_ms=number,correlation_id="same-correlation-in-each-scope")


def test_named_ledgers_cannot_read_or_verify_each_others_events(pg_dsn):
    a = PostgresLedger(pg_dsn,ledger_name="account-a")
    b = PostgresLedger(pg_dsn,ledger_name="account-b")
    try:
        a.append(event(1)); b.append(event(2))
        assert a.count() == b.count() == 1
        assert [e.hash for e in a.iter()] == [event(1).hash]
        assert [e.hash for e in b.iter(correlation_id=event(1).correlation_id)] == [event(2).hash]
        assert a.verify_chain() == b.verify_chain() == (True,1)
        assert a.verify_incremental() == b.verify_incremental() == (True,1)
        assert a._chain_at(2) is None and b._chain_at(1) is None
        assert a._count_upto(2) == b._count_upto(2) == 1
    finally:
        a.close(); b.close()


def test_identical_event_bytes_can_exist_in_separate_ledger_scopes(pg_dsn):
    a = PostgresLedger(pg_dsn,ledger_name="account-a")
    b = PostgresLedger(pg_dsn,ledger_name="account-b")
    try:
        assert a.append(event(1)) == b.append(event(1))
        assert a.count() == b.count() == 1
        assert a.verify_chain() == b.verify_chain() == (True,1)
    finally:
        a.close(); b.close()


def test_one_scope_rollback_cannot_remove_another_scopes_committed_event(pg_dsn):
    a = PostgresLedger(pg_dsn,ledger_name="account-a")
    b = PostgresLedger(pg_dsn,ledger_name="account-b")
    try:
        with pytest.raises(RuntimeError,match="injected"):
            with a.atomic():
                a.append(event(1))
                b.append(event(2))
                assert a.count() == b.count() == 1
                raise RuntimeError("injected atomic writer failure")
        assert a.count() == 0 and b.count() == 1
        assert a.head() == GENESIS and b.verify_chain() == (True,1)
    finally:
        a.close(); b.close()


def test_closing_a_partial_reader_releases_only_its_own_transaction(pg_dsn):
    from psycopg.pq import TransactionStatus
    a = PostgresLedger(pg_dsn)
    try:
        a.append(event(1)); a.append(event(2))
        iterator = a.iter()
        assert next(iterator).hash == event(1).hash
        iterator.close()
        assert a._conn.info.transaction_status == TransactionStatus.IDLE
        with a.atomic():
            a.append(event(3))
            iterator = a.iter()
            next(iterator); iterator.close()
            assert a._conn.info.transaction_status == TransactionStatus.INTRANS
        assert a.count() == 3 and a.verify_chain() == (True,3)
    finally:
        a.close()


LEGACY_SCHEMA = """
CREATE TABLE vati.events (
 seq BIGSERIAL PRIMARY KEY,kind TEXT NOT NULL,producer TEXT NOT NULL,correlation_id TEXT NOT NULL,
 event_time_ms BIGINT NOT NULL,received_time_ms BIGINT NOT NULL,decision_time_ms BIGINT,
 schema_version INTEGER NOT NULL,payload_json TEXT NOT NULL,event_hash TEXT NOT NULL,
 prev_hash TEXT NOT NULL,chain_hash TEXT NOT NULL UNIQUE);
CREATE TABLE vati.chain_head(ledger TEXT PRIMARY KEY,chain_hash TEXT NOT NULL,seq BIGINT NOT NULL);
"""


def legacy_store(dsn, *, ambiguous=False):
    import psycopg
    original = event(1)
    chain = hashlib.sha256((GENESIS+original.hash).encode()).hexdigest()
    with psycopg.connect(dsn) as conn:
        conn.execute(LEGACY_SCHEMA)
        conn.execute("INSERT INTO vati.events(kind,producer,correlation_id,event_time_ms,received_time_ms,decision_time_ms,schema_version,payload_json,event_hash,prev_hash,chain_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (original.kind.value,original.producer,original.correlation_id,1,1,None,1,canonical_json(original.payload),original.hash,GENESIS,chain))
        conn.execute("INSERT INTO vati.chain_head VALUES('account-a',%s,1)",(chain,))
        if ambiguous:
            conn.execute("INSERT INTO vati.chain_head VALUES('account-b',%s,1)",(chain,))
    return original,chain


def test_legacy_schema_requires_explicit_migration_before_runtime_use(pg_dsn):
    legacy_store(pg_dsn)
    with pytest.raises(LedgerError,match="migration"):
        PostgresLedger(pg_dsn,ledger_name="account-a")


def has_scope_column(dsn):
    import psycopg
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='vati' AND table_name='events' AND column_name='ledger'").fetchone() is not None


def test_explicit_single_chain_migration_preserves_original_bytes_and_head(pg_dsn):
    import psycopg
    from vati.core.ledger_pg_migration import migrate_legacy_scope
    original,chain = legacy_store(pg_dsn)
    with psycopg.connect(pg_dsn,autocommit=True) as conn:
        ready = migrate_legacy_scope(conn)
        assert ready["status"] == "READY" and not ready["changed"]
        assert not has_scope_column(pg_dsn)
        result = migrate_legacy_scope(conn,apply=True)
        assert result["status"] == "MIGRATED" and result["scope"] == "account-a"
        assert result["verified_head"] == chain
        assert migrate_legacy_scope(conn,apply=True) == {"status":"ALREADY_SCOPED","changed":False}
    a = PostgresLedger(pg_dsn,ledger_name="account-a")
    b = PostgresLedger(pg_dsn,ledger_name="account-b")
    try:
        assert next(a.iter()).body() == original.body()
        assert a.head() == chain and a.verify_chain() == (True,1)
        assert b.count() == 0
        b.append(original)  # independent identical bytes are no longer globally unique
        a.append(event(2))
        assert a.verify_chain() == (True,2) and b.verify_chain() == (True,1)
    finally:
        a.close(); b.close()


@pytest.mark.parametrize("fault", ["ambiguous", "body_corrupt", "head_corrupt"])
def test_migration_refuses_ambiguous_or_corrupt_histories_without_schema_changes(pg_dsn, fault):
    import psycopg
    from vati.core.ledger_pg_migration import migrate_legacy_scope
    legacy_store(pg_dsn,ambiguous=fault=="ambiguous")
    with psycopg.connect(pg_dsn) as conn:
        if fault == "body_corrupt":
            conn.execute("UPDATE vati.events SET payload_json = '{\"observation\":999}'")
        elif fault == "head_corrupt":
            conn.execute("UPDATE vati.chain_head SET chain_hash = %s", ("a"*64,))
    with psycopg.connect(pg_dsn,autocommit=True) as conn:
        with pytest.raises(LedgerError):
            migrate_legacy_scope(conn,apply=True)
    assert not has_scope_column(pg_dsn)


def test_migration_rolls_back_ddl_and_backfill_after_injected_failure(pg_dsn):
    import psycopg
    from vati.core.ledger_pg_migration import migrate_legacy_scope
    original,chain = legacy_store(pg_dsn)
    class FailingCursor:
        def __init__(self,raw):self.raw=raw
        def __enter__(self):self.raw.__enter__(); return self
        def __exit__(self,*args):return self.raw.__exit__(*args)
        def __getattr__(self,name):return getattr(self.raw,name)
        def execute(self,query,*args):
            if "ADD CONSTRAINT events_ledger_chain_hash_key" in query:
                raise RuntimeError("injected migration failure after backfill")
            return self.raw.execute(query,*args)
    class FailingConnection:
        def __init__(self,raw):self.raw=raw
        def transaction(self):return self.raw.transaction()
        def cursor(self):return FailingCursor(self.raw.cursor())
    with psycopg.connect(pg_dsn,autocommit=True) as conn:
        with pytest.raises(RuntimeError,match="injected"):
            migrate_legacy_scope(FailingConnection(conn),apply=True)
        assert not has_scope_column(pg_dsn)
        assert conn.execute("SELECT event_hash,chain_hash FROM vati.events").fetchone() == (original.hash,chain)
        assert conn.execute("SELECT chain_hash FROM vati.chain_head").fetchone() == (chain,)


def test_empty_scope_with_a_nonempty_head_is_corrupt_not_fresh(pg_dsn):
    import psycopg
    a = PostgresLedger(pg_dsn,ledger_name="account-a")
    try:
        with psycopg.connect(pg_dsn) as conn:
            conn.execute("UPDATE vati.chain_head SET seq=1,chain_hash=%s WHERE ledger='account-a'",("b"*64,))
        assert a.verify_chain() == (False,0)
        assert a.verify_incremental() == (False,0)
    finally:a.close()


def test_uncertain_exit_in_one_named_scope_does_not_block_another_named_scope(pg_dsn):
    from test_exit_uncertainty import CloseProbe,build,mark
    a = PostgresLedger(pg_dsn,ledger_name="account-a")
    b = PostgresLedger(pg_dsn,ledger_name="account-b")
    try:
        adapter_a,adapter_b = CloseProbe(),CloseProbe()
        mark(build(a,adapter_a))
        assert b.count(EventKind.EXIT_ATTEMPT) == 0
        mark(build(b,adapter_b))
        assert adapter_a.calls == adapter_b.calls == 1
        assert a.count(EventKind.EXIT_ATTEMPT) == b.count(EventKind.EXIT_ATTEMPT) == 2
        assert a.verify_chain()[0] and b.verify_chain()[0]
        assert mark(build(a,adapter_a),2) == [] and adapter_a.calls == 1
    finally:a.close();b.close()


def test_custom_legacy_global_unique_key_requires_native_review(pg_dsn):
    import psycopg
    from vati.core.ledger_pg_migration import migrate_legacy_scope
    legacy_store(pg_dsn)
    with psycopg.connect(pg_dsn) as conn:
        conn.execute("ALTER TABLE vati.events RENAME CONSTRAINT events_chain_hash_key TO owner_custom_chain_key")
    with psycopg.connect(pg_dsn,autocommit=True) as conn:
        with pytest.raises(LedgerError,match="migration"):
            migrate_legacy_scope(conn,apply=True)
    assert not has_scope_column(pg_dsn)


def test_explicit_operator_cli_checks_then_migrates_the_disposable_store(pg_dsn):
    import subprocess
    import sys
    import json
    from pathlib import Path
    legacy_store(pg_dsn)
    env=dict(os.environ,VATI_PG_MIGRATION_DSN=pg_dsn)
    root=Path(__file__).resolve().parents[2]
    for mode,expected in (("--check","READY"),("--apply","MIGRATED"),("--check","ALREADY_SCOPED")):
        result = subprocess.run([sys.executable,"tools/rebuild/pg_ledger_migration.py",mode],
            cwd=root,env=env,capture_output=True,text=True,timeout=20)
        assert result.returncode == 0,result.stdout+result.stderr
        assert json.loads(result.stdout)["status"] == expected
        assert pg_dsn not in result.stdout+result.stderr


def test_fresh_deployment_table_template_supports_scoped_runtime(pg_dsn):
    import psycopg
    from pathlib import Path
    template = (Path(__file__).resolve().parents[2]/"deploy/van-trading-core/supabase/init/01_vati_ledger.sql.tpl").read_text()
    # Apply the real table/index DDL. Role provisioning and production grants
    # remain a separate native deployment contract, not simulated by this test.
    ddl = "CREATE TABLE IF NOT EXISTS vati.events"+template.split("CREATE TABLE IF NOT EXISTS vati.events",1)[1].split("ALTER TABLE vati.events OWNER",1)[0]
    with psycopg.connect(pg_dsn) as conn:
        conn.execute(ddl)
    a,b = PostgresLedger(pg_dsn,ledger_name="a"),PostgresLedger(pg_dsn,ledger_name="b")
    try:
        a.append(event(1));b.append(event(1))
        assert a.verify_chain() == b.verify_chain() == (True,1)
    finally:a.close();b.close()


def test_parallel_writers_preserve_each_named_chain_with_global_sequence_gaps(pg_dsn):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    for name in ("a","b"):
        PostgresLedger(pg_dsn,ledger_name=name).close()
    ready = threading.Barrier(4)
    def write(worker):
        ledger = PostgresLedger(pg_dsn,ledger_name="a" if worker%2==0 else "b")
        try:
            ready.wait(timeout=10)
            for number in range(10):ledger.append(event(100+worker*10+number))
        finally:ledger.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write,range(4)))
    for name in ("a","b"):
        ledger = PostgresLedger(pg_dsn,ledger_name=name)
        try:
            assert ledger.count() == 20
            assert ledger.verify_chain() == ledger.verify_incremental() == (True,20)
            assert len({e.hash for e in ledger.iter()}) == 20
        finally:ledger.close()
