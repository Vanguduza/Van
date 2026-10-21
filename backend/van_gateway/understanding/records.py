"""Exact, privacy-screened owner record inspection and A4 erasure selectors."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from van_gateway.context.forget import DELIBERATELY_KEPT, FORGETTABLE
from van_gateway.owner_privacy import _reference, _text, _SECRET
from van_gateway.storage.db import Store

PRIMARY_KEYS = {
    "owner_facts": ("fact_id",), "owner_context_edges": ("edge_id",),
    "owner_cognitive_model": ("assertion_id",), "reasoning_assessments": ("assessment_id",),
    "symbiotic_growth": ("change_id",), "strategic_memory": ("entry_id",),
    "decision_fingerprints": ("decision_id",), "shared_vocabulary": ("term", "project_id"),
    "cognitive_complement_map": ("entry_id",), "intent_edges": ("edge_id",),
    "intent_nodes": ("intent_id",), "intent_missions": ("intent_id", "mission_id"),
}
RECORD_ID = re.compile(r"mr_[a-f0-9]{64}")
DIGEST = re.compile(r"[a-f0-9]{64}")


def record_identity(table: str, row: Any) -> str:
    key = {column: row[column] for column in PRIMARY_KEYS[table]}
    return "mr_" + hashlib.sha256(Store.dumps({"table": table, "key": key}).encode()).hexdigest()


def revision_sha256(row: Any) -> str:
    return hashlib.sha256(Store.dumps(dict(row)).encode()).hexdigest()


async def record_revision(db: Any, table: str, row: Any) -> str:
    """Seal the selected row and exact existing dependent rows, including their content."""
    from van_gateway.context.memory_erasure import _scope, selected_stores
    key = {column: row[column] for column in PRIMARY_KEYS[table]}
    # Ordered streaming keeps the full approval commitment deterministic without
    # accumulating arbitrarily many linked rows in memory.
    digest = hashlib.sha256()
    digest.update(Store.dumps({"schema_version": 1, "store": table, "root": revision_sha256(row)}).encode())
    for entry in selected_stores(table):
        if entry.table == table:
            continue
        where, params = _scope(entry, table, dependent_scope=True, record_key=key)
        digest.update(Store.dumps({"dependent_store": entry.table}).encode())
        cursor = await db.execute(f"SELECT * FROM {entry.table}{where} ORDER BY {','.join(PRIMARY_KEYS[entry.table])}", params)
        while rows := await cursor.fetchmany(256):
            for item in rows:
                digest.update(revision_sha256(item).encode())
    return digest.hexdigest()


def record_parameters(store: str, record_id: str, expected_sha256: str) -> dict:
    if store not in PRIMARY_KEYS or not RECORD_ID.fullmatch(record_id) or not DIGEST.fullmatch(expected_sha256):
        raise ValueError("memory_record_selector_invalid")
    from van_gateway.context.memory_erasure import selected_stores
    return {"store": store, "stores": [entry.table for entry in selected_stores(store)],
            "record_id": record_id, "expected_sha256": expected_sha256}


def owner_scope(table: str) -> tuple[str, tuple]:
    entry = next((entry for entry in FORGETTABLE if entry.table == table), None)
    if not entry or table not in PRIMARY_KEYS:
        raise ValueError("memory_store_not_allowlisted")
    return ((f" WHERE {entry.owner_column}=?", ("owner",)) if entry.owner_column else ("", ()))


async def find_record(db: Any, table: str, record_id: str) -> tuple[Any | None, dict | None]:
    """Stream only primary keys; never encode owner text in URLs or audit paths."""
    if not RECORD_ID.fullmatch(record_id):
        raise ValueError("memory_record_selector_invalid")
    where, params = owner_scope(table)
    columns = PRIMARY_KEYS[table]
    cursor = await db.execute(f"SELECT {','.join(columns)} FROM {table}{where}", params)
    while rows := await cursor.fetchmany(256):
        for key in rows:
            if record_identity(table, key) == record_id:
                key_dict = dict(key)
                exact = " AND ".join(f"{column}=?" for column in columns)
                # Owner scoping is rechecked on the actual selected row.
                suffix = where.replace(" WHERE ", " AND ")
                row = await (await db.execute(f"SELECT * FROM {table} WHERE {exact}{suffix}",
                    (*[key[column] for column in columns], *params))).fetchone()
                return row, key_dict
    return None, None


def _safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[nested content omitted]"
    if isinstance(value, dict):
        return {_text(key, 128): "[redacted]" if _SECRET.search(str(key) + "=") else _safe(item, depth=depth+1)
                for key, item in list(value.items())[:128]}
    if isinstance(value, list):
        return [_safe(item, depth=depth+1) for item in value[:128]]
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            return _reference(value) or "[reference withheld]"
        return _text(value, 16000)
    return value if isinstance(value, (bool, int, float, type(None))) else _text(value)


def _provenance_ref(value: Any) -> str | None:
    ref = _reference(value)
    if ref:
        return ref
    if isinstance(value, str) and value.startswith(("owner-device:", "assertion:", "owner-memory://")) and not _SECRET.search(value):
        return _text(value, 1024)
    return None


def _unpack(row: Any) -> dict:
    result = {}
    for name, value in dict(row).items():
        if name.endswith("_json") and isinstance(value, str):
            try:
                value = json.loads(value)
                name = name[:-5]
            except (ValueError, TypeError):
                pass
        result[name] = value
    return result


class OwnerRecords:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def _view(self, db: Any, table: str, row: Any) -> dict:
        data = _unpack(row)
        source = "UNCLASSIFIED"
        authority = str(data.get("authority", ""))
        state = str(data.get("state", ""))
        if (authority == "CANONICAL_OWNER" and data.get("source_trust") == "OWNER_EXPLICIT") or state == "OWNER_CONFIRMED":
            source = "OWNER_DECLARED"
        elif authority == "INFERRED" or data.get("inferred_reason"):
            source = "INFERRED"
        elif state == "OBSERVED" or authority == "EXTERNAL_EVIDENCE":
            source = "OBSERVED"
        if table in {"shared_vocabulary", "cognitive_complement_map"}:
            from van_gateway.understanding.owner_preferences import OwnerDeclarationStore
            kind = "vocabulary" if table == "shared_vocabulary" else "complement"
            declaration = await OwnerDeclarationStore(self.store)._view(db, kind, row)
            if declaration["provenance"].get("source") == "OWNER_AUTHORED":
                source = "OWNER_DECLARED" if kind == "vocabulary" else "MIXED"
        refs = data.get("evidence_refs", data.get("evidence_used", []))
        references = [ref for value in refs[:64] if (ref := _provenance_ref(value))] if isinstance(refs, list) else []
        record_id = record_identity(table, row)
        digest = await record_revision(db, table, row)
        title = next((str(data[name]) for name in ("owner_goal", "statement", "term", "field", "owner_choice", "problem_statement", "subject", "domain", "observed_pattern") if data.get(name)), table)
        return {"store": table, "record_id": record_id, "revision_sha256": digest,
                "kind": table, "title": _text(title, 256), "source_class": source,
                "fields": [{"name": name, "value": _safe(value)} for name, value in data.items()],
                "provenance": {"evidence_refs": references, "source_ref": _provenance_ref(data.get("source_ref")),
                    "authority": authority or None, "state": state or None, "confidence": data.get("confidence"),
                    "observed_at_ms": data.get("observed_at_ms", data.get("created_at_ms", data.get("created_at_unix_ms")))},
                "erasure": {"action_class": "A4", "command_text": self.command_text(table, record_id, digest),
                    "kept_deliberately": DELIBERATELY_KEPT},
                "content_screened": True, "execution_grant": False,
                "content_bounds": {"text_characters": 16000, "collection_entries": 128, "nested_depth": 8},
                "export_scope": "selected record, screened and bounded; revision seals complete stored scope"}

    @staticmethod
    def command_text(table: str, record_id: str, digest: str) -> str:
        record_parameters(table, record_id, digest)
        return f"forget owner-derived memory record {table} {record_id} {digest}"

    async def list(self, table: str, *, limit: int = 50, cursor: int = 0) -> dict:
        if not 1 <= limit <= 100 or not 0 <= cursor <= 1_000_000:
            raise ValueError("memory_record_pagination_invalid")
        where, params = owner_scope(table)
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            count = await (await db.execute(f"SELECT COUNT(*) n FROM {table}{where}", params)).fetchone()
            rows = await (await db.execute(f"SELECT * FROM {table}{where} ORDER BY {','.join(PRIMARY_KEYS[table])} LIMIT ? OFFSET ?", (*params, limit, cursor))).fetchall()
            records = [await self._view(db, table, row) for row in rows]
        total = int(count["n"])
        next_cursor = cursor + len(records) if cursor + len(records) < total else None
        return {"store": table, "records": records, "total": total, "next_cursor": next_cursor,
                "truncated": next_cursor is not None, "snapshot_consistent": True,
                "pagination_consistency": "refresh after writes; offsets may move"}

    async def exact(self, table: str, record_id: str) -> dict:
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            row, _ = await find_record(db, table, record_id)
            if row is None:
                raise LookupError("memory_record_not_found")
            return await self._view(db, table, row)

    async def erasure_plan(self, table: str, record_id: str) -> dict:
        from van_gateway.context.memory_erasure import _scope, selected_stores
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            row, key = await find_record(db, table, record_id)
            if row is None:
                raise LookupError("memory_record_not_found")
            record = await self._view(db, table, row)
            parameters = record_parameters(table, record_id, record["revision_sha256"])
            affected = []
            for entry in selected_stores(table):
                where, params = _scope(entry, table, dependent_scope=True, record_key=key)
                count = await (await db.execute(f"SELECT COUNT(*) n FROM {entry.table}{where}", params)).fetchone()
                rows = await (await db.execute(f"SELECT {','.join(PRIMARY_KEYS[entry.table])} FROM {entry.table}{where} ORDER BY {','.join(PRIMARY_KEYS[entry.table])} LIMIT 100", params)).fetchall()
                affected.append({"store": entry.table, "count": int(count["n"]),
                                 "record_ids": [record_identity(entry.table, item) for item in rows],
                                 "truncated": int(count["n"]) > len(rows)})
        return {"store": table, "record_id": record_id, "revision_sha256": record["revision_sha256"],
                "command_text": record["erasure"]["command_text"], "action_class": "A4",
                "affected_stores": parameters["stores"], "affected_records": affected,
                "kept_deliberately": DELIBERATELY_KEPT,
                "scope": "selected record and existing dependent links; retained work/audit are disclosed"}
