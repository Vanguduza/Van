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

from fastapi import APIRouter, HTTPException, Request

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
        await _validated_permission_uses(connection,row,current['parameters'])
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
    async def detail(grant_id: str, request: Request):
        from van_gateway.capability.permissions import PermissionError_
        try:
            cipher=request.app.state.auth._fernet
            return await owner_grant_detail(store,grant_id,device_id=getattr(request.state,"van_device_id",None),cipher=cipher,
                access_token_hash=hashlib.sha256(request.headers.get("X-Van-Device-Token","").encode()).hexdigest())
        except PermissionError_ as exc:
            raise permission_http_error(exc) from exc
    return router


def permission_http_error(exc):
    status=404 if exc.code in {"permission_grant_not_found","permission_revocation_unknown"} else 403 if exc.code in {"permission_device_mismatch","permission_device_revoked"} else 503 if exc.code in {"permission_scope_integrity_failed","permission_revocation_history_unavailable"} else 409
    return HTTPException(status_code=status,detail=exc.code)

# LAC-210 uses the existing permission registry and runtime_meta original journal.
# A receipt never grants provider/native authority or replaces the grant owner.
REVOCATION_PREFIX = 'owner_permission_revocation:'
REVOCATION_SCHEMA = 'van.owner-permission-revocation/1'
REVOCATION_REQUEST_TTL_MS = 600_000
REFUSALS = {'permission_revocation_stale_revision','permission_revocation_request_expired','permission_revocation_caller_changed'}

async def _validated_permission_uses(db,row,parameters):
    count=row['use_count']
    if type(count) is not int or not 0<=count<=parameters['max_uses']:
        raise OwnerPermissionDenied('permission_use_count_integrity_failed')
    claims=await (await db.execute(
        "SELECT key,value FROM runtime_meta WHERE key GLOB ? AND CASE WHEN json_valid(value) "
        "THEN json_extract(value,'$.grant_id')=? ELSE 0 END LIMIT 1001",
        (CLAIM_PREFIX+'*',row['grant_id']),
    )).fetchall()
    if count!=len(claims):raise OwnerPermissionDenied('permission_use_count_integrity_failed')
    for claim in claims:
        value=json.loads(claim['value'])
        if (set(value)!={'grant_id','scope_digest','action_id','parameters'}
            or not claim['key'][len(CLAIM_PREFIX):] or value['scope_digest']!=digest(parameters)
            or value['action_id']!=parameters['action_id'] or digest(value['parameters'])!=digest(parameters['parameters'])):
            raise OwnerPermissionDenied('permission_use_count_integrity_failed')
    return count

async def _raw_meta(db,key):
    row=await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',(key,))).fetchone()
    return row['value'] if row else None

async def grant_detail_in_snapshot(db,grant_id,*,now_ms=None):
    from van_gateway.capability.permissions import PermissionError_
    row=await (await db.execute('SELECT * FROM permission_grants WHERE grant_id=?',(grant_id,))).fetchone()
    if row is None:raise PermissionError_('permission_grant_not_found')
    immutable={k:row[k] for k in ('grant_id','permission','display_name','scope','origin','origin_evidence_ref','granted_at_ms','expires_at_ms')}
    result=dict(row)
    now=int(time.time()*1000) if now_ms is None else now_ms
    bound=False;accounting=False;witness=None;raw_witness=None;raw_authority=None
    owner_source=str(row['origin_evidence_ref'] or '').startswith('owner-permission://')
    if owner_source:
        command_id=str(row['origin_evidence_ref'])[len('owner-permission://'):]
        raw_witness=await _raw_meta(db,WITNESS_PREFIX+command_id)
        from van_gateway.command.authority import CommandAuthorityService
        raw_authority=await _raw_meta(db,CommandAuthorityService.PREFIX+command_id)
        try:
            if not raw_witness or len(raw_witness)>32768 or not raw_authority or len(raw_authority)>65536:
                raise ValueError('original source unavailable')
            witness=json.loads(raw_witness)
            params=permission_parameters(json.loads(row['scope']))
            bound=await _source_bound(db,witness,row,params)
        except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
            bound=False
    if bound:
        try:
            current=await _meta(db,scope_key(params['action_id'],params['parameters']))
            current_matches=isinstance(current,dict) and digest(current)==digest(witness)
            await _validated_permission_uses(db,row,params)
            accounting=True
        except (ValueError,TypeError,KeyError):current_matches=False
        issuer=await (await db.execute('SELECT revoked_at_unix FROM devices WHERE device_id=?',(witness['device_id'],))).fetchone()
        definition=await (await db.execute('SELECT enabled,action_class FROM action_definitions WHERE action_id=?',(params['action_id'],))).fetchone()
        available=bool(definition and definition['enabled'] and definition['action_class']!='A5')
        remaining=max(0,params['max_uses']-row['use_count']) if accounting else None
        live=bool(accounting and row['revoked_at_ms'] is None and row['expires_at_ms']>now and issuer and issuer['revoked_at_unix'] is None)
        usable=bool(live and current_matches and available and remaining and remaining>0)
        state=('CORRUPT' if not accounting else 'REVOKED' if row['revoked_at_ms'] is not None else
            'EXPIRED' if row['expires_at_ms']<=now else 'ISSUER_REVOKED' if not issuer or issuer['revoked_at_unix'] is not None else
            'SUPERSEDED' if not current_matches else 'UNAVAILABLE' if not available else 'EXHAUSTED' if remaining==0 else 'CURRENT')
        result.update(exact_scope=params,device_id=witness['device_id'],grant_device_id=witness['device_id'],
            max_uses=params['max_uses'],remaining_uses=remaining,effective_remaining_uses=remaining if usable else 0,
            grant_current=usable,source_verified=True,accounting_verified=accounting,
            use_count_semantics=USE_COUNT_SEMANTICS if accounting else 'UNVERIFIED_STORED_COUNT',
            fresh_native_approval_per_use=not definition or definition['action_class']=='A4',
            effect_scope='EXACT_OWNER_CONSENT_WITH_INDEPENDENT_NATIVE_AUTHORITY')
    else:
        state='CORRUPT' if owner_source else 'REVOKED' if row['revoked_at_ms'] is not None else 'EXPIRED' if row['expires_at_ms'] is not None and row['expires_at_ms']<=now else 'SOURCE_UNVERIFIED'
        result.update(device_id=None,grant_device_id=None,max_uses=None,remaining_uses=None,effective_remaining_uses=0,
            grant_current=False,source_verified=False,accounting_verified=False,use_count_semantics='UNVERIFIED_STORED_COUNT',
            effect_scope='LOCAL_REGISTRY_ONLY_CORRUPT_SOURCE' if owner_source else 'LOCAL_REGISTRY_ONLY_SOURCE_UNVERIFIED')
    # Untrusted source fields remain visible as stored claims, never as authority;
    # credential-shaped values are redacted even when corrupt history is inspected.
    for field in ('scope','origin_evidence_ref','display_name'):
        if _SECRET_SHAPED.search(str(result.get(field) or '')):result[field]='[redacted credential-shaped stored value]'
    result.update(authority_state=state,native_authority_required=True,observed_at_ms=now)
    result['source_digest']=digest({'grant':immutable,'witness_raw':raw_witness,'authority_raw':raw_authority})
    # Protective withdrawal selects immutable authority generation, not a moving
    # reservation counter. Accounting is independently read/preserved in this snapshot.
    result['source_revision']=digest({'grant_id':grant_id,'source':result['source_digest']})
    result['accounting_revision']=digest({'use_count':row['use_count'],'last_used_at_ms':row['last_used_at_ms'],
        'revoked_at_ms':row['revoked_at_ms'],'revocation_reason':row['revocation_reason'],'state':state})
    return result

async def _revocation_actor(db,device_id,*,access_token_hash=None,proof_required=False):
    from van_gateway.capability.permissions import PermissionError_
    row=await (await db.execute('SELECT * FROM devices WHERE device_id=?',(device_id,))).fetchone()
    if not row or row['revoked_at_unix'] is not None or access_token_hash is not None and row['access_token_hash']!=access_token_hash:
        raise PermissionError_('permission_device_revoked')
    binding=await (await db.execute('SELECT binding_id,status,device_key_fingerprint FROM owner_device_bindings WHERE device_id=?',(device_id,))).fetchone()
    if proof_required and (not binding or binding['status']!='ACTIVE'):
        raise PermissionError_('permission_device_revoked')
    return digest({'caller_device_id':device_id,'enrolled_at_unix':row['enrolled_at_unix'],
        'public_key_pem':row['public_key_pem'],'access_token_hash':row['access_token_hash'],
        'binding':dict(binding) if binding else None})

async def owner_grant_detail(store,grant_id,*,device_id=None,cipher=None,access_token_hash=None):
    import uuid
    async with store.connection() as db:
        await db.execute('BEGIN')
        detail=await grant_detail_in_snapshot(db,grant_id)
        if device_id is not None:
            caller=await _revocation_actor(db,device_id,access_token_hash=access_token_hash)
            detail['caller_device_id']=device_id
            detail['revocation_request_available']=cipher is not None
            if cipher is None:detail['revocation_unavailable_reason']='protected_operation_storage_unavailable'
            if cipher is not None:
                # Stateless inert proposal: GET creates no command, grant or journal row.
                proposal=dict(operation_id='permission-revoke-'+uuid.uuid4().hex,caller_device_id=device_id,
                    grant_device_id=detail['grant_device_id'],expected_revision=detail['source_revision'],
                    expected_source_digest=detail['source_digest'])
                token=dict(schema='van.permission-revocation-request/1',request=proposal,grant_id=grant_id,
                    caller_context=caller,issued_at_ms=detail['observed_at_ms'],expires_at_ms=detail['observed_at_ms']+REVOCATION_REQUEST_TTL_MS)
                detail['revocation_request']={**proposal,'request_token':cipher.encrypt(Store.dumps(token).encode()).decode()}
        return detail

REQUEST_FIELDS={'operation_id','caller_device_id','grant_device_id','expected_revision','expected_source_digest','request_token'}
RESULT_FIELDS={'operation_id','grant_id','caller_device_id','grant_device_id','state','revoked','revoked_at_ms',
    'source_digest','expected_revision','effect_scope','native_authority_issued','reason_code','changed','request_deadline_ms'}

def _decode_request(cipher,request,grant_id):
    from cryptography.fernet import InvalidToken
    from van_gateway.capability.permissions import PermissionError_
    try:
        raw=request['request_token']
        if not isinstance(raw,str) or not 1<=len(raw)<=16384:raise ValueError('token shape')
        token=json.loads(cipher.decrypt(raw.encode()))
        proposal={k:request[k] for k in REQUEST_FIELDS if k!='request_token'}
        if (set(token)!={'schema','request','grant_id','caller_context','issued_at_ms','expires_at_ms'}
            or token['schema']!='van.permission-revocation-request/1' or token['grant_id']!=grant_id
            or token['request']!=proposal or type(token['issued_at_ms']) is not int or type(token['expires_at_ms']) is not int
            or token['expires_at_ms']-token['issued_at_ms']!=REVOCATION_REQUEST_TTL_MS):raise ValueError('request binding')
        return token
    except (InvalidToken,ValueError,TypeError,KeyError,AttributeError):
        raise PermissionError_('permission_revocation_request_invalid') from None

async def _original_revocation(db,*,operation_id,grant_id,device_id,cipher):
    from cryptography.fernet import InvalidToken
    from van_gateway.capability.permissions import PermissionError_
    raw=await _raw_meta(db,REVOCATION_PREFIX+operation_id)
    if raw is None:return None
    try:
        record=json.loads(cipher.decrypt(raw.encode()))
        if set(record)!={'schema','grant_id','request','request_digest','source_digest','revocation_digest','result'} or record['schema']!=REVOCATION_SCHEMA:
            raise ValueError('original schema')
        request=record['request'];result=record['result']
        if (set(request)!=REQUEST_FIELDS or set(result)!=RESULT_FIELDS or digest(request)!=record['request_digest']
            or request['operation_id']!=operation_id or result['operation_id']!=operation_id
            or result['grant_id']!=record['grant_id'] or result['caller_device_id']!=request['caller_device_id']
            or result['expected_revision']!=request['expected_revision'] or result['source_digest']!=record['source_digest']
            or result['native_authority_issued'] is not False or result['state'] not in {'APPLIED','REFUSED'}
            or type(result['request_deadline_ms']) is not int or result['request_deadline_ms']<=0
            or request['request_token'] is not None and result['grant_device_id']!=request['grant_device_id']):raise ValueError('original binding')
        if result['state']=='APPLIED':
            if (result['revoked'] is not True or type(result['revoked_at_ms']) is not int or result['revoked_at_ms']<=0
                or result['reason_code'] is not None or type(result['changed']) is not bool):raise ValueError('applied outcome')
        elif result['revoked'] is not False or result['revoked_at_ms'] is not None or result['changed'] is not False or result['reason_code'] not in REFUSALS:
            raise ValueError('refused outcome')
    except (InvalidToken,ValueError,TypeError,KeyError,AttributeError):
        raise PermissionError_('permission_revocation_history_unavailable') from None
    if request['caller_device_id']!=device_id:raise PermissionError_('permission_device_mismatch')
    if record['grant_id']!=grant_id:raise PermissionError_('permission_revocation_operation_conflict')
    if result['state']=='REFUSED':return record
    detail=await grant_detail_in_snapshot(db,grant_id)
    if (detail['source_digest']!=record['source_digest'] or detail['grant_device_id']!=result['grant_device_id']
        or detail['effect_scope']!=result['effect_scope']
        or detail['revoked_at_ms']!=result['revoked_at_ms']
        or digest({'revoked_at_ms':detail['revoked_at_ms'],'reason':detail['revocation_reason']})!=record['revocation_digest']):
        raise PermissionError_('permission_revocation_subject_changed')
    return record

async def revoke_permission_grant(store,*,grant_id,device_id,cipher,operation_id=None,caller_device_id=None,
        grant_device_id=None,expected_revision=None,expected_source_digest=None,request_token=None,
        access_token_hash=None,proof_required=False):
    from van_gateway.capability.permissions import PermissionError_
    received_at=int(time.time()*1000)
    legacy=operation_id is None
    if legacy:
        if any(v is not None for v in (caller_device_id,grant_device_id,expected_revision,expected_source_digest,request_token)):
            raise PermissionError_('permission_revocation_identity_required')
        operation_id='legacy-'+digest({'grant_id':grant_id,'caller_device_id':device_id})
        caller_device_id=device_id
    else:
        if caller_device_id is None:raise PermissionError_('permission_revocation_precondition_required')
        if caller_device_id!=device_id:raise PermissionError_('permission_device_mismatch')
        if (not isinstance(operation_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{15,127}',operation_id)
            or not isinstance(expected_revision,str) or not re.fullmatch(r'[0-9a-f]{64}',expected_revision)
            or not isinstance(expected_source_digest,str) or not re.fullmatch(r'[0-9a-f]{64}',expected_source_digest)):
            raise PermissionError_('permission_revocation_precondition_required')
    request=dict(operation_id=operation_id,caller_device_id=caller_device_id,grant_device_id=grant_device_id,
        expected_revision=expected_revision,expected_source_digest=expected_source_digest,request_token=request_token)
    async with store.connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        caller=await _revocation_actor(db,device_id,access_token_hash=access_token_hash,proof_required=proof_required)
        try:
            original=await _original_revocation(db,operation_id=operation_id,grant_id=grant_id,device_id=device_id,cipher=cipher)
        except PermissionError_ as exc:
            if legacy and exc.code=='permission_revocation_subject_changed':raise PermissionError_('permission_revocation_identity_required') from exc
            raise
        if original is not None:
            if digest(request)!=original['request_digest']:raise PermissionError_('permission_revocation_operation_conflict')
            return original['result']
        token=_decode_request(cipher,request,grant_id) if not legacy else None
        detail=await grant_detail_in_snapshot(db,grant_id)
        if not legacy and (detail['source_digest']!=expected_source_digest or detail['grant_device_id']!=grant_device_id):
            raise PermissionError_('permission_revocation_subject_changed')
        if legacy and detail['revoked_at_ms'] is not None:
            raise PermissionError_('permission_revocation_original_identity_required')
        now=int(time.time()*1000)
        deadline=token['expires_at_ms'] if token else received_at+REVOCATION_REQUEST_TTL_MS
        refusal=('permission_revocation_request_expired' if now>=deadline or token and now+30000<token['issued_at_ms'] else
            'permission_revocation_caller_changed' if token and caller!=token['caller_context'] else
            'permission_revocation_stale_revision' if not legacy and detail['source_revision']!=expected_revision else None)
        changed=False;stamp=detail['revoked_at_ms'];reason=detail['revocation_reason']
        if refusal is None and stamp is None:
            now=int(time.time()*1000)
            update=await db.execute("UPDATE permission_grants SET revoked_at_ms=?,revocation_reason='owner revoked' "
                "WHERE grant_id=? AND revoked_at_ms IS NULL AND CAST((julianday('now')-2440587.5)*86400000 AS INTEGER)<?",(now,grant_id,deadline))
            if update.rowcount!=1:refusal='permission_revocation_request_expired'
            else:changed=True;stamp=now;reason='owner revoked'
        result=dict(operation_id=operation_id,grant_id=grant_id,caller_device_id=device_id,grant_device_id=detail['grant_device_id'],
            state='REFUSED' if refusal else 'APPLIED',revoked=False if refusal else True,revoked_at_ms=None if refusal else stamp,
            source_digest=detail['source_digest'],expected_revision=expected_revision,effect_scope=detail['effect_scope'],
            native_authority_issued=False,reason_code=refusal,changed=changed,request_deadline_ms=deadline)
        record=dict(schema=REVOCATION_SCHEMA,grant_id=grant_id,request=request,request_digest=digest(request),
            source_digest=detail['source_digest'],revocation_digest=digest({'revoked_at_ms':stamp,'reason':reason}),result=result)
        await db.execute('INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)',
            (REVOCATION_PREFIX+operation_id,cipher.encrypt(Store.dumps(record).encode()).decode(),now))
        await db.commit()
        return result

async def original_permission_revocation(store,*,operation_id,grant_id,device_id,cipher,access_token_hash=None):
    from van_gateway.capability.permissions import PermissionError_
    async with store.connection() as db:
        await db.execute('BEGIN')
        await _revocation_actor(db,device_id,access_token_hash=access_token_hash)
        record=await _original_revocation(db,operation_id=operation_id,grant_id=grant_id,device_id=device_id,cipher=cipher)
        if record is None:raise PermissionError_('permission_revocation_unknown')
        return record['result']
