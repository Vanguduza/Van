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

import asyncio
import json
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.observability import instruments
from van_gateway.browser.adapters import broker_lease_fence, harness_lease_fence
from van_gateway.browser.lane_gates import OwnerControlProbe
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry
from van_gateway.browser.acquisition_adapters import (
    AcquisitionRuntimeError,
    HttpAcquisitionRuntimeAdapter,
)
from van_gateway.browser.acquisition import (
    AcquisitionEvidenceLedger,
    AcquisitionFailure,
    AcquisitionFrontier,
    AcquisitionRoute,
    AcquisitionRouter,
    AcquisitionSignals,
    DomainSkillRegistry,
)
from van_gateway.browser.models import (
    AutonomyTier,
    BrowserBoundaryType,
    BrowserEscalationStatus,
    BrowserStrategy,
    BrowserTask,
    BrowserTaskStatus,
)
from van_gateway.browser.policy import BrowserPolicyEngine, BrowserPolicyError
from van_gateway.browser.task_scope import TaskScope, TaskScopeError, load_scope
from van_gateway.browser.service import (
    BrowserSessionBroker,
    BrowserTaskNotVerified,
    BrowserTaskRunInFlight,
    BrowserTaskService,
    BrowserTaskTransitionRefused,
    TERMINAL_TASK_STATUSES,
    network_owner_code,
)
from van_gateway.automation.canonical import digest
from van_gateway.automation.verifier import PostconditionSpec
from van_gateway.browser.worker import BrowserTaskPlan, SemanticWorkerUnavailable
from van_gateway.browser.subagent import (
    BrowserSubagentRunner,
    classify_boundary,
    SubagentAssignment,
    SubagentResult,
    SubagentStop,
    SubagentWorker,
)
from van_gateway.config import Settings
from van_gateway.decisions.service import DecisionCreate, DecisionService, DecisionStatus
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
    #: The owner-confirmed task-scope rule (docs/decisions/OWNER-DECISION-20260930-BROWSER-
    #: TASK-SCOPE.md, confirmation block; auth-20260930-owner-explicit-task-scope-confirmation) —
    #: the pages this task may act on, as URL prefixes (``https://host[:port][/path/]``), each inside ``target_domain``. Omitted:
    #: the task's ``target_domain`` origin is recorded. See ``browser/task_scope.py``.
    scope: list[str] | None = Field(default=None, max_length=32)


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


class AcquisitionEnqueueBody(BaseModel):
    url: str
    profile_alias: str = "public_research"
    source: str = "HERMES"
    parent_item_id: str | None = None
    depth: int = Field(default=0, ge=0)
    priority: int = Field(default=50, ge=0, le=100)
    preferred_route: AcquisitionRoute | None = None
    max_attempts: int = Field(default=5, ge=1, le=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcquisitionClaimBody(BaseModel):
    worker_id: str = Field(min_length=1, max_length=160)
    lease_seconds: int = Field(default=120, ge=30, le=3600)


class AcquisitionLeaseMutationBody(BaseModel):
    worker_id: str = Field(min_length=1, max_length=160)
    lease_token: str = Field(min_length=8, max_length=256)


class AcquisitionRenewBody(AcquisitionLeaseMutationBody):
    lease_seconds: int = Field(default=120, ge=30, le=3600)


class AcquisitionCheckpointBody(AcquisitionLeaseMutationBody):
    checkpoint_ref: str = Field(min_length=1, max_length=2048)


class AcquisitionRouteBody(AcquisitionLeaseMutationBody):
    signals: AcquisitionSignals


class AcquisitionCompleteBody(AcquisitionLeaseMutationBody):
    checkpoint_ref: str | None = Field(default=None, max_length=2048)


class AcquisitionFailBody(AcquisitionLeaseMutationBody):
    failure: AcquisitionFailure
    error_code: str = Field(min_length=1, max_length=256)
    retry_after_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class AcquisitionExecuteBody(AcquisitionLeaseMutationBody):
    signals: AcquisitionSignals = Field(default_factory=AcquisitionSignals)
    recon_depth: int = Field(default=2, ge=1, le=3)
    crawl_max_pages: int = Field(default=100, ge=1, le=1000)
    crawl_max_depth: int = Field(default=3, ge=0, le=6)
    crawl_max_concurrency: int = Field(default=6, ge=1, le=12)
    crawl_max_tasks_per_minute: int = Field(default=120, ge=1, le=240)
    crawl_timeout_seconds: int = Field(default=300, ge=30, le=1800)
    crawl_respect_robots_txt: bool = True


class DomainSkillProposeBody(BaseModel):
    domain: str = Field(min_length=1, max_length=253)
    goal_class: str = Field(min_length=1, max_length=160)
    route: AcquisitionRoute
    artifact_ref: str = Field(min_length=1, max_length=2048)
    site_fingerprint: str | None = Field(default=None, max_length=512)
    success_assertions: list[dict[str, Any]] = Field(default_factory=list)
    failure_signatures: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    golden_case_refs: list[str] = Field(default_factory=list)


class DomainSkillQualifyBody(BaseModel):
    replay_passed: bool
    evidence_refs: list[str] = Field(min_length=1)


class DomainSkillQuarantineBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ref: str | None = Field(default=None, max_length=2048)


class DomainSkillCanaryBody(BaseModel):
    passed: bool
    evidence_ref: str = Field(min_length=1, max_length=2048)
    observed_fingerprint: str | None = Field(default=None, max_length=512)
    latency_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class AcquisitionEvidenceBody(BaseModel):
    kind: str = Field(min_length=1, max_length=128)
    content_digest: str = Field(min_length=71, max_length=71)
    source_url: str
    route: AcquisitionRoute | None = None
    artifact_ref: str | None = Field(default=None, max_length=2048)
    signature_ref: str | None = Field(default=None, max_length=2048)
    byte_size: int = Field(default=0, ge=0)
    detail: dict[str, Any] = Field(default_factory=dict)


class AcquisitionTelemetryBody(BaseModel):
    route: AcquisitionRoute
    success: bool
    latency_ms: int = Field(default=0, ge=0)
    byte_count: int = Field(default=0, ge=0)
    verified_records: int = Field(default=0, ge=0)
    cost_micros: int = Field(default=0, ge=0)


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
    #: Select the exact owner-delegated target rather than an independent profile worker.
    interactive_session_id: str | None = Field(default=None, min_length=1, max_length=128)
    #: Owner decision 2026-09-29 §7 — what must be observably true for the worker's "done"
    #: to count. Absent means a "done" claim is UNVERIFIABLE, never COMPLETED.
    postcondition: PostconditionSpec | None = None


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
        verifier: Any | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.policy = policy or BrowserPolicyEngine()
        # Optional so the browser fabric stays testable alone; create_app
        # always supplies one.
        self.binder = binder
        self.broker = BrowserSessionBroker(store, self.policy)
        self.tasks = BrowserTaskService(store, self.broker, self.policy)
        # Review I M-4 / owner decision 2026-09-29 §9: owner takeover preempts the
        # assignment path exactly as it preempts the B5 router — the same probe.
        self.runner = BrowserSubagentRunner(self.policy, owner_control_probe=OwnerControlProbe(store))
        self.acquisition = AcquisitionFrontier(store)
        self.acquisition_evidence = AcquisitionEvidenceLedger(store)
        self.domain_skills = DomainSkillRegistry(store)
        self.acquisition_runtime = HttpAcquisitionRuntimeAdapter(
            ExternalRuntimeRegistry(store),
            base_url=settings.browser_acquisition_base_url,
            enabled=settings.browser_enabled,
            expected_version=settings.browser_acquisition_expected_version or None,
        )
        self.worker = worker
        #: Owner decision 2026-09-29 §7 — the independent postcondition verifier. None means
        #: every "done" claim is UNVERIFIABLE: fail closed, never COMPLETED.
        self.verifier = verifier
        #: Programme B / B5 — set by create_app; None keeps the fabric testable alone.
        self.interaction_router: Any | None = None
        self.decisions = decisions
        self.router = APIRouter(prefix="/v1/browser", tags=["browser"])
        self._install_routes()

    # ------------------------------------------------------------- guards

    def _require_internal(self, token: str | None) -> None:
        # GAP-F-009: scope-aware, same authority as the middleware.
        require_scoped_internal(self.settings, token, ControlScope.BROWSER)

    def _require_enabled(self) -> None:
        if not self.settings.browser_enabled:
            raise HTTPException(status_code=503, detail="BROWSER_FABRIC_DISABLED")

    async def _task_scope(self, row) -> TaskScope | None:
        """Task-scope rule (owner-confirmed 2026-09-30: docs/decisions/OWNER-DECISION-20260930-
        BROWSER-TASK-SCOPE.md, confirmation block; auth-20260930-owner-explicit-task-scope-
        confirmation) — the scope in the task's truth: what was
        recorded at creation, widened by the domain the owner approved for *this* task.

        Review I6 m1: only the approved *delta* widens it — the ``allowed_domain`` of the
        escalation the owner answered, not every domain the authorization row lists (those
        include the task's current domains, and adding them origin-wide would drop a declared
        path limit). A domain the recorded scope already names is not widened at all (the
        owner approved a domain, not the removal of that domain's path limit). Only an
        ACTIVE authorization that has not expired counts: a REVOKED, EXPIRED or CONSUMED
        row, or one past ``expires_at_ms``, widens nothing. (``consume_resume_authorization``
        consumes the row for the run it authorizes; that run's task was loaded, and its scope
        read, while the row was still ACTIVE.) Missing or unreadable recorded scope stays
        None — an approval does not invent the rest of a scope — and every action on the
        task is refused."""
        scope = load_scope(row["scope_json"] if "scope_json" in row.keys() else None)
        if scope is None:
            return None
        grants = await self.store.fetchall(
            "SELECT a.authorization_id, a.approved_domains_json, e.requested_scope_delta_json "
            "FROM browser_scope_authorizations a "
            "JOIN browser_escalations e ON e.escalation_id = a.escalation_id "
            "WHERE a.task_id = ? AND a.status = 'ACTIVE' "
            "AND (a.expires_at_ms IS NULL OR a.expires_at_ms > ?) "
            "ORDER BY a.issued_at_ms",
            (str(row["task_id"]), int(time.time() * 1000)),
        )
        declared_hosts = scope.hosts()
        for grant in grants:
            try:
                approved = json.loads(str(grant["approved_domains_json"]))
                delta = json.loads(str(grant["requested_scope_delta_json"]))
            except ValueError:
                continue
            domain = delta.get("allowed_domain") if isinstance(delta, dict) else None
            if not isinstance(domain, str) or not domain.strip() or not isinstance(approved, list) or domain not in approved:
                continue
            if domain.strip().lower().rstrip(".") in declared_hosts:
                continue
            try:
                scope = scope.with_origin(domain, f"OWNER_APPROVED:{grant['authorization_id']}")
            except TaskScopeError:
                continue  # unit G14: an approval never widens a task onto the zone overlay
        return scope

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
            scope=await self._task_scope(row),
            # Network-effect guard: admitted as mutating only when the row says so (1).
            mutating=("mutating" in row.keys() and row["mutating"] == 1),
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
            "SELECT lease_holder FROM browser_profiles WHERE profile_alias = ? "
            "AND lease_holder_kind = 'TASK' AND lease_holder_id = ?",
            (task.profile_alias, task.task_id),
        )
        lease_ref = None if row is None else row["lease_holder"]
        if lease_ref:
            # Unit G11 (review I7 MAJOR-1): the Harness freezes the lease's page and removes its
            # network interception before the lease is dropped.
            await self.broker.release_page(profile_alias=task.profile_alias, lease_id=lease_ref)
            await self.store.execute(
                "UPDATE browser_profiles SET lease_holder = NULL, lease_expires_at_ms = NULL, "
                "lease_holder_kind = NULL, lease_holder_id = NULL, updated_at_ms = ? "
                "WHERE profile_alias = ? AND lease_holder = ? AND lease_holder_id = ?",
                (int(time.time() * 1000), task.profile_alias, lease_ref, task.task_id),
            )
        return lease_ref

    async def _hand_late_block_to_owner(self, task_id: str, code: str) -> str:
        """Unit G15 (review I8 MAJOR-2) — a write the lease's guard blocked (or detected, or a
        guard it lost) that the Harness reported only when the lease was given back goes to
        the owner, as ``/interaction/step`` does: WAITING_FOR_OWNER with ``OWNER_TAKEOVER:
        <code>`` through the guarded writer. A task already in an end state stays there (the
        writer refuses); callers order their release before any end state they write. Returns
        the task's status afterwards."""
        from van_gateway.browser.models import BrowserTaskStatus as _Status

        try:
            await self.tasks.set_working_status(
                task_id=task_id, status=_Status.WAITING_FOR_OWNER,
                error_code=f"OWNER_TAKEOVER:{code}"[:200],
            )
        except BrowserTaskTransitionRefused as exc:
            return exc.current or "UNKNOWN"
        instruments.record_browser_task(_Status.WAITING_FOR_OWNER)
        return _Status.WAITING_FOR_OWNER.value

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
        # Review I3 MINOR-2: the task moves to WAITING_FOR_OWNER through the guarded writer
        # before anything is put to the owner. A task that ended while its run was in flight
        # (e.g. CANCELLED) refuses here, and no question is raised for it.
        await self.tasks.set_working_status(
            task_id=task.task_id, status=BrowserTaskStatus.WAITING_FOR_OWNER, error_code=reason,
        )
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
                request_id="browser-" + digest(idem),
                body=(
                    f"{why_required}\n\n{risk_summary}\n\n"
                    f"Task {task.task_id} stopped at step {len(result.steps)} of "
                    f"{assignment.max_steps} and is waiting for your decision. "
                    f"Your answer is advisory. Widening scope requires a fresh "
                    f"signed command with exact authority and parameters."
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
            # Already WAITING_FOR_OWNER (set by the caller through the guarded writer).
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
                f"A fresh sealed command is required to let this task read {requested_domain} at "
                f"{assignment.action_class_ceiling.value}. It does not admit the "
                f"domain for any other task and does not raise the action class."
            )
        return (
            f"A fresh sealed command is required to raise this task's ceiling to "
            f"{requested_class.value if requested_class else 'the requested class'} "
            f"within its existing domain scope. Payments and irreversible actions "
            f"remain prohibited on the browser at every class."
        )

    async def _sync_task_status(
        self, task: BrowserTask, status: BrowserTaskStatus, error_code: str | None, now: int
    ) -> BrowserTaskStatus:
        """The owner-decision sync's task write, through the guarded writers (I3 MINOR-2).

        An end state goes through ``complete()``, RESUME_AUTHORIZED through
        ``set_working_status`` (from WAITING_FOR_OWNER only). If the task ended meanwhile, the
        write is refused and the task's actual status is returned: the sync never moves a
        task out of an end state.
        """
        try:
            if status is BrowserTaskStatus.RESUME_AUTHORIZED:
                await self.tasks.set_working_status(
                    task_id=task.task_id, status=status, error_code=error_code, now_ms=now,
                )
            else:
                await self.tasks.complete(
                    task_id=task.task_id, status=status, error_code=error_code, now_ms=now,
                )
        except BrowserTaskTransitionRefused:
            row = await self.store.fetchone(
                "SELECT status FROM browser_tasks WHERE task_id = ?", (task.task_id,)
            )
            return BrowserTaskStatus(str(row["status"])) if row is not None else task.status
        return status

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
            return await self._sync_task_status(
                task, BrowserTaskStatus.EXPIRED, "BROWSER_ESCALATION_EXPIRED", now,
            )

        if decision_status in {DecisionStatus.APPROVED, DecisionStatus.ANSWERED}:
            delta = json.loads(str(row["requested_scope_delta_json"]))
            if delta.get("action_class_ceiling") in {"A4", "A5"}:
                await self.store.execute("UPDATE browser_tasks SET status=?,error_code=?,updated_at_ms=? WHERE task_id=?",
                    (BrowserTaskStatus.BLOCKED_POLICY.value, "BROWSER_LEGACY_SCOPE_GRANT_FORBIDDEN", now, task.task_id))
                return BrowserTaskStatus.BLOCKED_POLICY
            # An advisory answer is evidence of the owner's preference, never a
            # capability grant. A new exact sealed command is required to widen
            # domain, action class or resume a boundary-stopped task.
            await self.store.execute(
                "UPDATE browser_tasks SET error_code=?,updated_at_ms=? WHERE task_id=?",
                ("BROWSER_FRESH_SEALED_COMMAND_REQUIRED", now, task.task_id),
            )
            return BrowserTaskStatus.WAITING_FOR_OWNER
        if decision_status is DecisionStatus.REJECTED:
            await self.store.execute(
                "UPDATE browser_escalations SET status = ?, updated_at_ms = ? WHERE escalation_id = ?",
                (BrowserEscalationStatus.REJECTED.value, now, row["escalation_id"]),
            )
            return await self._sync_task_status(task, BrowserTaskStatus.CANCELLED, None, now)
        return BrowserTaskStatus.WAITING_FOR_OWNER


    async def _enforce_resume_authorization(
        self, task: BrowserTask, assignment: SubagentAssignment
    ) -> None:
        await self.consume_resume_authorization(
            task, requested_domains=list(assignment.allowed_domains),
            requested_class=assignment.action_class_ceiling,
        )

    async def consume_resume_authorization(
        self,
        task: BrowserTask,
        *,
        requested_domains: list[str] | None = None,
        requested_class: ActionClass | None = None,
    ) -> dict[str, Any]:
        """Bind one run of a RESUME_AUTHORIZED task to the owner's ACTIVE authorization.

        The status alone is not the owner's answer; the authorization row is, and it is
        single-use. Used by ``/assignments`` (which refuses a scope or class above the
        approval) and by ``/interaction/step`` (review I2 N-4, which caps its ceiling at the
        approved class). The consumption is conditional on the row still being ACTIVE, so two
        concurrent resumes cannot both spend it. Returns ``{"authorization_id",
        "approved_action_class_ceiling", "approved_domains"}``.
        """
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
        approved_domains = list(json.loads(str(row["approved_domains_json"])))
        if requested_domains is not None and not set(requested_domains).issubset(set(approved_domains)):
            raise HTTPException(status_code=409, detail="BROWSER_RESUME_SCOPE_EXCEEDS_APPROVAL")
        approved_class_raw = row["approved_action_class_ceiling"]
        approved_class = ActionClass(str(approved_class_raw)) if approved_class_raw else None
        if approved_class is not None and requested_class is not None:
            rank = {ActionClass.A1: 1, ActionClass.A2: 2, ActionClass.A3: 3, ActionClass.A4: 4, ActionClass.A5: 5}
            if rank.get(requested_class, 99) > rank.get(approved_class, 0):
                raise HTTPException(status_code=409, detail="BROWSER_RESUME_CLASS_EXCEEDS_APPROVAL")
        async with self.store.connection() as db:
            cur = await db.execute(
                "UPDATE browser_scope_authorizations SET status = 'CONSUMED', consumed_at_ms = ? "
                "WHERE authorization_id = ? AND status = 'ACTIVE'",
                (int(time.time() * 1000), row["authorization_id"]),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise HTTPException(status_code=409, detail="BROWSER_RESUME_AUTHORIZATION_MISSING")
        return {
            "authorization_id": str(row["authorization_id"]),
            "approved_action_class_ceiling": approved_class.value if approved_class is not None else None,
            "approved_domains": approved_domains,
        }

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
            acquisition_counts = await self.acquisition.stats()
            acquisition_runtime = await self.acquisition_runtime.status()
            crawlee_evidence = await self.acquisition_runtime.registry.get_evidence(
                "web_acquisition_crawlee"
            )
            return {
                "enabled": self.settings.browser_enabled,
                "acquisition_by_state": acquisition_counts,
                "acquisition_runtime": acquisition_runtime.model_dump(mode="json"),
                "crawlee_live_qualified": (
                    crawlee_evidence is not None
                    and crawlee_evidence.runtime_version == "1.10.2"
                    and not crawlee_evidence.contains_secrets
                ),
                "crawlee_evidence_pointer": (
                    crawlee_evidence.evidence_pointer if crawlee_evidence else None
                ),
                "worker_configured": self.worker is not None,
                "tasks_by_status": counts,
                "waiting_for_owner": int(waiting["count"]) if waiting else 0,
                "automation_runs_by_status": automation_counts,
                "admitted_automation_capabilities": int(admitted["count"]) if admitted else 0,
                "profiles": [dict(r) for r in profiles],
            }

        @router.get("/acquisition/items/{item_id}")
        async def acquisition_item(
            item_id: str, x_van_internal_token: str | None = Header(default=None)
        ):
            self._require_internal(x_van_internal_token)
            row = await self.store.fetchone(
                "SELECT * FROM web_acquisition_items WHERE item_id = ?", (item_id,)
            )
            if row is None:
                raise HTTPException(status_code=404, detail="UNKNOWN_WEB_ACQUISITION_ITEM")
            return self.acquisition._row_to_item(row).model_dump(mode="json")

        @router.post("/acquisition/items")
        async def acquisition_enqueue(
            body: AcquisitionEnqueueBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                self.policy.check_profile(body.profile_alias)
                item = await self.acquisition.enqueue(**body.model_dump())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return item.model_dump(mode="json")

        @router.post("/acquisition/claim")
        async def acquisition_claim(
            body: AcquisitionClaimBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            item = await self.acquisition.claim(
                worker_id=body.worker_id, lease_seconds=body.lease_seconds
            )
            return None if item is None else item.model_dump(mode="json")

        @router.post("/acquisition/items/{item_id}/start")
        async def acquisition_start(
            item_id: str,
            body: AcquisitionLeaseMutationBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                await self.acquisition.start(item_id, **body.model_dump())
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"ok": True}

        @router.post("/acquisition/items/{item_id}/renew")
        async def acquisition_renew(
            item_id: str,
            body: AcquisitionRenewBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                item = await self.acquisition.renew_lease(item_id, **body.model_dump())
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return item.model_dump(mode="json")

        @router.post("/acquisition/items/{item_id}/route")
        async def acquisition_route(
            item_id: str,
            body: AcquisitionRouteBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            row = await self.store.fetchone(
                "SELECT * FROM web_acquisition_items WHERE item_id = ?", (item_id,)
            )
            if row is None:
                raise HTTPException(status_code=404, detail="UNKNOWN_WEB_ACQUISITION_ITEM")
            item = self.acquisition._row_to_item(row)
            decision = AcquisitionRouter.decide(item, body.signals)
            try:
                await self.acquisition.set_route(
                    item_id, route=decision.route, worker_id=body.worker_id,
                    lease_token=body.lease_token,
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"route": decision.route.value, "reason": decision.reason}

        @router.post("/acquisition/items/{item_id}/checkpoint")
        async def acquisition_checkpoint(
            item_id: str,
            body: AcquisitionCheckpointBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                await self.acquisition.checkpoint(item_id, **body.model_dump())
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"ok": True}

        @router.post("/acquisition/items/{item_id}/complete")
        async def acquisition_complete(
            item_id: str,
            body: AcquisitionCompleteBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                await self.acquisition.complete(item_id, **body.model_dump())
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"ok": True}

        @router.post("/acquisition/items/{item_id}/fail")
        async def acquisition_fail(
            item_id: str,
            body: AcquisitionFailBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                state = await self.acquisition.fail(item_id, **body.model_dump())
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"state": state.value}

        @router.post("/acquisition/items/{item_id}/execute")
        async def acquisition_execute(
            item_id: str,
            body: AcquisitionExecuteBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            """Execute one leased public acquisition item through a qualified worker.

            Authenticated/account-visible items intentionally stop here: they are
            transformed into normal Browser Fabric work by Hermes so existing
            profile leases, secret indirection and subagent bounds remain authoritative.
            """
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            row = await self.store.fetchone(
                "SELECT * FROM web_acquisition_items WHERE item_id = ?", (item_id,)
            )
            if row is None:
                raise HTTPException(status_code=404, detail="UNKNOWN_WEB_ACQUISITION_ITEM")
            item = self.acquisition._row_to_item(row)
            try:
                decision = AcquisitionRouter.decide(item, body.signals)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            if decision.route in {AcquisitionRoute.HARNESS, AcquisitionRoute.STAGEHAND}:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ACQUISITION_MANAGED_BROWSER_REQUIRED",
                        "route": decision.route.value,
                        "profile_alias": item.profile_alias,
                    },
                )

            try:
                await self.acquisition.set_route(
                    item_id, route=decision.route,
                    worker_id=body.worker_id, lease_token=body.lease_token,
                )
                await self.acquisition.renew_lease(
                    item_id,
                    worker_id=body.worker_id,
                    lease_token=body.lease_token,
                    lease_seconds=(
                        min(3600, body.crawl_timeout_seconds + 60)
                        if decision.route is AcquisitionRoute.CRAWLEE_CRAWL
                        else 180
                    ),
                )
                await self.acquisition.start(
                    item_id, worker_id=body.worker_id, lease_token=body.lease_token
                )
            except RuntimeError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            started = int(time.time() * 1000)
            try:
                if decision.route in {
                    AcquisitionRoute.DIRECT_HTTP,
                    AcquisitionRoute.SCRAPLING_HTTP,
                }:
                    result = await self.acquisition_runtime.fetch_http(item)
                elif decision.route is AcquisitionRoute.SCRAPLING_BROWSER:
                    result = await self.acquisition_runtime.fetch_browser(item)
                elif decision.route is AcquisitionRoute.KATANA_RECON:
                    result = await self.acquisition_runtime.recon(
                        item, depth=body.recon_depth
                    )
                elif decision.route is AcquisitionRoute.CRAWLEE_CRAWL:
                    result = await self.acquisition_runtime.crawl(
                        item,
                        max_pages=body.crawl_max_pages,
                        max_depth=body.crawl_max_depth,
                        max_concurrency=body.crawl_max_concurrency,
                        max_tasks_per_minute=body.crawl_max_tasks_per_minute,
                        timeout_seconds=body.crawl_timeout_seconds,
                        respect_robots_txt=body.crawl_respect_robots_txt,
                    )
                    handoff = await self.acquisition.enqueue_many(
                        [str(url) for url in result.get("discovered_urls", [])],
                        profile_alias=item.profile_alias,
                        source="CRAWLEE_DISCOVERY",
                        parent_item_id=item.item_id,
                        depth=item.depth + 1,
                        priority=max(0, item.priority - 1),
                        max_attempts=item.max_attempts,
                        metadata={"discovered_by": "CRAWLEE_CRAWL"},
                        expected_domain=item.domain,
                        max_urls=2000,
                    )
                    result["frontier_handoff"] = handoff
                else:
                    raise AcquisitionRuntimeError(
                        "WEB_ACQUISITION_ROUTE_NOT_EXECUTABLE",
                        decision.route.value,
                    )

                content_digest = str(result.get("content_digest") or digest(result))
                byte_count = int(result.get("byte_size") or len(Store.dumps(result).encode("utf-8")))
                evidence = await self.acquisition_evidence.record(
                    item_id=item_id,
                    kind="PUBLIC_WEB_ACQUISITION",
                    content_digest=content_digest,
                    source_url=item.canonical_url,
                    route=decision.route,
                    byte_size=byte_count,
                    detail={
                        "runtime": "web_acquisition",
                        "representation": result.get("representation"),
                        "status": result.get("status"),
                    },
                )
                elapsed = max(0, int(time.time() * 1000) - started)
                await self.acquisition.record_telemetry(
                    item_id,
                    route=decision.route,
                    success=True,
                    latency_ms=elapsed,
                    byte_count=byte_count,
                    verified_records=(
                        int(result.get("visited_count") or 0)
                        if decision.route is AcquisitionRoute.CRAWLEE_CRAWL
                        else 0
                    ),
                    cost_micros=0,
                )
                await self.acquisition.complete(
                    item_id,
                    worker_id=body.worker_id,
                    lease_token=body.lease_token,
                    checkpoint_ref=f"web-acquisition-evidence://{evidence.evidence_id}",
                )
                response_result = result
                if decision.route is AcquisitionRoute.CRAWLEE_CRAWL:
                    response_result = dict(result)
                    discovered_urls = list(response_result.pop("discovered_urls", []))
                    response_result["discovered_url_sample"] = discovered_urls[:100]
                    response_result["discovered_urls_returned"] = len(
                        response_result["discovered_url_sample"]
                    )
                return {
                    "route": decision.route.value,
                    "reason": decision.reason,
                    "evidence_ref": f"web-acquisition-evidence://{evidence.evidence_id}",
                    "result": response_result,
                }
            except AcquisitionRuntimeError as exc:
                elapsed = max(0, int(time.time() * 1000) - started)
                try:
                    await self.acquisition.record_telemetry(
                        item_id,
                        route=decision.route,
                        success=False,
                        latency_ms=elapsed,
                    )
                    failure_class = (
                        AcquisitionFailure.CAPACITY
                        if exc.code == "CRAWLEE_BUSY"
                        else AcquisitionFailure.RUNTIME
                    )
                    state = await self.acquisition.fail(
                        item_id,
                        worker_id=body.worker_id,
                        lease_token=body.lease_token,
                        failure=failure_class,
                        error_code=exc.code,
                        retry_after_ms=15_000 if exc.code == "CRAWLEE_BUSY" else None,
                    )
                except RuntimeError:
                    state = None
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": exc.code,
                        "state": state.value if state else "LEASE_LOST",
                    },
                ) from exc

        @router.post("/acquisition/items/{item_id}/evidence")
        async def acquisition_evidence_record(
            item_id: str,
            body: AcquisitionEvidenceBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            row = await self.store.fetchone(
                "SELECT item_id FROM web_acquisition_items WHERE item_id=?", (item_id,)
            )
            if row is None:
                raise HTTPException(status_code=404, detail="UNKNOWN_WEB_ACQUISITION_ITEM")
            try:
                self.policy.assert_no_secrets(
                    body.detail, context="acquisition_evidence_detail"
                )
                evidence = await self.acquisition_evidence.record(
                    item_id=item_id, **body.model_dump()
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return evidence.model_dump(mode="json")

        @router.get("/acquisition/evidence/verify")
        async def acquisition_evidence_verify(
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            return await self.acquisition_evidence.verify_chain()

        @router.post("/acquisition/items/{item_id}/telemetry")
        async def acquisition_telemetry_record(
            item_id: str,
            body: AcquisitionTelemetryBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                record = await self.acquisition.record_telemetry(
                    item_id, **body.model_dump()
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return record.model_dump(mode="json")

        @router.post("/acquisition/skills")
        async def domain_skill_propose(
            body: DomainSkillProposeBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                skill = await self.domain_skills.propose(**body.model_dump())
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return skill.model_dump(mode="json")

        @router.post("/acquisition/skills/{skill_id}/qualify")
        async def domain_skill_qualify(
            skill_id: str,
            body: DomainSkillQualifyBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                skill = await self.domain_skills.qualify(skill_id, **body.model_dump())
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return skill.model_dump(mode="json")

        @router.post("/acquisition/skills/{skill_id}/canary")
        async def domain_skill_canary(
            skill_id: str,
            body: DomainSkillCanaryBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                skill = await self.domain_skills.record_canary(skill_id, **body.model_dump())
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return skill.model_dump(mode="json")

        @router.post("/acquisition/skills/{skill_id}/quarantine")
        async def domain_skill_quarantine(
            skill_id: str,
            body: DomainSkillQuarantineBody,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            try:
                skill = await self.domain_skills.quarantine(skill_id, **body.model_dump())
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return skill.model_dump(mode="json")

        @router.get("/acquisition/skills/hot/{domain}/{goal_class}")
        async def domain_skill_hot(
            domain: str,
            goal_class: str,
            x_van_internal_token: str | None = Header(default=None),
        ):
            self._require_internal(x_van_internal_token)
            self._require_enabled()
            skill = await self.domain_skills.hot(domain=domain, goal_class=goal_class)
            return None if skill is None else skill.model_dump(mode="json")

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
            return [
                {
                    **dict(r),
                    "execution_completed": r["status"] == BrowserTaskStatus.COMPLETED.value,
                    "owner_success": False,
                    "verification_state": "UNVERIFIED",
                }
                for r in rows
            ]

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

            released = await self.broker.release_lease(
                PageLease(
                    lease_id=body.lease_id, profile_alias=body.profile_alias,
                    task_id=body.task_id, acquired_at_ms=0, expires_at_ms=0,
                )
            )
            out: dict[str, Any] = {"released": True, "lease_id": body.lease_id}
            code = released.owner_code
            if code is not None:
                # Unit G15 (review I8 MAJOR-2): what the guard blocked after the lease's last
                # call is the owner's, whoever gives the lease back.
                out["blocked"] = code
                row = await self.store.fetchone(
                    "SELECT task_id FROM browser_tasks WHERE task_id = ?", (body.task_id,)
                )
                if row is not None:
                    out["task_status"] = await self._hand_late_block_to_owner(body.task_id, code)
            return out

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
                    capability_id=body.capability_id, inputs=body.inputs, scope=body.scope,
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
                "task": {
                    **task.model_dump(mode="json"),
                    "execution_completed": task.status == BrowserTaskStatus.COMPLETED,
                    "owner_success": False,
                    "verification_state": "UNVERIFIED",
                },
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
            task = await self._load_task(task_id)
            if body.status is BrowserTaskStatus.COMPLETED and task.status not in TERMINAL_TASK_STATUSES:
                # Unit G15 (review I8 MAJOR-2): an end state is final, so a page lease the task
                # still holds is ended first — a write its guard blocked after the task's last
                # call must reach the owner before COMPLETED could stand over it.
                code = await self._end_held_page(task)
                if code is not None:
                    status = await self._hand_late_block_to_owner(task_id, code)
                    raise HTTPException(
                        status_code=409, detail=f"BROWSER_TASK_HANDED_TO_OWNER:{code}:{status}",
                    )
            try:
                await self.tasks.complete(
                    task_id=task_id, status=body.status,
                    evidence_pointer=body.evidence_pointer, error_code=body.error_code,
                )
            except BrowserTaskTransitionRefused as exc:
                # Review I2 N-3: an end state only, and never out of one. RESUME_AUTHORIZED
                # comes from the owner's decision and PENDING from task creation, not here.
                raise HTTPException(
                    status_code=409, detail=f"BROWSER_TASK_TRANSITION_REFUSED:{exc.why}:{exc.current or 'UNKNOWN'}->{exc.requested}",
                ) from exc
            except BrowserTaskNotVerified as exc:
                # §7 / review I M-2: a caller cannot declare success. COMPLETED needs the
                # independent verifier's VERIFIED verdict on record for this task.
                raise HTTPException(
                    status_code=409, detail=f"BROWSER_TASK_NOT_VERIFIED:{exc.latest or 'NO_VERIFICATION'}"
                ) from exc
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
            # Review I3 MAJOR-3: one run per task at a time. An /assignments run and an
            # /interaction/step run on the same task would otherwise share the page and its
            # lease, and whichever finished first would drop the lease under the other.
            try:
                run_token = self.tasks.claim_run(task.task_id, "ASSIGNMENT")
            except BrowserTaskRunInFlight as exc:
                raise HTTPException(
                    status_code=409, detail=f"BROWSER_TASK_RUN_IN_FLIGHT:{exc.kind}"
                ) from exc
            try:
                return await self._run_assignment(body, task, run_token)
            finally:
                self.tasks.release_run(task.task_id, run_token)

    async def _run_assignment(
        self, body: "AssignmentBody", task: BrowserTask, run_token: str
    ) -> dict[str, Any]:
        """The body of ``POST /assignments``, run while the task's in-flight marker is held."""
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
        # Owner decision 2026-09-30 — the run acts within the task's recorded scope, narrowed
        # to the hosts this assignment allows (an assignment can narrow, never widen it). A
        # task with no recorded scope keeps None and every action is handed to the owner.
        if task.scope is not None:
            task = task.model_copy(update={"scope": task.scope.narrowed_to_hosts(assignment.allowed_domains)})
        # P2-BROW-001 — the worker is bound to *this* task and its plan before it
        # runs. A long-lived worker mutated per assignment would let two concurrent
        # assignments overwrite each other's task id, and the adapter is the only part
        # that is legitimately shared.
        worker = self.worker
        if body.interactive_session_id is not None:
            factory = getattr(self, "interactive_worker_factory", None)
            if factory is None:
                raise HTTPException(status_code=503, detail="INTERACTIVE_CONTROL_CLIENT_UNCONFIGURED")
            try:
                worker = await factory(task, assignment, body.plan, body.interactive_session_id)
            except SemanticWorkerUnavailable as exc:
                raise HTTPException(status_code=503, detail="INTERACTIVE_SEMANTIC_WORKER_UNCONFIGURED") from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(status_code=409, detail="INTERACTIVE_CONTROL_NOT_ADMITTED") from exc
        binder = getattr(worker, "for_task", None)
        if binder is not None and body.interactive_session_id is None:
            worker = binder(task, body.plan)
        # Review I4 MINOR-A — an assignment acts under the task's page lease, fenced like
        # /interaction/step: the lease the task holds, or one taken for this run and given
        # back after it. Every Harness call carries its generation, and the fence's guard
        # re-checks (and renews) the lease with the broker before each one.
        try:
            await self.broker.ensure_registered_profile(profile_alias=task.profile_alias)
            acquisition = asyncio.create_task(self.broker.lease_for_task_run(
                profile_alias=task.profile_alias, task_id=task.task_id,
            ))
            try:
                acquired, lease = await asyncio.shield(acquisition)
            except asyncio.CancelledError:
                try:
                    got_new, got_lease = await asyncio.shield(acquisition)
                except BrowserPolicyError:
                    pass
                else:
                    if got_new:
                        await self.broker.release_lease(got_lease)
                raise
        except BrowserPolicyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        async def assert_lease_active() -> None:
            await self.broker.assert_lease_active(
                lease_id=lease.lease_id, holder_id=task.task_id, generation=lease.generation)

        page_end: dict[str, Any] | None = None
        evidence = None
        evidence_pointer = None
        claimed = False
        try:
            try:
                current = await self._load_task(task.task_id)
                claim = asyncio.create_task(self.tasks.start_assignment(
                    task_id=task.task_id, expected_status=current.status))
                try:
                    await asyncio.shield(claim)
                    claimed = True
                except asyncio.CancelledError:
                    await asyncio.shield(claim)
                    claimed = True
                    raise
                deadline_first = assignment.deadline_ms is not None and assignment.deadline_ms <= lease.expires_at_ms
                stop_at_ms = min(lease.expires_at_ms, assignment.deadline_ms) if assignment.deadline_ms is not None else lease.expires_at_ms
                with harness_lease_fence(broker_lease_fence(self.broker, lease)):
                    try:
                        async with asyncio.timeout(max(0, (stop_at_ms - time.time() * 1000) / 1000)):
                            result = await self.runner.run(
                                assignment=assignment, worker=worker, task=task,
                                verifier=self.verifier, postcondition=body.postcondition,
                                assert_lease_active=assert_lease_active,
                            )
                    except TimeoutError:
                        result = SubagentResult(assignment_id=assignment.assignment_id, task_id=task.task_id,
                            stop_reason=SubagentStop.DEADLINE_REACHED if deadline_first else SubagentStop.WORKER_ERROR,
                            detail=None if deadline_first else "BROWSER_PROFILE_LEASE_EXPIRED")
                    if result.succeeded:
                        await assert_lease_active()
                        evidence = await self._seal_assignment_observation(task, assignment, result)
                        if evidence is not None:
                            evidence_pointer = f"browser-evidence://{evidence.evidence_id}"
            finally:
                page_end = await self._end_run_page(acquired, lease)
        except SemanticWorkerUnavailable as exc:
            await self._late_block_before_raising(task, page_end)
            if claimed:
                await self.tasks.interrupt_assignment(task_id=task.task_id)
            # An L2+ assignment asked for judgement about a page and no semantic
            # runtime is configured. Walking the deterministic plan instead would be
            # answering a different question and reporting success on this one.
            raise HTTPException(
                status_code=503, detail=f"BROWSER_SEMANTIC_RUNTIME_UNAVAILABLE:{exc}"
            ) from exc
        except BaseException:
            await self._late_block_before_raising(task, page_end)
            if claimed:
                await self.tasks.interrupt_assignment(task_id=task.task_id)
            raise
        # Unit G15 (review I8 MAJOR-2): the page ended before any outcome is written, so a write
        # the guard blocked after the run's last Harness call hands the task to the owner
        # instead of letting COMPLETED (or any end state) stand over it.
        result = self._with_late_block(result, page_end)

        if result.verification_outcome is not None:
            # The verifier's verdict on the worker's "done" claim goes on record for
            # this task, whatever it was; COMPLETED is only reachable over VERIFIED.
            await self.tasks.record_verification(
                task=task, outcome=result.verification_outcome,
                verifier=type(self.verifier).__name__ if self.verifier is not None else "NONE",
                detail=result.detail, assignment_id=assignment.assignment_id,
            )

        escalation = None
        try:
            escalation = await self._record_run_outcome(task, assignment, result, run_token, evidence_pointer)
        except BrowserTaskTransitionRefused as exc:
            # Review I3 MINOR-2: the task reached an end state while this run was in flight
            # (e.g. /complete CANCELLED). It stays there; the run's outcome is not applied.
            raise HTTPException(
                status_code=409,
                detail=f"BROWSER_TASK_ENDED_DURING_RUN:{exc.current or 'UNKNOWN'}",
            ) from exc
        if escalation is not None:
            instruments.record_browser_task("ESCALATED")
        response = self._assignment_response(assignment, task, result, escalation)
        response.update(evidence_pointer=evidence_pointer,
            evidence=evidence.model_dump(mode="json") if evidence is not None else None,
            execution_completed=result.execution_completed,
            session_lease_ref=lease.lease_id, session_lease_generation=lease.generation,
            session_lease_released=acquired is not None)
        return response

    async def _end_run_page(self, acquired: Any, lease: Any) -> dict[str, Any] | None:
        """Unit G15 — end the run's page and return the Harness's ``/release`` answer.

        A lease the run took is given back (only while it is still the holding). A lease the
        task already held outlives the run in the broker, but the run is the last one on it —
        every outcome ends the task, holds it for verification or hands it to the owner, and
        none of those runs again on this lease — so its page is ended here too, before the
        outcome is written."""
        if acquired is not None:
            return (await self.broker.release_lease_if_held(acquired)).page
        return await self.broker.release_page(profile_alias=lease.profile_alias, lease_id=lease.lease_id)

    async def _end_held_page(self, task: BrowserTask) -> str | None:
        """Unit G15 — end the page of the live lease ``task`` holds (if any) and return the
        owner code its ``/release`` answer carries."""
        row = await self.store.fetchone(
            "SELECT lease_holder, lease_expires_at_ms, lease_holder_id FROM browser_profiles "
            "WHERE profile_alias = ?",
            (task.profile_alias,),
        )
        if row is None or not row["lease_holder"] or row["lease_holder_id"] != task.task_id:
            return None
        return network_owner_code(
            await self.broker.release_page(profile_alias=task.profile_alias, lease_id=str(row["lease_holder"]))
        )

    async def _late_block_before_raising(self, task: BrowserTask, page_end: Any) -> None:
        """A run that raised still hands a late block to the owner before the error goes up."""
        code = network_owner_code(page_end)
        if code is not None:
            await self._hand_late_block_to_owner(task.task_id, code)

    @staticmethod
    def _with_late_block(result, page_end: Any):
        """The run's result with a late block applied: OWNER_TAKEOVER (lane 4), never success.
        A run that already handed over keeps its own reason."""
        code = network_owner_code(page_end)
        if code is None or result.stop_reason is SubagentStop.OWNER_TAKEOVER:
            return result
        return result.model_copy(update={
            "stop_reason": SubagentStop.OWNER_TAKEOVER, "detail": f"HARNESS_REFUSED:{code}",
        })

    async def _seal_assignment_observation(self, task, assignment, result):
        """Seal actual bounded observations; a verified claim alone supplies no page data."""
        observed_url = result.extraction.get("url")
        try:
            observed = urlsplit(observed_url) if isinstance(observed_url, str) else None
            host = (observed.hostname or "").lower().rstrip(".") if observed else ""
        except ValueError:
            observed, host = None, ""
        allowed = [domain.lower().rstrip(".") for domain in assignment.allowed_domains]
        if (not result.steps or not all(step.observation_digest for step in result.steps)
                or observed is None or observed.scheme not in ("http", "https")
                or not any(host == domain or host.endswith("." + domain) for domain in allowed)
                or observed.username is not None or observed.password is not None
                or "adapter_error" in result.extraction):
            result.stop_reason = SubagentStop.WORKER_ERROR
            result.detail = "BROWSER_COMPLETION_OBSERVATION_MISSING_OR_INVALID"
            return None
        return await self.tasks.seal_evidence(task=task, kind="ASSIGNMENT_COMPLETION", url=observed_url,
            extraction={"assignment_id": assignment.assignment_id, "turn_id": assignment.turn_id,
                "command_id": assignment.command_id, "goal_digest": assignment.goal_digest,
                "steps": [step.model_dump(mode="json") for step in result.steps],
                "observation": result.extraction})

    async def _record_run_outcome(
        self, task: BrowserTask, assignment: SubagentAssignment, result, run_token: str,
        evidence_pointer: str | None = None,
    ) -> dict[str, Any] | None:
        """Apply a finished run to its task, through the guarded writers only (I3 MINOR-2).

        Raises ``BrowserTaskTransitionRefused`` when the task ended while the run was in
        flight. Returns the escalation, if one was raised.
        """
        escalation = None
        if result.stop_reason is SubagentStop.OWNER_TAKEOVER:
            # Handed over, not finished: the owner is driving this profile. Not
            # terminal (completed_at_ms stays NULL) and never success; the task
            # lease is dropped so automation holds nothing while the owner acts.
            await self._release_task_lease(task)
            await self.tasks.set_working_status(
                task_id=task.task_id, status=BrowserTaskStatus.WAITING_FOR_OWNER,
                error_code=f"{SubagentStop.OWNER_TAKEOVER.value}:{result.detail or ''}"[:200],
            )
            instruments.record_browser_task(BrowserTaskStatus.WAITING_FOR_OWNER)
        elif result.stop_reason in (SubagentStop.SCOPE_VIOLATION, SubagentStop.ACTION_CLASS_VIOLATION):
            escalation = await self._create_boundary_escalation(
                task=task, assignment=assignment, result=result
            )
        else:
            # §7: COMPLETED only after VERIFIED. UNVERIFIABLE stays VERIFYING (not
            # terminal success, not a failure the page caused) and is escalated.
            terminal_status = BrowserTaskStatus.COMPLETED
            if result.stop_reason is SubagentStop.UNVERIFIABLE:
                terminal_status = BrowserTaskStatus.VERIFYING
            elif result.stop_reason in (SubagentStop.PAYMENT_REFUSED, SubagentStop.INJECTION_REFUSED):
                terminal_status = BrowserTaskStatus.BLOCKED_POLICY
            elif result.stop_reason is SubagentStop.GOAL_DRIFT:
                terminal_status = BrowserTaskStatus.BLOCKED_UNSAFE
            elif not result.succeeded:
                terminal_status = BrowserTaskStatus.FAILED
            error_code = None if result.succeeded else result.stop_reason.value
            if terminal_status is BrowserTaskStatus.VERIFYING:
                # Not an end state (review I2 N-3): held for the owner, never success.
                await self.tasks.hold_for_verification(
                    task_id=task.task_id, error_code=error_code,
                    now_ms=int(time.time() * 1000),
                )
            else:
                await self.tasks.complete(
                    task_id=task.task_id, status=terminal_status, error_code=error_code,
                    now_ms=int(time.time() * 1000), run_token=run_token,
                    evidence_pointer=evidence_pointer,
                )
            # P3-OBS-002 — "browser task status" is one of Gate 11's named
            # metrics. Recorded at the one place a task reaches a terminal
            # status, so a new stop reason is counted without being added here.
            instruments.record_browser_task(terminal_status)
        return escalation

    @staticmethod
    def _assignment_response(
        assignment: SubagentAssignment, task: BrowserTask, result, escalation: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "assignment_id": assignment.assignment_id,
            "task_id": task.task_id,
            "turn_id": assignment.turn_id,
            "stop_reason": result.stop_reason.value,
            "succeeded": result.succeeded,
            "verification_outcome": result.verification_outcome,
            "needs_owner": result.stop_reason in (SubagentStop.UNVERIFIABLE, SubagentStop.OWNER_TAKEOVER),
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
