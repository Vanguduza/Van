"""Rev 1 §§34, 36 — the owner-readable permission registry.

§36's list is short and entirely about visibility: grant, origin, expiry, last
use, revoke control. The reason each matters is that a standing permission is
the one kind of authority that accumulates silently — nobody notices the grant
they gave once, eighteen months ago, to something they no longer use.

So `last_used_at_ms` and `use_count` are not telemetry. They are what lets the
owner see that VAN still holds mail-send authority it has not exercised since
March, which is the question a permissions screen exists to answer.

§36's three prohibitions are enforced structurally rather than documented:
no raw provider tokens reach this table, no cookie material does, and a grant
with no stated origin cannot be created — a permission whose provenance nobody
recorded is indistinguishable from one VAN gave itself.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from van_gateway.storage.db import Store


class PermissionOrigin(str, Enum):
    """Where a grant came from. There is no "unknown"."""

    OWNER_DECISION = "OWNER_DECISION"
    OWNER_DEVICE_PAIRING = "OWNER_DEVICE_PAIRING"
    OAUTH_CONSENT = "OAUTH_CONSENT"
    STANDING_AUTOMATION = "STANDING_AUTOMATION"
    PROACTIVE_POLICY = "PROACTIVE_POLICY"


#: §36's examples, as a closed set so the screen can be exhaustive.
KNOWN_PERMISSIONS = {
    "email.read": "Read your email",
    "email.send": "Send email as you",
    "calendar.read": "Read your calendar",
    "calendar.write": "Change your calendar",
    "browser.authenticated_session": "Use a signed-in browser session",
    "github.write": "Push to your repositories",
    "github.merge": "Merge pull requests",
    "computer.remote": "Control a remote computer",
    "trading.read": "Read your trading state",
    "vati.execute": "Place trades through VATI",
}

#: §36 — "No raw provider tokens to Android. No cookie export." A grant that
#: carries credential-shaped material is refused rather than stored and hidden,
#: because a secret in a table the owner can read is a secret on the owner's
#: phone.
_SECRET_SHAPED = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._-]{12,}|ya29\.[A-Za-z0-9._-]+|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|cookie\s*[:=]|set-cookie|refresh_token|access_token\s*[:=]|-----BEGIN)"
)


class PermissionError_(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class PermissionGrant:
    grant_id: str
    permission: str
    display_name: str
    scope: str
    origin: PermissionOrigin
    origin_evidence_ref: str | None
    granted_at_ms: int
    expires_at_ms: int | None
    last_used_at_ms: int | None
    use_count: int
    revoked_at_ms: int | None

    def is_live(self, now_ms: int) -> bool:
        if self.revoked_at_ms is not None:
            return False
        return self.expires_at_ms is None or self.expires_at_ms > now_ms

    def unused_since_ms(self, now_ms: int) -> int:
        """How long VAN has held this without needing it."""
        return now_ms - (self.last_used_at_ms or self.granted_at_ms)


class PermissionRegistry:
    """One place the owner can see and revoke everything VAN may do."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def grant(
        self,
        *,
        permission: str,
        origin: PermissionOrigin,
        origin_evidence_ref: str,
        scope: str = "",
        expires_at_ms: int | None = None,
        now_ms: int | None = None,
    ) -> PermissionGrant:
        if permission not in KNOWN_PERMISSIONS:
            # An unlisted permission cannot be displayed meaningfully, and a
            # permissions screen that says "other" is not a permissions screen.
            raise PermissionError_("PERMISSION_UNKNOWN", permission)
        if not origin_evidence_ref:
            raise PermissionError_("PERMISSION_ORIGIN_REQUIRED", permission)
        for field in (scope, origin_evidence_ref):
            if _SECRET_SHAPED.search(field or ""):
                raise PermissionError_("PERMISSION_CARRIES_SECRET_MATERIAL", permission)

        now = int(time.time() * 1000) if now_ms is None else now_ms
        grant_id = f"perm_{uuid.uuid4().hex}"
        await self.store.execute(
            """
            INSERT INTO permission_grants(
              grant_id, permission, display_name, scope, origin, origin_evidence_ref,
              granted_at_ms, expires_at_ms, last_used_at_ms, use_count, revoked_at_ms,
              revocation_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL)
            """,
            (
                grant_id, permission, KNOWN_PERMISSIONS[permission], scope, origin.value,
                origin_evidence_ref, now, expires_at_ms,
            ),
        )
        return await self.get(grant_id)  # type: ignore[return-value]

    async def record_use(self, grant_id: str, *, now_ms: int | None = None) -> None:
        """§36 — "last use" is what makes a stale grant visible."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE permission_grants SET last_used_at_ms = ?, use_count = use_count + 1 "
            "WHERE grant_id = ? AND revoked_at_ms IS NULL",
            (now, grant_id),
        )

    async def revoke(
        self, grant_id: str, *, reason: str = "owner revoked", now_ms: int | None = None
    ) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE permission_grants SET revoked_at_ms = ?, revocation_reason = ? "
                "WHERE grant_id = ? AND revoked_at_ms IS NULL",
                (now, reason, grant_id),
            )
            await db.commit()
            return cur.rowcount == 1

    async def get(self, grant_id: str) -> PermissionGrant | None:
        row = await self.store.fetchone(
            "SELECT * FROM permission_grants WHERE grant_id = ?", (grant_id,)
        )
        return None if row is None else self._row(row)

    async def owner_view(self, *, now_ms: int | None = None) -> dict[str, Any]:
        """§36's screen: what VAN may do, where it came from, when it last did.

        `stale_grants` is the actionable part — a permission held for months
        without use is the one worth asking about.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        rows = await self.store.fetchall(
            "SELECT * FROM permission_grants ORDER BY permission, granted_at_ms DESC"
        )
        grants = [self._row(r) for r in rows]
        live = [g for g in grants if g.is_live(now)]
        ninety_days = 90 * 24 * 60 * 60 * 1000
        return {
            "granted": [
                {
                    "grant_id": g.grant_id, "permission": g.permission,
                    "display_name": g.display_name, "scope": g.scope,
                    "origin": g.origin.value, "origin_evidence_ref": g.origin_evidence_ref,
                    "granted_at_ms": g.granted_at_ms, "expires_at_ms": g.expires_at_ms,
                    "last_used_at_ms": g.last_used_at_ms, "use_count": g.use_count,
                    "never_used": g.last_used_at_ms is None,
                }
                for g in live
            ],
            "revoked": [
                {"grant_id": g.grant_id, "permission": g.permission,
                 "revoked_at_ms": g.revoked_at_ms}
                for g in grants if g.revoked_at_ms is not None
            ],
            "stale_grants": [
                g.grant_id for g in live if g.unused_since_ms(now) > ninety_days
            ],
            "available_permissions": dict(KNOWN_PERMISSIONS),
        }

    @staticmethod
    def _row(row: Any) -> PermissionGrant:
        return PermissionGrant(
            grant_id=str(row["grant_id"]), permission=str(row["permission"]),
            display_name=str(row["display_name"]), scope=str(row["scope"]),
            origin=PermissionOrigin(str(row["origin"])),
            origin_evidence_ref=row["origin_evidence_ref"],
            granted_at_ms=int(row["granted_at_ms"]), expires_at_ms=row["expires_at_ms"],
            last_used_at_ms=row["last_used_at_ms"], use_count=int(row["use_count"]),
            revoked_at_ms=row["revoked_at_ms"],
        )


__all__ = [
    "KNOWN_PERMISSIONS",
    "PermissionGrant",
    "PermissionOrigin",
    "PermissionRegistry",
    "PermissionError_",
]
