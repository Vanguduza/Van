from __future__ import annotations

import hashlib
import hmac
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


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
        # Persist a non-reversible verifier for diagnostics/rotation evidence only.
        secret_hash = hashlib.sha256(device_secret.encode("utf-8")).hexdigest()
        await self.store.execute(
            "INSERT INTO capability_grants(grant_id, device_id, capabilities_json, expires_at_unix, task_id, revoked_at_unix, created_at_unix) VALUES (?, ?, ?, ?, NULL, NULL, ?)",
            (f"enroll-{device_id}", device_id, Store.dumps({"secret_sha256": secret_hash, "capabilities": ["owner"]}), now + 10 * 365 * 24 * 3600, now),
        )
        return DeviceRecord(device_id, public_key_pem, now, None, label)

    def remember_secret(self, device_id: str, device_secret: str) -> None:
        """Test/recovery helper; production restart restoration uses encrypted DB state."""
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
