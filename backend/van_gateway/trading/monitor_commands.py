"""Signed alert controls over the existing monitor CAS and durable receipt protocol.

These commands change owner alert configuration only. Verification describes the
original control, even if a later command or observation changed the alert again.
"""
from __future__ import annotations

import hashlib
import re

from van_gateway.command.authority import AuthoritySource, CommandAuthorityService
from van_gateway.models import ActionClass, PrincipalType
from .monitor_models import MonitorControl, MonitorWrite
from .monitor_service import MonitorError, digest


ACTIONS = {"trading.alert.pause": "PAUSE", "trading.alert.restart": "RESTART",
           "trading.alert.delete": "DELETE"}
STATUSES = {"PAUSE": "PAUSED", "RESTART": "RESTARTED", "DELETE": "DELETED"}
MAX_AGE_SECONDS = 30


def parameters(value):
    if (not isinstance(value, dict) or set(value) != {"alert_id", "expected_revision"}
            or not isinstance(value["alert_id"], str)
            or re.fullmatch(r"mal_[0-9a-f]{32}", value["alert_id"]) is None
            or type(value["expected_revision"]) is not int
            or not 1 <= value["expected_revision"] < 2**63-1):
        raise ValueError("alert_control_exact_parameters_required")
    return dict(value)


def request_id(command_id):
    if not isinstance(command_id, str) or not command_id or len(command_id) > 256:
        raise ValueError("alert_control_original_command_required")
    return "mcmd_" + hashlib.sha256(command_id.encode()).hexdigest()


async def sealed_control(store, command_id, *, device_id=None, submitted=None):
    record = await CommandAuthorityService(store).get(command_id)
    if (record is None or record.command_id != command_id or record.authority_source is not AuthoritySource.OWNER_COMMAND
            or record.principal_type is not PrincipalType.OWNER_DEVICE
            or record.effective_action_class is not ActionClass.A2
            or record.typed_action_id not in ACTIONS
            or (device_id is not None and record.device_id != device_id)):
        raise ValueError("alert_control_owner_authority_required")
    pinned = parameters(record.typed_parameter_constraints)
    if submitted is not None and parameters(submitted) != pinned:
        raise ValueError("alert_control_sealed_parameters_mismatch")
    body = MonitorControl(request_id=request_id(command_id), expected_revision=pinned["expected_revision"])
    return record, pinned, body


async def control_readback(store, command_id):
    record, pinned, body = await sealed_control(store, command_id)
    operation = ACTIONS[record.typed_action_id]
    row = await store.fetchone(
        "SELECT request_sha256,result_json FROM market_monitor_operations WHERE owner_id=? AND request_id=?",
        ("owner", body.request_id))
    expected_hash = digest({"kind": "ALERT", "operation": operation,
                            "object_id": pinned["alert_id"], "body": body.model_dump(mode="json")})
    if row is None or row["request_sha256"] != expected_hash:
        raise ValueError("alert_control_receipt_missing_or_conflicting")
    receipt = MonitorWrite.model_validate_json(row["result_json"], strict=True)
    state_hash_valid = (receipt.state_sha256 is None if operation == "DELETE" else
        isinstance(receipt.state_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", receipt.state_sha256) is not None)
    if (receipt.request_id != body.request_id or receipt.object_id != pinned["alert_id"]
            or receipt.kind != "ALERT" or type(receipt.revision) is not int
            or receipt.revision != pinned["expected_revision"]+1
            or receipt.status != STATUSES[operation] or not state_hash_valid):
        raise ValueError("alert_control_receipt_integrity_failed")
    return {**pinned, "action_id": record.typed_action_id, "control_status": receipt.status,
            "control_revision": str(receipt.revision), "control_completed": True,
            "authority_effect": "NONE", "request_id": body.request_id,
            "evidence_ref": "market-monitor-operation://"+body.request_id}


async def execute_control(ctx):
    # Imports stay local so local_executors need not import the trading package at startup.
    from van_gateway.command.local_executors import LocalExecutionError, LocalExecutionResult

    if ctx.market_monitors is None:
        raise LocalExecutionError("market_monitors_unavailable", "Alert controls are unavailable", status="degraded")
    try:
        record, pinned, body = await sealed_control(ctx.store, ctx.command_id,
            device_id=ctx.device_id, submitted=ctx.parameters)
    except Exception as exc:
        raise LocalExecutionError("alert_control_owner_authority_required", "An exact sealed owner alert command is required") from exc
    expires = (record.issued_at_unix + MAX_AGE_SECONDS)*1000
    if record.expires_at_unix is not None:
        expires = min(expires, record.expires_at_unix*1000)
    try:
        await ctx.market_monitors.write("owner", "ALERT", ACTIONS[record.typed_action_id], body,
            pinned["alert_id"], expires_at_ms=expires)
    except MonitorError as exc:
        raise LocalExecutionError(exc.code, "Alert control refused: "+exc.code,
            status="degraded" if exc.status >= 500 else "denied") from exc
    except Exception as exc:
        raise LocalExecutionError("alert_control_write_unavailable", "Alert control outcome requires receipt recovery",
            status="degraded") from exc
    try:
        observed = await control_readback(ctx.store, ctx.command_id)
    except Exception as exc:
        raise LocalExecutionError("alert_control_readback_unavailable", "Alert control could not be independently verified",
            status="degraded") from exc
    return LocalExecutionResult(
        summary=f"Alert {pinned['alert_id']}: {observed['control_status'].lower()} control recorded at revision {observed['control_revision']}.",
        evidence_ref=observed["evidence_ref"], observed_postcondition=observed)
