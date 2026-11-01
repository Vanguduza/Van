"""One local writer for device retirement; remote effects retain their own receipts."""
from __future__ import annotations

import json


async def retire_device(db, *, device_id: str, public_key_pem: str, now_ms: int, reason: str):
    """Caller owns BEGIN IMMEDIATE. Never relabel a submitted effect as cancelled."""
    from van_gateway.auth.native_revocation import PREFIX, pending_record, public

    device = await (await db.execute(
        "SELECT public_key_pem, revoked_at_unix FROM devices WHERE device_id=?", (device_id,)
    )).fetchone()
    key = device["public_key_pem"] if device else public_key_pem
    stamp = int(device["revoked_at_unix"]) if device and device["revoked_at_unix"] is not None else now_ms // 1000
    record = pending_record(device_id, key, stamp)
    await db.execute(
        "UPDATE devices SET revoked_at_unix=COALESCE(revoked_at_unix,?) WHERE device_id=?",
        (stamp, device_id),
    )
    await db.execute(
        "UPDATE capability_grants SET revoked_at_unix=? WHERE device_id=? AND revoked_at_unix IS NULL",
        (stamp, device_id),
    )
    await db.execute(
        "UPDATE owner_device_bootstrap_tokens SET revoked_at_ms=? WHERE consumed_at_ms IS NULL AND revoked_at_ms IS NULL "
        "AND owner_principal_id=COALESCE((SELECT owner_principal_id FROM owner_device_bindings WHERE device_id=?),'owner')",
        (now_ms,device_id),
    )
    await db.execute(
        "UPDATE owner_device_bindings SET status='REVOKED',revoked_at_ms=?,revoke_reason=? "
        "WHERE device_id=? AND status='ACTIVE'", (now_ms, reason, device_id),
    )
    from van_gateway.action.service import revoke_privileged_in_transaction
    actions_retired = await revoke_privileged_in_transaction(db, f"device:{device_id}", now_ms)
    await db.execute(
        "UPDATE van_session_paths SET retired_at_ms=COALESCE(retired_at_ms,?) WHERE van_session_id IN "
        "(SELECT van_session_id FROM van_sessions WHERE device_id=?)", (now_ms, device_id),
    )
    await db.execute(
        "UPDATE van_sessions SET state='CLOSED',closed_at_ms=COALESCE(closed_at_ms,?) "
        "WHERE device_id=? AND state='ACTIVE'", (now_ms, device_id),
    )
    await db.execute(
        "INSERT OR IGNORE INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",
        (PREFIX + record["operation_id"], json.dumps(record, sort_keys=True, separators=(",", ":")), now_ms),
    )
    await db.execute(
        "INSERT OR IGNORE INTO device_certificate_retirements(device_id,native_operation_id,requested_at_ms,actions_retired) "
        "VALUES(?,?,?,?)", (device_id, record["operation_id"], now_ms, actions_retired),
    )
    return public(record)


async def require_enrollment_available(db, *, owner_principal_id="owner"):
    row = await (await db.execute(
        "SELECT operation_id FROM owner_device_reenrollments WHERE owner_principal_id=? AND phase='RETIRING'",
        (owner_principal_id,),
    )).fetchone()
    if row is not None:
        from van_gateway.auth.device_binding import DeviceBindingError
        raise DeviceBindingError("device_retirement_pending")
    # Normal device revocation uses the same barrier, even without a replacement intent.
    from van_gateway.auth.native_revocation import NativeOwnerRevocations, PREFIX, pending_record
    retirements = await (await db.execute(
        "SELECT r.certificates_retired_at_ms,r.native_operation_id,m.value FROM device_certificate_retirements r "
        "LEFT JOIN owner_device_bindings b ON b.device_id=r.device_id "
        "LEFT JOIN runtime_meta m ON m.key=?||r.native_operation_id "
        "WHERE COALESCE(b.owner_principal_id,'owner')=?", (PREFIX,owner_principal_id),
    )).fetchall()
    for retirement in retirements:
        try:
            record = json.loads(retirement["value"])
            expected = pending_record(record["device_id"],record["public_key_pem"],record["requested_at_unix"])
            applied = (record["phase"] == "APPLIED" and expected["operation_id"] == retirement["native_operation_id"]
                       and all(record[k] == expected[k] for k in expected if k not in {"phase","native_result"})
                       and NativeOwnerRevocations._matches_native(record,record["native_result"]))
        except (ValueError, TypeError, KeyError):
            applied = False
        if retirement["certificates_retired_at_ms"] is None or not applied:
            from van_gateway.auth.device_binding import DeviceBindingError
            raise DeviceBindingError("device_retirement_pending")



async def require_fresh_approval_key(db, public_key_pem: str):
    """Decoded key identity, so PEM reformatting cannot resurrect a retired owner key."""
    from van_gateway.auth.native_revocation import PREFIX, pending_record
    from van_gateway.auth.service import AuthError
    candidate = pending_record("candidate", public_key_pem, 0)["key_id"]
    if candidate is None:
        return  # Existing legacy enrolment validation retains its own contract.
    rows = await (await db.execute("SELECT value FROM runtime_meta WHERE key GLOB ?", (PREFIX + "*",))).fetchall()
    for row in rows:
        try:
            record = json.loads(row["value"])
            retired = pending_record(record["device_id"], record["public_key_pem"], record["requested_at_unix"])
        except (ValueError, TypeError, KeyError):
            raise AuthError("device_retirement_unavailable", "Owner key retirement history is unavailable") from None
        if any(record[k] != retired[k] for k in retired if k not in {"phase", "native_result"}):
            raise AuthError("device_retirement_unavailable", "Owner key retirement history is unavailable")
        if retired["key_id"] == candidate:
            raise AuthError("device_key_retired", "Retired owner key requires a fresh installation identity")
