"""Append-only event ledger with a hash chain and decision replay.

Storage is SQLite (stdlib) so the ledger is a single file, transactional and
queryable; JSONL export is available for the evidence bundle. Each row stores
prev_hash and chain_hash = sha256(prev_hash || event.hash), so tampering with
any row breaks verification of every later row. Nothing is ever updated or
deleted; corrections are new events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import Event, EventKind

GENESIS = "0" * 64


class LedgerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReplayReport:
    checked: int
    identical: int
    divergent: list[dict]

    @property
    def ok(self) -> bool:
        return not self.divergent


class Ledger:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL") if self.path != ":memory:" else None
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                 seq INTEGER PRIMARY KEY AUTOINCREMENT,
                 kind TEXT NOT NULL, producer TEXT NOT NULL, correlation_id TEXT NOT NULL,
                 event_time_ms INTEGER NOT NULL, received_time_ms INTEGER NOT NULL, decision_time_ms INTEGER,
                 schema_version INTEGER NOT NULL, payload_json TEXT NOT NULL,
                 event_hash TEXT NOT NULL, prev_hash TEXT NOT NULL, chain_hash TEXT NOT NULL UNIQUE)"""
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS ix_events_corr ON events(correlation_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS ix_events_kind ON events(kind)")

    # ------------------------------------------------------------------ write
    def append(self, event: Event) -> str:
        if not event.hash or event.hash != canonical_hash(event.body()):
            raise LedgerError("event hash missing or does not match body")
        with self._conn:
            row = self._conn.execute("SELECT chain_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row[0] if row else GENESIS
            chain = hashlib.sha256((prev + event.hash).encode()).hexdigest()
            self._conn.execute(
                "INSERT INTO events(kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, payload_json, event_hash, prev_hash, chain_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (event.kind.value, event.producer, event.correlation_id, event.event_time_ms, event.received_time_ms, event.decision_time_ms,
                 event.schema_version, canonical_json(event.payload), event.hash, prev, chain),
            )
        return chain

    # ------------------------------------------------------------------- read
    def _row_to_event(self, r: sqlite3.Row | tuple) -> Event:
        return Event(EventKind(r[1]), r[2], r[4], r[5], json.loads(r[8]), r[7], r[6], r[3], r[9])

    def iter(self, kind: Optional[EventKind] = None, correlation_id: Optional[str] = None) -> Iterator[Event]:
        q = "SELECT seq, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version, payload_json, event_hash FROM events"
        cond, args = [], []
        if kind is not None:
            cond.append("kind = ?"); args.append(kind.value)
        if correlation_id is not None:
            cond.append("correlation_id = ?"); args.append(correlation_id)
        if cond:
            q += " WHERE " + " AND ".join(cond)
        q += " ORDER BY seq"
        for r in self._conn.execute(q, args):
            yield self._row_to_event(r)

    def count(self, kind: Optional[EventKind] = None) -> int:
        if kind is None:
            return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM events WHERE kind = ?", (kind.value,)).fetchone()[0]

    def head(self) -> str:
        row = self._conn.execute("SELECT chain_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else GENESIS

    # ----------------------------------------------------------------- verify
    def verify_chain(self) -> tuple[bool, int]:
        prev = GENESIS
        n = 0
        for r in self._conn.execute("SELECT event_hash, prev_hash, chain_hash, payload_json, kind, producer, correlation_id, event_time_ms, received_time_ms, decision_time_ms, schema_version FROM events ORDER BY seq"):
            ev = Event(EventKind(r[4]), r[5], r[7], r[8], json.loads(r[3]), r[10], r[9], r[6], r[0])
            if canonical_hash(ev.body()) != r[0]:
                return False, n
            if r[1] != prev or hashlib.sha256((prev + r[0]).encode()).hexdigest() != r[2]:
                return False, n
            prev = r[2]
            n += 1
        return True, n

    def replay_decisions(self, recompute: Callable[[dict], dict]) -> ReplayReport:
        """Feed each RISK_DECISION's stored inputs (payload['inputs']) to `recompute`
        and compare the returned decision_hash to the stored one."""
        checked = identical = 0
        divergent: list[dict] = []
        for ev in self.iter(EventKind.RISK_DECISION):
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

    def export_jsonl(self, path: str | Path) -> int:
        n = 0
        with open(path, "w", encoding="utf-8") as f:
            for ev in self.iter():
                f.write(canonical_json({**ev.body(), "hash": ev.hash}) + "\n")
                n += 1
        return n

    def close(self) -> None:
        self._conn.close()
