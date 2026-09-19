"""Brute-force controls for the owner authentication surfaces.

P1-SEC-007: there was no failed-attempt counter, no backoff, no lockout and no throttle on
device pairing, the ingress token, the device token, the A4 approval challenge or command
signature verification. A tunnel-reachable attacker got unlimited attempts against every
credential in the system, and every failed attempt cost the gateway a full database round
trip.

Two design decisions are worth stating, because both are trade-offs and the wrong one is
easy to make:

**Failures are counted; successes are not.** Throttling successful owner activity would
make the product worse without making it safer.

**Two enforcement postures, chosen per surface.**

  * ``check()`` *before* verifying — a hard lockout. Used only on device pairing. Pairing
    is a rare, deliberate act by a person holding a freshly minted ticket; an
    unauthenticated stranger hammering it is never legitimate, and a fifteen-minute pause
    is the right answer. The cost is real and named: an attacker who can reach the tunnel
    can keep the pairing endpoint shut. That is survivable — the owner's existing devices
    keep working and a gateway restart clears it — whereas silently unlimited guessing at
    the one credential that mints owner-device authority is not.
  * ``record_failure()`` *after* verifying, then ``check()`` — a soft throttle. Used on the
    ingress token, the device token, command signatures and A4 approval proofs. These sit
    on the owner's live command path, so a hard lockout would let any stranger silence the
    assistant. A correct credential therefore always passes, whatever the counter says;
    incorrect ones past the threshold get a flat 429 with ``Retry-After`` and none of the
    downstream work.

What the soft posture does **not** do, stated plainly rather than implied away: it does not
reduce the number of requests an attacker can make. It bounds what a failed attempt costs
this process and makes sustained failure visible and auditable. Bounding request volume is
the reverse proxy's job and is not claimed here.

**The counter is keyed by the thing being attacked, not by the caller.** An attacker
controls their source address and can rotate it; they do not control which device id they
are trying to reach. Where the credential is global to the gateway — the ingress token,
the pairing endpoint — the subject is global too, which is what makes the posture choice
above load-bearing.

State is in-process and does not survive a restart. For the single-owner, single-gateway
topology that is the right trade: a restart clears a lockout, but a restart also costs the
attacker every bit of progress, and a persistent counter would mean a database write on
every failed attempt — an amplification vector in its own right.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class Throttled(Exception):
    """Too many recent failures against this subject."""

    def __init__(self, surface: str, subject: str, retry_after_seconds: int) -> None:
        self.surface = surface
        self.subject = subject
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"too many failed {surface} attempts; retry in {retry_after_seconds}s"
        )


@dataclass(frozen=True)
class ThrottlePolicy:
    """How many failures, in what window, and how long the lockout lasts."""

    max_failures: int
    window_seconds: int
    lockout_seconds: int


#: Per-surface policies. Pairing is the tightest because a pairing ticket is the one
#: credential that mints owner-device authority. Approval challenges are tight because a
#: successful forgery authorises a destructive action.
POLICIES: dict[str, ThrottlePolicy] = {
    "pairing": ThrottlePolicy(max_failures=5, window_seconds=300, lockout_seconds=900),
    "device_token": ThrottlePolicy(max_failures=10, window_seconds=300, lockout_seconds=300),
    "ingress_token": ThrottlePolicy(max_failures=10, window_seconds=300, lockout_seconds=300),
    "approval_challenge": ThrottlePolicy(max_failures=5, window_seconds=300, lockout_seconds=900),
    "command_signature": ThrottlePolicy(max_failures=10, window_seconds=300, lockout_seconds=600),
}

DEFAULT_POLICY = ThrottlePolicy(max_failures=10, window_seconds=300, lockout_seconds=300)

#: Surfaces where the whole gateway shares one credential, so there is nothing narrower to
#: key on. Named rather than inferred, so adding a surface forces the author to decide.
GLOBAL_SUBJECT = "*"


@dataclass
class _Record:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class AuthThrottle:
    """In-process failure counter with per-surface lockout."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], _Record] = {}

    @staticmethod
    def policy(surface: str) -> ThrottlePolicy:
        return POLICIES.get(surface, DEFAULT_POLICY)

    def check(self, surface: str, subject: str, *, now: float | None = None) -> None:
        """Raise ``Throttled`` if this subject is currently locked out."""
        stamp = time.monotonic() if now is None else now
        record = self._records.get((surface, subject))
        if record is None:
            return
        if record.locked_until > stamp:
            raise Throttled(surface, subject, int(record.locked_until - stamp) + 1)

    def record_failure(self, surface: str, subject: str, *, now: float | None = None) -> None:
        """Count a failed attempt and lock the subject out once the policy is exceeded."""
        stamp = time.monotonic() if now is None else now
        policy = self.policy(surface)
        record = self._records.setdefault((surface, subject), _Record())
        cutoff = stamp - policy.window_seconds
        record.failures = [f for f in record.failures if f > cutoff]
        record.failures.append(stamp)
        if len(record.failures) >= policy.max_failures:
            record.locked_until = stamp + policy.lockout_seconds
            record.failures.clear()

    def fail(self, surface: str, subject: str, *, now: float | None = None) -> None:
        """Soft posture in one call: count the failure, then raise if it tipped the policy.

        Callers use this *after* the credential has already been judged invalid, so a
        correct credential is never affected by the counter.
        """
        self.record_failure(surface, subject, now=now)
        self.check(surface, subject, now=now)

    def record_success(self, surface: str, subject: str) -> None:
        """Clear the failure history. A genuine owner is not penalised for a typo."""
        self._records.pop((surface, subject), None)

    def is_locked(self, surface: str, subject: str, *, now: float | None = None) -> bool:
        try:
            self.check(surface, subject, now=now)
        except Throttled:
            return True
        return False

    def reset(self) -> None:
        """Test and operational hook: forget all counters."""
        self._records.clear()
