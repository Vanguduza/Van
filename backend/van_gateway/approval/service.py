from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

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
    INTENT_SCHEMA = "van-a4-intent-json-v2"

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def intent_digest(*, device_id: str, action_id: str, text: str, project_id: str | None,
                      parameters: dict[str, Any] | None = None) -> str:
        # The digest is opaque to the device, which signs the unchanged v2
        # challenge. Structured encoding prevents text/project/parameter pipes
        # from moving field boundaries inside this hash.
        canonical = json.dumps([OwnerApprovalService.INTENT_SCHEMA, device_id, action_id,
                                project_id, " ".join(text.split()), parameters],
                               sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _legacy_intent_digest(*, device_id: str, action_id: str, text: str, project_id: str | None,
                              parameters: dict[str, Any] | None = None) -> str:
        canonical = "|".join(
            [
                "van-a4-intent-v1",
                device_id,
                action_id,
                project_id or "",
                " ".join(text.split()),
            ]
        )
        if parameters is not None:
            # Text can resolve differently after a resolver/configuration update.
            # The owner's biometric proof also binds the exact displayed values.
            canonical += "|" + json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_challenge(*, challenge_id, device_id, source_command_id, turn_id,
                             action_id, intent_digest, expires_at_unix):
        fields = [challenge_id, device_id, source_command_id, turn_id or "", action_id, intent_digest]
        if ((turn_id is not None and not isinstance(turn_id, str))
                or any(not isinstance(value, str) or "|" in value or any(ord(c)<32 or ord(c)==127 for c in value)
                for value in fields) or any(not fields[i] for i in (0,1,2,4,5))
                or type(expires_at_unix) is not int):
            raise OwnerApprovalError("approval_challenge_binding_corrupt")
        return "|".join(["van-a4-approval-v2", *fields, str(expires_at_unix)])

    async def issue(
        self,
        *,
        device_id: str,
        source_command_id: str,
        turn_id: str | None,
        action_id: str,
        text: str,
        project_id: str | None,
        parameters: dict[str, Any] | None = None,
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
            parameters=parameters,
        )
        canonical = self._canonical_challenge(challenge_id=challenge_id, device_id=device_id,
            source_command_id=source_command_id, turn_id=turn_id, action_id=action_id,
            intent_digest=digest, expires_at_unix=expires)
        record = {
            "challenge_id": challenge_id,
            "device_id": device_id,
            "source_command_id": source_command_id,
            "turn_id": turn_id,
            "action_id": action_id,
            "intent_digest": digest,
            "intent_digest_schema": self.INTENT_SCHEMA,
            "parameters_bound": parameters is not None,
            "parameters": parameters,
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

    async def _require_unexpired(self, db, record, challenge_id, now_unix):
        # One predicate owns both fresh checks. It is read after acquiring the
        # SQL writer and again after key/proof work; neither wait renews consent.
        now = int(time.time()) if now_unix is None else now_unix
        if int(record.get("expires_at_unix", 0)) <= now:
            await db.execute("DELETE FROM runtime_meta WHERE key = ?", (self.PREFIX + challenge_id,))
            await db.commit()
            raise OwnerApprovalError("approval_challenge_expired")
        return now

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
        parameters: dict[str, Any] | None = None,
        now_unix: int | None = None,
        durable_receipt: dict[str, Any] | None = None,
    ) -> dict:
        if not challenge_id or not signature_b64:
            raise OwnerApprovalError("approval_proof_missing")

        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            # The SQL writer may have waited behind another transaction. The
            # original owner deadline must not be extended by that queue.
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

            now = await self._require_unexpired(db, record, challenge_id, now_unix)
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

            if (record.get("parameters_bound") and
                record.get("parameters") != parameters):
                await db.rollback()
                raise OwnerApprovalError("approval_parameters_changed")
            schema = record.get("intent_digest_schema", "van-a4-intent-v1")
            if (not isinstance(schema, str) or schema not in {self.INTENT_SCHEMA, "van-a4-intent-v1"}
                    or type(record.get("parameters_bound", False)) is not bool):
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_binding_corrupt")
            legacy_recovery = (
                action_id in {"trading.runtime.clear_kill_switch", "trading.runtime.reset_loss_streak",
                              "trading.runtime.resume_drawdown"}
                and project_id is None and turn_id is None and parameters is None
                and record.get("parameters") is None and record.get("parameters_bound", False) is False
                and record.get("source_command_id") == "runtime:" + action_id.rsplit(".", 1)[-1]
                and re.fullmatch(r"trading-runtime-control\|[0-9a-f]{64}", text) is not None
            )
            if schema == "van-a4-intent-v1" and not legacy_recovery and any("|" in value for value in
                    (device_id, action_id, project_id or "", text)):
                # Old short-lived challenges keep their original encoding only
                # when it is unambiguous. Request a fresh proof for other text.
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_binding_corrupt")
            digest = self.intent_digest if schema == self.INTENT_SCHEMA else self._legacy_intent_digest
            expected_digest = digest(
                device_id=device_id,
                action_id=action_id,
                text=text,
                project_id=project_id,
                parameters=parameters if record.get("parameters_bound") else None,
            )
            if parameters is not None and not record.get("parameters_bound"):
                await db.rollback()
                raise OwnerApprovalError("approval_parameters_not_bound")
            if record.get("intent_digest") != expected_digest:
                await db.rollback()
                raise OwnerApprovalError("approval_intent_mismatch")

            try:
                expected_canonical = self._canonical_challenge(challenge_id=challenge_id,
                    device_id=device_id, source_command_id=record.get("source_command_id"), turn_id=turn_id,
                    action_id=action_id, intent_digest=expected_digest,
                    expires_at_unix=record.get("expires_at_unix"))
                if (record.get("challenge_id") != challenge_id or record.get("canonical") != expected_canonical):
                    raise OwnerApprovalError("approval_challenge_binding_corrupt")
            except OwnerApprovalError:
                await db.rollback()
                raise

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

            # Reading the enrolled device and checking its proof can cross the
            # same deadline too. Consume only within the original half-open
            # window, including when a durable recovery receipt is requested.
            now = await self._require_unexpired(db, record, challenge_id, now_unix)

            deleted = await db.execute(
                "DELETE FROM runtime_meta WHERE key = ?",
                (self.PREFIX + challenge_id,),
            )
            if deleted.rowcount != 1:
                await db.rollback()
                raise OwnerApprovalError("approval_challenge_unknown_or_consumed")
            if durable_receipt is not None:
                # A verified recovery dispatch may lose its HTTP response, or
                # the process may stop before contacting the native journal.
                # Persist its public exact-operation proof in this SAME commit
                # as consumption. This contains no bearer/private signing key.
                receipt = {"operation_id": challenge_id, "device_id": device_id,
                    "expires_at_unix": int(record["expires_at_unix"]),
                    "intent_digest": expected_digest, "context": durable_receipt}
                await db.execute(
                    "INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)",
                    ("owner_approval_receipt:" + challenge_id,
                     json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False), now*1000))
            await db.commit()
            # Non-secret attestation for the already verified, consumed act.
            # This return value never permits consuming the approval twice.
            return {"operation_id": challenge_id, "device_id": device_id,
                    "authority_ref": hashlib.sha256(str(record["canonical"]).encode()).hexdigest(),
                    "expires_at_unix": int(record["expires_at_unix"])}
