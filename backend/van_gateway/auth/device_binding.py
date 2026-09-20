"""Rev 1.5 §§0D.3, 5.7 — exactly one owner device, enforced by the database.

The production build may physically install on another handset; §0D.3 requires it to be
cryptographically non-functional there. That is a server-side fact, not a client-side check,
and it rests on one row: the active binding for this owner, keyed to a public key whose
private half never left the phone's secure hardware.

`uq_active_owner_device` (migration 27) is what makes "exactly one" true under concurrency.
Two enrolments racing do not both succeed and then get reconciled — the second fails at the
database, which is the only place that can answer that question atomically.

Rebinding is deliberately awkward. It is the recovery path for a lost or replaced phone, so
it exists; it revokes the old binding, records why, and is administrative rather than
something the new device can ask for. A rebind a device could perform on its own behalf
would be a way to become the owner's phone by claiming to be it.
"""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass
from enum import Enum

from van_gateway.auth.device_proof import (
    AttestationPolicy,
    AttestationVerdict,
    DeviceProofError,
    key_fingerprint,
    verify_attestation,
    verify_request_proof,
)
from van_gateway.storage.db import Store

#: ADR-RB-026 — single use and short lived. Enrolment happens once, on a bench, with the
#: installer present; an hour is generous for that and far too short to be useful to anyone
#: who finds the token later.
BOOTSTRAP_TTL_MS = 60 * 60_000
OWNER_PRINCIPAL = "owner"


class BindingStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class DeviceBindingError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OwnerDeviceBinding:
    binding_id: str
    owner_principal_id: str
    device_id: str
    device_key_fingerprint: str
    public_key_pem: str
    key_security_level: str
    app_package_name: str
    app_signing_cert_sha256: str
    status: BindingStatus
    bound_at_ms: int
    verified_boot_state: str | None = None
    attestation_root_fingerprint: str | None = None
    os_version: str | None = None
    os_patch_level: str | None = None
    last_proof_at_ms: int | None = None
    revoked_at_ms: int | None = None
    revoke_reason: str | None = None


class OwnerDeviceBindingService:
    def __init__(self, store: Store, policy: AttestationPolicy) -> None:
        self.store = store
        self.policy = policy

    # ------------------------------------------------------------------ bootstrap

    async def create_bootstrap_token(
        self, *, note: str | None = None, now_ms: int | None = None,
        owner_principal_id: str = OWNER_PRINCIPAL,
    ) -> tuple[str, str]:
        """ADR-RB-026 — the installer's one-time credential.

        Returns `(token, challenge)`. Only the hash of the token is stored: a readable
        bootstrap token in the database is a second copy of the one credential that can bind
        a new device, sitting in the file a backup copies.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        token = secrets.token_urlsafe(32)
        challenge = secrets.token_urlsafe(24)
        await self.store.execute(
            """
            INSERT INTO owner_device_bootstrap_tokens(
              token_id, token_sha256, owner_principal_id, challenge,
              created_at_ms, expires_at_ms, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"boot_{uuid.uuid4().hex}", _sha256(token), owner_principal_id, challenge,
                now, now + BOOTSTRAP_TTL_MS, note,
            ),
        )
        return token, challenge

    async def challenge_for(self, token: str, *, now_ms: int | None = None) -> str:
        """The attestation challenge this enrolment must be bound to."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT challenge, expires_at_ms, consumed_at_ms, revoked_at_ms "
            "FROM owner_device_bootstrap_tokens WHERE token_sha256 = ?",
            (_sha256(token),),
        )
        if row is None:
            raise DeviceBindingError("bootstrap_token_unknown")
        if row["consumed_at_ms"] is not None:
            raise DeviceBindingError("bootstrap_token_spent")
        if row["revoked_at_ms"] is not None:
            raise DeviceBindingError("bootstrap_token_revoked")
        if int(row["expires_at_ms"]) <= now:
            raise DeviceBindingError("bootstrap_token_expired")
        return str(row["challenge"])

    # ------------------------------------------------------------------ enrolment

    async def bind(
        self,
        *,
        token: str,
        device_id: str,
        public_key_pem: str,
        attestation_extension: bytes,
        attestation_root_fingerprint: str | None = None,
        os_version: str | None = None,
        os_patch_level: str | None = None,
        owner_principal_id: str = OWNER_PRINCIPAL,
        now_ms: int | None = None,
    ) -> OwnerDeviceBinding:
        """Enrol the owner's device, or refuse and say why.

        Order matters. The attestation is judged before anything is written, and the
        bootstrap token is spent in the same transaction as the binding: a failure between
        them would either burn a token with no device or leave a token that has already
        produced one.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        challenge = await self.challenge_for(token, now_ms=now)

        verdict = verify_attestation(
            extension=attestation_extension,
            challenge=challenge.encode("utf-8"),
            policy=self.policy,
            root_fingerprint=attestation_root_fingerprint,
        )
        await self._record_attestation(device_id, challenge, verdict, os_version,
                                       os_patch_level, attestation_root_fingerprint, now)
        if not verdict.accepted or verdict.facts is None:
            # §0E.1 D5 — a failed attestation blocks enrolment. There is no downgrade to
            # model-name or bearer-token binding, because that is the binding §0D.3 rules out.
            raise DeviceBindingError(verdict.refusal or "attestation_refused")

        fingerprint = key_fingerprint(public_key_pem)
        binding_id = f"bind_{uuid.uuid4().hex}"
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE owner_device_bootstrap_tokens
                   SET consumed_at_ms = ?, consumed_by_device_id = ?
                 WHERE token_sha256 = ? AND consumed_at_ms IS NULL
                """,
                (now, device_id, _sha256(token)),
            )
            if cur.rowcount != 1:
                await db.rollback()
                raise DeviceBindingError("bootstrap_token_spent")
            try:
                await db.execute(
                    """
                    INSERT INTO owner_device_bindings(
                      binding_id, owner_principal_id, device_id, device_key_fingerprint,
                      public_key_pem, key_security_level, app_package_name,
                      app_signing_cert_sha256, attestation_root_fingerprint,
                      verified_boot_state, os_version, os_patch_level, status, bound_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        binding_id, owner_principal_id, device_id, fingerprint,
                        public_key_pem, verdict.facts.attestation_security_level.value,
                        verdict.facts.package_name, verdict.facts.signing_cert_sha256,
                        attestation_root_fingerprint,
                        verdict.facts.verified_boot_state.value
                        if verdict.facts.verified_boot_state else None,
                        os_version, os_patch_level, BindingStatus.ACTIVE.value, now,
                    ),
                )
            except Exception as exc:
                await db.rollback()
                # The partial unique index. A second phone enrolling while one is active
                # fails here rather than becoming a second owner device.
                raise DeviceBindingError("owner_device_already_bound") from exc
            await db.commit()

        bound = await self.active(owner_principal_id)
        assert bound is not None
        return bound

    async def active(
        self, owner_principal_id: str = OWNER_PRINCIPAL
    ) -> OwnerDeviceBinding | None:
        row = await self.store.fetchone(
            "SELECT * FROM owner_device_bindings WHERE owner_principal_id = ? AND status = ?",
            (owner_principal_id, BindingStatus.ACTIVE.value),
        )
        return None if row is None else _row_to_binding(row)

    async def for_device(self, device_id: str) -> OwnerDeviceBinding | None:
        row = await self.store.fetchone(
            "SELECT * FROM owner_device_bindings WHERE device_id = ?", (device_id,)
        )
        return None if row is None else _row_to_binding(row)

    # ------------------------------------------------------------------ proof

    async def require_proof(
        self,
        *,
        device_id: str,
        signature: bytes,
        method: str,
        path: str,
        issued_at_ms: int,
        body: bytes,
        now_ms: int | None = None,
    ) -> OwnerDeviceBinding:
        """ADR-RB-025 — every privileged request proves possession of the bound key."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        binding = await self.for_device(device_id)
        if binding is None:
            raise DeviceBindingError("device_not_bound")
        if binding.status is not BindingStatus.ACTIVE:
            raise DeviceBindingError("device_binding_revoked")
        try:
            verify_request_proof(
                public_key_pem=binding.public_key_pem, signature=signature, method=method,
                path=path, device_id=device_id, issued_at_ms=issued_at_ms, body=body,
                now_ms=now,
            )
        except DeviceProofError as exc:
            raise DeviceBindingError(exc.reason) from exc
        await self.store.execute(
            "UPDATE owner_device_bindings SET last_proof_at_ms = ? WHERE binding_id = ?",
            (now, binding.binding_id),
        )
        return binding

    # ------------------------------------------------------------------ recovery

    async def revoke(
        self, *, owner_principal_id: str = OWNER_PRINCIPAL, reason: str,
        now_ms: int | None = None,
    ) -> None:
        """Administrative. The device cannot revoke itself into replaceability."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            UPDATE owner_device_bindings
               SET status = ?, revoked_at_ms = ?, revoke_reason = ?
             WHERE owner_principal_id = ? AND status = ?
            """,
            (BindingStatus.REVOKED.value, now, reason, owner_principal_id,
             BindingStatus.ACTIVE.value),
        )

    async def rebind_token(
        self, *, reason: str, owner_principal_id: str = OWNER_PRINCIPAL,
        now_ms: int | None = None,
    ) -> tuple[str, str]:
        """§0D.3's recovery: revoke, then issue one bootstrap token for the new phone.

        Both halves in one call, because a revoke without a way back is how an owner ends
        up locked out of their own assistant, and a token issued without a revoke would
        mean two phones could be bound at once — which the database would refuse anyway,
        confusingly, at the last possible moment.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.revoke(owner_principal_id=owner_principal_id, reason=reason, now_ms=now)
        return await self.create_bootstrap_token(
            note=f"rebind: {reason}", now_ms=now, owner_principal_id=owner_principal_id
        )

    # ------------------------------------------------------------------ internals

    async def _record_attestation(
        self, device_id: str, challenge: str, verdict: AttestationVerdict,
        os_version: str | None, os_patch_level: str | None,
        root_fingerprint: str | None, now: int,
    ) -> None:
        """Every attempt, accepted or not. The refusals are the interesting rows."""
        facts = verdict.facts
        await self.store.execute(
            """
            INSERT INTO device_attestation_events(
              event_id, device_id, challenge, outcome, refusal_reason, key_security_level,
              verified_boot_state, attestation_root_fingerprint, app_package_name,
              app_signing_cert_sha256, os_version, os_patch_level, occurred_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"att_{uuid.uuid4().hex}", device_id, challenge,
                "ACCEPTED" if verdict.accepted else "REFUSED", verdict.refusal,
                facts.attestation_security_level.value if facts else None,
                facts.verified_boot_state.value if facts and facts.verified_boot_state else None,
                root_fingerprint,
                facts.package_name if facts else None,
                facts.signing_cert_sha256 if facts else None,
                os_version, os_patch_level, now,
            ),
        )


def _row_to_binding(row) -> OwnerDeviceBinding:
    return OwnerDeviceBinding(
        binding_id=row["binding_id"],
        owner_principal_id=row["owner_principal_id"],
        device_id=row["device_id"],
        device_key_fingerprint=row["device_key_fingerprint"],
        public_key_pem=row["public_key_pem"],
        key_security_level=row["key_security_level"],
        app_package_name=row["app_package_name"],
        app_signing_cert_sha256=row["app_signing_cert_sha256"],
        status=BindingStatus(row["status"]),
        bound_at_ms=int(row["bound_at_ms"]),
        verified_boot_state=row["verified_boot_state"],
        attestation_root_fingerprint=row["attestation_root_fingerprint"],
        os_version=row["os_version"],
        os_patch_level=row["os_patch_level"],
        last_proof_at_ms=int(row["last_proof_at_ms"]) if row["last_proof_at_ms"] else None,
        revoked_at_ms=int(row["revoked_at_ms"]) if row["revoked_at_ms"] else None,
        revoke_reason=row["revoke_reason"],
    )


def _sha256(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()
