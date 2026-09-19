"""Rev 1.3 §§182-189, 219, 379, 385-387 — the Browser Fabric control surface.

The owner's 2026-09-18 decision granted the browser worker autonomy *as Hermes's
subagent*. That distinction is what this module exists to make structural rather
than aspirational:

* there is no route that starts a browser worker without an assignment. A run
  needs an assigning turn, a goal, a domain scope and a step budget, and
  `SubagentAssignment` will not construct without them;
* the assignment ceiling, the budget and the scope come from the request, but
  every one of them is then enforced by `BrowserSubagentRunner`, not by the
  worker that is being bounded;
* a run that discovers a legitimate scope or action-class extension checkpoints
  into WAITING_FOR_OWNER and creates a canonical owner decision; policy-forbidden
  paths remain hard stops. Approval never mutates the original assignment in place.

Everything here is internal-control only: Hermes is the only caller.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.observability import instruments
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserBoundaryType,
    BrowserEscalationStatus,
    BrowserStrategy,
    BrowserTask,
    BrowserTaskStatus,
)
from van_gateway.browser.policy import BrowserPolicyEngine, BrowserPolicyError
from van_gateway.browser.service import BrowserSessionBroker, BrowserTaskService
from van_gateway.automation.canonical import digest
from van_gateway.browser.worker import BrowserTaskPlan, SemanticWorkerUnavailable
from van_gateway.browser.subagent import (
    BrowserSubagentRunner,
    classify_boundary,
    SubagentAssignment,
    SubagentStop,
    SubagentWorker,
)
from van_gateway.config import Settings
from van_gateway.decisions.service import DecisionCreate, DecisionService, DecisionStatus
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.models import ActionClass
from van_gateway.storage.db import Store


class RegisterProfileBody(BaseModel):
    profile_alias: str
    #: §407 — a reference, never the credential itself.
    secret_ref: str | None = None


class CreateTaskBody(BaseModel):
    profile_alias: str
    strategy: BrowserStrategy
    autonomy_tier: AutonomyTier
    action_class: ActionClass
    target_domain: str
    goal: str
    mutating: bool = False
    command_id: str | None = None
    execution_id: str | None = None
    capability_id: str | None = None
    #: §5 — when the work belongs to a Mission, say so here and the task
    #: binds itself as an Activity. Without this the Missions page shows
    #: intentions while the real execution sits in browser_tasks.
    mission_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class LeaseBody(BaseModel):
    profile_alias: str
    task_id: str
    ttl_seconds: int | None = None


class ReleaseLeaseBody(BaseModel):
    lease_id: str
    profile_alias: str
    task_id: str


class EvidenceBody(BaseModel):
    kind: str
    url: str
    dom: str | None = None
    extraction: dict[str, Any] | None = None


class CompleteTaskBody(BaseModel):
    status: BrowserTaskStatus
    evidence_pointer: str | None = None
    error_code: str | None = None


class AssignmentBody(BaseModel):
    """§379 — what Hermes hands a worker, and the only way a worker starts.

    Every field except the optional deadline is a bound the worker cannot widen.
    There is deliberately no "unbounded" option and no way to omit the turn: an
    autonomous run with no assigning turn is an independent agent loop, which the
    security policy does not permit on any surface but Hermes itself.
    """

    task_id: str
    turn_id: str
    command_id: str
    goal: str
    allowed_domains: list[str] = Field(min_length=1)
    action_class_ceiling: ActionClass = ActionClass.A2
    autonomy_tier: AutonomyTier = AutonomyTier.L4_STAGEHAND_ACT
    max_steps: int = Field(default=12, ge=1, le=50)
    deadline_ms: int | None = None
    max_steps_without_progress: int = Field(default=3, ge=1, le=10)
    #: P2-BROW-001 — what a deterministic assignment is going to do, in order.
    #:
    #: The worker walks it and the runner grades each step against the bounds above, so a
    #: plan cannot widen an assignment: a planned step outside `allowed_domains` or above
    #: `action_class_ceiling` ends the task exactly as a model-chosen one would. Absent for
    #: a semantic tier, which selects its own actions and needs a runtime to do it.
    plan: BrowserTaskPlan | None = None


class BrowserApi:
    """`/v1/browser/*` — profiles, leases, tasks, evidence and subagent runs."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        policy: BrowserPolicyEngine | None = None,
        worker: SubagentWorker | None = None,
        decisions: DecisionService | None = None,
        binder: Any | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.policy = policy or BrowserPolicyEngine()
        # Optional so the browser fabric stays testable alone; create_app
        # always supplies one.
        self.binder = binder
        self.broker = BrowserSessionBroker(store, self.policy)
        self.tasks = BrowserTaskService(store, self.broker, self.policy)
        self.runner = BrowserSubagentRunner(self.policy)
        self.worker = worker
        self.decisions = decisions
        self.router = APIRouter(prefix="/v1/browser", tags=["browser"])
        self._install_routes()

    # ------------------------------------------------------------- guards

    def _require_internal(self, token: str | None) -> None:
        try:
            verify_internal_control(self.settings.internal_control_token, token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

    def _require_enabled(self) -> None:
        if not self.settings.browser_enabled:
            raise HTTPException(status_code=503, detail="BROWSER_FABRIC_DISABLED")

    async def _load_task(self, task_id: str) -> BrowserTask:
        row = await self.store.fetchone(
            "SELECT * FROM browser_tasks WHERE task_id = ?", (task_id,)
        )
        if row is None:
            raise HTTPException(status_code=404, detail="UNKNOWN_BROWSER_TASK")
        return BrowserTask(
            task_id=str(row["task_id"]),
            command_id=row["command_id"],
            execution_id=row["execution_id"],
            capability_id=row["capability_id"],
            profile_alias=str(row["profile_alias"]),
            strategy=BrowserStrategy(str(row["strategy"])),
            autonomy_tier=AutonomyTier(str(row["autonomy_tier"])),
            action_class=ActionClass(str(row["action_class"])),
            target_domain=str(row["target_domain"]),
            goal=str(row["goal"]),
            status=BrowserTaskStatus(str(row["status"])),
            evidence_pointer=row["evidence_pointer"],
            error_code=row["error_code"],
            started_at_ms=int(row["started_at_ms"]),
            completed_at_ms=row["completed_at_ms"],
        )

    #: §246-style bound on an open question: an approval prompt that nobody
    #: answers is not a pending task forever. The browser lease is long gone by
    #: then anyway, so a late approval would resume against a dead session.
    ESCALATION_TTL_MS = 24 * 60 * 60 * 1000

    @staticmethod
    def _requested_delta(result) -> tuple[dict[str, Any], ActionClass | None, str | None]:
        """Read what the worker was refused, without trusting how it is spelled.

        `result.detail` is assembled from worker-supplied values, so it is parsed
        defensively: anything that does not match the shape the runner produces
        yields no delta, which the classifier then treats as ambiguous.
        """
        detail = (result.detail or "").strip()
        if result.stop_reason is SubagentStop.SCOPE_VIOLATION:
            prefix = "domain_outside_assignment:"
            if not detail.startswith(prefix):
                return {}, None, None
            domain = detail[len(prefix):].strip()
            return ({"allowed_domain": domain} if domain else {}), None, domain or None
        if result.stop_reason is SubagentStop.ACTION_CLASS_VIOLATION:
            raw = detail.split(">", 1)[0].strip()
            try:
                requested = ActionClass(raw)
            except ValueError:
                return {}, None, None
            return {"action_class_ceiling": requested.value}, requested, None
        return {}, None, None

    async def _collect_evidence_refs(self, task: BrowserTask, result) -> list[str]:
        """§§184-185 — what the owner is shown to judge by, as digests only.

        An approval prompt with no evidence is one that gets approved on the
        strength of its own wording, which is exactly what this is here to stop.
        """
        rows = await self.store.fetchall(
            "SELECT evidence_id FROM browser_evidence WHERE task_id = ? "
            "ORDER BY created_at_ms DESC LIMIT 10",
            (task.task_id,),
        )
        refs = [f"browser-evidence://{row['evidence_id']}" for row in rows]
        for step in result.steps[-3:]:
            if step.observation_digest:
                refs.append(f"observation://{step.observation_digest}")
        return refs

    async def _release_task_lease(self, task: BrowserTask) -> str | None:
        """Waiting on a person can take hours; a held profile lease cannot.

        The lease is recorded on the escalation before it is dropped, so the
        owner can still see which session the question came from.
        """
        row = await self.store.fetchone(
            "SELECT lease_holder FROM browser_profiles WHERE profile_alias = ?",
            (task.profile_alias,),
        )
        lease_ref = None if row is None else row["lease_holder"]
        if lease_ref:
            await self.store.execute(
                "UPDATE browser_profiles SET lease_holder = NULL, lease_expires_at_ms = NULL, "
                "updated_at_ms = ? WHERE profile_alias = ? AND lease_holder = ?",
                (int(time.time() * 1000), task.profile_alias, lease_ref),
            )
        return lease_ref

    async def _terminate_without_asking(
        self, task: BrowserTask, result, *, boundary_type: BrowserBoundaryType
    ) -> dict[str, Any]:
        """A stop the owner is told about but never asked to approve.

        Reporting and asking are different acts. A forbidden or ambiguous stop is
        reported — it ends the task and is visible — but it never becomes a
        prompt, because a prompt the page can provoke is a way to obtain
        authority rather than a way to supervise it.
        """
        status = (
            BrowserTaskStatus.BLOCKED_POLICY
            if boundary_type is BrowserBoundaryType.POLICY_FORBIDDEN
            else BrowserTaskStatus.BLOCKED_UNSAFE
        )
        await self._release_task_lease(task)
        await self.tasks.complete(
            task_id=task.task_id, status=status, error_code=result.stop_reason.value,
            now_ms=int(time.time() * 1000),
        )
        return {
            "status": status.value,
            "boundary_type": boundary_type.value,
            "escalated": False,
            "reason_code": result.stop_reason.value,
        }

    async def _create_boundary_escalation(
        self,
        *,
        task: BrowserTask,
        assignment: SubagentAssignment,
        result,
    ) -> dict[str, Any]:
        delta, requested_class, requested_domain = self._requested_delta(result)
        boundary_type = classify_boundary(
            result.stop_reason,
            requested_action_class=requested_class,
            requested_domain=requested_domain,
        )
        if boundary_type is not BrowserBoundaryType.OWNER_EXTENSION_REQUIRED:
            return await self._terminate_without_asking(
                task, result, boundary_type=boundary_type
            )

        if self.decisions is None:
            await self._release_task_lease(task)
            await self.tasks.complete(
                task_id=task.task_id,
                status=BrowserTaskStatus.BLOCKED_UNSAFE,
                error_code="BROWSER_DECISION_SERVICE_UNAVAILABLE",
            )
            return {"status": BrowserTaskStatus.BLOCKED_UNSAFE.value, "escalated": False}

        reason = result.stop_reason.value
        # The key carries *what was asked for*, not just why the run stopped.
        # Keyed on the reason alone, a second overrun for a different domain
        # collided with the first and the owner was never asked about it.
        delta_digest = digest(delta)
        idem = f"browser-escalation:{task.task_id}:{reason}:{delta_digest}"
        existing = await self.store.fetchone(
            "SELECT escalation_id, decision_id, status FROM browser_escalations "
            "WHERE idempotency_key = ?",
            (idem,),
        )
        now = int(time.time() * 1000)
        if existing is not None:
            return await self._reuse_escalation(task, existing, reason=reason, now=now)

        summary = (
            f"Browser task needs access to {requested_domain}"
            if requested_domain
            else f"Browser task needs {delta.get('action_class_ceiling')} authorization"
        )
        why_required = self._why_required(assignment, result, delta, requested_domain)
        risk_summary = self._risk_summary(assignment, requested_domain, requested_class)
        evidence_refs = await self._collect_evidence_refs(task, result)
        lease_ref = await self._release_task_lease(task)
        pending_step = result.steps[-1].kind if result.steps else None

        decision = await self.decisions.escalate(
            DecisionCreate(
                title=summary,
                body=(
                    f"{why_required}\n\n{risk_summary}\n\n"
                    f"Task {task.task_id} stopped at step {len(result.steps)} of "
                    f"{assignment.max_steps} and is waiting for your decision. "
                    f"Approving widens this task only; it does not change the "
                    f"browser policy or any other task."
                ),
                source="browser",
                hermes_ref=assignment.turn_id,
                blocking=True,
            )
        )
        escalation_id = f"besc_{task.task_id}_{reason.lower()}_{delta_digest[-12:]}"
        await self.store.execute(
            """
            INSERT INTO browser_escalations(
              escalation_id, task_id, decision_id, boundary_type, reason_code,
              summary, why_required, risk_summary, current_scope_json,
              requested_scope_delta_json, current_action_class, required_action_class,
              pending_step, evidence_refs_json, session_lease_ref, idempotency_key,
              status, expires_at_ms, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                escalation_id, task.task_id, decision.id, boundary_type.value, reason,
                summary, why_required, risk_summary,
                Store.dumps({
                    "allowed_domains": assignment.allowed_domains,
                    "action_class_ceiling": assignment.action_class_ceiling.value,
                    "autonomy_tier": assignment.autonomy_tier.value,
                    "max_steps": assignment.max_steps,
                }),
                Store.dumps(delta), task.action_class.value,
                requested_class.value if requested_class else None,
                pending_step, Store.dumps(evidence_refs), lease_ref, idem,
                BrowserEscalationStatus.OPEN.value, now + self.ESCALATION_TTL_MS, now, now,
            ),
        )
        await self.store.execute(
            "UPDATE browser_tasks SET status = ?, error_code = ?, completed_at_ms = NULL, "
            "updated_at_ms = ? WHERE task_id = ?",
            (BrowserTaskStatus.WAITING_FOR_OWNER.value, reason, now, task.task_id),
        )
        return {
            "status": BrowserTaskStatus.WAITING_FOR_OWNER.value,
            "boundary_type": boundary_type.value,
            "escalated": True,
            "escalation_id": escalation_id,
            "decision_id": decision.id,
            "requested_scope_delta": delta,
            "expires_at_ms": now + self.ESCALATION_TTL_MS,
            "evidence_refs": evidence_refs,
            "pending_step": pending_step,
        }

    async def _reuse_escalation(
        self, task: BrowserTask, existing, *, reason: str, now: int
    ) -> dict[str, Any]:
        """The same question, asked again. What that means depends on the answer.

        Re-prompting for something already decided would either spam the owner or,
        worse, let a resolved decision be re-presented as if it were new.
        """
        status = BrowserEscalationStatus(str(existing["status"]))
        if status is BrowserEscalationStatus.OPEN:
            await self.store.execute(
                "UPDATE browser_tasks SET status = ?, error_code = ?, updated_at_ms = ? "
                "WHERE task_id = ?",
                (BrowserTaskStatus.WAITING_FOR_OWNER.value, reason, now, task.task_id),
            )
            return {
                "status": BrowserTaskStatus.WAITING_FOR_OWNER.value,
                "escalated": True,
                "escalation_id": existing["escalation_id"],
                "decision_id": existing["decision_id"],
            }
        # Already answered. An approval that did not unblock the run is not a
        # reason to ask again — the widening was granted and the wall is still
        # there, which is a different problem and belongs to whoever reads this.
        terminal = (
            BrowserTaskStatus.CANCELLED
            if status is BrowserEscalationStatus.REJECTED
            else BrowserTaskStatus.FAILED
        )
        error_code = (
            "BROWSER_ESCALATION_REJECTED"
            if status is BrowserEscalationStatus.REJECTED
            else "BROWSER_ESCALATION_ALREADY_SATISFIED"
        )
        await self._release_task_lease(task)
        await self.tasks.complete(
            task_id=task.task_id, status=terminal, error_code=error_code, now_ms=now
        )
        return {
            "status": terminal.value,
            "escalated": False,
            "escalation_id": existing["escalation_id"],
            "decision_id": existing["decision_id"],
            "reason_code": error_code,
        }

    @staticmethod
    def _why_required(
        assignment: SubagentAssignment, result, delta: dict[str, Any], requested_domain: str | None
    ) -> str:
        if requested_domain:
            return (
                f"The worker reached a link to {requested_domain}, which is outside "
                f"the {len(assignment.allowed_domains)} domain(s) this task was "
                f"assigned: {', '.join(assignment.allowed_domains)}."
            )
        requested = delta.get("action_class_ceiling", "a higher class")
        return (
            f"The worker proposed a {requested} action while this task is limited "
            f"to {assignment.action_class_ceiling.value}."
        )

    @staticmethod
    def _risk_summary(
        assignment: SubagentAssignment,
        requested_domain: str | None,
        requested_class: ActionClass | None,
    ) -> str:
        if requested_domain:
            return (
                f"Approving lets this one task read {requested_domain} at "
                f"{assignment.action_class_ceiling.value}. It does not admit the "
                f"domain for any other task and does not raise the action class."
            )
        return (
            f"Approving raises this one task's ceiling to "
            f"{requested_class.value if requested_class else 'the requested class'} "
            f"within its existing domain scope. Payments and irreversible actions "
            f"remain prohibited on the browser at every class."
        )

    async def _sync_waiting_owner_decision(self, task: BrowserTask) -> BrowserTaskStatus:
        row = await self.store.fetchone(
            """
            SELECT e.escalation_id, e.status AS escalation_status,
                   e.current_scope_json, e.requested_scope_delta_json,
                   e.expires_at_ms, e.boundary_type,
                   e.decision_id, d.status AS decision_status
            FROM browser_escalations e
            JOIN decisions d ON d.id = e.decision_id
            WHERE e.task_id = ?
            ORDER BY e.created_at_ms DESC
            LIMIT 1
            """,
            (task.task_id,),
        )
        if row is None:
            return task.status
        decision_status = DecisionStatus(str(row["decision_status"]))
        now = int(time.time() * 1000)

        # An approval that arrives after the question went stale is not an
        # approval of anything that still exists: the lease is long released and
        # the page the worker was looking at is gone. Expiry is therefore checked
        # before the decision, so a late yes cannot authorize a resume.
        expires_at = row["expires_at_ms"]
        escalation_status = BrowserEscalationStatus(str(row["escalation_status"]))
        if (
            expires_at is not None
            and now >= int(expires_at)
            and escalation_status is BrowserEscalationStatus.OPEN
        ):
            await self.store.execute(
                "UPDATE browser_escalations SET status = ?, updated_at_ms = ? "
                "WHERE escalation_id = ?",
                (BrowserEscalationStatus.EXPIRED.value, now, row["escalation_id"]),
            )
            await self.store.execute(
                "UPDATE browser_tasks SET status = ?, error_code = ?, completed_at_ms = ?, "
                "updated_at_ms = ? WHERE task_id = ?",
                (
                    BrowserTaskStatus.EXPIRED.value, "BROWSER_ESCALATION_EXPIRED",
                    now, now, task.task_id,
                ),
            )
            return BrowserTaskStatus.EXPIRED

        if decision_status is DecisionStatus.APPROVED:
            current_scope = json.loads(str(row["current_scope_json"]))
            delta = json.loads(str(row["requested_scope_delta_json"]))
            approved_domains = list(current_scope.get("allowed_domains", []))
            if delta.get("allowed_domain") and delta["allowed_domain"] not in approved_domains:
                approved_domains.append(delta["allowed_domain"])
            approved_class = delta.get("action_class_ceiling") or current_scope.get(
                "action_class_ceiling"
            )
            # §§108, 391 — belt and braces. `classify_boundary` refuses to raise
            # an A4 question at all, but a row written by an earlier build could
            # still carry one, and an owner-approved A4 browser grant must not be
            # able to exist in this table whatever asked for it.
            if approved_class in (ActionClass.A4.value, ActionClass.A5.value):
                await self.store.execute(
                    "UPDATE browser_escalations SET status = ?, boundary_type = ?, "
                    "updated_at_ms = ? WHERE escalation_id = ?",
                    (
                        BrowserEscalationStatus.REJECTED.value,
                        BrowserBoundaryType.POLICY_FORBIDDEN.value,
                        now, row["escalation_id"],
                    ),
                )
                await self.store.execute(
                    "UPDATE browser_tasks SET status = ?, error_code = ?, completed_at_ms = ?, "
                    "updated_at_ms = ? WHERE task_id = ?",
                    (
                        BrowserTaskStatus.BLOCKED_POLICY.value,
                        "BROWSER_ACTION_CLASS_NEVER_PERMITTED",
                        now, now, task.task_id,
                    ),
                )
                return BrowserTaskStatus.BLOCKED_POLICY
            authorization_id = f"bsauth_{row['escalation_id']}"
            await self.store.execute(
                """
                INSERT INTO browser_scope_authorizations(
                  authorization_id, escalation_id, task_id, decision_id,
                  approved_domains_json, approved_action_class_ceiling, status,
                  issued_at_ms, expires_at_ms, consumed_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, NULL, NULL)
                ON CONFLICT(escalation_id) DO NOTHING
                """,
                (
                    authorization_id, row["escalation_id"], task.task_id, row["decision_id"],
                    Store.dumps(approved_domains), approved_class, now,
                ),
            )
            await self.store.execute(
                "UPDATE browser_escalations SET status = ?, updated_at_ms = ? WHERE escalation_id = ?",
                (BrowserEscalationStatus.APPROVED.value, now, row["escalation_id"]),
            )
            await self.store.execute(
                "UPDATE browser_tasks SET status = ?, error_code = NULL, updated_at_ms = ? WHERE task_id = ?",
                (BrowserTaskStatus.RESUME_AUTHORIZED.value, now, task.task_id),
            )
            return BrowserTaskStatus.RESUME_AUTHORIZED
        if decision_status is DecisionStatus.REJECTED:
            await self.store.execute(
                "UPDATE browser_escalations SET status = ?, updated_at_ms = ? WHERE escalation_id = ?",
                (BrowserEscalationStatus.REJECTED.value, now, row["escalation_id"]),
            )
            await self.store.execute(
                "UPDATE browser_tasks SET status = ?, completed_at_ms = ?, updated_at_ms = ? WHERE task_id = ?",
                (BrowserTaskStatus.CANCELLED.value, now, now, task.task_id),
            )
            return BrowserTaskStatus.CANCELLED
        return BrowserTaskStatus.WAITING_FOR_OWNER


    async def _enforce_resume_authorization(
        self, task: BrowserTask, assignment: SubagentAssignment
    ) -> None:
        row = await self.store.fetchone(
            """
            SELECT authorization_id, approved_domains_json,
                   approved_action_class_ceiling, status
            FROM browser_scope_authorizations
            WHERE task_id = ? AND status = 'ACTIVE'
            ORDER BY issued_at_ms DESC
            LIMIT 1
            """,
            (task.task_id,),
        )
        if row is None:
            raise HTTPException(status_code=409, detail="BROWSER_RESUME_AUTHORIZATION_MISSING")
        approved_domains = set(json.loads(str(row["approved_domains_json"])))
        requested_domains = set(assignment.allowed_domains)
        if not requested_domains.issubset(approved_domains):
            raise HTTPException(status_code=409, detail="BROWSER_RESUME_SCOPE_EXCEEDS_APPROVAL")
        approved_class_raw = row["approved_action_class_ceiling"]
        if approved_class_raw:
            rank = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}
            approved_class = ActionClass(str(approved_class_raw))
            if rank[assignment.action_class_ceiling] > rank[approved_class]:
                raise HTTPException(status_code=409, detail="BROWSER_RESUME_CLASS_EXCEEDS_APPROVAL")
        await self.store.execute(
            "UPDATE browser_scope_authorizations SET status = 'CONSUMED', consumed_at_ms = ? WHERE authorization_id = ?",
            (int(time.time() * 1000), row["authorization_id"]),
        )

    # ------------------------------------------------------------- routes

    def _install_routes(self) -> None:
        router = self.router

        @router.get("/status")
        async def browser_status():
            rows = await self.store.fetchall(
                "SELECT status, COUNT(*) AS count FROM browser_tasks GROUP BY status"
            )
            counts = {str(r["status"]): int(r["count"]) for r in rows}
            waiting = await self.store.fetchone(
                "SELECT COUNT(*) AS count FROM browser_escalations WHERE status = ?",
                (BrowserEscalationStatus.OPEN.value,),
            )
            automation_rows = await self.store.fetchall(
                "SELECT status, COUNT(*) AS count FROM automation_runs GROUP BY status"
            )
            automation_counts = {str(r["status"]): int(r["count"]) for r in automation_rows}
            admitted = await self.store.fetchone(
                "SELECT COUNT(*) AS count FROM automation_capabilities WHERE lifecycle_state = 'ADMITTED'"
            )
            profiles = await self.store.fetchall(
                "SELECT profile_alias, persistence, authentication, mutation_policy, "
                "lease_holder, lease_expires_at_ms, last_verified_at_ms FROM browser_profiles "
                "ORDER BY profile_alias"
            )
            return {
                "enabled": self.settings.browser_enabled,
                "worker_configured": self.worker is not None,
                "tasks_by_status": counts,
                "waiting_for_owner": int(waiting["count"]) if waiting else 0,
                "automation_runs_by_status": automation_counts,
                "admitted_automation_capabilities": int(admitted["count"]) if admitted else 0,
                "profiles": [dict(r) for r in profiles],
            }

        @router.get("/policy")
        async def browser_policy():
            policy = self.policy.policy
            return {
                "policy_version": policy.policy_version,
                "admitted_domains": sorted(policy.admitted_domains),
                "profiles": {
                    alias: {
                        "persistence": spec.get("persistence"),
                        "authentication": spec.get("authentication"),
                        "mutation": spec.get("mutation"),
                        "download_policy": spec.get("download_policy"),
                    }
                    for alias, spec in policy.profiles.items()
                },
                "mutation_default_deny": policy.mutate_default_deny,
                "download_default_deny": policy.download_default_deny,
                "raw_cookie_export_forbidden": policy.raw_cookie_export_forbidden,
                "session_leases_required": policy.session_leases_required,
                "max_autonomy_tier": policy.max_autonomy_tier,
                "hard_prohibitions": [
                    "broker_live_order_submission",
                    "owner_signing_service",
                    "raw_cookie_export",
                    "raw_credential_export",
                    "automated_payment",
                ],
            }

        @router.get("/tasks/{task_id}/evidence")
        async def task_evidence(task_id: str):
            await self._load_task(task_id)
            rows = await self.store.fetchall(
                """
                SELECT evidence_id, kind, url_digest, dom_digest, screenshot_digest,
                       extraction_digest, source_trust, injection_assessment,
                       contains_secrets, created_at_ms, evidence_json
                FROM browser_evidence
                WHERE task_id = ?
                ORDER BY created_at_ms
                """,
                (task_id,),
            )
            return [dict(r) for r in rows]

        @router.get("/tasks")
        async def list_tasks():
            rows = await self.store.fetchall(
                "SELECT * FROM browser_tasks ORDER BY updated_at_ms DESC LIMIT 100"
            )
            return [dict(r) for r in rows]

        @router.get("/escalations")
        async def list_escalations():
            """What the owner is actually asked, with what it is asked about.

            The JSON columns are decoded here rather than handed over as strings,
            and `pending_step` and the evidence refs are surfaced: an approval
            prompt is only as good as what the person deciding can see.
            """
            rows = await self.store.fetchall(
                """
                SELECT e.*, d.title AS decision_title, d.status AS decision_status
                FROM browser_escalations e
                JOIN decisions d ON d.id = e.decision_id
                ORDER BY e.updated_at_ms DESC
                LIMIT 100
                """
            )
            now = int(time.time() * 1000)
            out = []
            for row in rows:
                item = dict(row)
                for column, key in (
                    ("current_scope_json", "current_scope"),
                    ("requested_scope_delta_json", "requested_scope_delta"),
                    ("evidence_refs_json", "evidence_refs"),
                ):
                    raw = item.pop(column, None)
                    try:
                        item[key] = json.loads(str(raw)) if raw else None
                    except ValueError:
                        item[key] = None
                expires_at = item.get("expires_at_ms")
                item["expired"] = expires_at is not None and now >= int(expires_at)
                item["actionable"] = (
                    item["status"] == BrowserEscalationStatus.OPEN.value
                    and not item["expired"]
                )
                out.append(item)
            return out

        @router.post("/profiles")
        async def register_profile(
            body: RegisterProfileBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§§182, 407 — the broker records a reference; it never holds a secret."""
            self._require_internal(x_van_internal_token)
            try:
                return await self.broker.register_profile(
                    profile_alias=body.profile_alias, secret_ref=body.secret_ref
                )
            except BrowserPolicyError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        @router.post("/leases")
        async def acquire_lease(
            body: LeaseBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§183 — exclusive while live. A second task is refused, not queued."""
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                lease = await self.broker.acquire_lease(
                    profile_alias=body.profile_alias, task_id=body.task_id,
                    ttl_seconds=body.ttl_seconds,
                )
            except BrowserPolicyError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return lease.model_dump(mode="json")

        @router.post("/leases/release")
        async def release_lease(
            body: ReleaseLeaseBody, x_van_internal_token: str | None = Header(default=None)
        ):
            self._require_internal(x_van_internal_token)
            from van_gateway.browser.models import PageLease

            await self.broker.release_lease(
                PageLease(
                    lease_id=body.lease_id, profile_alias=body.profile_alias,
                    task_id=body.task_id, acquired_at_ms=0, expires_at_ms=0,
                )
            )
            return {"released": True, "lease_id": body.lease_id}

        @router.post("/tasks")
        async def create_task(
            body: CreateTaskBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§§88, 184 — policy decides admissibility before a task exists at all."""
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                task = await self.tasks.create_task(
                    profile_alias=body.profile_alias, strategy=body.strategy,
                    autonomy_tier=body.autonomy_tier, action_class=body.action_class,
                    target_domain=body.target_domain, goal=body.goal, mutating=body.mutating,
                    command_id=body.command_id, execution_id=body.execution_id,
                    capability_id=body.capability_id, inputs=body.inputs,
                )
            except BrowserPolicyError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            # §5 — bind at creation, so a mission's Activity list is the truth
            # about what ran rather than something reconstructed later. A
            # binding refusal must not lose the task: the browser task is
            # already created and valid, so the refusal is reported alongside it.
            binding: dict[str, Any] | None = None
            if body.mission_id and self.binder is not None:
                try:
                    activity_id = await self.binder.bind_browser_task(
                        mission_id=body.mission_id, task_id=task.task_id
                    )
                    binding = {"mission_id": body.mission_id, "activity_id": activity_id}
                except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
                    binding = {
                        "mission_id": body.mission_id, "activity_id": None,
                        "error": type(exc).__name__, "detail": str(exc),
                    }
            payload = task.model_dump(mode="json")
            payload["mission_binding"] = binding
            return payload

        @router.get("/tasks/{task_id}")
        async def get_task(task_id: str):
            task = await self._load_task(task_id)
            evidence = await self.store.fetchall(
                "SELECT evidence_id, kind, injection_assessment, created_at_ms "
                "FROM browser_evidence WHERE task_id = ? ORDER BY created_at_ms",
                (task_id,),
            )
            return {
                "task": task.model_dump(mode="json"),
                "evidence": [dict(row) for row in evidence],
            }

        @router.post("/tasks/{task_id}/evidence")
        async def seal_evidence(
            task_id: str,
            body: EvidenceBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            """§§184-185 — digests only, and secret-shaped material is refused."""
            self._require_internal(x_van_internal_token)
            task = await self._load_task(task_id)
            try:
                evidence = await self.tasks.seal_evidence(
                    task=task, kind=body.kind, url=body.url, dom=body.dom,
                    extraction=body.extraction,
                )
            except BrowserPolicyError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return evidence.model_dump(mode="json")

        @router.post("/tasks/{task_id}/complete")
        async def complete_task(
            task_id: str,
            body: CompleteTaskBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            await self._load_task(task_id)
            await self.tasks.complete(
                task_id=task_id, status=body.status,
                evidence_pointer=body.evidence_pointer, error_code=body.error_code,
            )
            return {"task_id": task_id, "status": body.status.value}

        @router.post("/assignments")
        async def run_assignment(
            body: AssignmentBody, x_van_internal_token: str | None = Header(default=None)
        ):
            """§379 — the only way a browser worker runs autonomously.

            Hermes assigns; the runner enforces. The worker selects its own actions
            inside the assignment and cannot widen it: leaving the domain scope,
            exceeding the class ceiling, restating a different goal, or proposing a
            payment all end the task rather than prompting for more authority.
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            if self.worker is None:
                raise HTTPException(status_code=503, detail="BROWSER_WORKER_UNCONFIGURED")

            task = await self._load_task(body.task_id)
            status = task.status
            if status is BrowserTaskStatus.WAITING_FOR_OWNER:
                status = await self._sync_waiting_owner_decision(task)
            if status not in (BrowserTaskStatus.PENDING, BrowserTaskStatus.RESUME_AUTHORIZED):
                raise HTTPException(status_code=409, detail=f"BROWSER_TASK_NOT_RUNNABLE:{status.value}")

            assignment = SubagentAssignment(
                turn_id=body.turn_id, command_id=body.command_id, task_id=body.task_id,
                goal=body.goal, allowed_domains=list(body.allowed_domains),
                action_class_ceiling=body.action_class_ceiling,
                autonomy_tier=body.autonomy_tier, max_steps=body.max_steps,
                deadline_ms=body.deadline_ms,
                max_steps_without_progress=body.max_steps_without_progress,
            )
            if status is BrowserTaskStatus.RESUME_AUTHORIZED:
                await self._enforce_resume_authorization(task, assignment)
            # P2-BROW-001 — the worker is bound to *this* task and its plan before it
            # runs. A long-lived worker mutated per assignment would let two concurrent
            # assignments overwrite each other's task id, and the adapter is the only part
            # that is legitimately shared.
            worker = self.worker
            binder = getattr(worker, "for_task", None)
            if binder is not None:
                worker = binder(task, body.plan)
            try:
                result = await self.runner.run(
                    assignment=assignment, worker=worker, task=task
                )
            except SemanticWorkerUnavailable as exc:
                # An L2+ assignment asked for judgement about a page and no semantic
                # runtime is configured. Walking the deterministic plan instead would be
                # answering a different question and reporting success on this one.
                raise HTTPException(
                    status_code=503, detail=f"BROWSER_SEMANTIC_RUNTIME_UNAVAILABLE:{exc}"
                ) from exc

            escalation = None
            if result.stop_reason in (SubagentStop.SCOPE_VIOLATION, SubagentStop.ACTION_CLASS_VIOLATION):
                escalation = await self._create_boundary_escalation(
                    task=task, assignment=assignment, result=result
                )
            else:
                terminal_status = BrowserTaskStatus.COMPLETED
                if result.stop_reason in (SubagentStop.PAYMENT_REFUSED, SubagentStop.INJECTION_REFUSED):
                    terminal_status = BrowserTaskStatus.BLOCKED_POLICY
                elif result.stop_reason is SubagentStop.GOAL_DRIFT:
                    terminal_status = BrowserTaskStatus.BLOCKED_UNSAFE
                elif result.stop_reason is not SubagentStop.GOAL_ACHIEVED:
                    terminal_status = BrowserTaskStatus.FAILED
                await self.tasks.complete(
                    task_id=task.task_id,
                    status=terminal_status,
                    error_code=(
                        None if result.stop_reason is SubagentStop.GOAL_ACHIEVED
                        else result.stop_reason.value
                    ),
                    now_ms=int(time.time() * 1000),
                )
                # P3-OBS-002 — "browser task status" is one of Gate 11's named
                # metrics. Recorded at the one place a task reaches a terminal
                # status, so a new stop reason is counted without being added here.
                instruments.record_browser_task(terminal_status)
            if escalation is not None:
                instruments.record_browser_task("ESCALATED")
            return {
                "assignment_id": assignment.assignment_id,
                "task_id": task.task_id,
                "turn_id": assignment.turn_id,
                "stop_reason": result.stop_reason.value,
                "succeeded": result.succeeded,
                "step_count": result.step_count,
                "steps": [step.model_dump(mode="json") for step in result.steps],
                "extraction": result.extraction,
                "detail": result.detail,
                "escalation": escalation,
                # Stated so the subordination is observable, not just documented.
                "assigned_by_turn": assignment.turn_id,
                "bounds": {
                    "max_steps": assignment.max_steps,
                    "allowed_domains": assignment.allowed_domains,
                    "action_class_ceiling": assignment.action_class_ceiling.value,
                    "autonomy_tier": assignment.autonomy_tier.value,
                },
            }


__all__ = ["BrowserApi"]
