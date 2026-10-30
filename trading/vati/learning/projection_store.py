"""Transactional derived snapshots on the existing SQLite/PostgreSQL ledger store.

One snapshot contains the applied revision set, contributions and input cursor.
Its history and current pointer commit together under the journal writer lock.
No source event is changed and no order is submitted by this component.
"""
from __future__ import annotations

import json

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.ledger import GENESIS, Ledger, LedgerError


MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
STORE_SCHEMA = "vati.learning-projection-store/1"


class ProjectionStoreError(RuntimeError):
    pass


class ProjectionConflict(ProjectionStoreError):
    pass


class ProjectionCorrupt(ProjectionStoreError):
    pass


class ProjectionStore:
    def __init__(self, ledger, scope: dict, *, fault=None):
        from vati.core.ledger_pg import PostgresLedger

        if not isinstance(ledger, (Ledger, PostgresLedger)):
            raise TypeError("projection requires the existing native ledger store")
        self.ledger = ledger
        self.pg = isinstance(ledger, PostgresLedger)
        self.namespace = ledger.name if self.pg else "sqlite-main"
        # Canonicalize once so later mutation of a caller's dict cannot rebind it.
        self.scope = json.loads(canonical_json(scope))
        self.scope_key = canonical_hash(self.scope)
        self.fault = fault
        self.prefix = "vati." if self.pg else ""
        self.current = self.prefix + "learning_projection_current"
        self.history = self.prefix + "learning_projection_history"
        with ledger.atomic():
            self._query(f"""CREATE TABLE IF NOT EXISTS {self.history} (
                ledger_name TEXT NOT NULL, scope_key TEXT NOT NULL,
                snapshot_version BIGINT NOT NULL, snapshot_hash TEXT NOT NULL,
                snapshot_json TEXT NOT NULL, recovery_reason TEXT NOT NULL,
                PRIMARY KEY (ledger_name, scope_key, snapshot_version))""")
            self._query(f"""CREATE TABLE IF NOT EXISTS {self.current} (
                ledger_name TEXT NOT NULL, scope_key TEXT NOT NULL,
                snapshot_version BIGINT NOT NULL, snapshot_hash TEXT NOT NULL,
                PRIMARY KEY (ledger_name, scope_key))""")

    def _query(self, sql: str, args=()):
        cursor = self.ledger._conn.cursor()
        try:
            cursor.execute(sql.replace("?", "%s") if self.pg else sql, args)
            return cursor.fetchall() if cursor.description is not None else []
        finally:
            cursor.close()

    def _read(self, sql: str, args=()):
        try:
            return self._query(sql, args)
        finally:
            if self.pg:
                self.ledger._finish_read()

    def publication_rows(self, after_seq: int, *, limit: int = 256):
        """Fully consumed native journal publications; this is not a venue sequence."""
        if type(after_seq) is not int or after_seq < 0 or type(limit) is not int or not 1 <= limit <= 4096:
            raise ValueError("invalid projection journal cursor or batch limit")
        table = self.prefix + "events"
        condition = "ledger = ? AND seq > ?" if self.pg else "seq > ?"
        args = (self.namespace, after_seq, limit) if self.pg else (after_seq, limit)
        rows = self._read(
            "SELECT seq,kind,producer,correlation_id,event_time_ms,received_time_ms,decision_time_ms,"
            f"schema_version,payload_json,event_hash,chain_hash FROM {table} WHERE {condition} ORDER BY seq LIMIT ?",
            args,
        )
        return [(int(row[0]), self.ledger._row_to_event(row[:10]), str(row[10])) for row in rows]

    def _pointer(self):
        rows = self._read(
            f"SELECT snapshot_version,snapshot_hash FROM {self.current} WHERE ledger_name=? AND scope_key=?",
            (self.namespace, self.scope_key),
        )
        try:
            return None if not rows else (int(rows[0][0]), str(rows[0][1]))
        except (ValueError, TypeError) as exc:
            raise ProjectionCorrupt("projection checkpoint pointer cannot be decoded") from exc

    def _validate(self, snapshot: dict):
        if (not isinstance(snapshot, dict) or snapshot.get("store_schema") != STORE_SCHEMA
            or snapshot.get("scope") != self.scope or snapshot.get("scope_key") != self.scope_key
            or not isinstance(snapshot.get("state"), dict)):
            raise ProjectionCorrupt("projection snapshot scope/schema mismatch")
        digest = canonical_hash({k: v for k, v in snapshot.items() if k != "snapshot_hash"})
        if snapshot.get("snapshot_hash") != digest:
            raise ProjectionCorrupt("projection snapshot seal mismatch")
        cursor = snapshot.get("cursor")
        if (not isinstance(cursor, dict) or type(cursor.get("seq")) is not int or cursor["seq"] < 0
            or not isinstance(cursor.get("chain_hash"), str)):
            raise ProjectionCorrupt("projection cursor is invalid")
        actual = GENESIS if cursor["seq"] == 0 else self.ledger._chain_at(cursor["seq"])
        if actual != cursor["chain_hash"]:
            raise ProjectionCorrupt("projection cursor is not on this native journal")

    def load(self):
        pointer = self._pointer()
        if pointer is None:
            history = self._read(
                f"SELECT MAX(snapshot_version) FROM {self.history} WHERE ledger_name=? AND scope_key=?",
                (self.namespace, self.scope_key),
            )
            if history[0][0] is not None:
                raise ProjectionCorrupt("projection checkpoint pointer is missing from retained history")
            return None
        rows = self._read(
            f"SELECT snapshot_hash,snapshot_json FROM {self.history} "
            "WHERE ledger_name=? AND scope_key=? AND snapshot_version=?",
            (self.namespace, self.scope_key, pointer[0]),
        )
        if len(rows) != 1 or str(rows[0][0]) != pointer[1]:
            raise ProjectionCorrupt("projection checkpoint history is missing or mismatched")
        try:
            if len(rows[0][1].encode()) > MAX_SNAPSHOT_BYTES:
                raise ProjectionCorrupt("projection checkpoint exceeds its capacity")
            snapshot = json.loads(rows[0][1])
            self._validate(snapshot)
        except (ValueError, TypeError, KeyError, LedgerError) as exc:
            raise ProjectionCorrupt("projection checkpoint cannot be decoded or verified") from exc
        if snapshot["snapshot_hash"] != pointer[1]:
            raise ProjectionCorrupt("projection checkpoint pointer is corrupt")
        return snapshot

    def envelope(self, state: dict, *, cursor_seq: int, cursor_hash: str):
        body = {"store_schema": STORE_SCHEMA, "scope": self.scope, "scope_key": self.scope_key,
                "cursor": {"seq": cursor_seq, "chain_hash": cursor_hash}, "state": state}
        return {**body, "snapshot_hash": canonical_hash(body)}

    def save(self, snapshot: dict, *, expected_hash: str | None, recovery_reason: str = ""):
        """Compare/read/history/pointer under one native transaction.

        Explicit recovery can retain an invalid old history while publishing a
        rebuilt snapshot, but only after verifying the underlying source chain.
        The reducer must rebuild its state; this store never invents empty state.
        """
        encoded = canonical_json(snapshot)
        if len(encoded.encode()) > MAX_SNAPSHOT_BYTES:
            raise ProjectionStoreError("projection snapshot capacity exceeded")
        with self.ledger.atomic():
            self._validate(snapshot)
            pointer = self._pointer()
            current_hash = pointer[1] if pointer is not None else None
            if recovery_reason:
                if current_hash != expected_hash:
                    raise ProjectionConflict("projection changed while recovery was rebuilding")
                if not self.ledger.verify_chain()[0]:
                    raise ProjectionCorrupt("source journal is corrupt; checkpoint recovery refused")
            else:
                if pointer is not None and current_hash == snapshot["snapshot_hash"]:
                    # A retry after a lost commit reply leaves the same history/version.
                    self.load()
                    return snapshot
                if current_hash != expected_hash:
                    raise ProjectionConflict("projection advanced in another consumer")
                previous = self.load()
                if previous is not None and snapshot["cursor"]["seq"] <= previous["cursor"]["seq"]:
                    raise ProjectionConflict("projection cannot rewind or change state without a new publication")
            rows = self._query(
                f"SELECT MAX(snapshot_version) FROM {self.history} WHERE ledger_name=? AND scope_key=?",
                (self.namespace, self.scope_key),
            )
            version = 1 + int(rows[0][0] or 0)
            self._query(
                f"INSERT INTO {self.history} (ledger_name,scope_key,snapshot_version,snapshot_hash,snapshot_json,recovery_reason) "
                "VALUES (?,?,?,?,?,?)",
                (self.namespace, self.scope_key, version, snapshot["snapshot_hash"], encoded, recovery_reason),
            )
            if self.fault:
                self.fault("after_history_before_cursor")
            self._query(
                f"INSERT INTO {self.current} (ledger_name,scope_key,snapshot_version,snapshot_hash) VALUES (?,?,?,?) "
                "ON CONFLICT (ledger_name,scope_key) DO UPDATE SET "
                "snapshot_version=excluded.snapshot_version,snapshot_hash=excluded.snapshot_hash",
                (self.namespace, self.scope_key, version, snapshot["snapshot_hash"]),
            )
            if self.fault:
                self.fault("after_cursor_before_commit")
        if self.fault:
            self.fault("after_commit_before_reply")
        return snapshot
