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
* a run that ends for any reason other than `GOAL_ACHIEVED` is reported with
  that reason and the task is completed as failed. Nothing retries itself and
  nothing escalates.

Everything here is internal-control only: Hermes is the only caller.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.browser.models import (
    AutonomyTier,
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
    ) -> None:
        self.store = store
        self.settings = settings
        self.policy = policy or BrowserPolicyEngine()
        self.broker = BrowserSessionBroker(store, self.policy)
        self.tasks = BrowserTaskService(store, self.broker, self.policy)
        self.runner = BrowserSubagentRunner(self.policy)
        self.worker = worker
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

    # ------------------------------------------------------------- routes

    def _install_routes(self) -> None:
        router = self.router

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
        async def get_task(task_id: str, x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
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
            if task.status is not BrowserTaskStatus.PENDING:
                raise HTTPException(status_code=409, detail="BROWSER_TASK_NOT_PENDING")

            assignment = SubagentAssignment(
                turn_id=body.turn_id, command_id=body.command_id, task_id=body.task_id,
                goal=body.goal, allowed_domains=list(body.allowed_domains),
                action_class_ceiling=body.action_class_ceiling,
                autonomy_tier=body.autonomy_tier, max_steps=body.max_steps,
                deadline_ms=body.deadline_ms,
                max_steps_without_progress=body.max_steps_without_progress,
            )
            result = await self.runner.run(
                assignment=assignment, worker=self.worker, task=task
            )

            # A stop is terminal. The task is completed either way, so a bounded
            # run never leaves a PENDING row that something else might resume.
            await self.tasks.complete(
                task_id=task.task_id,
                status=(
                    BrowserTaskStatus.COMPLETED
                    if result.stop_reason is SubagentStop.GOAL_ACHIEVED
                    else BrowserTaskStatus.FAILED
                ),
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
