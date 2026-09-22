"""Rev 1.3 §§5-6, 25, 32, 301-303 — the deterministic Capability Router.

§5's point: Hermes specifies a *goal*; a deterministic router picks the execution
medium. That keeps expensive tools from being chosen by a model's mood, and it is
what makes §24's ladder real — the router is where COLD becomes WARM becomes HOT.

Selection order (§6), for machine-readable services:

    1. native authoritative capability
    2. existing HOT n8n workflow        <- no model, no network, p95 <= 10 ms
    3. WARM template specialisation     <- deterministic, no model
    4. COLD compilation                 <- the only expensive path

and for web-only systems: harness before semantic browser (§66, §302).

§32 matters as much as the order: when a goal is *also* satisfiable right now by
a native capability, the router says so, so the owner is served immediately while
the reusable workflow compiles behind them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from van_gateway.automation.models import IntentSignature, WorkflowLifecycle
from van_gateway.automation.payments import PaymentBoundaryError, assert_not_automated_payment
from van_gateway.automation.registry import AutomationRegistry, HotWorkflowIndex
from van_gateway.automation.templates import TemplateLibrary
from van_gateway.automation.workflow_health import HealthStatus, WorkflowHealthService
from van_gateway.models import ActionClass


class ExecutionMedium(str, Enum):
    NATIVE = "NATIVE"
    N8N_HOT = "N8N_HOT"
    N8N_WARM = "N8N_WARM"
    WORKFLOW_COMPILER = "WORKFLOW_COMPILER"
    BROWSER_HARNESS = "BROWSER_HARNESS"
    BROWSER_SEMANTIC = "BROWSER_SEMANTIC"
    TEMPORAL = "TEMPORAL"
    REFUSED = "REFUSED"


class RouteReason(str, Enum):
    ADMITTED_HOT_CAPABILITY = "ADMITTED_HOT_CAPABILITY"
    HOT_CAPABILITY_DEGRADED = "HOT_CAPABILITY_DEGRADED"
    NATIVE_CAPABILITY_AVAILABLE = "NATIVE_CAPABILITY_AVAILABLE"
    TEMPLATE_AVAILABLE = "TEMPLATE_AVAILABLE"
    NOVEL_GOAL = "NOVEL_GOAL"
    KNOWN_BROWSER_WORKFLOW = "KNOWN_BROWSER_WORKFLOW"
    BROWSER_SEMANTICS_REQUIRED = "BROWSER_SEMANTICS_REQUIRED"
    CRITICAL_DURABLE_PROCESS = "CRITICAL_DURABLE_PROCESS"
    PAYMENT_PROHIBITED = "PAYMENT_PROHIBITED"
    ACTION_CLASS_PROHIBITED = "ACTION_CLASS_PROHIBITED"


@dataclass(frozen=True)
class RouteRequest:
    goal: str
    signature: IntentSignature
    #: Set when a native capability could satisfy this goal right now (§32).
    native_capability_id: str | None = None
    #: True when the target has no machine interface at all.
    web_only: bool = False
    #: Set when a Browser Workflow Capsule already covers this goal (§279).
    known_browser_capsule_id: str | None = None
    #: True for long-lived financial state machines (§86, §325).
    critical_durable: bool = False
    #: True when the owner asked for this to recur, so a workflow is worth compiling.
    wants_reuse: bool = False


@dataclass(frozen=True)
class RouteDecision:
    medium: ExecutionMedium
    reason: RouteReason
    capability_id: str | None = None
    workflow_version: int | None = None
    workflow_ref: str | None = None
    template_id: str | None = None
    #: §32 — satisfy the owner now while the reusable capability compiles.
    immediate_native_capability_id: str | None = None
    compile_in_background: bool = False
    detail: str | None = None

    @property
    def requires_generation(self) -> bool:
        return self.medium is ExecutionMedium.WORKFLOW_COMPILER


class AutomationMediumRouter:
    """Deterministic. No model participates in choosing the medium.

    Named for what it does: given a goal already known to be automation work,
    it picks the execution *medium* — native, HOT, WARM, COLD, browser or
    Temporal. It does not choose *which capability* to use; that is
    `van_gateway.capability.router.CapabilityRouter`, one level up. The two were
    briefly both called CapabilityRouter, which made a genuine confusion easy.
    """

    def __init__(
        self,
        *,
        registry: AutomationRegistry,
        hot_index: HotWorkflowIndex,
        templates: TemplateLibrary | None = None,
        health: WorkflowHealthService | None = None,
        temporal_available: bool = False,
    ) -> None:
        self.registry = registry
        self.hot_index = hot_index
        self.templates = templates or TemplateLibrary()
        self.health = health
        self.temporal_available = temporal_available

    async def route(self, request: RouteRequest) -> RouteDecision:
        # 0. Hard refusals first, so nothing downstream has to re-check them.
        try:
            assert_not_automated_payment(goal=request.goal, context="capability_routing")
        except PaymentBoundaryError as exc:
            return RouteDecision(
                medium=ExecutionMedium.REFUSED, reason=RouteReason.PAYMENT_PROHIBITED,
                detail=str(exc),
            )
        if request.signature.mutation_class is ActionClass.A5:
            return RouteDecision(
                medium=ExecutionMedium.REFUSED, reason=RouteReason.ACTION_CLASS_PROHIBITED,
                detail="A5",
            )

        # 1. Critical durable processes leave n8n and use the Temporal coordination
        #    runtime. The implementation is always a real route; deployment readiness is
        #    stated separately so a missing Temporal host never masquerades as durability.
        if request.critical_durable:
            return RouteDecision(
                medium=ExecutionMedium.TEMPORAL,
                reason=RouteReason.CRITICAL_DURABLE_PROCESS,
                detail=(
                    "Temporal durable runtime configured; start through "
                    "/v1/automation/temporal/start"
                    if self.temporal_available
                    else
                    "Temporal durable runtime is implemented but this gateway has not "
                    "configured its bridge; execution fails closed until VAN_TEMPORAL_* "
                    "deployment settings are present"
                ),
            )

        # 2. Web-only targets take the browser ladder, harness first (§§66, 302).
        if request.web_only:
            if request.known_browser_capsule_id:
                return RouteDecision(
                    medium=ExecutionMedium.BROWSER_HARNESS,
                    reason=RouteReason.KNOWN_BROWSER_WORKFLOW,
                    capability_id=request.known_browser_capsule_id,
                )
            return RouteDecision(
                medium=ExecutionMedium.BROWSER_SEMANTIC,
                reason=RouteReason.BROWSER_SEMANTICS_REQUIRED,
            )

        # 3. HOT. The whole point is that this costs a dict lookup (§25).
        hit = self.hot_index.lookup(request.signature)
        if hit is not None:
            capability_id, version, workflow_ref = hit
            capability = await self.registry.get_capability(capability_id)
            if capability is not None and capability.lifecycle_state in (
                WorkflowLifecycle.ADMITTED,
                WorkflowLifecycle.HOT,
            ):
                # §77 — VAN stops routing through a degraded workflow. Withdrawing
                # here rather than only refusing means the next lookup is a miss,
                # so one health check does not become a per-request cost.
                degraded = await self._degraded(capability_id, version)
                if degraded is None:
                    return RouteDecision(
                        medium=ExecutionMedium.N8N_HOT,
                        reason=RouteReason.ADMITTED_HOT_CAPABILITY,
                        capability_id=capability_id, workflow_version=version,
                        workflow_ref=workflow_ref,
                    )
                self.hot_index.withdraw(capability_id)
                return await self._fallback(
                    request,
                    detail=f"{capability_id} v{version} is {degraded.value}",
                )
            # A stale index entry must not route work to a withdrawn capability.
            self.hot_index.withdraw(capability_id)

        # 4. A native capability beats compiling anything (§§6, 303).
        #    If the owner also wants this to recur, serve now and compile behind.
        if request.native_capability_id is not None:
            template = self.templates.for_goal_class(request.signature.goal_class)
            return RouteDecision(
                medium=ExecutionMedium.NATIVE,
                reason=RouteReason.NATIVE_CAPABILITY_AVAILABLE,
                capability_id=request.native_capability_id,
                immediate_native_capability_id=request.native_capability_id,
                compile_in_background=request.wants_reuse,
                template_id=template.template_id if template is not None else None,
                detail=(
                    "compiling a reusable capability in the background (§32)"
                    if request.wants_reuse
                    else None
                ),
            )

        # 5. WARM — a known shape, specialised deterministically.
        template = self.templates.for_goal_class(request.signature.goal_class)
        if template is not None:
            return RouteDecision(
                medium=ExecutionMedium.N8N_WARM, reason=RouteReason.TEMPLATE_AVAILABLE,
                template_id=template.template_id,
            )

        # 6. COLD — the only expensive path.
        return RouteDecision(
            medium=ExecutionMedium.WORKFLOW_COMPILER, reason=RouteReason.NOVEL_GOAL,
        )

    async def _degraded(self, capability_id: str, version: int) -> HealthStatus | None:
        """Return the non-GREEN status, or None when this version is fine to use."""
        if self.health is None:
            return None
        health = await self.health.get(capability_id, version)
        if health is None or health.routable:
            return None
        return health.status

    async def _fallback(self, request: RouteRequest, *, detail: str) -> RouteDecision:
        """Where work goes when the HOT capability is no longer trustworthy.

        Native first, because it is authoritative and available now; then the
        template, because a specialisation of a known shape is still cheaper than
        generating one. The owner gets an answer either way.
        """
        if request.native_capability_id is not None:
            return RouteDecision(
                medium=ExecutionMedium.NATIVE,
                reason=RouteReason.HOT_CAPABILITY_DEGRADED,
                capability_id=request.native_capability_id,
                immediate_native_capability_id=request.native_capability_id,
                detail=detail,
            )
        template = self.templates.for_goal_class(request.signature.goal_class)
        if template is not None:
            return RouteDecision(
                medium=ExecutionMedium.N8N_WARM,
                reason=RouteReason.HOT_CAPABILITY_DEGRADED,
                template_id=template.template_id, detail=detail,
            )
        return RouteDecision(
            medium=ExecutionMedium.WORKFLOW_COMPILER,
            reason=RouteReason.HOT_CAPABILITY_DEGRADED, detail=detail,
        )


__all__ = [
    "AutomationMediumRouter",
    "ExecutionMedium",
    "RouteDecision",
    "RouteReason",
    "RouteRequest",
]
