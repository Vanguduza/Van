"""Rev 1.3 §§182-185, 189, 385, 387 — Browser Session Broker, leases and evidence.

The broker owns browser profiles so that session material has exactly one home
(§367.3). A task never receives cookies or tokens; it receives a profile alias and
a lease, and the worker resolves ``secretref://`` handles internally.

Evidence is digest-only and is refused outright if it carries secret-shaped
material — a leak fails loudly rather than being quietly redacted.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from van_gateway.automation.canonical import digest, new_id
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserEvidence,
    BrowserStrategy,
    BrowserTask,
    BrowserTaskStatus,
    InjectionAssessment,
    PageLease,
    ProfileLeaseHolderKind,
)
from van_gateway.browser.policy import BrowserPolicyEngine, BrowserPolicyError
from van_gateway.models import ActionClass
from van_gateway.storage.db import Store


#: Owner decision 2026-09-29 §7 / review I M-2. A browser task's postcondition verdict is
#: an append-only ``browser_evidence`` row of this kind. It is written only by
#: ``BrowserTaskService.record_verification`` (``seal_evidence`` refuses the kind), and
#: ``complete(status=COMPLETED)`` requires the task's latest verdict to be VERIFIED.
VERIFICATION_EVIDENCE_KIND = "postcondition_verification"
VERIFIED = "VERIFIED"
#: Review I2 N-11. The interaction router's per-step record (``RouterStepLedger``) lives in
#: ``browser_evidence`` under this kind and is read back as "the steps this task took". Only
#: the ledger writes it; ``seal_evidence`` refuses it like the verdict kind.
ROUTER_STEP_EVIDENCE_KIND = "interaction_router_step"
#: Kinds only VAN's own verifier / router may write. Compared case-insensitively and with
#: surrounding whitespace ignored, so ``Interaction_Router_Step`` is the same reserved kind.
RESERVED_EVIDENCE_KINDS = frozenset({VERIFICATION_EVIDENCE_KIND, ROUTER_STEP_EVIDENCE_KIND})

#: Review I2 N-3. The statuses a task ends in. Nothing moves a task out of one of these.
TERMINAL_TASK_STATUSES = frozenset({
    BrowserTaskStatus.COMPLETED,
    BrowserTaskStatus.FAILED,
    BrowserTaskStatus.DENIED,
    BrowserTaskStatus.BLOCKED_POLICY,
    BrowserTaskStatus.BLOCKED_UNSAFE,
    BrowserTaskStatus.CANCELLED,
    BrowserTaskStatus.EXPIRED,
})
#: What ``complete()`` may set: a terminal status, COMPLETED only over a VERIFIED verdict.
#: PENDING and RESUME_AUTHORIZED are authority, not end states: PENDING is reachable only by
#: creating the task and RESUME_AUTHORIZED only through the owner-decision sync. The
#: non-terminal working states are written by the paths that own them.
COMPLETABLE_TASK_STATUSES = TERMINAL_TASK_STATUSES


def is_reserved_evidence_kind(kind: str) -> bool:
    return str(kind or "").strip().casefold() in RESERVED_EVIDENCE_KINDS


class BrowserTaskNotVerified(BrowserPolicyError):
    """COMPLETED was requested for a task with no VERIFIED postcondition verdict."""

    def __init__(self, task_id: str, latest: str | None) -> None:
        super().__init__(
            f"browser_task_completion_requires_verified_postcondition:{latest or 'NO_VERIFICATION'}"
        )
        self.task_id = task_id
        self.latest = latest


class BrowserTaskTransitionRefused(BrowserPolicyError):
    """A status change ``complete()`` does not perform (review I2 N-3)."""

    def __init__(self, task_id: str, current: str | None, requested: str, why: str) -> None:
        super().__init__(f"browser_task_transition_refused:{why}:{current or 'UNKNOWN'}->{requested}")
        self.task_id = task_id
        self.current = current
        self.requested = requested
        self.why = why


class BrowserSessionBroker:
    """§§182-183 — profile registry plus exclusive, time-bounded page leases."""

    DEFAULT_LEASE_SECONDS = 300
    LEASE_PREFIX = "browser_lease:"

    def __init__(self, store: Store, policy: BrowserPolicyEngine | None = None) -> None:
        self.store = store
        self.policy = policy or BrowserPolicyEngine()

    async def register_profile(
        self,
        *,
        profile_alias: str,
        secret_ref: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        """Profiles come from ``config/browser/profiles.yaml``; this records runtime state."""
        spec = self.policy.check_profile(profile_alias)
        if secret_ref is not None and not secret_ref.startswith("secretref://"):
            # §407 — the broker stores a reference, never the credential.
            raise BrowserPolicyError("browser_profile_requires_secret_reference")
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO browser_profiles(
              profile_alias, persistence, authentication, mutation_policy, secret_ref,
              lease_holder, lease_expires_at_ms, last_verified_at_ms, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            ON CONFLICT(profile_alias) DO UPDATE SET
              persistence=excluded.persistence,
              authentication=excluded.authentication,
              mutation_policy=excluded.mutation_policy,
              secret_ref=excluded.secret_ref,
              updated_at_ms=excluded.updated_at_ms
            """,
            (
                profile_alias, str(spec.get("persistence", "ephemeral")),
                str(spec.get("authentication", "none")), str(spec.get("mutation", "forbidden")),
                secret_ref, now, now,
            ),
        )
        return {"profile_alias": profile_alias, **spec}

    #: Rev 1.5 §5.3's normative timing for an interactive session. Short, because the
    #: failure it bounds is a phone that went away without saying so: a long lease means the
    #: profile stays locked to a session nobody is watching.
    INTERACTIVE_LEASE_SECONDS = 120
    HEARTBEAT_SECONDS = 20
    RENEW_WHEN_REMAINING_MS = 80_000
    #: §5.3 / §0E.1 D7 — cleanup and reconnect only. It never extends actuation authority,
    #: which stops at the expiry instant.
    EXPIRY_GRACE_SECONDS = 30

    async def acquire_lease(
        self, *, profile_alias: str, task_id: str | None = None,
        holder_kind: ProfileLeaseHolderKind = ProfileLeaseHolderKind.TASK,
        holder_id: str | None = None,
        ttl_seconds: int | None = None,
        now_ms: int | None = None,
    ) -> PageLease:
        """Exclusive while live. A second holder on the same profile is refused, not queued.

        §5.3: a task passes ``task_id`` and gets the historical behaviour. An interactive
        session passes ``holder_kind=INTERACTIVE_SESSION`` and its session id.

        The generation increments on every successful acquisition, and that is the fence:
        work still holding the previous one is refused rather than applied to whoever holds
        the profile now.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        resolved_holder = holder_id or task_id
        if not resolved_holder:
            raise BrowserPolicyError("browser_lease_requires_a_holder")
        default_ttl = (
            self.INTERACTIVE_LEASE_SECONDS
            if holder_kind is ProfileLeaseHolderKind.INTERACTIVE_SESSION
            else self.DEFAULT_LEASE_SECONDS
        )
        ttl = max(30, int(ttl_seconds or default_ttl))
        expires = now + ttl * 1000
        lease_id = f"blease_{uuid.uuid4().hex}"
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE browser_profiles
                SET lease_holder = ?, lease_expires_at_ms = ?, updated_at_ms = ?,
                    lease_holder_kind = ?, lease_holder_id = ?, lease_acquired_at_ms = ?,
                    lease_generation = lease_generation + 1
                WHERE profile_alias = ?
                  AND (lease_holder IS NULL OR lease_expires_at_ms IS NULL OR lease_expires_at_ms <= ?)
                """,
                (
                    lease_id, expires, now, holder_kind.value, resolved_holder, now,
                    profile_alias, now,
                ),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise BrowserPolicyError(f"browser_profile_leased:{profile_alias}")
            cur = await db.execute(
                "SELECT lease_generation FROM browser_profiles WHERE profile_alias = ?",
                (profile_alias,),
            )
            row = await cur.fetchone()
            generation = int(row["lease_generation"]) if row else 0
        return PageLease(
            lease_id=lease_id, profile_alias=profile_alias,
            task_id=task_id if holder_kind is ProfileLeaseHolderKind.TASK else None,
            holder_kind=holder_kind, holder_id=resolved_holder,
            acquired_at_ms=now, expires_at_ms=expires, generation=generation,
        )

    async def renew_lease(
        self, *, lease_id: str, holder_id: str, generation: int,
        ttl_seconds: int | None = None, now_ms: int | None = None,
    ) -> PageLease:
        """§5.3 — extend exclusivity, and nothing else.

        Renewal does not increment the generation and confers no new authority: it says the
        holder is still here. All three of lease id, holder and generation must match, so a
        stale client cannot keep a profile alive for a session the Gateway has already
        replaced.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        ttl = max(30, int(ttl_seconds or self.INTERACTIVE_LEASE_SECONDS))
        expires = now + ttl * 1000
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE browser_profiles
                SET lease_expires_at_ms = ?, updated_at_ms = ?
                WHERE lease_holder = ? AND lease_holder_id = ? AND lease_generation = ?
                  AND lease_expires_at_ms > ?
                """,
                (expires, now, lease_id, holder_id, generation, now),
            )
            await db.commit()
            if cur.rowcount != 1:
                # Either it expired, or it was taken. Both mean the caller must stop
                # actuating now and reacquire, which is why this is an error rather than a
                # silent re-acquire: reacquiring here would hand the profile back to a
                # holder whose lease had already lapsed to someone else.
                raise BrowserPolicyError("browser_lease_not_renewable")
            cur = await db.execute(
                "SELECT profile_alias, lease_holder_kind, lease_acquired_at_ms "
                "FROM browser_profiles WHERE lease_holder = ?",
                (lease_id,),
            )
            row = await cur.fetchone()
        kind = ProfileLeaseHolderKind(row["lease_holder_kind"] or ProfileLeaseHolderKind.TASK.value)
        return PageLease(
            lease_id=lease_id, profile_alias=row["profile_alias"],
            task_id=holder_id if kind is ProfileLeaseHolderKind.TASK else None,
            holder_kind=kind, holder_id=holder_id,
            acquired_at_ms=int(row["lease_acquired_at_ms"] or now),
            expires_at_ms=expires, generation=generation,
        )

    async def assert_lease_active(
        self, *, lease_id: str, holder_id: str, generation: int, now_ms: int | None = None
    ) -> None:
        """Refuse actuation the moment the lease lapses (§5.3, §0E.1 D7).

        The 30-second grace is for cleanup and reconnect. It is deliberately not consulted
        here: video may stay frozen on screen during that window, and nothing may act.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self.store.fetchone(
            "SELECT lease_expires_at_ms, lease_holder_id, lease_generation "
            "FROM browser_profiles WHERE lease_holder = ?",
            (lease_id,),
        )
        if row is None:
            raise BrowserPolicyError("browser_lease_unknown")
        if row["lease_holder_id"] != holder_id:
            raise BrowserPolicyError("browser_lease_holder_mismatch")
        if int(row["lease_generation"]) != int(generation):
            raise BrowserPolicyError("browser_lease_generation_stale")
        if int(row["lease_expires_at_ms"] or 0) <= now:
            raise BrowserPolicyError("browser_profile_lease_expired")

    async def release_lease(self, lease: PageLease, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE browser_profiles SET lease_holder = NULL, lease_expires_at_ms = NULL, "
            "lease_holder_kind = NULL, lease_holder_id = NULL, updated_at_ms = ? "
            "WHERE profile_alias = ? AND lease_holder = ?",
            (now, lease.profile_alias, lease.lease_id),
        )


class BrowserTaskService:
    """Creates policy-checked tasks and seals their evidence."""

    def __init__(
        self,
        store: Store,
        broker: BrowserSessionBroker | None = None,
        policy: BrowserPolicyEngine | None = None,
    ) -> None:
        self.store = store
        self.policy = policy or BrowserPolicyEngine()
        self.broker = broker or BrowserSessionBroker(store, self.policy)

    async def create_task(
        self,
        *,
        profile_alias: str,
        strategy: BrowserStrategy,
        autonomy_tier: AutonomyTier,
        action_class: ActionClass,
        target_domain: str,
        goal: str,
        mutating: bool = False,
        command_id: str | None = None,
        execution_id: str | None = None,
        capability_id: str | None = None,
        inputs: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> BrowserTask:
        self.policy.check_task(
            profile_alias=profile_alias, strategy=strategy, tier=autonomy_tier,
            action_class=action_class, target_domain=target_domain, mutating=mutating,
        )
        inputs = inputs or {}
        # §407 — a literal secret in task inputs is a policy failure, not a warning.
        self.policy.assert_no_secrets(inputs, context="task_inputs")

        now = int(time.time() * 1000) if now_ms is None else now_ms
        task = BrowserTask(
            task_id=new_id("browser_task"), command_id=command_id, execution_id=execution_id,
            capability_id=capability_id, profile_alias=profile_alias, strategy=strategy,
            autonomy_tier=autonomy_tier, action_class=action_class, target_domain=target_domain,
            goal=goal, inputs=inputs, status=BrowserTaskStatus.PENDING, started_at_ms=now,
        )
        await self.store.execute(
            """
            INSERT INTO browser_tasks(
              task_id, command_id, execution_id, capability_id, profile_alias, strategy,
              autonomy_tier, action_class, target_domain, goal, status, evidence_pointer,
              error_code, started_at_ms, completed_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?)
            """,
            (
                task.task_id, task.command_id, task.execution_id, task.capability_id,
                task.profile_alias, task.strategy.value, task.autonomy_tier.value,
                task.action_class.value, task.target_domain, task.goal, task.status.value,
                task.started_at_ms, now,
            ),
        )
        return task

    async def seal_evidence(
        self,
        *,
        task: BrowserTask,
        kind: str,
        url: str,
        dom: str | None = None,
        screenshot_bytes: bytes | None = None,
        extraction: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> BrowserEvidence:
        """§§184-185 — digests only, and refuse anything secret-shaped."""
        if is_reserved_evidence_kind(kind):
            # §7: a verdict is recorded by the verifier path, and a router step record by
            # the router's ledger (review I2 N-11) — never sealed by a caller.
            raise BrowserPolicyError("browser_evidence_kind_reserved_for_verifier")
        for payload, context in ((dom, "dom"), (extraction, "extraction")):
            if payload is not None:
                self.policy.assert_no_secrets(payload, context=f"evidence_{context}")

        assessment = InjectionAssessment.NONE_DETECTED
        if dom is not None or extraction is not None:
            assessment = self.policy.assess_injection({"dom": dom, "extraction": extraction})

        now = int(time.time() * 1000) if now_ms is None else now_ms
        evidence = BrowserEvidence(
            evidence_id=new_id("browser_evidence"),
            task_id=task.task_id,
            kind=kind,
            url_digest=digest({"url": url}),
            dom_digest=digest({"dom": dom}) if dom is not None else None,
            screenshot_digest=digest({"png_len": len(screenshot_bytes)}) if screenshot_bytes else None,
            extraction_digest=digest(extraction) if extraction is not None else None,
            source_trust="UNTRUSTED_EXTERNAL",
            injection_assessment=assessment,
            contains_secrets=False,
            created_at_ms=now,
            detail={"domain": task.target_domain, "tier": task.autonomy_tier.value},
        )
        await self.store.execute(
            """
            INSERT INTO browser_evidence(
              evidence_id, task_id, kind, url_digest, dom_digest, screenshot_digest,
              extraction_digest, source_trust, injection_assessment, contains_secrets,
              created_at_ms, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                evidence.evidence_id, evidence.task_id, evidence.kind, evidence.url_digest,
                evidence.dom_digest, evidence.screenshot_digest, evidence.extraction_digest,
                evidence.source_trust, evidence.injection_assessment.value,
                evidence.created_at_ms, Store.dumps(evidence.detail),
            ),
        )
        return evidence

    async def record_verification(
        self,
        *,
        task: BrowserTask,
        outcome: str,
        verifier: str,
        detail: str | None = None,
        assignment_id: str | None = None,
        now_ms: int | None = None,
    ) -> str:
        """Append the independent verifier's verdict for ``task``. Returns the evidence id."""
        now = int(time.time() * 1000) if now_ms is None else now_ms
        evidence_id = new_id("browser_evidence")
        record = {
            "outcome": str(outcome),
            "verifier": str(verifier)[:128],
            "detail": (str(detail)[:512] if detail is not None else None),
            "assignment_id": assignment_id,
        }
        await self.store.execute(
            """
            INSERT INTO browser_evidence(
              evidence_id, task_id, kind, url_digest, dom_digest, screenshot_digest,
              extraction_digest, source_trust, injection_assessment, contains_secrets,
              created_at_ms, evidence_json
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, 'VAN_VERIFIER', ?, 0, ?, ?)
            """,
            (
                evidence_id, task.task_id, VERIFICATION_EVIDENCE_KIND,
                digest({"url": task.target_domain}), digest(record),
                InjectionAssessment.NONE_DETECTED.value, now, Store.dumps(record),
            ),
        )
        return evidence_id

    async def verify_read_only_evidence(
        self, *, task: BrowserTask, evidence_id: str, now_ms: int | None = None
    ) -> str:
        """Verdict for a read-only (A1) task whose whole postcondition is "a page was read
        and its digest sealed" — e.g. an owner-authored watch. The durable evidence row is
        read back; the caller's word is not taken. Anything above A1 is UNVERIFIABLE here:
        a task that changes the world needs a real postcondition verifier."""
        outcome = "UNVERIFIABLE"
        detail = "read_only_verification_requires_A1"
        if task.action_class is ActionClass.A1:
            row = await self.store.fetchone(
                "SELECT task_id, kind FROM browser_evidence WHERE evidence_id = ?", (evidence_id,)
            )
            if row is None or str(row["task_id"]) != task.task_id:
                detail = "sealed_evidence_not_found_for_task"
            elif str(row["kind"]) == VERIFICATION_EVIDENCE_KIND:
                detail = "verdict_is_not_observation_evidence"
            else:
                outcome, detail = VERIFIED, f"sealed_evidence:{evidence_id}"
        await self.record_verification(
            task=task, outcome=outcome, verifier="READ_ONLY_EVIDENCE_READ_BACK", detail=detail,
            now_ms=now_ms,
        )
        return outcome

    async def latest_verification(self, task_id: str) -> str | None:
        """The outcome of the task's most recent verdict, or None when there is none."""
        row = await self.store.fetchone(
            "SELECT evidence_json FROM browser_evidence WHERE task_id = ? AND kind = ? "
            "ORDER BY created_at_ms DESC, rowid DESC LIMIT 1",
            (task_id, VERIFICATION_EVIDENCE_KIND),
        )
        if row is None:
            return None
        try:
            import json

            outcome = json.loads(str(row["evidence_json"])).get("outcome")
        except (ValueError, AttributeError):
            return "UNREADABLE"
        return str(outcome) if outcome is not None else "UNREADABLE"

    async def complete(
        self,
        *,
        task_id: str,
        status: BrowserTaskStatus,
        evidence_pointer: str | None = None,
        error_code: str | None = None,
        now_ms: int | None = None,
    ) -> None:
        """Set a task's end state. The one choke point for every caller.

        * Only a terminal status may be set (review I2 N-3). ``/complete`` used to accept any
          status, so a caller could write RESUME_AUTHORIZED on a task still waiting for the
          owner, or PENDING on one the owner had rejected, and then drive it. PENDING and
          RESUME_AUTHORIZED are refused here whoever asks.
        * COMPLETED only over a VERIFIED verdict (§7, review I M-2).
        * A task that has ended stays ended: the update is conditional on the current status
          not being terminal, so two racing callers cannot both write an end state.
        """
        if status not in COMPLETABLE_TASK_STATUSES:
            raise BrowserTaskTransitionRefused(task_id, None, status.value, "NOT_A_TERMINAL_STATUS")
        if status is BrowserTaskStatus.COMPLETED:
            latest = await self.latest_verification(task_id)
            if latest != VERIFIED:
                raise BrowserTaskNotVerified(task_id, latest)
        await self._write_status(
            task_id=task_id, status=status, evidence_pointer=evidence_pointer,
            error_code=error_code, completed=True, now_ms=now_ms,
        )

    async def hold_for_verification(
        self, *, task_id: str, error_code: str | None = None, now_ms: int | None = None
    ) -> None:
        """VERIFYING: a done claim nobody could verify. Not terminal, never success (§7)."""
        await self._write_status(
            task_id=task_id, status=BrowserTaskStatus.VERIFYING, evidence_pointer=None,
            error_code=error_code, completed=False, now_ms=now_ms,
        )

    async def _write_status(
        self, *, task_id: str, status: BrowserTaskStatus, evidence_pointer: str | None,
        error_code: str | None, completed: bool, now_ms: int | None,
    ) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        terminal = tuple(s.value for s in TERMINAL_TASK_STATUSES)
        placeholders = ", ".join("?" for _ in terminal)
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE browser_tasks SET status = ?, evidence_pointer = ?, error_code = ?, "
                f"completed_at_ms = ?, updated_at_ms = ? WHERE task_id = ? AND status NOT IN ({placeholders})",
                (status.value, evidence_pointer, error_code, now if completed else None, now,
                 task_id, *terminal),
            )
            await db.commit()
            changed = cur.rowcount
        if changed != 1:
            row = await self.store.fetchone("SELECT status FROM browser_tasks WHERE task_id = ?", (task_id,))
            current = None if row is None else str(row["status"])
            raise BrowserTaskTransitionRefused(
                task_id, current, status.value,
                "TASK_UNKNOWN" if row is None else "TASK_ALREADY_TERMINAL",
            )

__all__ = [
    "COMPLETABLE_TASK_STATUSES",
    "RESERVED_EVIDENCE_KINDS",
    "ROUTER_STEP_EVIDENCE_KIND",
    "TERMINAL_TASK_STATUSES",
    "VERIFICATION_EVIDENCE_KIND",
    "BrowserTaskTransitionRefused",
    "is_reserved_evidence_kind",
    "BrowserSessionBroker",
    "BrowserTaskNotVerified",
    "BrowserTaskService",
]
