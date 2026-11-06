"""LAC-348 supported replacement, retaining the original intent through uncertainty.

Credentials are encrypted with the existing device-secret key. They remain inert until
the original native key and local certificates have independently been retired.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import time
import uuid

from cryptography.fernet import InvalidToken

from van_gateway.auth.device_binding import DeviceBindingError, OWNER_PRINCIPAL
from van_gateway.auth.retirement import retire_device
from van_gateway.connectivity.provisioning import (
    PROVISIONING_TTL_MS, build_provisioning_payload, sign_provisioning_payload,
)

LOG = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class OwnerDeviceReenrollment:
    def __init__(self, *, store, auth, native_revocations, device_ca, connectivity):
        self.store, self.auth = store, auth
        self.native_revocations = native_revocations
        self.device_ca, self.connectivity = device_ca, connectivity

    async def start(self, *, operator_id, reason, operation_id=None, expected_binding_id=None,
                    expected_bound_at_ms=None, gateway_url=None, now_ms=None):
        if not reason.strip() or len(reason) > 1000:
            raise DeviceBindingError("rebind_reason_invalid")
        legacy = operation_id is None
        if legacy:
            if expected_binding_id is not None or expected_bound_at_ms is not None:
                raise DeviceBindingError("rebind_identity_required")
            operation_id = "legacy-" + digest({"operator": operator_id, "owner": OWNER_PRINCIPAL})
        elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{15,127}", operation_id):
            raise DeviceBindingError("rebind_operation_invalid")
        elif not expected_binding_id or type(expected_bound_at_ms) is not int:
            raise DeviceBindingError("rebind_precondition_required")
        request_digest = digest({"operator": operator_id, "owner": OWNER_PRINCIPAL, "reason": reason,
                                 "binding": expected_binding_id, "bound_at_ms": expected_bound_at_ms,
                                 "gateway_url": gateway_url})
        # A replay consumes the protected original response, even after signing rotation.
        existing = await self.store.fetchone("SELECT * FROM owner_device_reenrollments WHERE operation_id=?", (operation_id,))
        if existing is not None:
            if existing["operator_id"] != operator_id or existing["request_digest"] != request_digest:
                raise DeviceBindingError("rebind_operation_conflict")
            if legacy:
                active = await self.store.fetchone("SELECT binding_id FROM owner_device_bindings WHERE owner_principal_id=? AND status='ACTIVE'", (OWNER_PRINCIPAL,))
                if active is not None and active["binding_id"] != existing["original_binding_id"]:
                    raise DeviceBindingError("rebind_identity_required")
            return await self.recover(operation_id=operation_id, operator_id=operator_id, now_ms=now_ms)
        # Encryption/configuration failures precede the retirement transaction.
        cipher = self.auth._cipher()
        now = int(time.time() * 1000) if now_ms is None else now_ms
        token, challenge, pairing = secrets.token_urlsafe(32), secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        envelope = None
        if gateway_url is not None:
            if not self.connectivity.private_pem or not self.connectivity.kid:
                raise DeviceBindingError("connectivity_signing_unconfigured")
            active = await self.connectivity.active()
            payload = build_provisioning_payload(gateway_url=gateway_url, bootstrap_token=token,
                pairing_token=pairing, attestation_challenge=challenge, now_ms=now,
                manifest_version=active.manifest_version if active else 0)
            envelope = {"payload": payload, "signature": sign_provisioning_payload(
                payload, private_pem=self.connectivity.private_pem), "kid": self.connectivity.kid}
        secret = {"bootstrap_token": token, "attestation_challenge": challenge, "envelope": envelope}
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            existing = await (await db.execute(
                "SELECT * FROM owner_device_reenrollments WHERE operation_id=?", (operation_id,)
            )).fetchone()
            if existing is not None:
                if existing["operator_id"] != operator_id or existing["request_digest"] != request_digest:
                    raise DeviceBindingError("rebind_operation_conflict")
                if legacy:
                    active = await (await db.execute(
                        "SELECT binding_id FROM owner_device_bindings WHERE owner_principal_id=? AND status='ACTIVE'",
                        (OWNER_PRINCIPAL,),
                    )).fetchone()
                    if active is not None and active["binding_id"] != existing["original_binding_id"]:
                        raise DeviceBindingError("rebind_identity_required")
                await db.commit()
            else:
                binding = await (await db.execute(
                    "SELECT * FROM owner_device_bindings WHERE owner_principal_id=? AND status='ACTIVE'",
                    (OWNER_PRINCIPAL,),
                )).fetchone()
                if binding is None:
                    raise DeviceBindingError("rebind_original_binding_unavailable")
                if not legacy and (binding["binding_id"] != expected_binding_id
                                   or binding["bound_at_ms"] != expected_bound_at_ms):
                    raise DeviceBindingError("rebind_precondition_failed")
                pending = await (await db.execute(
                    "SELECT operation_id FROM owner_device_reenrollments WHERE owner_principal_id=? AND phase='RETIRING'",
                    (OWNER_PRINCIPAL,),
                )).fetchone()
                if pending is not None:
                    raise DeviceBindingError("rebind_operation_in_progress")
                committed_now = int(time.time() * 1000) if now_ms is None else now_ms
                if now + PROVISIONING_TTL_MS <= committed_now:
                    raise DeviceBindingError("rebind_credential_expired")
                native = await retire_device(db, device_id=binding["device_id"],
                    public_key_pem=binding["public_key_pem"], now_ms=committed_now, reason=reason)
                # Superseded enrollment credentials belong to this owner only.
                await db.execute(
                    "UPDATE owner_device_bootstrap_tokens SET revoked_at_ms=? "
                    "WHERE owner_principal_id=? AND consumed_at_ms IS NULL AND revoked_at_ms IS NULL",
                    (committed_now, OWNER_PRINCIPAL),
                )
                secret["identity"] = {"operation_id":operation_id,"operator_id":operator_id,
                    "owner_principal_id":OWNER_PRINCIPAL,"request_digest":request_digest,
                    "original_binding_id":binding["binding_id"],"original_bound_at_ms":binding["bound_at_ms"],
                    "original_device_id":binding["device_id"],"native_operation_id":native["operation_id"],
                    "created_at_ms":now,"expires_at_ms":now+PROVISIONING_TTL_MS,
                    "reason":reason,"gateway_url":gateway_url,"legacy":int(legacy)}
                secret["native_key_id"] = native["key_id"]
                encrypted = cipher.encrypt(json.dumps(secret, sort_keys=True).encode()).decode()
                await db.execute(
                    "INSERT INTO owner_device_reenrollments(operation_id,operator_id,owner_principal_id,request_digest,"
                    "legacy,original_binding_id,original_bound_at_ms,original_device_id,native_operation_id,phase,"
                    "created_at_ms,expires_at_ms,encrypted_response,bootstrap_token_sha256,pairing_ticket_sha256,"
                    "challenge,gateway_url,reason) VALUES(?,?,?,?,?,?,?,?,?,'RETIRING',?,?,?,?,?,?,?,?)",
                    (operation_id,operator_id,OWNER_PRINCIPAL,request_digest,int(legacy),binding["binding_id"],
                     binding["bound_at_ms"],binding["device_id"],native["operation_id"],now,now+PROVISIONING_TTL_MS,
                     encrypted,hashlib.sha256(token.encode()).hexdigest(),
                     hashlib.sha256(pairing.encode()).hexdigest() if envelope else None,challenge,gateway_url,reason),
                )
                # Audit the original accepted intent in the same writer. Exact
                # retries/readback never create a second rebind event, and a
                # crash cannot commit retirement without its original audit.
                from van_gateway.audit.service import AuditService
                await AuditService(self.store).record_in_transaction(db,
                    result="accepted", device_id=binding["device_id"],
                    capability="device.rebind",
                    after={"operation_id":operation_id,"original_binding_id":binding["binding_id"],
                        "original_bound_at_ms":binding["bound_at_ms"],
                        "native_operation_id":native["operation_id"],"phase":"RETIRING"})
                await db.commit()
                self.auth._device_secrets.pop(binding["device_id"], None)
        return await self.recover(operation_id=operation_id, operator_id=operator_id, now_ms=now_ms)

    async def retire_certificates(self, device_id):
        row = await self.store.fetchone(
            "SELECT * FROM device_certificate_retirements WHERE device_id=?", (device_id,))
        if row is None or row["certificates_retired_at_ms"] is not None:
            return
        ca = self.device_ca()
        if ca is None:
            return  # An unavailable issuer is not authoritative absence.
        count = await asyncio.to_thread(ca.revoke_device, device_id, "owner device retired")
        current = await asyncio.to_thread(ca.listing)
        if any(c.get("device_id") == device_id and not c.get("revoked_at_unix") for c in current):
            return
        await self.store.execute(
            "UPDATE device_certificate_retirements SET certificates_retired_at_ms=? WHERE device_id=?",
            (int(time.time() * 1000),device_id),
        )

        return count

    def _original_secret(self, row):
        try:
            secret = json.loads(self.auth._cipher().decrypt(row["encrypted_response"].encode()))
            identity = secret["identity"]
            keys = ("operation_id","operator_id","owner_principal_id","request_digest","original_binding_id",
                    "original_bound_at_ms","original_device_id","native_operation_id","created_at_ms","expires_at_ms",
                    "reason","gateway_url","legacy")
            if set(identity) != set(keys) or any(identity[k] != row[k] for k in keys):
                raise ValueError("original identity changed")
            if (hashlib.sha256(secret["bootstrap_token"].encode()).hexdigest() != row["bootstrap_token_sha256"]
                    or secret["attestation_challenge"] != row["challenge"]):
                raise ValueError("original credential changed")
            envelope = secret["envelope"]
            if row["gateway_url"] is not None:
                payload = envelope["payload"]
                if (payload["bootstrap_token"] != secret["bootstrap_token"]
                        or payload["attestation_challenge"] != secret["attestation_challenge"]
                        or payload["gateway_url"] != row["gateway_url"].rstrip("/")
                        or payload["issued_at_ms"] != row["created_at_ms"]
                        or payload["expires_at_ms"] != row["expires_at_ms"]
                        or hashlib.sha256(payload["pairing_token"].encode()).hexdigest() != row["pairing_ticket_sha256"]):
                    raise ValueError("original envelope changed")
            elif envelope is not None or row["pairing_ticket_sha256"] is not None:
                raise ValueError("unexpected original envelope")
            return secret
        except (InvalidToken, ValueError, TypeError, KeyError, AttributeError):
            raise DeviceBindingError("rebind_original_response_unavailable") from None

    async def recover(self, *, operation_id, operator_id, now_ms=None, reconcile=True):
        row = await self.store.fetchone("SELECT * FROM owner_device_reenrollments WHERE operation_id=?", (operation_id,))
        if row is None or row["operator_id"] != operator_id:
            raise DeviceBindingError("rebind_operation_unknown")
        secret = self._original_secret(row)  # Verify original identity before either recovery effect.
        if reconcile:
            try:
                await self.retire_certificates(row["original_device_id"])
            except Exception:
                LOG.warning("original device certificate retirement remains pending")
        # Native retirement remains independent of an unavailable local CA/marker.
        try:
            if reconcile:
                await self.native_revocations.reconcile_operation(row["native_operation_id"])
            native = await self.native_revocations.original(row["native_operation_id"])
        except (OSError, ValueError, TypeError):
            native = {"operation_id":row["native_operation_id"],"device_id":row["original_device_id"],
                      "key_id":secret["native_key_id"],"phase":"UNKNOWN","native_result":None}
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT * FROM owner_device_reenrollments WHERE operation_id=?", (operation_id,))).fetchone()
            secret = self._original_secret(row)
            now = int(time.time() * 1000) if now_ms is None else now_ms
            cert = await (await db.execute("SELECT certificates_retired_at_ms FROM device_certificate_retirements WHERE device_id=?",
                (row["original_device_id"],))).fetchone()
            phase = row["phase"]
            if reconcile and phase == "RETIRING" and native["phase"] == "APPLIED" and cert and cert[0] is not None:
                original = await (await db.execute("SELECT status FROM owner_device_bindings WHERE binding_id=?",
                    (row["original_binding_id"],))).fetchone()
                active = await (await db.execute("SELECT binding_id FROM owner_device_bindings WHERE owner_principal_id=? AND status='ACTIVE'",
                    (row["owner_principal_id"],))).fetchone()
                if original is None or original["status"] != "REVOKED" or active is not None:
                    raise DeviceBindingError("rebind_precondition_failed")
                if now >= row["expires_at_ms"]:
                    phase = "EXPIRED"
                else:
                    now = int(time.time() * 1000) if now_ms is None else now_ms
                    if now >= row["expires_at_ms"]:
                        raise DeviceBindingError("rebind_credential_expired")
                    await db.execute(
                        "INSERT INTO owner_device_bootstrap_tokens(token_id,token_sha256,owner_principal_id,challenge,created_at_ms,expires_at_ms,note) "
                        "VALUES(?,?,?,?,?,?,?)", ("boot_"+uuid.uuid4().hex,row["bootstrap_token_sha256"],row["owner_principal_id"],
                        row["challenge"],row["created_at_ms"],row["expires_at_ms"],"rebind: "+row["reason"]),
                    )
                    if row["pairing_ticket_sha256"]:
                        await db.execute("INSERT INTO pairing_tickets(ticket_hash,label,expires_at_unix,created_at_unix) VALUES(?,?,?,?)",
                            (row["pairing_ticket_sha256"],"owner-device",row["expires_at_ms"]//1000,row["created_at_ms"]//1000))
                    phase = "READY"
                await db.execute("UPDATE owner_device_reenrollments SET phase=? WHERE operation_id=?", (phase,operation_id))
            await db.commit()
        response = {"operation_id": operation_id, "phase": phase, "original_binding_id": row["original_binding_id"],
                    "original_device_id": row["original_device_id"], "expires_at_ms": row["expires_at_ms"],
                    "native_authority_revocation": native, "certificates_retired": bool(cert and cert[0] is not None),
                    "bootstrap_token": None, "attestation_challenge": None, "envelope": None}
        if phase == "READY":
            if now >= row["expires_at_ms"]:
                response["phase"] = "EXPIRED"
            else:
                response.update({k:secret[k] for k in ("bootstrap_token","attestation_challenge","envelope")})
        return response

    async def _batch(self, table, identity, predicate, cursor_key):
        cursor = await self.store.fetchone("SELECT value FROM runtime_meta WHERE key=?", (cursor_key,))
        after = cursor["value"] if cursor else ""
        # Table/column/predicate are fixed internal call-site literals, never request input.
        query = f"SELECT * FROM {table} WHERE {predicate} AND {identity}>? ORDER BY {identity} LIMIT 50"
        rows = await self.store.fetchall(query, (after,))
        if not rows and after:
            rows = await self.store.fetchall(query, ("",))
        return rows

    async def _cursor(self, key, value):
        await self.store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
            (key,value,int(time.time()*1000)))

    async def reconcile_once(self):
        cert_cursor = "owner_device_certificate_retirement_cursor_v1"
        certificates = await self._batch("device_certificate_retirements", "device_id",
            "certificates_retired_at_ms IS NULL", cert_cursor)
        for row in certificates:
            try:
                await self.retire_certificates(row["device_id"])
            except Exception:
                LOG.warning("original device certificate retirement remains pending")
            await self._cursor(cert_cursor,row["device_id"])
        cursor = "owner_device_reenrollment_cursor_v1"
        rows = await self._batch("owner_device_reenrollments", "operation_id", "phase='RETIRING'", cursor)
        for row in rows:
            try:
                await self.recover(operation_id=row["operation_id"],operator_id=row["operator_id"])
            except Exception:
                LOG.warning("original owner-device replacement remains pending")
            await self._cursor(cursor,row["operation_id"])

    async def run(self):
        while True:
            try:
                await self.reconcile_once()
            except Exception:
                LOG.warning("owner-device retirement reconciliation is unavailable")
            await asyncio.sleep(5)
