"""Exact owner consent grants, created by fresh A4 and enforced at native effect entry.

A grant constrains consent for a registered action and its immutable parameters.
Canonical command authority, native A4 approval, provider credentials and VATI policy
remain independently required. This is not a general-purpose executor.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from van_gateway.capability.permissions import KNOWN_PERMISSIONS, _SECRET_SHAPED
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store

ACTION_ID = "owner.permission.grant"
COMMAND_PREFIX = "grant owner permission "
MAX_DURATION_MS = 30 * 86400 * 1000
WITNESS_PREFIX = "owner_permission_witness:"
CURRENT_PREFIX = "owner_permission_current:"
CLAIM_PREFIX = "owner_permission_claim:"
USE_COUNT_SEMANTICS = "CANONICAL_EFFECT_ADMISSION_RESERVATIONS"
FAMILIES = {
    "email.read": ("google.gmail.read",),
    "email.send": ("google.gmail.draft", "google.gmail.send"),
    "calendar.read": ("google.calendar.read",),
    "calendar.write": ("google.calendar.reschedule",),
    "browser.authenticated_session": ("browser.plan.execute", "browser.file.provider.submit"),
    "github.write": ("github.write",),
    "github.merge": ("github.merge",),
    "computer.remote": ("computer.remote",),
    "trading.read": ("trading.read",),
    "vati.execute": ("vati.execute",),
}

class OwnerPermissionDenied(ValueError):
    pass

def digest(value: Any) -> str:
    return hashlib.sha256(Store.dumps(value).encode()).hexdigest()

def permission_parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"permission", "action_id", "parameters", "expires_at_ms", "max_uses"}:
        raise OwnerPermissionDenied("permission_exact_fields_required")
    if not isinstance(value["permission"], str) or not isinstance(value["action_id"], str) or value["permission"] not in KNOWN_PERMISSIONS or value["action_id"] not in FAMILIES[value["permission"]]:
        raise OwnerPermissionDenied("permission_action_not_declared")
    if not isinstance(value["parameters"], dict) or len(value["parameters"]) > 32:
        raise OwnerPermissionDenied("permission_parameters_invalid")
    if type(value["expires_at_ms"]) is not int or value["expires_at_ms"] <= 0:
        raise OwnerPermissionDenied("permission_expiry_required")
    if type(value["max_uses"]) is not int or not 1 <= value["max_uses"] <= 1000:
        raise OwnerPermissionDenied("permission_use_budget_invalid")
    try:
        text = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        encoded = text.encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise OwnerPermissionDenied("permission_parameters_invalid") from exc
    if len(encoded) > 8192 or _SECRET_SHAPED.search(text):
        raise OwnerPermissionDenied("permission_scope_private_credentials_refused")
    def inspect(v, depth=0):
        if depth > 16:
            raise OwnerPermissionDenied("permission_scope_too_deep")
        if isinstance(v, dict):
            for k, item in v.items():
                if not isinstance(k, str) or re.search(r"(?i)(token|password|secret|cookie|private_key)", k):
                    raise OwnerPermissionDenied("permission_scope_private_credentials_refused")
                inspect(item, depth + 1)
        elif isinstance(v, list):
            if len(v) > 64: raise OwnerPermissionDenied("permission_scope_too_large")
            for item in v: inspect(item, depth + 1)
        elif isinstance(v, str) and (v.strip() in {"*", "**"} or len(v) > 4096):
            raise OwnerPermissionDenied("permission_wildcard_or_unbounded_scope_refused")
    inspect(value["parameters"])
    return json.loads(text)

def scope_key(action_id: str, parameters: dict[str, Any]) -> str:
    return CURRENT_PREFIX + digest({"action_id": action_id, "parameters": parameters})

def _bound(a, command_id, device_id, params):
    from van_gateway.command.authority import AuthoritySource
    return bool(a and a.command_id == command_id and a.device_id == device_id
        and a.authority_source is AuthoritySource.OWNER_COMMAND
        and a.principal_type is PrincipalType.OWNER_DEVICE and a.owner_approved
        and a.effective_action_class is ActionClass.A4 and a.typed_action_id == ACTION_ID
        and digest(a.typed_parameter_constraints) == digest(params) and a.no_stale_replay
        and a.expires_at_unix is not None)

async def _meta(db, key):
    row = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?", (key,))).fetchone()
    try:
        return json.loads(row["value"]) if row else None
    except (ValueError, TypeError) as exc:
        raise OwnerPermissionDenied("permission_scope_integrity_failed") from exc


async def _source_bound(db, witness, row, parameters) -> bool:
    """Validate the durable grant against its original authenticated source.

    A current pointer is only a lookup; it cannot substitute another grant or
    manufacture the immutable owner operation that produced one.
    """
    from van_gateway.command.authority import CommandAuthorityRecord, CommandAuthorityService
    if not isinstance(witness, dict) or not row:
        return False
    required = {"schema_version", "grant_id", "command_id", "device_id", "parameters",
                "created_at_ms", "native_action_class"}
    if set(witness) != required or type(witness["schema_version"]) is not int or witness["schema_version"] != 1:
        return False
    if (not isinstance(witness["command_id"], str) or not witness["command_id"]
        or not isinstance(witness["device_id"], str) or not witness["device_id"]
        or type(witness["created_at_ms"]) is not int or witness["created_at_ms"] <= 0
        or witness["native_action_class"] not in {"A1", "A2", "A3", "A4"}):
        return False
    try:
        canonical = permission_parameters(witness["parameters"])
        raw = await _meta(db, CommandAuthorityService.PREFIX + witness["command_id"])
        authority = CommandAuthorityRecord.model_validate(raw) if raw else None
        scope = json.loads(row["scope"])
    except (ValueError, TypeError):
        return False
    expected_id = "perm_" + hashlib.sha256(witness["command_id"].encode()).hexdigest()[:32]
    return bool(witness["grant_id"] == expected_id == row["grant_id"]
        and _bound(authority, witness["command_id"], witness["device_id"], canonical)
        and digest(canonical) == digest(parameters) == digest(scope)
        and row["permission"] == canonical["permission"]
        and row["origin"] == "OWNER_DECISION"
        and row["origin_evidence_ref"] == "owner-permission://" + witness["command_id"]
        and row["expires_at_ms"] == canonical["expires_at_ms"]
        and row["granted_at_ms"] == witness["created_at_ms"])

async def grant_owner_permission(store: Store, parameters: dict[str, Any], command_id: str, *, device_id: str):
    from van_gateway.command.authority import CommandAuthorityRecord, CommandAuthorityService
    parameters = permission_parameters(parameters)
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            now = int(time.time() * 1000)
            raw = await _meta(db, CommandAuthorityService.PREFIX + command_id)
            authority = CommandAuthorityRecord.model_validate(raw) if raw else None
            if not _bound(authority, command_id, device_id, parameters):
                raise OwnerPermissionDenied("permission_fresh_owner_a4_required")
            if now // 1000 >= authority.expires_at_unix or now // 1000 - authority.issued_at_unix > 30:
                raise OwnerPermissionDenied("permission_owner_approval_expired")
            device = await (await db.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?", (device_id,))).fetchone()
            mission = await (await db.execute("SELECT state FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id')=?", (command_id,))).fetchone()
            if not device or device["revoked_at_unix"] is not None or not mission or mission["state"] != "RUNNING":
                raise OwnerPermissionDenied("permission_current_owner_command_required")
            old = await _meta(db, WITNESS_PREFIX + command_id)
            if old:
                if old["parameters"] != parameters or old["device_id"] != device_id:
                    raise OwnerPermissionDenied("permission_operation_conflict")
                await db.rollback()
                return
            if not now < parameters["expires_at_ms"] <= now + MAX_DURATION_MS:
                raise OwnerPermissionDenied("permission_expiry_outside_bounds")
            definition = await (await db.execute("SELECT * FROM action_definitions WHERE action_id=?", (parameters["action_id"],))).fetchone()
            if not definition or not definition["enabled"] or definition["action_class"] == "A5":
                raise OwnerPermissionDenied("permission_native_action_unavailable")
            schema = json.loads(definition["parameter_schema_json"])
            supplied = parameters["parameters"]
            if set(schema.get("required", [])) - set(supplied) or set(supplied) - set(schema.get("properties", {})):
                raise OwnerPermissionDenied("permission_native_parameter_shape_invalid")
            for field, item in supplied.items():
                declared = schema.get("properties", {}).get(field)
                kind = declared.get("type") if isinstance(declared, dict) else declared
                if ((kind == "string" and not isinstance(item, str))
                    or (kind == "integer" and type(item) is not int)
                    or (kind == "array" and not isinstance(item, list))
                    or (kind == "object" and not isinstance(item, dict))):
                    raise OwnerPermissionDenied("permission_native_parameter_type_invalid")
            grant_id = "perm_" + hashlib.sha256(command_id.encode()).hexdigest()[:32]
            witness = {"schema_version": 1, "grant_id": grant_id, "command_id": command_id,
                "device_id": device_id, "parameters": parameters, "created_at_ms": now,
                "native_action_class": definition["action_class"]}
            await db.execute("INSERT INTO permission_grants(grant_id,permission,display_name,scope,origin,origin_evidence_ref,granted_at_ms,expires_at_ms,use_count) VALUES(?,?,?,?,?,?,?,?,0)",
                (grant_id, parameters["permission"], KNOWN_PERMISSIONS[parameters["permission"]], Store.dumps(parameters),
                 "OWNER_DECISION", "owner-permission://" + command_id, now, parameters["expires_at_ms"]))
            for key in (WITNESS_PREFIX + command_id, scope_key(parameters["action_id"], supplied)):
                await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms", (key, Store.dumps(witness), now))
            final_now = int(time.time() * 1000)
            if final_now // 1000 >= authority.expires_at_unix or final_now // 1000 - authority.issued_at_unix > 30:
                raise OwnerPermissionDenied("permission_owner_approval_expired")
            if final_now >= parameters["expires_at_ms"]:
                raise OwnerPermissionDenied("permission_expiry_outside_bounds")
        except BaseException:
            await db.rollback()
            raise
        await db.commit()

async def permission_readback(store: Store, parameters: dict[str, Any], command_id: str) -> dict[str, Any]:
    parameters = permission_parameters(parameters)
    async with store.connection() as db:
        await db.execute("BEGIN")
        witness = await _meta(db, WITNESS_PREFIX + command_id)
        current = await _meta(db, scope_key(parameters["action_id"], parameters["parameters"]))
        row = await (await db.execute("SELECT * FROM permission_grants WHERE grant_id=?", (witness.get("grant_id", "") if isinstance(witness, dict) else "",))).fetchone()
        bound = bool(isinstance(witness, dict) and witness.get("command_id") == command_id
                     and await _source_bound(db, witness, row, parameters))
        device = await (await db.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?",
            (witness.get("device_id", "") if isinstance(witness, dict) else "",))).fetchone()
        grant_current = bool(bound and row["revoked_at_ms"] is None and row["expires_at_ms"] > int(time.time()*1000)
                             and device and device["revoked_at_unix"] is None)
        matched = bool(bound and grant_current and isinstance(current, dict) and digest(current) == digest(witness))
    observed = {"grant_id": witness.get("grant_id") if isinstance(witness, dict) else None,
        "permission": parameters["permission"], "action_id": parameters["action_id"],
        "owner_approved_command_bound": bound, "current_owner_operation_matches": matched,
        "grant_exists": bool(bound), "grant_current":grant_current, "native_authority_required": True}
    if bound and matched:
        observed["evidence_refs"] = ["owner-permission://" + command_id]
    return observed

async def enforce_permission_scope(store: Store, *, action_id: str, parameters: dict[str, Any], execution_id: str,
                                   claim: bool, db=None) -> None:
    """Fence exact consent, optionally inside the effect admission transaction.

    Claimed uses are admission reservations, not assertions that a provider effect
    occurred. A reservation is charged once per canonical execution and survives
    reply loss; no unsafe replay refunds a possibly used authorization.
    """
    async def check(connection):
        current = await _meta(connection, scope_key(action_id, parameters))
        prior = await _meta(connection, CLAIM_PREFIX + execution_id)
        if not current:
            if prior:
                raise OwnerPermissionDenied("permission_execution_scope_changed")
            return
        if not isinstance(current, dict) or not isinstance(current.get("parameters"), dict):
            raise OwnerPermissionDenied("permission_scope_integrity_failed")
        if (current["parameters"].get("action_id") != action_id
            or digest(current["parameters"].get("parameters")) != digest(parameters)):
            raise OwnerPermissionDenied("permission_scope_integrity_failed")
        now = int(time.time() * 1000)
        row = await (await connection.execute("SELECT * FROM permission_grants WHERE grant_id=?", (current.get("grant_id", ""),))).fetchone()
        original = await _meta(connection, WITNESS_PREFIX + str(current.get("command_id", "")))
        if (not isinstance(original, dict) or digest(current) != digest(original)
            or not await _source_bound(connection, current, row, current["parameters"])):
            raise OwnerPermissionDenied("permission_scope_integrity_failed")
        device = await (await connection.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?", (current["device_id"],))).fetchone()
        if not row or row["revoked_at_ms"] is not None or row["expires_at_ms"] <= now or not device or device["revoked_at_unix"] is not None:
            raise OwnerPermissionDenied("permission_scope_revoked_or_expired")
        if prior and (not isinstance(prior, dict) or prior.get("grant_id") != current["grant_id"]
            or prior.get("scope_digest") != digest(current["parameters"])
            or prior.get("action_id") != action_id or digest(prior.get("parameters")) != digest(parameters)):
            raise OwnerPermissionDenied("permission_execution_scope_changed")
        if not prior and row["use_count"] >= current["parameters"]["max_uses"]:
            raise OwnerPermissionDenied("permission_scope_use_budget_exhausted")
        if claim and not prior:
            await connection.execute("UPDATE permission_grants SET last_used_at_ms=?,use_count=use_count+1 WHERE grant_id=?", (now,current["grant_id"]))
            await connection.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)", (CLAIM_PREFIX + execution_id, Store.dumps({"grant_id":current["grant_id"],"scope_digest":digest(current["parameters"]),"action_id":action_id,"parameters":parameters}),now))
    if db is not None:
        await check(db)
        return
    async with store.connection() as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            await check(connection)
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise

async def permission_contracts(store: Store) -> dict[str, Any]:
    rows = await store.fetchall("SELECT * FROM action_definitions WHERE enabled=1 AND action_class<>'A5' ORDER BY action_id")
    contracts = []
    for row in rows:
        for permission, actions in FAMILIES.items():
            if row["action_id"] in actions:
                schema=json.loads(row["parameter_schema_json"])
                contracts.append({"permission":permission,"action_id":row["action_id"],"action_class":row["action_class"],
                    "required_fields":schema.get("required",[]),"parameter_schema":schema,
                    "execution_semantics":"EXACT_CONSENT_WITH_INDEPENDENT_CANONICAL_COMMAND_AUTHORITY",
                    "fresh_native_approval_per_use":row["action_class"]=="A4"})
    return {"contracts":contracts,"max_duration_ms":MAX_DURATION_MS,"max_uses":1000,"command_prefix":COMMAND_PREFIX,
        "native_authority_required":True,"use_count_semantics":USE_COUNT_SEMANTICS,
        "unavailable_permissions":[p for p in KNOWN_PERMISSIONS if not any(c["permission"]==p for c in contracts)]}

async def recheck_permission_execution(store: Store, execution_id: str, *, db=None) -> None:
    if db is None:
        async with store.connection() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            try:
                await recheck_permission_execution(store, execution_id, db=connection)
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return
    claimed = await _meta(db, CLAIM_PREFIX + execution_id)
    if claimed:
        await enforce_permission_scope(store,action_id=claimed["action_id"],parameters=claimed["parameters"],execution_id=execution_id,claim=False,db=db)

def build_owner_permission_router(store: Store) -> APIRouter:
    router=APIRouter(prefix="/v1/permissions")
    @router.get("/contracts")
    async def contracts(): return await permission_contracts(store)
    @router.get("/grants/{grant_id}")
    async def detail(grant_id: str):
        row=await store.fetchone("SELECT * FROM permission_grants WHERE grant_id=?",(grant_id,))
        if not row: raise HTTPException(status_code=404,detail="permission_grant_not_found")
        result=dict(row)
        if str(row["origin_evidence_ref"] or "").startswith("owner-permission://"):
            result["exact_scope"]=json.loads(row["scope"])
            result["native_authority_required"]=True
            result["use_count_semantics"] = USE_COUNT_SEMANTICS
            result["fresh_native_approval_per_use"] = next((c["fresh_native_approval_per_use"] for c in (await permission_contracts(store))["contracts"] if c["action_id"]==result["exact_scope"]["action_id"]),True)
        return result
    return router
