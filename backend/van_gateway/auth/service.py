from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from van_gateway.storage.db import Store


@dataclass
class DeviceRecord:
    device_id: str
    public_key_pem: str
    enrolled_at_unix: int
    revoked_at_unix: int | None
    label: str | None


@dataclass
class PairingTicket:
    token: str
    expires_at_unix: int
    label: str | None


@dataclass
class PairingResult:
    device: DeviceRecord
    access_token: str


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#: P2-SEC-008. Enrolment grants were minted with a ten-year expiry, which is a standing
#: grant with a number attached. A year is long enough that a device the owner uses is
#: never inconvenienced and short enough that one they forgot about stops working.
ENROLMENT_GRANT_SECONDS = 365 * 24 * 3600

#: How long before expiry a grant should be renewed. Renewal is the reason an expiry is
#: safe to set: without one, the only options are ten years or breaking the owner's phone.
GRANT_RENEWAL_WINDOW_SECONDS = 30 * 24 * 3600


class AuthService:
    """Device enrollment + restart-durable HMAC request authentication.

    Device HMAC secrets are encrypted at rest with a dedicated Fernet key and
    rehydrated into process memory at startup. Raw secrets never enter audit or
    capability tables. Revoked devices are never rehydrated.
    """

    def __init__(self, store: Store, secret_fernet_key: str = "") -> None:
        self.store = store
        self._device_secrets: dict[str, bytes] = {}
        self._fernet: Fernet | None = None
        if secret_fernet_key:
            try:
                self._fernet = Fernet(secret_fernet_key.encode("utf-8"))
            except (ValueError, TypeError) as exc:
                raise AuthError("device_secret_cipher_invalid", "Device secret encryption key is invalid") from exc

    def _cipher(self) -> Fernet:
        if self._fernet is None:
            raise AuthError(
                "device_secret_encryption_unconfigured",
                "Device secret encryption is not configured; refusing device authentication",
            )
        return self._fernet

    async def load_persisted_secrets(self) -> int:
        rows = await self.store.fetchall(
            "SELECT device_id, encrypted_secret FROM devices WHERE revoked_at_unix IS NULL AND encrypted_secret IS NOT NULL"
        )
        self._device_secrets.clear()
        if not rows:
            return 0
        cipher = self._cipher()
        for row in rows:
            ciphertext = str(row["encrypted_secret"] or "")
            if not ciphertext:
                continue
            try:
                secret = cipher.decrypt(ciphertext.encode("utf-8"))
            except InvalidToken as exc:
                raise AuthError(
                    "device_secret_decryption_failed",
                    f"Encrypted credential for device {row['device_id']} cannot be decrypted",
                ) from exc
            self._device_secrets[str(row["device_id"])] = secret
        return len(self._device_secrets)

    async def create_pairing_ticket(
        self,
        label: str | None = None,
        ttl_seconds: int = 600,
    ) -> PairingTicket:
        ttl = max(60, min(int(ttl_seconds), 3600))
        token = secrets.token_urlsafe(32)
        ticket_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = int(time.time())
        expires = now + ttl
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            if label is None:
                await db.execute(
                    "UPDATE pairing_tickets SET used_at_unix = ? WHERE used_at_unix IS NULL AND expires_at_unix >= ?",
                    (now, now),
                )
            else:
                await db.execute(
                    "UPDATE pairing_tickets SET used_at_unix = ? WHERE label = ? AND used_at_unix IS NULL AND expires_at_unix >= ?",
                    (now, label, now),
                )
            await db.execute(
                "INSERT INTO pairing_tickets(ticket_hash, label, expires_at_unix, used_at_unix, created_at_unix) VALUES (?, ?, ?, NULL, ?)",
                (ticket_hash, label, expires, now),
            )
            await db.commit()
        return PairingTicket(token=token, expires_at_unix=expires, label=label)

    async def pair_device(
        self,
        pairing_token: str,
        device_id: str,
        device_secret: str,
        public_key_pem: str,
        label: str | None = None,
    ) -> PairingResult:
        if not pairing_token:
            raise AuthError("pairing_ticket_invalid", "Pairing ticket invalid or expired")
        cipher = self._cipher()
        encrypted_secret = cipher.encrypt(device_secret.encode("utf-8")).decode("utf-8")
        secret_hash = hashlib.sha256(device_secret.encode("utf-8")).hexdigest()
        access_token = secrets.token_urlsafe(32)
        access_token_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
        ticket_hash = hashlib.sha256(pairing_token.encode("utf-8")).hexdigest()
        now = int(time.time())
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT label, expires_at_unix, used_at_unix FROM pairing_tickets WHERE ticket_hash = ?",
                (ticket_hash,),
            )
            ticket = await cur.fetchone()
            if ticket is None or ticket["used_at_unix"] is not None or int(ticket["expires_at_unix"]) <= now:
                await db.rollback()
                raise AuthError("pairing_ticket_invalid", "Pairing ticket invalid or expired")
            cur = await db.execute(
                "SELECT device_id, revoked_at_unix FROM devices WHERE device_id = ?",
                (device_id,),
            )
            existing = await cur.fetchone()
            if existing is not None:
                await db.rollback()
                code = "device_revoked" if existing["revoked_at_unix"] is not None else "already_enrolled"
                raise AuthError(code, "Device cannot be enrolled")
            effective_label = label or ticket["label"]
            await db.execute(
                "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix, revoked_at_unix, label, encrypted_secret, access_token_hash) VALUES (?, ?, ?, NULL, ?, ?, ?)",
                (device_id, public_key_pem, now, effective_label, encrypted_secret, access_token_hash),
            )
            await db.execute(
                "INSERT INTO capability_grants(grant_id, device_id, capabilities_json, expires_at_unix, task_id, revoked_at_unix, created_at_unix) VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                (
                    f"enroll-{device_id}",
                    device_id,
                    Store.dumps({"secret_sha256": secret_hash, "capabilities": ["owner"]}),
                    now + ENROLMENT_GRANT_SECONDS,
                    now,
                ),
            )
            await db.execute(
                "UPDATE pairing_tickets SET used_at_unix = ? WHERE ticket_hash = ? AND used_at_unix IS NULL",
                (now, ticket_hash),
            )
            await db.commit()
        self._device_secrets[device_id] = device_secret.encode("utf-8")
        return PairingResult(DeviceRecord(device_id, public_key_pem, now, None, effective_label), access_token)

    async def require_access_token(self, access_token: str) -> DeviceRecord:
        if not access_token:
            raise AuthError("device_access_denied", "Device access token invalid or revoked")
        digest = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
        row = await self.store.fetchone(
            "SELECT device_id, public_key_pem, enrolled_at_unix, revoked_at_unix, label FROM devices WHERE access_token_hash = ? AND revoked_at_unix IS NULL",
            (digest,),
        )
        if row is None:
            raise AuthError("device_access_denied", "Device access token invalid or revoked")
        return DeviceRecord(row["device_id"], row["public_key_pem"], int(row["enrolled_at_unix"]), None, row["label"])

    async def enroll(self, device_id: str, device_secret: str, public_key_pem: str, label: str | None = None) -> DeviceRecord:
        existing = await self.store.fetchone("SELECT device_id, revoked_at_unix FROM devices WHERE device_id = ?", (device_id,))
        if existing is not None:
            if existing["revoked_at_unix"] is not None:
                raise AuthError("device_revoked", "Device was revoked; re-enrollment denied")
            raise AuthError("already_enrolled", "Device already enrolled")
        cipher = self._cipher()
        encrypted_secret = cipher.encrypt(device_secret.encode("utf-8")).decode("utf-8")
        now = int(time.time())
        await self.store.execute(
            "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix, revoked_at_unix, label, encrypted_secret) VALUES (?, ?, ?, NULL, ?, ?)",
            (device_id, public_key_pem, now, label, encrypted_secret),
        )
        self._device_secrets[device_id] = device_secret.encode("utf-8")
        secret_hash = hashlib.sha256(device_secret.encode("utf-8")).hexdigest()
        await self.store.execute(
            "INSERT INTO capability_grants(grant_id, device_id, capabilities_json, expires_at_unix, task_id, revoked_at_unix, created_at_unix) VALUES (?, ?, ?, ?, NULL, NULL, ?)",
            (f"enroll-{device_id}", device_id, Store.dumps({"secret_sha256": secret_hash, "capabilities": ["owner"]}), now + ENROLMENT_GRANT_SECONDS, now),
        )
        return DeviceRecord(device_id, public_key_pem, now, None, label)

    async def grant_status(self, device_id: str, *, now: int | None = None) -> dict:
        """Where this device's enrolment grant stands: valid, due for renewal, or expired.

        P2-SEC-008 — nothing expired and nothing was rotated, so there was nothing to
        report. An expiry the owner cannot see coming is an outage waiting to happen.
        """
        stamp = int(time.time()) if now is None else now
        row = await self.store.fetchone(
            "SELECT expires_at_unix, revoked_at_unix, created_at_unix FROM capability_grants "
            "WHERE grant_id = ?",
            (f"enroll-{device_id}",),
        )
        if row is None:
            return {"device_id": device_id, "state": "ABSENT", "expires_at_unix": None}
        if row["revoked_at_unix"] is not None:
            return {"device_id": device_id, "state": "REVOKED", "expires_at_unix": int(row["expires_at_unix"])}
        expires = int(row["expires_at_unix"])
        remaining = expires - stamp
        if remaining <= 0:
            state = "EXPIRED"
        elif remaining <= GRANT_RENEWAL_WINDOW_SECONDS:
            state = "RENEW_SOON"
        else:
            state = "VALID"
        return {
            "device_id": device_id,
            "state": state,
            "expires_at_unix": expires,
            "seconds_remaining": max(0, remaining),
            "renew_within_seconds": GRANT_RENEWAL_WINDOW_SECONDS,
        }

    async def renew_grant(self, device_id: str, *, now: int | None = None) -> dict:
        """Extend a live enrolment grant. Refuses a revoked or expired one.

        An expired grant is deliberately not renewable: re-pairing is the path back, and
        silently reviving a grant the owner let lapse would make the expiry decorative.
        """
        stamp = int(time.time()) if now is None else now
        status = await self.grant_status(device_id, now=stamp)
        if status["state"] in {"ABSENT", "REVOKED", "EXPIRED"}:
            raise AuthError(
                "grant_not_renewable",
                f"enrolment grant for {device_id} is {status['state']}; pair the device again",
            )
        await self.store.execute(
            "UPDATE capability_grants SET expires_at_unix = ? WHERE grant_id = ? "
            "AND revoked_at_unix IS NULL",
            (stamp + ENROLMENT_GRANT_SECONDS, f"enroll-{device_id}"),
        )
        return await self.grant_status(device_id, now=stamp)

    async def expiring_grants(self, *, now: int | None = None) -> list[dict]:
        """Every live grant that is expired or due for renewal, for the degraded surface."""
        stamp = int(time.time()) if now is None else now
        rows = await self.store.fetchall(
            "SELECT grant_id, device_id, expires_at_unix FROM capability_grants "
            "WHERE revoked_at_unix IS NULL AND expires_at_unix <= ? ORDER BY expires_at_unix",
            (stamp + GRANT_RENEWAL_WINDOW_SECONDS,),
        )
        return [await self.grant_status(str(r["device_id"]), now=stamp) for r in rows]

    def remember_secret(self, device_id: str, device_secret: str) -> None:
        """Test/recovery helper; production restart restoration uses encrypted DB state."""
        self._device_secrets[device_id] = device_secret.encode("utf-8")

    async def revoke(self, device_id: str) -> None:
        now = int(time.time())
        row = await self.store.fetchone("SELECT device_id FROM devices WHERE device_id = ?", (device_id,))
        if row is None:
            raise AuthError("unknown_device", "Device not found")
        async with self.store.connection() as db:
            await db.execute(
                "UPDATE capability_grants SET revoked_at_unix = ? WHERE device_id = ? AND revoked_at_unix IS NULL",
                (now, device_id),
            )
            await db.execute(
                "UPDATE devices SET revoked_at_unix = ? WHERE device_id = ?",
                (now, device_id),
            )
            await db.commit()
        self._device_secrets.pop(device_id, None)

    async def require_device(self, device_id: str) -> DeviceRecord:
        row = await self.store.fetchone(
            "SELECT device_id, public_key_pem, enrolled_at_unix, revoked_at_unix, label FROM devices WHERE device_id = ?",
            (device_id,),
        )
        if row is None:
            raise AuthError("unknown_device", "Device not enrolled")
        if row["revoked_at_unix"] is not None:
            raise AuthError("device_revoked", "Device revoked")
        return DeviceRecord(
            row["device_id"],
            row["public_key_pem"],
            int(row["enrolled_at_unix"]),
            int(row["revoked_at_unix"]) if row["revoked_at_unix"] is not None else None,
            row["label"],
        )

    def sign(self, device_id: str, canonical: str) -> str:
        secret = self._device_secrets.get(device_id)
        if secret is None:
            raise AuthError("secret_unavailable", "Device secret not loaded in gateway process")
        return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_signature(self, device_id: str, canonical: str, signature: str) -> None:
        expected = self.sign(device_id, canonical)
        if not hmac.compare_digest(expected, signature):
            raise AuthError("bad_signature", "Request signature invalid")

    @staticmethod
    def canonical_command(
        command_id: str,
        idempotency_key: str,
        device_id: str,
        issued_at_unix: int,
        text: str,
        action_class: str,
        project_id: str | None,
    ) -> str:
        """Legacy v1 canonical form retained only for default-provenance clients."""
        return "|".join(
            [
                command_id,
                idempotency_key,
                device_id,
                str(issued_at_unix),
                action_class,
                project_id or "",
                text,
            ]
        )

    @staticmethod
    def canonical_command_v3(
        *,
        command_id: str,
        idempotency_key: str,
        device_id: str,
        issued_at_unix: int,
        text: str,
        action_class: str,
        project_id: str | None,
        turn_id: str | None,
        origin_channel: str,
        principal_type: str,
        requested_by: str,
        expires_at_unix: int | None,
        nonce: str | None,
        context_capsule_revision: int | None,
        context_capsule_hash: str | None,
        speech_evidence_ref: str | None,
        speaker_evidence_milli: int | None,
        no_stale_replay: bool,
        context_trust: str,
    ) -> str:
        """Voice-aware authority envelope with deterministic fixed-point speaker evidence.

        v2 is retained byte-for-byte for existing clients. v3 adds only the signed
        speaker-evidence field; omitting it is still meaningful (UNAVAILABLE) and therefore
        cannot be rewritten in transit into a positive owner-speaker claim.
        """
        return "|".join(
            [
                "v3",
                command_id,
                idempotency_key,
                device_id,
                str(issued_at_unix),
                action_class,
                project_id or "",
                turn_id or "",
                origin_channel,
                principal_type,
                requested_by,
                str(expires_at_unix) if expires_at_unix is not None else "",
                nonce or "",
                str(context_capsule_revision) if context_capsule_revision is not None else "",
                context_capsule_hash or "",
                speech_evidence_ref or "",
                str(speaker_evidence_milli) if speaker_evidence_milli is not None else "",
                "1" if no_stale_replay else "0",
                context_trust,
                text,
            ]
        )

    @staticmethod
    def canonical_command_v2(
        *,
        command_id: str,
        idempotency_key: str,
        device_id: str,
        issued_at_unix: int,
        text: str,
        action_class: str,
        project_id: str | None,
        turn_id: str | None,
        origin_channel: str,
        principal_type: str,
        requested_by: str,
        expires_at_unix: int | None,
        nonce: str | None,
        context_capsule_revision: int | None,
        context_capsule_hash: str | None,
        speech_evidence_ref: str | None,
        no_stale_replay: bool,
        context_trust: str,
    ) -> str:
        """Rev 3.1 authority-bearing canonical form.

        Every field that can change provenance, privilege, replay behavior or
        context binding is covered by the device HMAC. ``client_context`` is
        deliberately excluded because it is a non-authoritative hint only.
        """
        return "|".join(
            [
                "v2",
                command_id,
                idempotency_key,
                device_id,
                str(issued_at_unix),
                action_class,
                project_id or "",
                turn_id or "",
                origin_channel,
                principal_type,
                requested_by,
                str(expires_at_unix) if expires_at_unix is not None else "",
                nonce or "",
                str(context_capsule_revision) if context_capsule_revision is not None else "",
                context_capsule_hash or "",
                speech_evidence_ref or "",
                "1" if no_stale_replay else "0",
                context_trust,
                text,
            ]
        )
