from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from van_gateway.storage.db import Store


@dataclass
class DeviceRecord:
    device_id: str
    public_key_pem: str
    enrolled_at_unix: int
    revoked_at_unix: int | None
    label: str | None


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AuthService:
    """Device enrollment + HMAC request authentication.

    Production devices enroll once with a device secret. Requests carry
    HMAC-SHA256(signature) over canonical payload. Revoked devices fail closed.
    """

    def __init__(self, store: Store) -> None:
        self.store = store
        self._device_secrets: dict[str, bytes] = {}

    async def enroll(self, device_id: str, device_secret: str, public_key_pem: str, label: str | None = None) -> DeviceRecord:
        existing = await self.store.fetchone("SELECT device_id, revoked_at_unix FROM devices WHERE device_id = ?", (device_id,))
        if existing is not None:
            if existing["revoked_at_unix"] is not None:
                raise AuthError("device_revoked", "Device was revoked; re-enrollment denied")
            raise AuthError("already_enrolled", "Device already enrolled")
        now = int(time.time())
        await self.store.execute(
            "INSERT INTO devices(device_id, public_key_pem, enrolled_at_unix, revoked_at_unix, label) VALUES (?, ?, ?, NULL, ?)",
            (device_id, public_key_pem, now, label),
        )
        self._device_secrets[device_id] = device_secret.encode("utf-8")
        # Persist secret hash only (never store raw secret in audit tables)
        secret_hash = hashlib.sha256(device_secret.encode("utf-8")).hexdigest()
        await self.store.execute(
            "INSERT INTO capability_grants(grant_id, device_id, capabilities_json, expires_at_unix, task_id, revoked_at_unix, created_at_unix) VALUES (?, ?, ?, ?, NULL, NULL, ?)",
            (f"enroll-{device_id}", device_id, Store.dumps({"secret_sha256": secret_hash, "capabilities": ["owner"]}), now + 10 * 365 * 24 * 3600, now),
        )
        return DeviceRecord(device_id, public_key_pem, now, None, label)

    def remember_secret(self, device_id: str, device_secret: str) -> None:
        self._device_secrets[device_id] = device_secret.encode("utf-8")

    async def revoke(self, device_id: str) -> None:
        now = int(time.time())
        row = await self.store.fetchone("SELECT device_id FROM devices WHERE device_id = ?", (device_id,))
        if row is None:
            raise AuthError("unknown_device", "Device not found")
        await self.store.execute(
            "UPDATE devices SET revoked_at_unix = ? WHERE device_id = ?",
            (now, device_id),
        )
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
