from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from van_gateway.storage.db import Store


class OwnerApprovalError(ValueError):
    pass


@dataclass(frozen=True)
class ApprovalChallenge:
    challenge_id: str
    canonical: str
    expires_at_unix: int


class OwnerApprovalService:
    """One-time A4 owner approvals bound to device, intent, command lineage and turn.

    The Android device signs ``canonical`` with a biometric-bound Android
    Keystore EC key whose public key was enrolled during secure pairing. The
    canonical challenge contains the originating command ID and turn. The client
    may echo the source command ID, but that echo is never treated as authority.
    A challenge is consumed atomically, so it cannot authorize more than one
    execution even if the proof is replayed concurrently.
    """

    PREFIX = "owner_approval:"
    ALGORITHM = "ECDSA_P256_SHA256"
    DEFAULT_TTL_SECONDS = 60

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def intent_digest(*, device_id: str, action_id: str, text: str, project_id: str | None) -> str:
        canonical = "|".join(
            [
                "van-a4-intent-v1",
                device_id,
                action_id,
                project_id or "",
                " ".join(text.split()),
            ]
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def issue(
        self,
        *,
        device_id: str,
        source_command_id: str,
        turn_id: str | None,
        action_id: str,
        text: str,
        project_id: str | None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        now_unix: int | None = None,
    ) -> ApprovalChallenge:
        now = int(time.time()) if now_unix is None else now_unix
        ttl = max(15, min(int(ttl_seconds), 120))
        expires = now + ttl
        challenge_id = secrets.token_urlsafe(24)
        digest = self.intent_digest(
            device_id=device_id,
            action_id=action_id,
            text=text,
            project_id=project_id,
        )
        canonical = "|".join(
            [
                "van-a4-approval-v2",
                challenge_id,
                device_id,
                source_command_id,
                turn_id or "",
                action_id,
                digest,
                str(expires),
            ]
        )
        record = {
            "challenge_id": challenge_id,
            "device_id": device_id,
            "source_command_id": source_command_id,
            "turn_id": turn_id,
            "action_id": action_id,
            "intent_digest": digest,
            "canonical": canonical,
            "expires_at_unix": expires,
            "created_at_unix": now,
        }
        await self.store.execute(
            "INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES (?, ?, ?)",
            (
                self.PREFIX + challenge_id,
                json.dumps(record, sort_keys=True, separators=(",", ":")),
                now * 1000,
            ),
        )
        return ApprovalChallenge(challenge_id, canonical, expires)

    async def verify_and_consume(
        self,
        *,
        challenge_id: str,
        source_command_id: str | None = None,
        signature_b64: str,
        device_id: str,
        turn_id: str | None,
        action_id: str,
        text: str,
        project_id: str | None,
        now_unix: int | None = None,
    ) -> None:
        now = int(time.time()) if now_unix is None else now_unix
        if not challenge_id or not signature_b64:
            raise OwnerApprovalError("approval_proof_missing")

        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                "SELECT value FROM runtime_meta WHERE key = ?",
                (self.PREFIX + challenge_id,),
            )
            row = await cur.fetchone()
            if row is None:
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_unknown_or_consumed")

            try:
                record = json.loads(str(row["value"]))
            except json.JSONDecodeError as exc:
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_corrupt") from exc

            if int(record.get("expires_at_unix", 0)) <= now:
                await db.execute("DELETE FROM runtime_meta WHERE key = ?", (self.PREFIX + challenge_id,))
                await db.commit()
                raise OwnerApprovalError("approval_challenge_expired")
            if (
                record.get("device_id") != device_id
                or record.get("action_id") != action_id
                or record.get("turn_id") != turn_id
                or (
                    source_command_id is not None
                    and record.get("source_command_id") != source_command_id
                )
            ):
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_binding_mismatch")

            expected_digest = self.intent_digest(
                device_id=device_id,
                action_id=action_id,
                text=text,
                project_id=project_id,
            )
            if record.get("intent_digest") != expected_digest:
                await db.rollback()
                raise OwnerApprovalError("approval_intent_mismatch")

            device_cur = await db.execute(
                "SELECT public_key_pem, revoked_at_unix FROM devices WHERE device_id = ?",
                (device_id,),
            )
            device = await device_cur.fetchone()
            if device is None or device["revoked_at_unix"] is not None:
                await db.rollback()
                raise OwnerApprovalError("approval_device_revoked")

            try:
                public_key = serialization.load_pem_public_key(str(device["public_key_pem"]).encode("utf-8"))
            except (ValueError, TypeError) as exc:
                await db.rollback()
                raise OwnerApprovalError("approval_public_key_invalid") from exc
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                await db.rollback()
                raise OwnerApprovalError("approval_public_key_wrong_type")

            try:
                signature = base64.b64decode(signature_b64, validate=True)
                public_key.verify(
                    signature,
                    str(record["canonical"]).encode("utf-8"),
                    ec.ECDSA(hashes.SHA256()),
                )
            except (ValueError, InvalidSignature) as exc:
                await db.rollback()
                raise OwnerApprovalError("approval_signature_invalid") from exc

            deleted = await db.execute(
                "DELETE FROM runtime_meta WHERE key = ?",
                (self.PREFIX + challenge_id,),
            )
            if deleted.rowcount != 1:
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_unknown_or_consumed")
            await db.commit()
