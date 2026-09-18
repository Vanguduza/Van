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

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

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
from van_gateway.browser.subagent import (
    BrowserSubagentRunner,
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
    ) -> None:
        self.store = store
        self.settings = settings
        self.policy = policy or BrowserPolicyEngine()
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

    async def _create_boundary_escalation(
        self,
        *,
        task: BrowserTask,
        assignment: SubagentAssignment,
        result,
    ) -> dict[str, Any]:
        if self.decisions is None:
            await self.tasks.complete(
                task_id=task.task_id,
                status=BrowserTaskStatus.BLOCKED_UNSAFE,
                error_code="BROWSER_DECISION_SERVICE_UNAVAILABLE",
            )
            return {"status": BrowserTaskStatus.BLOCKED_UNSAFE.value}

        reason = result.stop_reason.value
        idem = f"browser-escalation:{task.task_id}:{reason}"
        existing = await self.store.fetchone(
            "SELECT escalation_id, decision_id, status FROM browser_escalations WHERE idempotency_key = ?",
            (idem,),
        )
        if existing is not None:
            await self.store.execute(
                "UPDATE browser_tasks SET status = ?, error_code = ?, updated_at_ms = ? WHERE task_id = ?",
                (BrowserTaskStatus.WAITING_FOR_OWNER.value, reason, int(time.time() * 1000), task.task_id),
            )
            return {
                "status": BrowserTaskStatus.WAITING_FOR_OWNER.value,
                "escalation_id": existing["escalation_id"],
                "decision_id": existing["decision_id"],
            }

        boundary_type = BrowserBoundaryType.OWNER_EXTENSION_REQUIRED
        summary = (
            "Browser task needs owner-authorized scope extension"
            if result.stop_reason is SubagentStop.SCOPE_VIOLATION
            else "Browser task needs a higher action-class authorization"
        )
        decision = await self.decisions.escalate(
            DecisionCreate(
                title=summary,
                body=(
                    f"Task {task.task_id} cannot continue inside its current browser assignment. "
                    f"Reason: {reason}. {result.detail or ''}".strip()
                ),
                source="browser",
                hermes_ref=assignment.turn_id,
                blocking=True,
            )
        )
        now = int(time.time() * 1000)
        escalation_id = f"besc_{task.task_id}_{reason.lower()}"
        if result.stop_reason is SubagentStop.SCOPE_VIOLATION:
            requested_domain = (result.detail or "").removeprefix("domain_outside_assignment:")
            requested_delta = {"allowed_domain": requested_domain}
        else:
            requested_class = (result.detail or "").split(">", 1)[0]
            requested_delta = {"action_class_ceiling": requested_class}
        await self.store.execute(
            """
            INSERT INTO browser_escalations(
              escalation_id, task_id, decision_id, boundary_type, reason_code,
              summary, why_required, risk_summary, current_scope_json,
              requested_scope_delta_json, current_action_class, required_action_class,
              pending_step, evidence_refs_json, session_lease_ref, idempotency_key,
              status, expires_at_ms, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, NULL, ?, ?)
            """,
            (
                escalation_id, task.task_id, decision.id, boundary_type.value, reason,
                summary, result.detail or reason, "Requires explicit owner authorization before continuation.",
                Store.dumps({
                    "allowed_domains": assignment.allowed_domains,
                    "action_class_ceiling": assignment.action_class_ceiling.value,
                    "autonomy_tier": assignment.autonomy_tier.value,
                }),
                Store.dumps(requested_delta), task.action_class.value,
                result.steps[-1].kind if result.steps else None,
                Store.dumps([]), idem, BrowserEscalationStatus.OPEN.value, now, now,
            ),
        )
        await self.store.execute(
            "UPDATE browser_tasks SET status = ?, error_code = ?, completed_at_ms = NULL, updated_at_ms = ? WHERE task_id = ?",
            (BrowserTaskStatus.WAITING_FOR_OWNER.value, reason, now, task.task_id),
        )
        return {
            "status": BrowserTaskStatus.WAITING_FOR_OWNER.value,
            "escalation_id": escalation_id,
            "decision_id": decision.id,
        }

    async def _sync_waiting_owner_decision(self, task: BrowserTask) -> BrowserTaskStatus:
        row = await self.store.fetchone(
            """
            SELECT e.escalation_id, e.status AS escalation_status,
                   e.current_scope_json, e.requested_scope_delta_json,
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
        if decision_status is DecisionStatus.APPROVED:
            current_scope = __import__("json").loads(str(row["current_scope_json"]))
            delta = __import__("json").loads(str(row["requested_scope_delta_json"]))
            approved_domains = list(current_scope.get("allowed_domains", []))
            if delta.get("allowed_domain") and delta["allowed_domain"] not in approved_domains:
                approved_domains.append(delta["allowed_domain"])
            approved_class = delta.get("action_class_ceiling") or current_scope.get("action_class_ceiling")
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
        approved_domains = set(__import__("json").loads(str(row["approved_domains_json"])))
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
            rows = await self.store.fetchall(
                """
                SELECT e.*, d.title AS decision_title, d.status AS decision_status
                FROM browser_escalations e
                JOIN decisions d ON d.id = e.decision_id
                ORDER BY e.updated_at_ms DESC
                LIMIT 100
                """
            )
            return [dict(r) for r in rows]

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
            return task.model_dump(mode="json")

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
            result = await self.runner.run(
                assignment=assignment, worker=self.worker, task=task
            )

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
