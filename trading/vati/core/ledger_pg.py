"""PostgreSQL ledger (Rev 4 Part J, Phase 4): the same hash-chained event log
as `vati.core.ledger.Ledger`, on the transactional authority store. Append is
serialised with a row lock on the chain head so two writers cannot fork the
chain; every read path mirrors the SQLite API so callers do not care which
backend they hold. Chain hashes are byte-identical across backends."""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Iterator, Optional

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import Event, EventKind
from vati.core.ledger import GENESIS, LedgerError, ReplayReport

# The vati schema is provisioned by the privileged deployment reconciler.
# Runtime deliberately has no CREATE privilege on the database.
SCHEMA = """
CREATE TABLE IF NOT EXISTS vati.events (
  seq BIGSERIAL PRIMARY KEY,
  kind TEXT NOT NULL, producer TEXT NOT NULL, correlation_id TEXT NOT NULL,
  event_time_ms BIGINT NOT NULL, received_time_ms BIGINT NOT NULL, decision_time_ms BIGINT,
  schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL,
  event_hash TEXT NOT NULL, prev_hash TEXT NOT NULL, chain_hash TEXT NOT NULL UNIQUE,
  inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_vati_events_corr ON vati.events(correlation_id);
CREATE INDEX IF NOT EXISTS ix_vati_events_kind ON vati.events(kind);
CREATE TABLE IF NOT EXISTS vati.chain_head (
  ledger TEXT PRIMARY KEY, chain_hash TEXT NOT NULL, seq BIGINT NOT NULL
);
"""


class PostgresLedger:
    """Drop-in for `Ledger` over a PostgreSQL DSN (postgres://user:pw@host:port/db)."""

    def __init__(self, dsn: str, *, ledger_name: str = "vati", connect: Optional[Callable[[str], object]] = None) -> None:
        import psycopg  # local import: the SQLite ledger must not need psycopg
        self.path = dsn
        self.name = ledger_name
        self._conn = (connect or psycopg.connect)(dsn)
        self._conn.autocommit = False
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute("INSERT INTO vati.chain_head(ledger, chain_hash, seq) VALUES (%s, %s, 0) ON CONFLICT (ledger) DO NOTHING", (ledger_name, GENESIS))
        self._conn.commit()

    # ------------------------------------------------------------------ write
    def append(self, event: Event) -> str:
        if not event.hash or event.hash != canonical_hash(event.body()):
            raise LedgerError("event hash missing or does not match body")
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT chain_hash FROM vati.chain_head WHERE ledger = %s FOR UPDATE", (self.name,))
                prev = cur.fetchone()[0]
                chain = hashlib.sha256((prev + event.hash).encode()).hexdigest()
                cur.execute(
                    "INSERT INTO vati.events(kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, payload_json, event_hash, prev_hash, chain_hash) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING seq",
                    (event.kind.value, event.producer, event.correlation_id, event.event_time_ms, event.received_time_ms, event.decision_time_ms, event.schema_version,
                     canonical_json(event.payload), event.hash, prev, chain),
                )
                seq = cur.fetchone()[0]
                cur.execute("UPDATE vati.chain_head SET chain_hash = %s, seq = %s WHERE ledger = %s", (chain, seq, self.name))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return chain

    # ------------------------------------------------------------------- read
    @staticmethod
    def _row_to_event(r) -> Event:
        return Event(EventKind(r[1]), r[2], r[4], r[5], json.loads(r[8]), r[7], r[6], r[3], r[9])

    def iter(self, kind: Optional[EventKind] = None, correlation_id: Optional[str] = None) -> Iterator[Event]:
        q = "SELECT seq, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, payload_json, event_hash FROM vati.events"
        cond, args = [], []
        if kind is not None:
            cond.append("kind = %s"); args.append(kind.value)
        if correlation_id is not None:
            cond.append("correlation_id = %s"); args.append(correlation_id)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY seq"
        with self._conn.cursor() as cur:
            cur.execute(q, args)
            for r in cur:
                yield self._row_to_event(r)
        self._conn.rollback()

    def count(self, kind: Optional[EventKind] = None) -> int:
        with self._conn.cursor() as cur:
            if kind is None:
                cur.execute("SELECT COUNT(*) FROM vati.events")
            else:
                cur.execute("SELECT COUNT(*) FROM vati.events WHERE kind = %s", (kind.value,))
            n = cur.fetchone()[0]
        self._conn.rollback()
        return n

    def head(self) -> str:
        with self._conn.cursor() as cur:
            cur.execute("SELECT chain_hash FROM vati.chain_head WHERE ledger = %s", (self.name,))
            row = cur.fetchone()
        self._conn.rollback()
        return row[0] if row else GENESIS

    # ----------------------------------------------------------------- verify
    def verify_chain(self) -> tuple[bool, int]:
        prev = GENESIS
        n = 0
        with self._conn.cursor() as cur:
            cur.execute("SELECT event_hash, prev_hash, chain_hash, payload_json, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version FROM vati.events ORDER BY seq")
            for r in cur:
                ev = Event(EventKind(r[4]), r[5], r[7], r[8], json.loads(r[3]), r[10], r[9], r[6], r[0])
                if canonical_hash(ev.body()) != r[0] or r[1] != prev or hashlib.sha256((prev + r[0]).encode()).hexdigest() != r[2]:
                    self._conn.rollback()
                    return False, n
                prev = r[2]
                n += 1
        self._conn.rollback()
        if n and prev != self.head():
            return False, n
        return True, n

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
