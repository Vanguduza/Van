"""Credential age, so nothing lives forever by default.

P2-SEC-008: enrolment grants were minted with a ten-year expiry, and the ingress token,
the internal control token, device secrets and the commander tokens were never rotated at
all. There was no expiry to reach, no rotation to perform and nothing that would ever say
so — which is how a credential ends up older than the threat model it was chosen under.

Two honest limits on what this module is:

**It reports; it does not rotate.** Rotating the ingress token means updating the gateway,
the phone and the tunnel at the same instant, and a process that did that unattended would
be a far better way to lock the owner out than any attacker has. So this makes age visible
and actionable, and the rotation itself stays a deliberate act.

**It cannot see a credential's true birthday.** A static token in an environment file has
no issue date the gateway can read, so its age is taken from when the gateway first saw
it. That is a floor, not the truth, and the report says so rather than implying precision
it does not have.

What it does give is the thing that was missing: a surface that says "this credential is
older than its policy" instead of silence.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from van_gateway.storage.db import Store

#: How long each credential may go unrotated before the gateway starts saying so. These
#: are starting points chosen for a single-owner system, not measured optima, and they are
#: here as data so they can be argued with rather than buried in a comparison.
ROTATION_POLICY_SECONDS: dict[str, int] = {
    "ingress_token": 180 * 24 * 3600,
    "internal_control_token": 90 * 24 * 3600,
    "commander_token": 90 * 24 * 3600,
    "automation_grant_signing_key": 180 * 24 * 3600,
}

#: How far ahead of the deadline to start asking.
ROTATION_WARNING_SECONDS = 14 * 24 * 3600


@dataclass(frozen=True)
class CredentialAge:
    name: str
    state: str           # VALID | ROTATE_SOON | OVERDUE | UNCONFIGURED
    first_seen_unix: int
    age_seconds: int
    policy_seconds: int

    @property
    def needs_owner(self) -> bool:
        return self.state in {"ROTATE_SOON", "OVERDUE"}


def fingerprint(secret: str) -> str:
    """A stable, non-reversing identity for a credential value.

    Stored instead of the credential so that the table recording *when* a token was first
    seen cannot itself become a way to learn the token.
    """
    return hashlib.sha256(f"van-credential-v1|{secret}".encode("utf-8")).hexdigest()


class CredentialRotation:
    """Tracks when each credential value was first seen, and how old that makes it."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def observe(self, name: str, secret: str, *, now: int | None = None) -> CredentialAge:
        """Record this credential value, and report its age.

        A changed value is a rotation: the fingerprint differs, so the clock restarts. The
        gateway does not have to be told a rotation happened, which matters because the
        one thing an operator reliably forgets is to tell a system what they did.
        """
        stamp = int(time.time()) if now is None else now
        policy = ROTATION_POLICY_SECONDS.get(name, 180 * 24 * 3600)
        if not secret or not secret.strip():
            return CredentialAge(name, "UNCONFIGURED", 0, 0, policy)

        digest = fingerprint(secret)
        row = await self.store.fetchone(
            "SELECT value FROM runtime_meta WHERE key = ?", (f"credential_age:{name}",)
        )
        first_seen = stamp
        if row is not None:
            try:
                stored_digest, stored_first_seen = str(row["value"]).split("|", 1)
            except ValueError:
                stored_digest, stored_first_seen = "", "0"
            if stored_digest == digest:
                first_seen = int(stored_first_seen or stamp)

        if row is None or first_seen == stamp:
            await self.store.execute(
                "INSERT INTO runtime_meta(key, value, updated_at_unix_ms) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at_unix_ms = excluded.updated_at_unix_ms",
                (f"credential_age:{name}", f"{digest}|{first_seen}", stamp * 1000),
            )

        age = max(0, stamp - first_seen)
        if age >= policy:
            state = "OVERDUE"
        elif age >= policy - ROTATION_WARNING_SECONDS:
            state = "ROTATE_SOON"
        else:
            state = "VALID"
        return CredentialAge(name, state, first_seen, age, policy)

    async def report(self, credentials: dict[str, str], *, now: int | None = None) -> dict:
        """Every tracked credential, and whether anything needs the owner."""
        ages = [await self.observe(name, value, now=now) for name, value in credentials.items()]
        return {
            "credentials": [
                {
                    "name": a.name,
                    "state": a.state,
                    "age_days": round(a.age_seconds / 86400, 1),
                    "policy_days": round(a.policy_seconds / 86400),
                    "first_seen_unix": a.first_seen_unix,
                }
                for a in ages
            ],
            "needs_owner": [a.name for a in ages if a.needs_owner],
            # Said plainly rather than left for the reader to assume otherwise.
            "age_basis": "first seen by this gateway; a static token carries no issue date",
        }


__all__ = [
    "ROTATION_POLICY_SECONDS",
    "ROTATION_WARNING_SECONDS",
    "CredentialAge",
    "CredentialRotation",
    "fingerprint",
]
