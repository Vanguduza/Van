"""Bounded owner-approved autonomy ceilings and command-bound target readback.

This changes only the domain trust ceiling. It creates no action, standing
policy, capability permission, or permission to bypass native A4 approval.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from van_gateway.command.authority import AuthoritySource, CommandAuthorityRecord, CommandAuthorityService
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.proactive.autonomy import AutonomyLevel, _domain_for
from van_gateway.storage.db import Store

ACTION_ID = "owner.autonomy.ceiling.set"
COMMAND_PREFIX = "set domain autonomy ceiling "
SUPPORTED_LEVELS = tuple(f"S{ordinal}" for ordinal in range(5))
WITNESS_PREFIX = "domain_autonomy_witness:"
CURRENT_PREFIX = "domain_autonomy_current:"


class DomainCeilingDenied(ValueError):
    """A named refusal before a ceiling is changed."""


def ceiling_parameters(parameters: Any) -> dict[str, str]:
    """Closed parameter contract, with no wildcard or unlimited domain/level."""
    if not isinstance(parameters, dict) or set(parameters) != {"domain", "level"}:
        raise ValueError("domain_ceiling_exact_parameters_required")
    domain, level = parameters["domain"], parameters["level"]
    if (not isinstance(domain, str) or len(domain) > 128
            or not re.fullmatch(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*){0,7}", domain)):
        raise ValueError("domain_ceiling_domain_invalid")
    if not isinstance(level, str) or level not in SUPPORTED_LEVELS:
        raise ValueError("domain_ceiling_level_invalid")
    return {"domain": domain, "level": level}


async def _known_domains(db: Any) -> list[str]:
    actions = await (await db.execute("SELECT action_id FROM action_definitions")).fetchall()
    records = await (await db.execute("SELECT domain FROM domain_trust")).fetchall()
    names = {_domain_for(str(row["action_id"])) for row in actions}
    names.update(str(row["domain"]) for row in records)
    # Legacy records can remain visible in the original read surface without
    # admitting malformed/new wildcard authority through this writer.
    return sorted(name for name in names if re.fullmatch(
        r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*){0,7}", name) and len(name) <= 128)


async def known_autonomy_domains(store: Store) -> list[str]:
    async with store.connection() as db:
        return await _known_domains(db)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _bound(authority: CommandAuthorityRecord | None, *, command_id: str,
           device_id: str, parameters: dict[str, str]) -> bool:
    return bool(authority and authority.command_id == command_id
        and authority.authority_source is AuthoritySource.OWNER_COMMAND
        and authority.principal_type is PrincipalType.OWNER_DEVICE
        and authority.device_id == device_id and authority.owner_approved
        and authority.effective_action_class is ActionClass.A4
        and authority.typed_action_id == ACTION_ID
        and authority.typed_parameter_constraints == parameters
        and authority.no_stale_replay and authority.expires_at_unix is not None)


async def set_owner_domain_ceiling(store: Store, parameters: dict[str, str],
                                   command_id: str, *, device_id: str) -> None:
    """Recheck owner authority under the same lock as grant+witness commit.

    Re-entering this operation never reapplies its ceiling, including after a
    newer owner command lowers it. Lost responses are recovered by readback.
    """
    parameters = ceiling_parameters(parameters)
    domain, level = parameters["domain"], parameters["level"]
    async with store.connection() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            sealed = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?",
                (CommandAuthorityService.PREFIX + command_id,))).fetchone()
            authority = CommandAuthorityRecord.model_validate_json(sealed["value"]) if sealed else None
            if not _bound(authority, command_id=command_id, device_id=device_id, parameters=parameters):
                raise DomainCeilingDenied("domain_ceiling_fresh_owner_approval_required")
            now = _now_ms()
            if now // 1000 >= authority.expires_at_unix or now // 1000 - authority.issued_at_unix > 30:
                raise DomainCeilingDenied("domain_ceiling_authority_expired")
            device = await (await db.execute("SELECT revoked_at_unix FROM devices WHERE device_id=?", (device_id,))).fetchone()
            if device is None or device["revoked_at_unix"] is not None:
                raise DomainCeilingDenied("domain_ceiling_device_revoked")
            mission = await (await db.execute("SELECT state FROM missions WHERE "
                "json_extract(authority_envelope_json,'$.source_command_id')=?", (command_id,))).fetchone()
            if mission is None or mission["state"] != "RUNNING":
                raise DomainCeilingDenied("domain_ceiling_command_not_running")
            if domain not in await _known_domains(db):
                raise DomainCeilingDenied("domain_ceiling_domain_not_registered")
            existing = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?",
                (WITNESS_PREFIX + command_id,))).fetchone()
            if existing:
                witness = json.loads(existing["value"])
                if any(witness.get(key) != value for key, value in
                       {**parameters, "command_id": command_id, "device_id": device_id}.items()):
                    raise DomainCeilingDenied("domain_ceiling_operation_conflict")
                await db.rollback()
                return
            before = await (await db.execute("SELECT owner_granted_ceiling FROM domain_trust WHERE domain=?", (domain,))).fetchone()
            witness = {"schema_version": 1, **parameters, "command_id": command_id,
                "device_id": device_id, "previous_level": before["owner_granted_ceiling"] if before else None,
                "changed_at_ms": now}
            await db.execute("INSERT INTO domain_trust(domain,owner_granted_ceiling,updated_at_ms) VALUES(?,?,?) "
                "ON CONFLICT(domain) DO UPDATE SET owner_granted_ceiling=excluded.owner_granted_ceiling,"
                "updated_at_ms=excluded.updated_at_ms", (domain, level, now))
            # The materialized display ceiling must retain evidence suspension.
            row = await (await db.execute("SELECT * FROM domain_trust WHERE domain=?", (domain,))).fetchone()
            from van_gateway.proactive.autonomy import DomainTrust

            trust = DomainTrust(domain=domain, owner_granted_ceiling=AutonomyLevel(level),
                **{name: int(row[name]) for name in ("verified_successes", "meaningful_failures", "false_successes", "owner_overrides", "recovery_successes")})
            await db.execute("UPDATE domain_trust SET current_autonomy_ceiling=? WHERE domain=?",
                (trust.effective_ceiling.value, domain))
            for key in (WITNESS_PREFIX + command_id, CURRENT_PREFIX + domain):
                await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
                    (key, Store.dumps(witness), now))
            if _now_ms() // 1000 >= authority.expires_at_unix:
                raise DomainCeilingDenied("domain_ceiling_authority_expired")
        except BaseException:
            await db.rollback()
            raise
        await db.commit()


async def domain_ceiling_readback(store: Store, parameters: dict[str, str], command_id: str) -> dict[str, Any]:
    """Observe current committed target and the exact approved owner operation.

    Expiration blocks a new effect, but does not erase evidence of a committed
    effect. An older command cannot certify or reapply a newer owner's choice.
    """
    parameters = ceiling_parameters(parameters)
    authority = await CommandAuthorityService(store).get(command_id)
    async with store.connection() as db:
        await db.execute("BEGIN")
        row = await (await db.execute("SELECT owner_granted_ceiling FROM domain_trust WHERE domain=?",
            (parameters["domain"],))).fetchone()
        stored = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?", (WITNESS_PREFIX + command_id,))).fetchone()
        current = await (await db.execute("SELECT value FROM runtime_meta WHERE key=?", (CURRENT_PREFIX + parameters["domain"],))).fetchone()
        witness = json.loads(stored["value"]) if stored else {}
        latest = json.loads(current["value"]) if current else {}
    bound = bool(_bound(authority, command_id=command_id,
        device_id=str(witness.get("device_id") or ""), parameters=parameters)
        and witness.get("schema_version") == 1
        and isinstance(witness.get("changed_at_ms"), int)
        and all(witness.get(k) == v for k, v in {**parameters, "command_id": command_id}.items()))
    observed = {**parameters, "owner_granted_ceiling": row["owner_granted_ceiling"] if row else None,
        "owner_approved_command_bound": bound, "current_owner_operation_matches": bool(bound and latest == witness)}
    if (bound and observed["current_owner_operation_matches"]
            and observed["owner_granted_ceiling"] == parameters["level"]):
        observed["evidence_refs"] = [f"domain-autonomy://{command_id}"]
    return observed
