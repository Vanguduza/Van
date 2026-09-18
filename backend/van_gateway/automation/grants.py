"""Rev 1.3 §§160-161, 412 — short-lived run capability grants and durable replay protection.

A run grant is **worker scope, never the source of owner authority**. Before one
can be minted the Gateway must already hold either a live owner-command
``CommandAuthorityRecord`` or a per-run record derived from a
``StandingAutomationAuthority``. The grant then narrows what the worker may ask
the Gateway to do; it can never widen it.

Replay protection is durable by construction: §412 states plainly that
"no in-memory-only replay protection is acceptable". Consumption is a single
conditional ``UPDATE`` whose affected row count must be exactly one, so two
concurrent redemptions of the same mutation nonce cannot both succeed even
across processes, and a consumed nonce cannot be resurrected by a restart.

n8n never receives a general-purpose VAN internal token — only a MAC-bound
grant scoped to one run, one artifact version, one context snapshot and one
input digest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.models import ActionClass
from van_gateway.storage.db import Store

_RANK = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}


class GrantKind(str, Enum):
    #: One mutation, one redemption. The canonical consequential-effect grant.
    SINGLE_USE_MUTATION = "SINGLE_USE_MUTATION"
    #: Bounded read-only session: several Gateway reads under one run, counted.
    BOUNDED_READ_SESSION = "BOUNDED_READ_SESSION"


class GrantDenied(ValueError):
    """403 CAPABILITY_GRANT_DENIED with a structured internal reason (§161)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CapabilityGrant(BaseModel):
    """The grant handed to a worker. ``secret`` is returned once and never stored."""

    grant_id: str
    run_id: str
    command_id: str
    standing_authority_id: str | None = None
    capability_id: str
    artifact_id: str
    artifact_version: int
    allowed_gateway_operations: list[str] = Field(default_factory=list)
    allowed_external_domains: list[str] = Field(default_factory=list)
    action_class_ceiling: ActionClass
    input_digest: str
    context_snapshot_id: str
    grant_kind: GrantKind
    max_uses: int
    issued_at_ms: int
    expires_at_ms: int

    def canonical(self) -> str:
        """Stable MAC input. Every field the Gateway later re-verifies appears here."""
        payload = {
            "v": "van-capability-grant-v1",
            "grant_id": self.grant_id,
            "run_id": self.run_id,
            "command_id": self.command_id,
            "standing_authority_id": self.standing_authority_id,
            "capability_id": self.capability_id,
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "allowed_gateway_operations": sorted(self.allowed_gateway_operations),
            "allowed_external_domains": sorted(self.allowed_external_domains),
            "action_class_ceiling": self.action_class_ceiling.value,
            "input_digest": self.input_digest,
            "context_snapshot_id": self.context_snapshot_id,
            "grant_kind": self.grant_kind.value,
            "max_uses": self.max_uses,
            "issued_at_ms": self.issued_at_ms,
            "expires_at_ms": self.expires_at_ms,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class MintedGrant(BaseModel):
    """What the Gateway hands the dispatcher: the grant plus its one-time token."""

    grant: CapabilityGrant
    #: ``<nonce>.<mac>`` — opaque to the worker, never persisted in clear.
    token: str


class RunGrantService:
    """Mints, validates and atomically consumes run capability grants."""

    DEFAULT_TTL_SECONDS = 300

    def __init__(self, store: Store, *, signing_key: str) -> None:
        self.store = store
        self._signing_key = (signing_key or "").encode("utf-8")

    # ------------------------------------------------------------------ crypto

    @property
    def configured(self) -> bool:
        return bool(self._signing_key)

    @staticmethod
    def hash_nonce(nonce: str) -> str:
        return hashlib.sha256(nonce.encode("utf-8")).hexdigest()

    def _mac(self, nonce: str, canonical: str) -> str:
        return hmac.new(
            self._signing_key, f"{nonce}|{canonical}".encode("utf-8"), hashlib.sha256
        ).hexdigest()

    # -------------------------------------------------------------------- mint

    async def mint(
        self,
        *,
        run_id: str,
        command_id: str,
        capability_id: str,
        artifact_id: str,
        artifact_version: int,
        context_snapshot_id: str,
        input_digest: str,
        action_class_ceiling: ActionClass,
        allowed_gateway_operations: list[str],
        allowed_external_domains: list[str],
        grant_kind: GrantKind = GrantKind.SINGLE_USE_MUTATION,
        max_uses: int = 1,
        standing_authority_id: str | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        now_ms: int | None = None,
    ) -> MintedGrant:
        if not self.configured:
            # Fail closed: without a signing key no grant can be verified later.
            raise GrantDenied("GRANT_SIGNING_KEY_UNCONFIGURED")
        if action_class_ceiling in (ActionClass.A4, ActionClass.A5):
            # §160: a run grant never carries A4. A4 needs a fresh owner approval
            # bound to the exact action, and A5 is always denied.
            raise GrantDenied("GRANT_ACTION_CLASS_PROHIBITED")

        now = int(time.time() * 1000) if now_ms is None else now_ms
        uses = 1 if grant_kind is GrantKind.SINGLE_USE_MUTATION else max(1, int(max_uses))
        grant = CapabilityGrant(
            grant_id=f"grant_{uuid.uuid4().hex}",
            run_id=run_id,
            command_id=command_id,
            standing_authority_id=standing_authority_id,
            capability_id=capability_id,
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            allowed_gateway_operations=sorted(allowed_gateway_operations),
            allowed_external_domains=sorted(allowed_external_domains),
            action_class_ceiling=action_class_ceiling,
            input_digest=input_digest,
            context_snapshot_id=context_snapshot_id,
            grant_kind=grant_kind,
            max_uses=uses,
            issued_at_ms=now,
            expires_at_ms=now + max(30, int(ttl_seconds)) * 1000,
        )
        nonce = secrets.token_urlsafe(32)
        nonce_hash = self.hash_nonce(nonce)
        await self.store.execute(
            """
            INSERT INTO automation_run_nonces(
              nonce_hash, grant_id, run_id, command_id, capability_id, artifact_id,
              artifact_version, standing_authority_id, context_snapshot_id, input_digest,
              action_class_ceiling, allowed_operations_json, allowed_domains_json, grant_kind,
              max_uses, use_count, status, issued_at_ms, expires_at_ms, consumed_at_ms, revoked_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'ISSUED', ?, ?, NULL, NULL)
            """,
            (
                nonce_hash, grant.grant_id, grant.run_id, grant.command_id, grant.capability_id,
                grant.artifact_id, grant.artifact_version, grant.standing_authority_id,
                grant.context_snapshot_id, grant.input_digest, grant.action_class_ceiling.value,
                Store.dumps(grant.allowed_gateway_operations), Store.dumps(grant.allowed_external_domains),
                grant.grant_kind.value, grant.max_uses, grant.issued_at_ms, grant.expires_at_ms,
            ),
        )
        return MintedGrant(grant=grant, token=f"{nonce}.{self._mac(nonce, grant.canonical())}")

    # ---------------------------------------------------------------- redeem

    async def redeem(
        self,
        *,
        token: str,
        grant: CapabilityGrant,
        requested_operation: str,
        requested_action_class: ActionClass,
        requested_domain: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """Run the full §161 checklist and atomically consume/advance the nonce.

        Every failure raises :class:`GrantDenied` with the structured reason the
        caller maps to ``403 CAPABILITY_GRANT_DENIED``.
        """
        if not self.configured:
            raise GrantDenied("GRANT_SIGNING_KEY_UNCONFIGURED")
        now = int(time.time() * 1000) if now_ms is None else now_ms

        # 1. signature/MAC
        nonce, _, presented_mac = token.partition(".")
        if not nonce or not presented_mac:
            raise GrantDenied("GRANT_MALFORMED")
        if not hmac.compare_digest(self._mac(nonce, grant.canonical()), presented_mac):
            raise GrantDenied("GRANT_SIGNATURE_INVALID")

        nonce_hash = self.hash_nonce(nonce)
        row = await self.store.fetchone(
            "SELECT * FROM automation_run_nonces WHERE nonce_hash = ?", (nonce_hash,)
        )
        if row is None:
            raise GrantDenied("GRANT_REPLAYED")

        # 2-9. scope binding, checked before any state change.
        if str(row["grant_id"]) != grant.grant_id or str(row["run_id"]) != grant.run_id:
            raise GrantDenied("GRANT_SCOPE_MISMATCH")
        if str(row["capability_id"]) != grant.capability_id:
            raise GrantDenied("GRANT_SCOPE_MISMATCH")
        if str(row["artifact_id"]) != grant.artifact_id or int(row["artifact_version"]) != grant.artifact_version:
            raise GrantDenied("ARTIFACT_VERSION_MISMATCH")
        if str(row["context_snapshot_id"]) != grant.context_snapshot_id:
            raise GrantDenied("CONTEXT_BINDING_MISMATCH")
        if str(row["input_digest"]) != grant.input_digest:
            raise GrantDenied("GRANT_SCOPE_MISMATCH")
        if requested_operation not in json.loads(row["allowed_operations_json"] or "[]"):
            raise GrantDenied("GRANT_SCOPE_MISMATCH")
        ceiling = ActionClass(str(row["action_class_ceiling"]))
        if _RANK[requested_action_class] > _RANK[ceiling]:
            raise GrantDenied("GRANT_SCOPE_MISMATCH")
        if requested_domain is not None:
            allowed = json.loads(row["allowed_domains_json"] or "[]")
            if requested_domain not in allowed:
                raise GrantDenied("GRANT_SCOPE_MISMATCH")
        if row["revoked_at_ms"] is not None:
            raise GrantDenied("SOURCE_AUTHORITY_REVOKED")
        if int(row["expires_at_ms"]) <= now:
            raise GrantDenied("GRANT_EXPIRED")

        # 10-11. the source authority and its owner device must still be live.
        await self._assert_source_authority_live(str(row["command_id"]), row["standing_authority_id"], now)

        # 12. atomically consume or advance.
        if GrantKind(str(row["grant_kind"])) is GrantKind.SINGLE_USE_MUTATION:
            await self._consume_single_use(nonce_hash, now)
        else:
            await self._advance_bounded(nonce_hash, now)

    async def _consume_single_use(self, nonce_hash: str, now: int) -> None:
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE automation_run_nonces
                SET consumed_at_ms = ?, status = 'CONSUMED', use_count = use_count + 1
                WHERE nonce_hash = ?
                  AND consumed_at_ms IS NULL
                  AND revoked_at_ms IS NULL
                  AND expires_at_ms > ?
                  AND status = 'ISSUED'
                """,
                (now, nonce_hash, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise GrantDenied("GRANT_REPLAYED")

    async def _advance_bounded(self, nonce_hash: str, now: int) -> None:
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE automation_run_nonces
                SET use_count = use_count + 1,
                    status = CASE WHEN use_count + 1 >= max_uses THEN 'CONSUMED' ELSE 'ISSUED' END,
                    consumed_at_ms = CASE WHEN use_count + 1 >= max_uses THEN ? ELSE NULL END
                WHERE nonce_hash = ?
                  AND revoked_at_ms IS NULL
                  AND expires_at_ms > ?
                  AND status = 'ISSUED'
                  AND use_count < max_uses
                """,
                (now, nonce_hash, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise GrantDenied("GRANT_REPLAYED")

    async def _assert_source_authority_live(
        self, command_id: str, standing_authority_id: Any, now: int
    ) -> None:
        record = await self.store.fetchone(
            "SELECT value FROM runtime_meta WHERE key = ?", (f"command_authority:{command_id}",)
        )
        if record is None:
            raise GrantDenied("SOURCE_AUTHORITY_REVOKED")
        authority = json.loads(str(record["value"]))

        device = await self.store.fetchone(
            "SELECT revoked_at_unix FROM devices WHERE device_id = ?", (authority.get("device_id"),)
        )
        if device is None or device["revoked_at_unix"] is not None:
            raise GrantDenied("SOURCE_DEVICE_REVOKED")

        if standing_authority_id is not None:
            standing = await self.store.fetchone(
                "SELECT revoked_at_ms, expires_at_ms FROM standing_automation_authorities "
                "WHERE authority_id = ?",
                (str(standing_authority_id),),
            )
            if standing is None or standing["revoked_at_ms"] is not None:
                raise GrantDenied("SOURCE_AUTHORITY_REVOKED")
            if standing["expires_at_ms"] is not None and now >= int(standing["expires_at_ms"]):
                raise GrantDenied("SOURCE_AUTHORITY_REVOKED")

    # ------------------------------------------------------------------ revoke

    async def revoke_run(self, run_id: str, *, now_ms: int | None = None) -> int:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE automation_run_nonces SET revoked_at_ms = ?, status = 'REVOKED' "
                "WHERE run_id = ? AND revoked_at_ms IS NULL AND consumed_at_ms IS NULL",
                (now, run_id),
            )
            await db.commit()
            return int(cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0)


__all__ = ["CapabilityGrant", "GrantDenied", "GrantKind", "MintedGrant", "RunGrantService"]
