"""Atomic, approved owner-memory erasure and independent identity-bound readback."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from van_gateway.command.authority import AuthoritySource, CommandAuthorityRecord, CommandAuthorityService
from van_gateway.context.forget import DELIBERATELY_KEPT, FORGETTABLE, ForgettableStore
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store

WITNESS_PREFIX = "memory_erasure_witness:"
OWNER_PRINCIPAL = "owner"


class MemoryErasureDenied(ValueError):
    """Named authorization refusal before committing a destructive write."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def selected_stores(store_id: str) -> tuple[ForgettableStore, ...]:
    if store_id == "all":
        return FORGETTABLE
    selected = tuple(entry for entry in FORGETTABLE if entry.table == store_id)
    if not selected:
        raise ValueError("memory_store_not_allowlisted")
    if store_id == "intent_nodes":
        by_name = {entry.table: entry for entry in FORGETTABLE}
        return tuple(by_name[name] for name in ("intent_edges", "intent_missions", "intent_nodes"))
    if store_id == "owner_cognitive_model":
        by_name = {entry.table: entry for entry in FORGETTABLE}
        return tuple(by_name[name] for name in ("symbiotic_growth", "owner_cognitive_model"))
    return selected


def _identity(table: str, columns: list[str], row: Any) -> str:
    # Commit to exact primary keys without retaining erased owner content.
    return hashlib.sha256(Store.dumps({"table": table, "key": {c: row[c] for c in columns}}).encode()).hexdigest()


def _scope(entry: ForgettableStore, store_id: str, *, dependent_scope: bool,
           record_key: dict | None = None) -> tuple[str, tuple[Any, ...]]:
    if record_key is not None:
        from van_gateway.understanding.records import PRIMARY_KEYS
        if entry.table == store_id:
            columns = PRIMARY_KEYS[store_id]
            where = " WHERE " + " AND ".join(f"{column}=?" for column in columns)
            params = tuple(record_key[column] for column in columns)
            if entry.owner_column:
                where += f" AND {entry.owner_column}=?"
                params += (OWNER_PRINCIPAL,)
            return where, params
        if store_id == "intent_nodes":
            intent = record_key["intent_id"]
            if entry.table == "intent_edges":
                return " WHERE from_intent_id=? OR to_intent_id=?", (intent, intent)
            if entry.table == "intent_missions":
                return " WHERE intent_id=?", (intent,)
        if store_id == "owner_cognitive_model" and entry.table == "symbiotic_growth":
            return " WHERE json_valid(evidence_refs_json) AND EXISTS (SELECT 1 FROM json_each(evidence_refs_json) WHERE value=?)", ("assertion:" + record_key["assertion_id"],)
        raise ValueError("memory_record_dependency_scope_invalid")
    if dependent_scope and store_id == "intent_nodes":
        if entry.table == "intent_edges":
            return (" WHERE from_intent_id IN (SELECT intent_id FROM intent_nodes) "
                    "OR to_intent_id IN (SELECT intent_id FROM intent_nodes)", ())
        if entry.table == "intent_missions":
            return " WHERE intent_id IN (SELECT intent_id FROM intent_nodes)", ()
    if dependent_scope and store_id == "owner_cognitive_model" and entry.table == "symbiotic_growth":
        return (" WHERE json_valid(evidence_refs_json) AND EXISTS (SELECT 1 FROM json_each(evidence_refs_json) "
                "WHERE value IN (SELECT 'assertion:' || assertion_id FROM owner_cognitive_model WHERE owner_principal_id=?))", (OWNER_PRINCIPAL,))
    return ((f" WHERE {entry.owner_column}=?", (OWNER_PRINCIPAL,)) if entry.owner_column else ("", ()))


async def _ids(db: Any, entry: ForgettableStore, store_id: str, *, dependent_scope: bool = False,
               record_key: dict | None = None) -> tuple[list[str], list[str]]:
    info = await (await db.execute(f"PRAGMA table_info({entry.table})")).fetchall()  # trusted inventory only
    columns = [str(r["name"]) for r in sorted(info, key=lambda r: r["pk"]) if r["pk"]]
    if not columns:
        raise ValueError("memory_store_has_no_identity")
    where, params = _scope(entry, store_id, dependent_scope=dependent_scope, record_key=record_key)
    cursor = await db.execute(f"SELECT {','.join(columns)} FROM {entry.table}{where}", params)
    identities = []
    while rows := await cursor.fetchmany(256):
        identities.extend(_identity(entry.table, columns, row) for row in rows)
    return columns, sorted(identities)


async def erase_memory(store: Store, store_id: str, command_id: str, *, device_id: str,
                       record_id: str | None = None, expected_sha256: str | None = None) -> dict[str, int]:
    """Recheck sealed A4 authority inside the same lock as the destructive write."""
    entries = selected_stores(store_id)
    witness: dict[str, Any] = {
        "schema_version": 1, "command_id": command_id, "store": store_id,
        "owner_principal_id": OWNER_PRINCIPAL, "tables": {},
    }
    removed = {}
    record_key = None
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            sealed = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?",
                (CommandAuthorityService.PREFIX + command_id,))).fetchone()
            authority = CommandAuthorityRecord.model_validate_json(sealed["value"]) if sealed else None
            if not authority or (
                authority.authority_source is not AuthoritySource.OWNER_COMMAND
                or authority.principal_type is not PrincipalType.OWNER_DEVICE
                or authority.device_id != device_id or not authority.owner_approved
                or authority.effective_action_class not in {ActionClass.A4, ActionClass.A5}
                or not authority.no_stale_replay or authority.expires_at_unix is None
                or authority.typed_action_id != "memory.erase"
                or authority.typed_parameter_constraints.get("store") != store_id
                or authority.typed_parameter_constraints.get("stores") != [entry.table for entry in entries]
            ):
                raise MemoryErasureDenied("memory_erasure_approved_command_required")
            if record_id is not None or expected_sha256 is not None:
                from van_gateway.understanding.records import find_record, record_parameters, record_revision
                parameters = record_parameters(store_id, record_id or "", expected_sha256 or "")
                if any(authority.typed_parameter_constraints.get(name) != value for name, value in parameters.items()):
                    raise MemoryErasureDenied("memory_erasure_record_approval_mismatch")
                row, record_key = await find_record(db, store_id, record_id)
                if row is None:
                    raise MemoryErasureDenied("memory_record_not_found")
                if await record_revision(db, store_id, row) != expected_sha256:
                    raise MemoryErasureDenied("memory_record_revision_stale")
                witness.update(record_id=record_id, expected_sha256=expected_sha256)
            elif any(authority.typed_parameter_constraints.get(name) is not None for name in ("record_id", "expected_sha256")):
                raise MemoryErasureDenied("memory_erasure_record_scope_required")
            device = await (await db.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?", (device_id,))).fetchone()
            if device is None or device["revoked_at_unix"] is not None:
                raise MemoryErasureDenied("memory_erasure_device_revoked")
            if _now_ms() // 1000 >= authority.expires_at_unix:
                raise MemoryErasureDenied("memory_erasure_authority_expired")
            for entry in entries:
                columns, ids = await _ids(db, entry, store_id, dependent_scope=True, record_key=record_key)
                witness["tables"][entry.table] = {"primary_key_columns": columns, "before_ids": ids, "before_count": len(ids)}
            now_ms = _now_ms()
            witness["observed_before_write_ms"] = now_ms
            for entry in entries:
                if _now_ms() // 1000 >= authority.expires_at_unix:
                    raise MemoryErasureDenied("memory_erasure_authority_expired")
                where, params = _scope(entry, store_id, dependent_scope=True, record_key=record_key)
                cursor = await db.execute(f"DELETE FROM {entry.table}{where}", params)
                count = int(cursor.rowcount or 0)
                if count != witness["tables"][entry.table]["before_count"]:
                    raise ValueError("memory_erasure_count_mismatch")
                removed[entry.table] = count
                witness["tables"][entry.table]["removed_count"] = count
                if entry.table in {"shared_vocabulary", "cognitive_complement_map"}:
                    kind = "vocabulary" if entry.table == "shared_vocabulary" else "complement"
                    if record_key is None:
                        await db.execute("DELETE FROM runtime_meta WHERE key GLOB ?", (f"owner_memory_declaration:{kind}:*",))
                    else:
                        from van_gateway.understanding.owner_preferences import _key
                        content = {"term": record_key["term"], "project_id": record_key["project_id"] or None} if kind == "vocabulary" else {"domain": row["domain"]}
                        await db.execute("DELETE FROM runtime_meta WHERE key=?", (_key(kind, content),))
            if _now_ms() // 1000 >= authority.expires_at_unix:
                raise MemoryErasureDenied("memory_erasure_authority_expired")
            revision = await (await db.execute(
                "SELECT value FROM runtime_meta WHERE key='owner_context_revision'"
            )).fetchone()
            before_revision = int(revision["value"]) if revision else 0
            witness["context_revision_before"] = before_revision
            witness["context_revision_after"] = before_revision + 1
            await db.execute(
                "INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES('owner_context_revision',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
                (str(before_revision + 1), now_ms),
            )
            await db.execute(
                "INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
                (WITNESS_PREFIX + command_id, Store.dumps(witness), now_ms),
            )
        except BaseException:
            await db.rollback()
            raise
        await db.commit()
    return removed


async def memory_erasure_readback(store: Store, store_id: str, command_id: str, *,
                                  record_id: str | None = None, expected_sha256: str | None = None) -> dict[str, Any]:
    """Read committed scope and exact captured identities, never a worker success claim."""
    entries = selected_stores(store_id)
    row = await store.fetchone("SELECT value FROM runtime_meta WHERE key=?", (WITNESS_PREFIX + command_id,))
    witness = json.loads(row["value"]) if row else {}
    authority = await CommandAuthorityService(store).get(command_id)
    bound = bool(
        authority and authority.authority_source is AuthoritySource.OWNER_COMMAND
        and authority.principal_type is PrincipalType.OWNER_DEVICE
        and authority.effective_action_class in {ActionClass.A4, ActionClass.A5}
        and authority.owner_approved and authority.typed_action_id == "memory.erase"
        and authority.typed_parameter_constraints.get("store") == store_id
        and authority.typed_parameter_constraints.get("stores") == [entry.table for entry in entries]
        and witness.get("command_id") == command_id and witness.get("store") == store_id
        and witness.get("owner_principal_id") == OWNER_PRINCIPAL
        and set(witness.get("tables", {})) == {entry.table for entry in entries}
    )
    if record_id is not None or expected_sha256 is not None:
        bound = bound and bool(authority and authority.typed_parameter_constraints.get("record_id") == record_id
            and authority.typed_parameter_constraints.get("expected_sha256") == expected_sha256
            and witness.get("record_id") == record_id and witness.get("expected_sha256") == expected_sha256)
    else:
        bound = bound and not witness.get("record_id") and bool(authority and not authority.typed_parameter_constraints.get("record_id"))
    absent = empty = True
    removed: dict[str, int] = {}
    async with store.connection() as db:
        for entry in entries:
            columns, ids = await _ids(db, entry, store_id)
            captured = witness.get("tables", {}).get(entry.table, {})
            before = captured.get("before_ids")
            valid = bool(
                isinstance(before, list) and all(isinstance(i, str) and len(i) == 64 for i in before)
                and captured.get("primary_key_columns") == columns
                and captured.get("before_count") == len(set(before))
                and captured.get("removed_count") == len(before)
            )
            absent = absent and valid and not bool(set(before or []) & set(ids))
            # Per-store intent deletion affects only linked child rows, so unrelated
            # orphan links are retained. Their absence was never an authorized effect.
            if record_id is None and (store_id not in {"intent_nodes", "owner_cognitive_model"} or entry.table == store_id):
                empty = empty and not ids
            if valid:
                removed[entry.table] = len(before)
    observed = {
        "store": store_id, "affected_stores": [entry.table for entry in entries],
        "scope_empty": empty, "captured_ids_absent": absent,
        "owner_approved_command_bound": bound, "removed_counts": removed,
        "kept_deliberately": DELIBERATELY_KEPT,
    }
    if record_id is not None:
        from van_gateway.understanding.records import find_record
        async with store.connection() as db:
            row, _ = await find_record(db, store_id, record_id)
        observed.update(record_id=record_id, expected_sha256=expected_sha256)
        empty = row is None and absent
        observed["scope_empty"] = empty
    revision = await store.fetchone("SELECT value FROM runtime_meta WHERE key='owner_context_revision'")
    before_revision, after_revision = witness.get("context_revision_before"), witness.get("context_revision_after")
    invalidated = bool(isinstance(before_revision, int) and isinstance(after_revision, int)
                       and after_revision > before_revision and revision and int(revision["value"]) >= after_revision)
    observed["context_cache_invalidated"] = invalidated
    if bound and absent and empty and invalidated:
        observed["evidence_refs"] = [f"memory-erasure://{command_id}"]
    return observed


__all__ = ["MemoryErasureDenied", "erase_memory", "memory_erasure_readback", "selected_stores"]
