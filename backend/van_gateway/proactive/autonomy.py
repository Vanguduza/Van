"""Rev 1 §§11, 27, 31 — proactive autonomy and domain trust.

§30's rule is the one that keeps this safe: *autonomy must be domain-specific,
not global*. VAN being reliable at collecting broker statements says nothing
about whether it should act unprompted on the owner's calendar, and a single
global "autonomy level" would let competence in one place buy permission in
another.

§31 adds the asymmetry that makes trust mean something:

    Trust grows from verified evidence.
    False success must severely penalize autonomy.
    Never infer new standing authority solely from successful execution history.

That last line is the important one, and it is why `DomainTrust` has both a
computed `earned_ceiling` and a separate `owner_granted_ceiling`. Execution
history can *lower* what VAN will do on its own and can support a case for
raising it, but it can never raise it by itself. The owner grants; evidence only
ever spends.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store


class AutonomyLevel(str, Enum):
    """§30's S0-S5 ladder, per domain."""

    S0_RESPOND_ONLY = "S0"
    S1_SUGGEST = "S1"
    S2_PREPARE = "S2"
    S3_REVERSIBLE_EXECUTION = "S3"
    S4_STANDING_AUTHORITY = "S4"
    S5_MAINTAIN_DOMAIN = "S5"

    @property
    def ordinal(self) -> int:
        return int(self.value[1:])

    @property
    def may_execute(self) -> bool:
        return self.ordinal >= 3

    @property
    def requires_owner_grant(self) -> bool:
        """§31 — anything that acts without asking is granted, never earned."""
        return self.ordinal >= 3


#: DECISION (recorded, no owner input): the ceiling VAN will reach on evidence
#: alone is S2 — it may prepare work and present it, never execute it. Every
#: level that acts without asking requires an explicit owner grant. This is the
#: most conservative reading of §31 that still lets trust be useful.
MAX_EARNED_LEVEL = AutonomyLevel.S2_PREPARE

#: DECISION (recorded): one false success costs more than ten verified ones earn.
#: §31 says false success must "severely penalize" autonomy, and a symmetric
#: penalty would let a system that lies occasionally still climb.
FALSE_SUCCESS_PENALTY = 10


class ProactiveMissionType(str, Enum):
    """§30 — what a proactive mission is allowed to be."""

    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    RECOMMENDATION = "RECOMMENDATION"
    SAFE_BOUNDED_AUTOMATIC = "SAFE_BOUNDED_AUTOMATIC"
    OWNER_APPROVAL_REQUIRED = "OWNER_APPROVAL_REQUIRED"

    @property
    def minimum_level(self) -> AutonomyLevel:
        return {
            ProactiveMissionType.OBSERVATION_ONLY: AutonomyLevel.S1_SUGGEST,
            ProactiveMissionType.RECOMMENDATION: AutonomyLevel.S1_SUGGEST,
            ProactiveMissionType.OWNER_APPROVAL_REQUIRED: AutonomyLevel.S2_PREPARE,
            ProactiveMissionType.SAFE_BOUNDED_AUTOMATIC: AutonomyLevel.S3_REVERSIBLE_EXECUTION,
        }[self]


class DomainTrust(BaseModel):
    domain: str
    verified_successes: int = 0
    meaningful_failures: int = 0
    false_successes: int = 0
    owner_overrides: int = 0
    recovery_successes: int = 0
    owner_granted_ceiling: AutonomyLevel | None = None

    @property
    def net_evidence(self) -> int:
        """What execution history has actually demonstrated."""
        return (
            self.verified_successes
            + self.recovery_successes
            - self.meaningful_failures
            - self.false_successes * FALSE_SUCCESS_PENALTY
            - self.owner_overrides
        )

    @property
    def has_unrecovered_false_success(self) -> bool:
        """§31 — a domain that reported success falsely is worse than unknown.

        Not merely penalised: a brand-new domain has never misreported, and this
        one has, so netting the penalty against past successes back to "even"
        would treat the two as equivalent. `recovery_successes` exists in §31
        precisely so this is escapable, and demonstrated recovery is the only
        thing that escapes it.
        """
        return self.false_successes > self.recovery_successes

    @property
    def earned_ceiling(self) -> AutonomyLevel:
        """What evidence supports, capped at MAX_EARNED_LEVEL.

        §31 — history can never mint standing authority, so this tops out below
        every level that acts without asking.
        """
        if self.has_unrecovered_false_success:
            return AutonomyLevel.S0_RESPOND_ONLY
        net = self.net_evidence
        if net < 0:
            return AutonomyLevel.S0_RESPOND_ONLY
        if net >= 10:
            return MAX_EARNED_LEVEL
        if net >= 3:
            return AutonomyLevel.S1_SUGGEST
        return AutonomyLevel.S0_RESPOND_ONLY

    @property
    def effective_ceiling(self) -> AutonomyLevel:
        """The lower of what the owner granted and what evidence still supports.

        Both directions matter: an owner grant does not survive VAN demonstrating
        it cannot be trusted here, and good history does not exceed the grant.
        """
        earned = self.earned_ceiling
        if self.owner_granted_ceiling is None:
            return earned
        if self.net_evidence < 0 or self.has_unrecovered_false_success:
            # Demonstrated unreliability overrides a standing grant until the
            # domain recovers. The grant is not revoked, only suspended.
            return AutonomyLevel.S0_RESPOND_ONLY
        return (
            self.owner_granted_ceiling
            if self.owner_granted_ceiling.ordinal >= earned.ordinal
            else earned
        )

    def permits(self, mission_type: ProactiveMissionType) -> bool:
        return self.effective_ceiling.ordinal >= mission_type.minimum_level.ordinal


@dataclass(frozen=True)
class AutonomyVerdict:
    """GAP-F-008 — what `ActionRuntime.begin` gets back from an autonomy check.

    Deliberately two fields. `allowed` is the only thing `begin` acts on; `reason` is
    what an owner reads on `/v1/understanding/autonomy` or in the execution's
    `error_code` to see *why* — never a bare denial with nothing to argue with.
    """

    allowed: bool
    reason: str


class AutonomyPolicy(Protocol):
    """The shape `ActionRuntime(autonomy=...)` consults. See `ActionAutonomyGate`.

    Kept as a `Protocol` rather than a base class so `ActionRuntime` (action/service.py)
    never has to import anything from `proactive` beyond this type — the dependency runs
    one way, into the module that owns autonomy policy, not back out of it.
    """

    async def permits(
        self,
        *,
        action_id: str,
        action_class: ActionClass,
        principal_type: PrincipalType,
        requested_by: str,
    ) -> AutonomyVerdict: ...


#: GAP-F-008 — the least-privilege reading of "reads": only A1 is guaranteed
#: non-mutating everywhere it appears in `action/registry.py` today (§10's read-only
#: side of `owner.context.read`). A2 already covers non-mutating capabilities such as
#: `research.web.search`, so it is treated as mutating here rather than assumed safe —
#: the asymmetry costs nothing (a domain with real evidence reaches S1 quickly) and
#: means this table can only ever be too cautious, never too permissive.
#:
#: The level required rises with the class because what a class *means* rises with it:
#: A2 is prepared/proposed work, which S1_SUGGEST already covers; A3 is a reversible
#: execution, which needs VAN to have earned the right to prepare unprompted (S2); A4 is
#: the class that mutates without an easy way back, which needs S3 — actual unprompted
#: execution — before an unprompted agent may even attempt it. A5 is unreachable here:
#: `ActionRuntime.begin` refuses it before any principal or autonomy check runs.
_REQUIRED_CEILING: dict[ActionClass, AutonomyLevel] = {
    ActionClass.A2: AutonomyLevel.S1_SUGGEST,
    ActionClass.A3: AutonomyLevel.S2_PREPARE,
    ActionClass.A4: AutonomyLevel.S3_REVERSIBLE_EXECUTION,
    ActionClass.A5: AutonomyLevel.S5_MAINTAIN_DOMAIN,
}


def _domain_for(action_id: str) -> str:
    """`google.gmail.send` → `google.gmail`; `trading.halt` → `trading`.

    §30 asks for domain-specific autonomy, and `action_id` is already namespaced by
    provider and surface (`action/registry.py`), so the first two dotted segments are a
    real domain boundary rather than an invented one — gmail and calendar trust stay
    apart even though both are Google.
    """
    parts = action_id.split(".")
    return ".".join(parts[:2]) if len(parts) > 1 else action_id


class ActionAutonomyGate:
    """GAP-F-008 — the `AutonomyPolicy` `ActionRuntime` consults for non-owner principals.

    §31's asymmetry is the whole implementation: a domain's `DomainTrust` grows only
    from verified evidence or an owner grant, never from this gate, and this gate does
    nothing but read that ceiling and compare it with what the action asks for. It
    cannot raise anything — `DomainTrustService.grant` and `ProactivePolicyService`
    already own that, and this class holds no write path to either store.

    Default deny: an unknown domain has `DomainTrust()`'s zero-evidence ceiling (S0),
    which permits nothing above A1, so a mutating action from an agent principal is
    refused until the domain has actually earned trust or the owner has granted it.
    """

    def __init__(self, trust: DomainTrustService) -> None:
        self.trust = trust

    async def permits(
        self,
        *,
        action_id: str,
        action_class: ActionClass,
        principal_type: PrincipalType,
        requested_by: str,
    ) -> AutonomyVerdict:
        if action_class is ActionClass.A1:
            # §10 — reads are not what §31 is protecting; refusing them here would not
            # add safety, only make VAN unable to look at its own context unprompted.
            return AutonomyVerdict(True, "read_action")
        domain = _domain_for(action_id)
        trust = await self.trust.get(domain)
        required = _REQUIRED_CEILING.get(action_class, AutonomyLevel.S5_MAINTAIN_DOMAIN)
        if trust.effective_ceiling.ordinal >= required.ordinal:
            return AutonomyVerdict(
                True,
                f"{domain} ceiling {trust.effective_ceiling.value} permits "
                f"{action_class.value} for {principal_type.value}",
            )
        return AutonomyVerdict(
            False,
            f"{domain} ceiling {trust.effective_ceiling.value} < {required.value} "
            f"required for {principal_type.value} to run {action_class.value} "
            f"({action_id}) unprompted",
        )


class AutonomyError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class DomainTrustService:
    """Records outcomes per domain and answers what VAN may do unprompted."""

    def __init__(self, store: Store) -> None:
        self.store = store

    async def get(self, domain: str) -> DomainTrust:
        row = await self.store.fetchone(
            "SELECT * FROM domain_trust WHERE domain = ?", (domain,)
        )
        if row is None:
            return DomainTrust(domain=domain)
        return DomainTrust(
            domain=domain,
            verified_successes=int(row["verified_successes"]),
            meaningful_failures=int(row["meaningful_failures"]),
            false_successes=int(row["false_successes"]),
            owner_overrides=int(row["owner_overrides"]),
            recovery_successes=int(row["recovery_successes"]),
            owner_granted_ceiling=(
                AutonomyLevel(str(row["owner_granted_ceiling"]))
                if row["owner_granted_ceiling"] else None
            ),
        )

    async def record(
        self,
        domain: str,
        *,
        verified_success: int = 0,
        meaningful_failure: int = 0,
        false_success: int = 0,
        owner_override: int = 0,
        recovery_success: int = 0,
        now_ms: int | None = None,
    ) -> DomainTrust:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO domain_trust(
              domain, verified_successes, meaningful_failures, false_successes,
              owner_overrides, recovery_successes, current_autonomy_ceiling,
              owner_granted_ceiling, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, 'S0', NULL, ?)
            ON CONFLICT(domain) DO UPDATE SET
              verified_successes = verified_successes + excluded.verified_successes,
              meaningful_failures = meaningful_failures + excluded.meaningful_failures,
              false_successes = false_successes + excluded.false_successes,
              owner_overrides = owner_overrides + excluded.owner_overrides,
              recovery_successes = recovery_successes + excluded.recovery_successes,
              updated_at_ms = excluded.updated_at_ms
            """,
            (
                domain, verified_success, meaningful_failure, false_success,
                owner_override, recovery_success, now,
            ),
        )
        trust = await self.get(domain)
        await self.store.execute(
            "UPDATE domain_trust SET current_autonomy_ceiling = ? WHERE domain = ?",
            (trust.effective_ceiling.value, domain),
        )
        return trust

    async def grant(
        self, domain: str, *, level: AutonomyLevel, evidence_ref: str,
        now_ms: int | None = None,
    ) -> DomainTrust:
        """§31 — only this raises a ceiling above what evidence can earn."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        if not evidence_ref:
            raise AutonomyError("AUTONOMY_GRANT_REQUIRES_OWNER_EVIDENCE", domain)
        await self.store.execute(
            "INSERT INTO domain_trust(domain, owner_granted_ceiling, updated_at_ms) "
            "VALUES (?, ?, ?) ON CONFLICT(domain) DO UPDATE SET "
            "owner_granted_ceiling = excluded.owner_granted_ceiling, "
            "updated_at_ms = excluded.updated_at_ms",
            (domain, level.value, now),
        )
        return await self.get(domain)

    async def assert_may_run(
        self, domain: str, mission_type: ProactiveMissionType
    ) -> DomainTrust:
        """§30 — never silently widen authority."""
        trust = await self.get(domain)
        if not trust.permits(mission_type):
            raise AutonomyError(
                "PROACTIVE_MISSION_NOT_PERMITTED",
                f"{domain} ceiling {trust.effective_ceiling.value} < "
                f"{mission_type.minimum_level.value} required for {mission_type.value}",
            )
        return trust


#: GAP-F-028 — the `mission_class` marker for a policy row that turns proactive
#: follow-ups off for a domain, rather than granting standing autonomy. Reuses
#: `proactive_policies` instead of a new table: it is still "a policy under which VAN
#: may [not] start work unprompted", which is exactly what that table already records.
#: It carries `autonomy_level='S0'` because the column is `NOT NULL` and S0 is the
#: truthful value — a disabled domain gets no unprompted initiative at all — not
#: because disabling is a grant.
FOLLOW_UP_POLICY_MARKER = "__proactive_follow_up_disabled__"


class ProactivePolicyService:
    """§11 — the standing policies under which VAN may start work unprompted."""

    def __init__(self, store: Store, trust: DomainTrustService) -> None:
        self.store = store
        self.trust = trust

    async def grant_policy(
        self,
        *,
        domain: str,
        autonomy_level: AutonomyLevel,
        mission_class: str,
        owner_evidence_ref: str,
        now_ms: int | None = None,
    ) -> str:
        if autonomy_level.requires_owner_grant and not owner_evidence_ref:
            raise AutonomyError("PROACTIVE_POLICY_REQUIRES_OWNER_EVIDENCE", domain)
        now = int(time.time() * 1000) if now_ms is None else now_ms
        policy_id = f"ppol_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO proactive_policies(policy_id, domain, autonomy_level, mission_class, "
            "owner_granted_at_ms, owner_evidence_ref, enabled, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                policy_id, domain, autonomy_level.value, mission_class, now,
                owner_evidence_ref, now, now,
            ),
        )
        await self.trust.grant(domain, level=autonomy_level, evidence_ref=owner_evidence_ref)
        return policy_id

    async def may_create(
        self, *, domain: str, mission_type: ProactiveMissionType
    ) -> tuple[bool, str | None]:
        """Whether a proactive mission may be created, and why not."""
        try:
            await self.trust.assert_may_run(domain, mission_type)
        except AutonomyError as exc:
            return False, exc.detail
        return True, None

    async def disable_follow_ups(
        self, domain: str, *, reason: str = "owner request", now_ms: int | None = None
    ) -> str:
        """GAP-F-028 — turn `ProactiveFollowUpJob` off for a domain.

        §31's asymmetry the other way round: earning trust needs verified evidence and
        an owner grant needs `evidence_ref`; muting VAN's own initiative needs neither,
        because the direction that needs safeguarding is VAN acting, not VAN staying
        quiet. `reason` is kept for the owner-visible record, not as a gate.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        policy_id = f"ppol_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO proactive_policies(policy_id, domain, autonomy_level, "
            "mission_class, owner_granted_at_ms, owner_evidence_ref, enabled, "
            "created_at_ms, updated_at_ms) VALUES (?, ?, 'S0', ?, ?, ?, 1, ?, ?)",
            (policy_id, domain, FOLLOW_UP_POLICY_MARKER, now, reason, now, now),
        )
        return policy_id

    async def follow_ups_enabled(self, domain: str) -> bool:
        """GAP-F-028 — whether `ProactiveFollowUpJob` may surface anything for `domain`.

        Enabled unless an owner has explicitly disabled it: a domain nobody has an
        opinion about is exactly the case the job exists for, so absence of a policy
        means "go ahead", not "wait for permission" — the job never executes anything
        and never opens a mission, so there is nothing here for §31's earn-don't-infer
        rule to protect against.
        """
        rows = await self.policies(domain)
        return not any(
            str(row["mission_class"]) == FOLLOW_UP_POLICY_MARKER for row in rows
        )

    async def policies(self, domain: str | None = None) -> list[dict[str, Any]]:
        if domain is None:
            rows = await self.store.fetchall(
                "SELECT * FROM proactive_policies WHERE enabled = 1 ORDER BY domain"
            )
        else:
            rows = await self.store.fetchall(
                "SELECT * FROM proactive_policies WHERE enabled = 1 AND domain = ?", (domain,)
            )
        return [dict(r) for r in rows]

    async def revoke(self, policy_id: str, *, now_ms: int | None = None) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE proactive_policies SET enabled = 0, updated_at_ms = ? "
                "WHERE policy_id = ? AND enabled = 1",
                (now, policy_id),
            )
            await db.commit()
            return cur.rowcount == 1


__all__ = [
    "FALSE_SUCCESS_PENALTY",
    "FOLLOW_UP_POLICY_MARKER",
    "MAX_EARNED_LEVEL",
    "ActionAutonomyGate",
    "AutonomyError",
    "AutonomyLevel",
    "AutonomyPolicy",
    "AutonomyVerdict",
    "DomainTrust",
    "DomainTrustService",
    "ProactiveMissionType",
    "ProactivePolicyService",
]
