"""Rev 1.3 §§99-100, 219, 370-371, 421 — Automation & Browser Fabric health surface.

§421 makes the no-cascading-failure rule universal: a missing n8n degrades
n8n-backed automations only, a missing Stagehand leaves the deterministic and
native paths intact, and VATI T0 is independent of all of it. This module reports
that truthfully — including reporting `PENDING_OWNER` while the adoption
decisions and Security Policy amendment are unsigned, rather than implying the
fabric is merely switched off — and, since owner decision 2026-09-29 §6, reporting
production activation as permitted only when every gate in the explicit gate model
(`production_gates.py`) is GREEN.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from van_gateway.auth.control_scopes import ControlScope, require_scoped_internal
from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, RuntimeState
from van_gateway.automation.n8n_client import N8nManagementClient
from van_gateway.automation.deadletter import DeadLetterService
from van_gateway.automation.policy import load_automation_policy, load_browser_policy
from van_gateway.automation.production_gates import GATE_MODEL, evaluate_production_gates
from van_gateway.automation.registry import HotWorkflowIndex
from van_gateway.automation.telemetry import TelemetryService
from van_gateway.automation.workflow_health import WorkflowHealthService
from van_gateway.browser.adapters import (
    HttpBrowserHarnessAdapter,
    StagehandAdapter,
    harness_fence_key_from_settings,
)
from van_gateway.computer_use.fabric import ComputerInteractionFabric
from van_gateway.config import Settings
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.models import DegradedCode
from van_gateway.storage.db import Store

REPO_ROOT = Path(__file__).resolve().parents[3]
DECISIONS = REPO_ROOT / "docs" / "decisions"

#: The decisions that gate production activation (§§365, 368). Derived from the explicit
#: gate model so the list and the gates cannot drift apart; kept as a name for callers.
def _required_decisions() -> tuple[str, ...]:
    try:
        model = json.loads(GATE_MODEL.read_text(encoding="utf-8"))
        return tuple(str(e["decision"]) for e in model["required_decisions"])
    except Exception:  # noqa: BLE001 — the gate evaluation itself reports the error
        return ()


REQUIRED_DECISIONS = _required_decisions()


def governance_state() -> dict[str, Any]:
    """Report whether production activation is permitted, and why.

    Owner decision 2026-09-29 §6: this used to declare activation permitted when no required
    decision file contained the literal ``owner_signature_status: PENDING``, which ignored
    every production gate (Stagehand's ``production_gate.status: PENDING`` among them). It now
    evaluates the explicit gate model in ``registries/production_activation_gates.json``:
    activation is permitted only when every governance *and* production gate is GREEN, and
    anything unknown, missing or unparseable fails closed.

    An agent cannot set these (§365); it can only read them, which is exactly why this is
    computed rather than configured. The first three keys keep their original meaning for
    existing consumers; ``gates`` is the per-gate breakdown that explains the answer.
    """
    evaluation = evaluate_production_gates()
    return {
        "owner_decisions_pending": evaluation["owner_decisions_pending"],
        "owner_decisions_missing": evaluation["owner_decisions_missing"],
        "production_activation_permitted": evaluation["production_activation_permitted"],
        "production_gates_not_green": evaluation["production_gates_not_green"],
        "gates": evaluation["gates"],
        "gate_model": evaluation["gate_model"],
        "gate_model_error": evaluation["gate_model_error"],
        # Reviewer I minor 8 — the same model, per capability. The global flag above keeps
        # its meaning (every gate GREEN); these say which capability a gate belongs to.
        "capabilities": evaluation["capabilities"],
        "production_activation_permitted_by_capability": {
            name: cap["production_activation_permitted"]
            for name, cap in evaluation["capabilities"].items()
        },
    }


class AutomationHealthApi:
    """`/v1/automation/health` and `/v1/browser/health`, internal control only."""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        degraded: DegradedRegistry,
        hot_index: HotWorkflowIndex | None = None,
        computer_use: ComputerInteractionFabric | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.degraded = degraded
        self.runtime = ExternalRuntimeRegistry(store)
        self.hot_index = hot_index or HotWorkflowIndex()
        self.workflow_health = WorkflowHealthService(store)
        self.dead_letter = DeadLetterService(store)
        self.telemetry = TelemetryService(store)
        self.n8n = N8nManagementClient(
            self.runtime,
            base_url=settings.automation_n8n_base_url,
            api_key=settings.automation_n8n_api_key,
            enabled=settings.automation_enabled,
            expected_version=settings.automation_n8n_expected_version or self._manifest("n8n"),
            timeout_seconds=settings.automation_timeout_seconds,
        )
        self.harness = HttpBrowserHarnessAdapter(
            self.runtime,
            base_url=settings.browser_harness_base_url,
            enabled=settings.browser_enabled,
            expected_version=settings.browser_harness_expected_version
            or self._manifest("browser_harness"),
            fence_key=harness_fence_key_from_settings(settings),
        )
        self.stagehand = StagehandAdapter(
            self.runtime,
            base_url=settings.browser_stagehand_base_url,
            enabled=settings.browser_enabled,
            expected_version=settings.browser_stagehand_expected_version
            or self._manifest("stagehand"),
            model_provider=settings.browser_stagehand_model_provider,
            model_name=settings.browser_stagehand_model_name,
            # Unit G2a: the adapter's production gate reads *these* settings (placement,
            # model, mTLS identity), so health reports the gate's verdict for this process.
            settings=settings,
        )
        # P2-CU-001 — the fabric is constructed in production for the first time. Its
        # health surface is here rather than in its own module because the three fabrics
        # degrade on the same terms and an owner asking "what can VAN act through?" should
        # not have to know they were written separately.
        self.computer_use = computer_use or ComputerInteractionFabric(store)
        self.router = APIRouter(prefix="/v1", tags=["automation-browser"])
        self._install_routes()

    @staticmethod
    def _manifest(name: str) -> str:
        path = REPO_ROOT / "registries" / "automation_browser_dependencies.json"
        if not path.is_file():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data["automation_browser_fabric"].get(name, {}).get("version", ""))

    def _require_internal(self, token: str | None) -> None:
        # GAP-F-009: scope-aware, same authority as the middleware.
        require_scoped_internal(self.settings, token, ControlScope.RUNTIME)

    async def automation_health(self) -> dict[str, Any]:
        status = await self.n8n.status()
        governance = governance_state()
        policy = load_automation_policy()

        counts = {}
        for state in ("PROPOSED", "QUARANTINED", "VALIDATED", "ADMITTED", "HOT", "DEGRADED", "REVOKED"):
            row = await self.store.fetchone(
                "SELECT COUNT(*) AS n FROM automation_artifacts WHERE lifecycle_state = ?", (state,)
            )
            counts[state.lower()] = int(row["n"]) if row else 0

        self._sync_degraded(status.state, DegradedCode.AUTOMATION_FABRIC_UNAVAILABLE)
        if not self.settings.automation_ingress_enabled:
            self.degraded.set(DegradedCode.AUTOMATION_INGRESS_DISABLED, True)

        return {
            "capability": "automation_fabric",
            "runtime": status.model_dump(mode="json"),
            "governance": governance,
            "policy_version": policy.policy_version,
            "node_catalog_denies_community": not policy.community_nodes_allowed,
            "engine_success_is_owner_success": policy.engine_success_is_owner_success,
            "ingress_enabled": self.settings.automation_ingress_enabled,
            "egress_enabled": self.settings.automation_egress_enabled,
            "max_concurrency": self.settings.automation_max_concurrency,
            "artifacts": counts,
            "hot_index_size": self.hot_index.size,
            # §§76-77, 246 — the fabric's operating state, not just its config.
            "workflow_health": await self.workflow_health.counts_by_status(),
            "workflows_needing_attention": [
                {
                    "capability_id": h.capability_id,
                    "workflow_version": h.workflow_version,
                    "status": h.status.value,
                    "consecutive_failures": h.consecutive_failures,
                    "last_failure_class": (
                        h.last_failure_class.value if h.last_failure_class else None
                    ),
                }
                for h in await self.workflow_health.needing_attention()
            ],
            "open_dead_letters": await self.dead_letter.open_count(),
            # §102 — the core success metric, reported rather than asserted.
            "ladder": self._ladder_payload(await self.telemetry.ladder_metrics()),
            # §§68, 421 — stated explicitly so the invariant is observable.
            "t0_isolation": {
                "in_tick_to_order_path": False,
                "may_send_live_orders": False,
                "vati_independent_of_automation": True,
            },
        }

    @staticmethod
    def _ladder_payload(metrics: Any) -> dict[str, Any]:
        return {
            "window_ms": metrics.window_ms,
            "generations": metrics.total,
            "hot_hit_rate": round(metrics.hot_hit_rate, 4),
            "warm_specialisation_rate": round(metrics.warm_specialisation_rate, 4),
            "cold_generation_rate": round(metrics.cold_generation_rate, 4),
            "pattern_reuse_rate": round(metrics.pattern_reuse_rate, 4),
            "ir_cache_hit_rate": round(metrics.ir_cache_hit_rate, 4),
            "generation_failures": metrics.generation_failures,
            "median_first_use_latency_ms": metrics.median_first_use_latency_ms,
        }

    async def _stagehand_production(self, governance: dict[str, Any]) -> dict[str, Any]:
        """Reviewer I minor 8 — unit M's placement/model state, surfaced, and ANDed with the
        Stagehand slice of the gate model exactly as the router's Stagehand gate does."""
        from van_gateway.browser.interaction_router import _fetch_stagehand_worker_health

        try:
            from van_gateway.automation.placement import stagehand_production_state
        except ImportError:
            placement = {"state": "PRODUCTION_DISABLED", "reason": "PLACEMENT_GATE_MISSING"}
        else:
            health = await _fetch_stagehand_worker_health(self.stagehand)
            placement = stagehand_production_state(self.settings, worker_health=health)
        gates = governance["capabilities"]["stagehand"]
        return {
            **placement,
            "gate_model_permitted": gates["production_activation_permitted"],
            "gates_not_green": gates["gates_not_green"],
            "production_activation_permitted": placement.get("state") == "PLACEMENT_SATISFIED"
            and gates["production_activation_permitted"] is True,
        }

    async def browser_health(self) -> dict[str, Any]:
        harness = await self.harness.status()
        stagehand = await self.stagehand.status()
        policy = load_browser_policy()
        governance = governance_state()

        self._sync_degraded(harness.state, DegradedCode.BROWSER_HARNESS_UNAVAILABLE)
        self._sync_degraded(stagehand.state, DegradedCode.BROWSER_SEMANTIC_UNAVAILABLE)

        return {
            "capability": "browser_fabric",
            "harness": harness.model_dump(mode="json"),
            "stagehand": stagehand.model_dump(mode="json"),
            "governance": governance,
            # Reviewer I minor 8 — per capability, so Stagehand's pending gates do not make
            # the deterministic Harness path look not-permitted, and Stagehand's own answer
            # includes its placement (van-browser-core, model, provider-key rules).
            "production_activation": {
                "browser_harness": {
                    "production_activation_permitted": governance["capabilities"]["browser_harness"][
                        "production_activation_permitted"
                    ],
                    "gates_not_green": governance["capabilities"]["browser_harness"]["gates_not_green"],
                },
                "stagehand": await self._stagehand_production(governance),
                # Review I2 N-7 — VAN's own gate on Jev browser effect (SHADOW only until GREEN).
                "jev_browser_effect": {
                    "production_activation_permitted": governance["capabilities"]["jev_browser_effect"][
                        "production_activation_permitted"
                    ],
                    "gates_not_green": governance["capabilities"]["jev_browser_effect"]["gates_not_green"],
                },
            },
            "policy_version": policy.policy_version,
            "max_autonomy_tier": policy.max_autonomy_tier,
            "raw_cookie_export_forbidden": policy.raw_cookie_export_forbidden,
            "session_leases_required": policy.session_leases_required,
            # §421 — degradation is scoped; the other paths keep working.
            "degradation_scope": {
                "harness_unavailable_affects": ["deterministic browser workflows"],
                "stagehand_unavailable_affects": ["semantic observation", "workflow discovery"],
                "native_and_automation_paths_unaffected": True,
                "vati_t0_unaffected": True,
            },
        }

    async def computer_use_health(self) -> dict[str, Any]:
        """P2-CU-001 — which surfaces can be acted on, and what happens if one cannot.

        The fabric's boundary is complete and its executor does not exist. Reporting that
        is the difference between a capability that is honestly unavailable and one a
        matrix lists as BUILT because the code compiles.
        """
        registered = self.computer_use.surfaces()
        surfaces = dict(registered)
        worker_status: dict[str, Any] = {}
        for surface, worker in self.computer_use.worker_impls.items():
            status_fn = getattr(worker, "status", None)
            if status_fn is None:
                worker_status[surface.value] = {"state": "UNKNOWN", "ready": False}
                surfaces[surface.value] = False
                continue
            status = await status_fn()
            worker_status[surface.value] = status
            surfaces[surface.value] = bool(status.get("ready"))
        available = sorted(name for name, ready in surfaces.items() if ready)
        self.degraded.set(DegradedCode.COMPUTER_USE_NO_SURFACE_WORKER, not available)
        return {
            "capability": "computer_interaction_fabric",
            "registered_surfaces": registered,
            "surfaces": surfaces,
            "worker_status": worker_status,
            "surfaces_with_a_worker": available,
            # A refusal before the ledger write, so an operation nobody can perform never
            # appears as a PENDING row the owner would read as queued work.
            "operations_are_recorded_when_refused": False,
            "typed_operations_only": True,
            "arbitrary_execution_primitive": None,
            "max_action_class": "A3",
            "degradation_scope": {
                "browser_fabric_unaffected": True,
                "native_and_automation_paths_unaffected": True,
                "vati_t0_unaffected": True,
            },
        }

    def _sync_degraded(self, state: RuntimeState, code: DegradedCode) -> None:
        self.degraded.set(code, state is not RuntimeState.READY)

    def _install_routes(self) -> None:
        @self.router.get("/automation/health")
        async def automation(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.automation_health()

        @self.router.get("/browser/health")
        async def browser(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.browser_health()

        @self.router.get("/computer-use/health")
        async def computer_use(x_van_internal_token: str | None = Header(default=None)):
            self._require_internal(x_van_internal_token)
            return await self.computer_use_health()


__all__ = ["AutomationHealthApi", "governance_state"]
