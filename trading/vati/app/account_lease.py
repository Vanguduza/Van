"""Cross-host account runtime lease (§13, TRD-ENH-035).

`SessionLock` already prevents an operator starting `serve` twice, and states
its own limit honestly: it is per-host and advisory. A second VM running the
same alias passes it, and both processes then believe they are alone.

The lease fixes that *when the authority store is shared*. On the baseline
topology the store is loopback-only, so a second host cannot reach it — and that
is the distinction the blueprint's B2 correction insists on:

    LEASE_REFUSED_HELD_BY_OTHER   arbitration ran and said no
    LEASE_STORE_UNREACHABLE       fail-closed; arbitration did not run

Both block new orders. Only the first proves the control works. A test asserting
"the second host cannot trade" against an unreachable store proves unreachability
and would let the `remove lease_epoch fence` mutation survive.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class LeaseOutcome(str, Enum):
    GRANTED = "GRANTED"
    RENEWED = "RENEWED"
    #: Another live holder. Arbitration ran.
    REFUSED_HELD_BY_OTHER = "REFUSED_HELD_BY_OTHER"
    #: Our epoch is stale — someone took the lease and we did not notice.
    REFUSED_STALE_EPOCH = "REFUSED_STALE_EPOCH"
    #: Fail-closed. Arbitration did NOT run; this proves nothing about fencing.
    STORE_UNREACHABLE = "STORE_UNREACHABLE"


#: Outcomes that permit new orders. Exactly two.
PERMITS_ORDERS = frozenset({LeaseOutcome.GRANTED, LeaseOutcome.RENEWED})


class LeaseStoreUnavailable(RuntimeError):
    """The transactional store could not be reached."""


@dataclass(frozen=True)
class AccountLease:
    account_alias: str
    holder_instance_id: str
    lease_epoch: int
    acquired_at_ms: int
    heartbeat_at_ms: int
    expires_at_ms: int
    software_version: str = ""
    git_sha: str = ""

    def live_at(self, now_ms: int) -> bool:
        return now_ms < self.expires_at_ms


@dataclass(frozen=True)
class LeaseResult:
    outcome: LeaseOutcome
    lease: Optional[AccountLease] = None
    holder_instance_id: str = ""
    detail: str = ""

    @property
    def permits_orders(self) -> bool:
        return self.outcome in PERMITS_ORDERS


class LeaseStore(Protocol):
    """Transactional compare-and-set over one row per account alias."""

    def read(self, account_alias: str) -> Optional[AccountLease]: ...

    def write_if(self, expected: Optional[AccountLease], new: AccountLease) -> bool:
        """Atomic CAS. False when another writer won the race."""
        ...


class InMemoryLeaseStore:
    """A single shared store. Reachable by construction, so fencing tests that
    use it are testing arbitration rather than connectivity."""

    def __init__(self) -> None:
        self._rows: dict[str, AccountLease] = {}
        self.reachable = True

    def read(self, account_alias: str) -> Optional[AccountLease]:
        if not self.reachable:
            raise LeaseStoreUnavailable(account_alias)
        return self._rows.get(account_alias)

    def write_if(self, expected: Optional[AccountLease], new: AccountLease) -> bool:
        if not self.reachable:
            raise LeaseStoreUnavailable(new.account_alias)
        current = self._rows.get(new.account_alias)
        if current != expected:
            return False
        self._rows[new.account_alias] = new
        return True


class AccountRuntimeLease:
    """Acquire, renew and fence one account alias across hosts."""

    DEFAULT_TTL_MS = 30_000

    def __init__(
        self,
        store: LeaseStore,
        *,
        account_alias: str,
        instance_id: str,
        ttl_ms: int = DEFAULT_TTL_MS,
        software_version: str = "",
        git_sha: str = "",
    ) -> None:
        self.store = store
        self.account_alias = account_alias
        self.instance_id = instance_id
        self.ttl_ms = ttl_ms
        self.software_version = software_version
        self.git_sha = git_sha
        self._held: Optional[AccountLease] = None

    @property
    def held(self) -> Optional[AccountLease]:
        return self._held

    @property
    def epoch(self) -> Optional[int]:
        return self._held.lease_epoch if self._held else None

    def _now(self, now_ms: Optional[int]) -> int:
        return int(time.time() * 1000) if now_ms is None else now_ms

    def acquire(self, *, now_ms: Optional[int] = None) -> LeaseResult:
        now = self._now(now_ms)
        try:
            current = self.store.read(self.account_alias)
        except LeaseStoreUnavailable as exc:
            # Fail closed, and say *why* — this is not evidence of fencing.
            return LeaseResult(LeaseOutcome.STORE_UNREACHABLE, detail=str(exc))

        if current is not None and current.live_at(now) and current.holder_instance_id != self.instance_id:
            return LeaseResult(LeaseOutcome.REFUSED_HELD_BY_OTHER,
                               holder_instance_id=current.holder_instance_id,
                               detail=f"held until {current.expires_at_ms}")

        new = AccountLease(
            account_alias=self.account_alias, holder_instance_id=self.instance_id,
            lease_epoch=(current.lease_epoch + 1) if current else 1,
            acquired_at_ms=now, heartbeat_at_ms=now, expires_at_ms=now + self.ttl_ms,
            software_version=self.software_version, git_sha=self.git_sha,
        )
        try:
            if not self.store.write_if(current, new):
                return LeaseResult(LeaseOutcome.REFUSED_HELD_BY_OTHER,
                                   detail="lost compare-and-set race")
        except LeaseStoreUnavailable as exc:
            return LeaseResult(LeaseOutcome.STORE_UNREACHABLE, detail=str(exc))
        self._held = new
        return LeaseResult(LeaseOutcome.GRANTED, lease=new)

    def renew(self, *, now_ms: Optional[int] = None) -> LeaseResult:
        now = self._now(now_ms)
        if self._held is None:
            return self.acquire(now_ms=now)
        try:
            current = self.store.read(self.account_alias)
        except LeaseStoreUnavailable as exc:
            return LeaseResult(LeaseOutcome.STORE_UNREACHABLE, detail=str(exc))

        if current is None or current.holder_instance_id != self.instance_id:
            self._held = None
            return LeaseResult(LeaseOutcome.REFUSED_HELD_BY_OTHER,
                               holder_instance_id=current.holder_instance_id if current else "")
        if current.lease_epoch != self._held.lease_epoch:
            # Someone took and released the lease while we slept.
            self._held = None
            return LeaseResult(LeaseOutcome.REFUSED_STALE_EPOCH,
                               detail=f"epoch {self._held.lease_epoch if self._held else '?'} != {current.lease_epoch}")

        renewed = AccountLease(**{**current.__dict__, "heartbeat_at_ms": now,
                                  "expires_at_ms": now + self.ttl_ms})
        try:
            if not self.store.write_if(current, renewed):
                self._held = None
                return LeaseResult(LeaseOutcome.REFUSED_HELD_BY_OTHER, detail="lost renewal race")
        except LeaseStoreUnavailable as exc:
            return LeaseResult(LeaseOutcome.STORE_UNREACHABLE, detail=str(exc))
        self._held = renewed
        return LeaseResult(LeaseOutcome.RENEWED, lease=renewed)

    def fence(self, epoch: Optional[int]) -> bool:
        """True when `epoch` is the currently held one.

        Every order-producing path carries an epoch; the router refuses a stale
        one. This is what makes the lease a fence rather than a hint.
        """
        return self._held is not None and epoch is not None and epoch == self._held.lease_epoch

    def release(self, *, now_ms: Optional[int] = None) -> None:
        if self._held is None:
            return
        now = self._now(now_ms)
        expired = AccountLease(**{**self._held.__dict__, "expires_at_ms": now})
        try:
            self.store.write_if(self._held, expired)
        except LeaseStoreUnavailable:
            pass          # the lease will expire on its own TTL
        self._held = None


__all__ = [
    "PERMITS_ORDERS",
    "AccountLease", "AccountRuntimeLease", "InMemoryLeaseStore",
    "LeaseOutcome", "LeaseResult", "LeaseStore", "LeaseStoreUnavailable",
]
