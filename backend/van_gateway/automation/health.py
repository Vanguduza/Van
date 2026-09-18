"""Rev 1.3 §§99-100, 219, 370-371, 421 — Automation & Browser Fabric health surface.

§421 makes the no-cascading-failure rule universal: a missing n8n degrades
n8n-backed automations only, a missing Stagehand leaves the deterministic and
native paths intact, and VATI T0 is independent of all of it. This module reports
that truthfully — including reporting `PENDING_OWNER` while the adoption
decisions and Security Policy amendment are unsigned, rather than implying the
fabric is merely switched off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from van_gateway.automation.external_runtime import ExternalRuntimeRegistry, RuntimeState
from van_gateway.automation.n8n_client import N8nManagementClient
from van_gateway.automation.deadletter import DeadLetterService
from van_gateway.automation.policy import load_automation_policy, load_browser_policy
from van_gateway.automation.registry import HotWorkflowIndex
from van_gateway.automation.telemetry import TelemetryService
from van_gateway.automation.workflow_health import WorkflowHealthService
from van_gateway.browser.adapters import HttpBrowserHarnessAdapter, StagehandAdapter
from van_gateway.config import Settings
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.google.control import GoogleControlAuthError, verify_internal_control
from van_gateway.models import DegradedCode
from van_gateway.storage.db import Store

REPO_ROOT = Path(__file__).resolve().parents[3]
DECISIONS = REPO_ROOT / "docs" / "decisions"

#: The decisions that gate production activation (§§365, 368).
REQUIRED_DECISIONS = (
    "VAN-ADOPT-N8N-001.yaml",
    "VAN-ADOPT-STAGEHAND-001.yaml",
    "VAN-ADOPT-BROWSER-HARNESS-001.yaml",
    "VAN-AMEND-SECURITY-POLICY-001.md",
)


def governance_state() -> dict[str, Any]:
    """Report whether the owner has signed the gating decisions.

    An agent cannot set these (§365); it can only read them, which is exactly
    why this is computed rather than configured.
    """
    pending: list[str] = []
    missing: list[str] = []
    for name in REQUIRED_DECISIONS:
        path = DECISIONS / name
        if not path.is_file():
            missing.append(name)
            continue
        if "owner_signature_status: PENDING" in path.read_text(encoding="utf-8"):
            pending.append(name)
    return {
        "owner_decisions_pending": sorted(pending),
        "owner_decisions_missing": sorted(missing),
        "production_activation_permitted": not pending and not missing,
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
        )
        self.stagehand = StagehandAdapter(
            self.runtime,
            base_url=settings.browser_stagehand_base_url,
            enabled=settings.browser_enabled,
            expected_version=settings.browser_stagehand_expected_version
            or self._manifest("stagehand"),
            model_provider=settings.browser_stagehand_model_provider,
            model_name=settings.browser_stagehand_model_name,
        )
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
        try:
            verify_internal_control(self.settings.internal_control_token, token)
        except GoogleControlAuthError as exc:
            code = 503 if exc.code == "internal_control_token_unconfigured" else 403
            raise HTTPException(status_code=code, detail=exc.code) from exc

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

    async def browser_health(self) -> dict[str, Any]:
        harness = await self.harness.status()
        stagehand = await self.stagehand.status()
        policy = load_browser_policy()

        self._sync_degraded(harness.state, DegradedCode.BROWSER_HARNESS_UNAVAILABLE)
        self._sync_degraded(stagehand.state, DegradedCode.BROWSER_SEMANTIC_UNAVAILABLE)

        return {
            "capability": "browser_fabric",
            "harness": harness.model_dump(mode="json"),
            "stagehand": stagehand.model_dump(mode="json"),
            "governance": governance_state(),
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


__all__ = ["AutomationHealthApi", "governance_state"]
