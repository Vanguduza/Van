"""Read-only installer receipt; neither device logs nor declared paths prove admission."""
from __future__ import annotations

import hashlib
import json
import time

from van_gateway.auth.device_binding import DeviceBindingError
from van_gateway.storage.db import Store


async def provisioning_status(store: Store, bootstrap_token: str, device_ca, *, now_ms: int | None = None) -> dict:
    now = int(time.time() * 1000) if now_ms is None else now_ms
    token = await store.fetchone(
        "SELECT * FROM owner_device_bootstrap_tokens WHERE token_sha256 = ?",
        (hashlib.sha256(bootstrap_token.encode()).hexdigest(),),
    )
    if token is None:
        raise DeviceBindingError("bootstrap_token_unknown")
    steps = {"binding": False, "pairing": False, "tls_certificate": False, "session_admitted": False}
    result = {"state": "NEEDS_BINDING", "steps": steps, "observed_at_ms": now,
              "transport_receipt": None, "owner_e2e_verified": False, "hermes_verified": False}
    if token["revoked_at_ms"] is not None:
        return {**result, "state": "REVOKED"}
    if token["consumed_at_ms"] is None:
        if int(token["expires_at_ms"]) <= now:
            result["state"] = "EXPIRED"
        return result
    device_id = token["consumed_by_device_id"]
    result["device_id"] = device_id
    binding = await store.fetchone(
        "SELECT * FROM owner_device_bindings WHERE owner_principal_id = ? "
        "AND device_id = ? AND status = 'ACTIVE'",
        (token["owner_principal_id"], device_id),
    )
    if binding is None:
        return {**result, "state": "REVOKED"}
    if not binding["attestation_chain_verified"]:
        return {**result, "state": "NEEDS_CERTIFICATION"}
    steps["binding"] = True
    paired = await store.fetchone(
        "SELECT public_key_pem, access_token_hash FROM devices WHERE device_id = ? "
        "AND revoked_at_unix IS NULL", (device_id,),
    )
    grant = await store.fetchone(
        "SELECT grant_id FROM capability_grants WHERE device_id = ? "
        "AND revoked_at_unix IS NULL AND expires_at_unix > ? LIMIT 1", (device_id, now // 1000),
    )
    if (paired is None or not paired["access_token_hash"] or grant is None
            or paired["public_key_pem"] != binding["public_key_pem"]):
        return {**result, "state": "NEEDS_PAIRING"}
    steps["pairing"] = True
    certificates = device_ca.listing() if device_ca is not None else []
    admitted_serials = {c["serial"] for c in certificates if c.get("device_id") == device_id
                        and not c.get("revoked_at_unix") and int(c.get("not_after_unix", 0)) > now // 1000}
    if not admitted_serials:
        return {**result, "state": "NEEDS_TLS_CERTIFICATE"}
    steps["tls_certificate"] = True
    # Admission is recorded by the actual WebSocket handler after accept, never inferred
    # from session/open or the handset's requested path. A renewed/revoked certificate
    # cannot reuse an old admission receipt.
    receipts = await store.fetchall(
        "SELECT id, after_json, created_at_unix FROM audit WHERE device_id = ? "
        "AND capability = 'session.transport.admitted' AND result = 'accepted' "
        "AND created_at_unix >= ? ORDER BY chain_seq DESC LIMIT 100",
        (device_id, int(token["created_at_ms"]) // 1000),
    )
    for receipt in receipts:
        try:
            after = json.loads(receipt["after_json"] or "{}")
        except (ValueError, TypeError):
            continue
        if (after.get("binding_id") != binding["binding_id"] or after.get("certified_matching") is not True
                or after.get("certificate_serial") not in admitted_serials):
            continue
        session = await store.fetchone(
            "SELECT state FROM van_sessions WHERE van_session_id = ? AND device_id = ?",
            (after.get("van_session_id"), device_id),
        )
        if session is None or session["state"] != "ACTIVE":
            continue
        steps["session_admitted"] = True
        result["state"] = "SESSION_ADMITTED"
        result["transport_receipt"] = {
            "audit_id": receipt["id"], "van_session_id": after["van_session_id"],
            "transport": after.get("transport"), "observed_at_ms": int(receipt["created_at_unix"]) * 1000,
            "currently_connected_verified": False,
        }
        return result
    return {**result, "state": "NEEDS_SESSION_ADMISSION"}
