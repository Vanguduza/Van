"""PostgreSQL ledger (Rev 4 Part J, Phase 4): the same hash-chained event log
as `vati.core.ledger.Ledger`, on the transactional authority store. Append is
serialised with a row lock on the chain head so two writers cannot fork the
chain; every read path mirrors the SQLite API so callers do not care which
backend they hold. Chain hashes are byte-identical across backends."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import Event, EventKind
from vati.core.ledger import GENESIS, IncrementalChainVerifier, LedgerError, ReplayReport, _check_row

# The vati schema is provisioned by the privileged deployment reconciler.
# Runtime deliberately has no CREATE privilege on the database.
SCHEMA = """
CREATE TABLE IF NOT EXISTS vati.events (
  seq BIGSERIAL PRIMARY KEY, ledger TEXT NOT NULL,
  kind TEXT NOT NULL, producer TEXT NOT NULL, correlation_id TEXT NOT NULL,
  event_time_ms BIGINT NOT NULL, received_time_ms BIGINT NOT NULL, decision_time_ms BIGINT,
  schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  event_hash TEXT NOT NULL, prev_hash TEXT NOT NULL, chain_hash TEXT NOT NULL,
  CONSTRAINT events_ledger_chain_hash_key UNIQUE(ledger, chain_hash),
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_vati_events_ledger_corr ON vati.events(ledger, correlation_id);
CREATE INDEX IF NOT EXISTS ix_vati_events_ledger_kind ON vati.events(ledger, kind);
CREATE TABLE IF NOT EXISTS vati.chain_head (
  ledger TEXT PRIMARY KEY, chain_hash TEXT NOT NULL, seq BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS vati.account_runtime_leases (
  account_alias TEXT PRIMARY KEY,
  holder_instance_id TEXT NOT NULL,
  lease_epoch BIGINT NOT NULL,
  acquired_at_ms BIGINT NOT NULL,
  heartbeat_at_ms BIGINT NOT NULL,
  expires_at_ms BIGINT NOT NULL,
  software_version TEXT NOT NULL DEFAULT '',
  git_sha TEXT NOT NULL DEFAULT ''
);
"""


def require_scoped_schema(cursor) -> None:
    cursor.execute("SELECT is_nullable FROM information_schema.columns WHERE table_schema = 'vati' AND table_name = 'events' AND column_name = 'ledger'")
    column = cursor.fetchone()
    cursor.execute("SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'vati.events'::regclass AND conname = 'events_ledger_chain_hash_key'")
    constraint = cursor.fetchone()
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey::smallint[]) WHERE i.indrelid = 'vati.events'::regclass AND i.indisunique AND i.indnkeyatts = 1 AND a.attname = 'chain_hash')")
    global_unique = cursor.fetchone()[0]
    if column != ("NO",) or constraint != ("u", "UNIQUE (ledger, chain_hash)") or global_unique:
        raise LedgerError("PostgreSQL ledger scope schema incomplete; explicit verified migration required")


class PostgresLedger:
    """Drop-in for `Ledger` over a PostgreSQL DSN (postgres://user:pw@host:port/db)."""

    def __init__(self, dsn: str, *, ledger_name: str = "vati", connect: Optional[Callable[[str], object]] = None) -> None:
        import psycopg  # local import: the SQLite ledger must not need psycopg
        if not isinstance(ledger_name, str) or not ledger_name.strip() or len(ledger_name) > 128:
            raise LedgerError("ledger_name must identify one bounded nonempty scope")
        self.path = dsn
        self.name = ledger_name
        self._atomic_depth = 0
        self._conn = (connect or psycopg.connect)(dsn)
        self._conn.autocommit = False
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT to_regclass('vati.events')")
                if cur.fetchone()[0] is not None:
                    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = 'vati' AND table_name = 'events' AND column_name = 'ledger'")
                    if cur.fetchone() is None:
                        raise LedgerError("legacy PostgreSQL ledger requires explicit verified scope migration before runtime use")
                cur.execute(SCHEMA)
                require_scoped_schema(cur)
                cur.execute("INSERT INTO vati.chain_head(ledger, chain_hash, seq) VALUES (%s, %s, 0) ON CONFLICT (ledger) DO NOTHING", (ledger_name, GENESIS))
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            self._conn.close()
            raise

    # ------------------------------------------------------------------ write
    @contextmanager
    def atomic(self):
        """Keep a read/validate/append operation under the chain-head writer lock."""
        if getattr(self,'_read_snapshot_depth',0):
            raise LedgerError('cannot acquire a writer inside a read-only ledger snapshot')
        outer = self._atomic_depth == 0
        if outer:
            with self._conn.cursor() as cur:
                cur.execute("SELECT chain_hash FROM vati.chain_head WHERE ledger = %s FOR UPDATE", (self.name,))
                cur.fetchone()
        self._atomic_depth += 1
        try:
            yield self
            if outer:
                self._conn.commit()
        except BaseException:
            if outer:
                self._conn.rollback()
            raise
        finally:
            self._atomic_depth -= 1

    @contextmanager
    def read_snapshot(self):
        """A repeatable read does not lock the financial chain-head writer."""
        if self._atomic_depth:
            yield self
            return
        if int(self._conn.info.transaction_status)!=0:
            raise LedgerError('read snapshot requires an idle ledger connection')
        with self._conn.cursor() as cur:
            cur.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self._atomic_depth+=1
        self._read_snapshot_depth=1
        try:
            yield self
        finally:
            self._conn.rollback()
            self._read_snapshot_depth=0
            self._atomic_depth-=1

    def _finish_read(self):
        if self._atomic_depth == 0:
            self._conn.rollback()

    def append(self, event: Event) -> str:
        if getattr(self,'_read_snapshot_depth',0):
            raise LedgerError('cannot append inside a read-only ledger snapshot')
        if not event.hash or event.hash != canonical_hash(event.body()):
            raise LedgerError("event hash missing or does not match body")
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT chain_hash FROM vati.chain_head WHERE ledger = %s FOR UPDATE", (self.name,))
                prev = cur.fetchone()[0]
                chain = hashlib.sha256((prev + event.hash).encode()).hexdigest()
                cur.execute(
                    "INSERT INTO vati.events(ledger, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, payload_json, event_hash, prev_hash, chain_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING seq",
                    (self.name, event.kind.value, event.producer, event.correlation_id, event.event_time_ms, event.received_time_ms, event.decision_time_ms, event.schema_version,
                     canonical_json(event.payload), event.hash, prev, chain),
                )
                seq = cur.fetchone()[0]
                cur.execute("UPDATE vati.chain_head SET chain_hash = %s, seq = %s WHERE ledger = %s", (chain, seq, self.name))
            if self._atomic_depth == 0:
                self._conn.commit()
        except Exception:
            if self._atomic_depth == 0:
                self._conn.rollback()
            raise
        return chain

    # ------------------------------------------------------------------- read
    @staticmethod
    def _row_to_event(r) -> Event:
        return Event(EventKind(r[1]), r[2], r[4], r[5], json.loads(r[8]), r[7], r[6], r[3], r[9])

    def iter(self, kind: Optional[EventKind] = None, correlation_id: Optional[str] = None) -> Iterator[Event]:
        q = "SELECT seq, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, payload_json, event_hash FROM vati.events"
        cond, args = ["ledger = %s"], [self.name]
        if kind is not None:
            cond.append("kind = %s"); args.append(kind.value)
        if correlation_id is not None:
            cond.append("correlation_id = %s"); args.append(correlation_id)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY seq"
        try:
            with self._conn.cursor() as cur:
                cur.execute(q, args)
                for r in cur:
                    yield self._row_to_event(r)
        finally:
            self._finish_read()

    def count(self, kind: Optional[EventKind] = None) -> int:
        with self._conn.cursor() as cur:
            if kind is None:
                cur.execute("SELECT COUNT(*) FROM vati.events WHERE ledger = %s", (self.name,))
            else:
                cur.execute("SELECT COUNT(*) FROM vati.events WHERE ledger = %s AND kind = %s", (self.name, kind.value))
            n = cur.fetchone()[0]
        self._finish_read()
        return n

    def head(self) -> str:
        with self._conn.cursor() as cur:
            cur.execute("SELECT chain_hash FROM vati.chain_head WHERE ledger = %s", (self.name,))
            row = cur.fetchone()
        self._finish_read()
        return row[0] if row else GENESIS

    # ----------------------------------------------------------------- verify
    def verify_chain(self) -> tuple[bool, int]:
        """Full verification from genesis. For audits, startup and evidence."""
        ok, n, _seq, prev = self._verify_from(0, GENESIS)
        if not ok:
            return False, n
        if prev != self.head():
            return False, n
        return True, n

    def verify_incremental(self) -> tuple[bool, int]:
        """Per-decision check whose cost does not grow with the ledger
        (see vati.core.ledger.IncrementalChainVerifier)."""
        if getattr(self, "_incremental", None) is None:
            self._incremental = IncrementalChainVerifier(self)
        ok, n = self._incremental.verify()
        if ok and self._incremental._anchor and self._incremental._anchor[1] != self.head():
            self._incremental._anchor = None
            return False, n
        return ok, n

    def _verify_from(self, after_seq: int, prev: str) -> tuple[bool, int, int, str]:
        n, seq = 0, after_seq
        with self._conn.cursor() as cur:
            cur.execute("SELECT event_hash, prev_hash, chain_hash, payload_json, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, seq FROM vati.events WHERE ledger = %s AND seq > %s ORDER BY seq", (self.name, after_seq))
            for r in cur:
                if not _check_row(prev, r):
                    self._finish_read()
                    return False, n, seq, prev
                prev, seq = r[2], r[11]
                n += 1
        self._finish_read()
        return True, n, seq, prev

    def _chain_at(self, seq: int) -> Optional[str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT chain_hash FROM vati.events WHERE ledger = %s AND seq = %s", (self.name, seq))
            row = cur.fetchone()
        self._finish_read()
        return row[0] if row else None

    def _count_upto(self, seq: int) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vati.events WHERE ledger = %s AND seq <= %s", (self.name, seq))
            n = cur.fetchone()[0]
        self._finish_read()
        return n

    def replay_decisions(self, recompute: Callable[[dict], dict]) -> ReplayReport:
        checked = identical = 0
        divergent: list[dict] = []
        for ev in list(self.iter(EventKind.RISK_DECISION)):
            inputs = ev.payload.get("inputs")
            stored = ev.payload.get("decision", {}).get("decision_hash")
            if inputs is None or stored is None:
                continue
            checked += 1
            got = recompute(inputs).get("decision_hash")
            if got == stored:
                identical += 1
            else:
                divergent.append({"correlation_id": ev.correlation_id, "stored": stored, "recomputed": got})
        return ReplayReport(checked, identical, divergent)

    def export_jsonl(self, path) -> int:
        n = 0
        with open(path, "w", encoding="utf-8") as f:
            for ev in self.iter():
                f.write(canonical_json({**ev.body(), "hash": ev.hash}) + "\n")
                n += 1
        return n

    def close(self) -> None:
        self._conn.close()


def open_ledger(spec: str, **kw):
    """`postgres://...` or `postgresql://...` → PostgresLedger; anything else → SQLite Ledger path."""
    if spec.startswith(("postgres://", "postgresql://")):
        return PostgresLedger(spec, **kw)
    from vati.core.ledger import Ledger
    return Ledger(spec)
