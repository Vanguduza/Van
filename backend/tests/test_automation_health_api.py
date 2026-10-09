"""Rev 1.3 §§219, 368, 421 — the automation/browser health surface.

Two properties matter. The endpoints are internal-control only, because they
expose runtime identity and governance state. And they tell the truth while the
owner decisions are unsigned: `production_activation_permitted` is False, and no
runtime claims READY.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.automation.health import governance_state
from van_gateway.config import get_settings

INGRESS = "test-ingress-token-0123456789abcdef"
INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "health.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": INGRESS}
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def test_automation_health_requires_internal_control(client):
    ac, _app = client
    assert (await ac.get("/v1/automation/health")).status_code in (401, 403)
    assert (await ac.get("/v1/browser/health")).status_code in (401, 403)


async def test_automation_health_reports_governance_approved_but_production_gated(client):
    """§368 — the owner signed all four decisions on 2026-09-18; production is still gated.

    Owner signatures are satisfied, so nothing is reported as a pending owner decision. Until
    2026-09-29 this test asserted `production_activation_permitted is True`, which encoded the
    §6 governance bypass: approval was read as activation while the Stagehand production gate,
    signed ingress and live qualification were PENDING. Activation now needs every gate GREEN.
    """
    ac, _app = client
    body = (await ac.get("/v1/automation/health", headers=HEADERS)).json()
    assert body["capability"] == "automation_fabric"
    governance = body["governance"]
    assert governance["owner_decisions_pending"] == []
    assert governance["owner_decisions_missing"] == []
    assert governance["production_activation_permitted"] is False
    assert "VAN-ADOPT-STAGEHAND-001.yaml:production_gate" in governance["production_gates_not_green"]
    # The surface explains itself: every gate names its status and the file it was read from.
    for gate in governance["gates"]:
        assert set(gate) >= {"decision", "gate", "status", "source", "path"}
        assert gate["source"].startswith("docs/decisions/")
    browser = (await ac.get("/v1/browser/health", headers=HEADERS)).json()
    assert browser["governance"]["production_activation_permitted"] is False


async def test_automation_health_does_not_claim_ready(client):
    """§369 — code existing is not readiness."""
    ac, _app = client
    body = (await ac.get("/v1/automation/health", headers=HEADERS)).json()
    assert body["runtime"]["state"] != "READY"
    assert body["runtime"]["evidence_pointer"] is None
    assert body["ingress_enabled"] is False
    assert body["egress_enabled"] is False


async def test_automation_health_states_t0_isolation(client):
    """§§68, 421 — the trading invariant is observable, not just documented."""
    ac, _app = client
    body = (await ac.get("/v1/automation/health", headers=HEADERS)).json()
    assert body["t0_isolation"] == {
        "in_tick_to_order_path": False,
        "may_send_live_orders": False,
        "vati_independent_of_automation": True,
    }
    assert body["engine_success_is_owner_success"] is False
    assert body["node_catalog_denies_community"] is True


async def test_browser_health_reports_ladder_cap_and_scope(client):
    ac, _app = client
    body = (await ac.get("/v1/browser/health", headers=HEADERS)).json()
    # Owner decision 2026-09-18: autonomy permitted as a Hermes-managed subagent.
    assert body["max_autonomy_tier"] == "L5"
    assert body["raw_cookie_export_forbidden"] is True
    assert body["harness"]["state"] != "READY"
    assert body["stagehand"]["state"] != "READY"
    assert body["degradation_scope"]["vati_t0_unaffected"] is True
    assert body["degradation_scope"]["native_and_automation_paths_unaffected"] is True


async def test_degraded_registry_reflects_unavailable_fabric(client):
    """§§99-100 — the degraded surface names what still works."""
    ac, app = client
    await ac.get("/v1/automation/health", headers=HEADERS)
    await ac.get("/v1/browser/health", headers=HEADERS)
    codes = set(app.state.degraded.codes())
    assert "AUTOMATION_FABRIC_UNAVAILABLE" in codes
    assert "BROWSER_HARNESS_UNAVAILABLE" in codes
    assert "BROWSER_SEMANTIC_UNAVAILABLE" in codes
    assert "AUTOMATION_INGRESS_DISABLED" in codes

    snapshot = {entry.code.value: entry for entry in app.state.degraded.snapshot()}
    fabric = snapshot["AUTOMATION_FABRIC_UNAVAILABLE"]
    # Fail-closed reporting must say what still works, per the Truth Protocol.
    assert "VATI trading" in fabric.still_works
    assert fabric.restore_action


def test_governance_state_is_read_from_the_decision_files():
    """§365 — the gateway reads signature status; it never configures it.

    Flipping this to True required editing `docs/decisions/*`, which is why the
    state is computed from those files rather than from a setting.
    """
    state = governance_state()
    assert state["owner_decisions_missing"] == []
    assert state["owner_decisions_pending"] == []
    assert state["gate_model_error"] is None
    # The real repository today: intent approved, production gates pending => not permitted.
    assert state["production_activation_permitted"] is False


async def test_computer_use_health_requires_internal_control(client):
    ac, _app = client
    assert (await ac.get("/v1/computer-use/health")).status_code in (401, 403)


async def test_computer_use_health_reports_no_worker_for_any_surface(client):
    """P2-CU-001 — the fabric's missing executor, said out loud.

    Every matrix that listed the Computer Interaction Fabric read it as built, because the
    module compiles and its refusals are real. What it has no worker for is every surface,
    and until this endpoint existed nothing in the running system said so.
    """
    ac, _app = client
    body = (await ac.get("/v1/computer-use/health", headers=HEADERS)).json()
    assert body["capability"] == "computer_interaction_fabric"
    assert body["surfaces"] == {
        "BROWSER": False, "DESKTOP": False, "TERMINAL": False, "MOBILE": False,
    }
    assert body["surfaces_with_a_worker"] == []
    # §38 — the constraint that is the whole value of the fabric, reported not assumed.
    assert body["typed_operations_only"] is True
    assert body["arbitrary_execution_primitive"] is None
    assert body["max_action_class"] == "A3"
    # §421 — degradation is scoped. Nothing else stops because this has no worker.
    assert body["degradation_scope"] == {
        "browser_fabric_unaffected": True,
        "native_and_automation_paths_unaffected": True,
        "vati_t0_unaffected": True,
    }


async def test_computer_use_degradation_names_what_still_works(client):
    ac, app = client
    await ac.get("/v1/computer-use/health", headers=HEADERS)
    snapshot = {entry.code.value: entry for entry in app.state.degraded.snapshot()}
    entry = snapshot["COMPUTER_USE_NO_SURFACE_WORKER"]
    assert "VATI" in entry.still_works
    assert "Browser fabric" in entry.still_works
    # The restore action has to name the actual change, or it is a shrug in a field.
    assert "SURFACE_WORKERS" in entry.restore_action


async def test_browser_health_surfaces_stagehand_placement_and_per_capability_gates(client):
    """Reviewer I minor 8 — stagehand_production_state() was never surfaced, and one global
    flag made Stagehand's pending gates read as the whole browser fabric's."""
    ac, _app = client
    body = (await ac.get("/v1/browser/health", headers=HEADERS)).json()
    activation = body["production_activation"]
    stagehand = activation["stagehand"]
    # unit M's projection, verbatim keys, fail-closed here (no van-browser-core worker).
    assert stagehand["state"] == "PRODUCTION_DISABLED"
    assert stagehand["reason"]
    assert stagehand["required_zone"] == "van-browser-core"
    assert stagehand["model"] == "anthropic/claude-sonnet-5"
    assert stagehand["production_activation_permitted"] is False
    assert "VAN-ADOPT-STAGEHAND-001.yaml:production_gate" in stagehand["gates_not_green"]
    # The Harness path is judged on its own gates, none of them Stagehand's.
    harness = activation["browser_harness"]
    assert not any("STAGEHAND" in g for g in harness["gates_not_green"])
    # Existing semantics are unchanged.
    assert body["governance"]["production_activation_permitted"] is False
    assert set(body["governance"]["production_activation_permitted_by_capability"]) == {
        "n8n", "browser_harness", "stagehand", "jev_browser_effect",
    }
    # Review I2 N-7: Jev browser effect has its own VAN gate, SHADOW_ONLY today.
    assert activation["jev_browser_effect"]["production_activation_permitted"] is False
    assert "VAN-JEV-BROWSER-EFFECT-001.yaml:jev_browser_effect" in activation["jev_browser_effect"]["gates_not_green"]


async def test_browser_health_stagehand_status_is_the_gate_verdict_for_these_settings(monkeypatch):
    """Unit G2a request: health builds StagehandAdapter with its own settings, so a wired but
    not-permitted Stagehand reports POLICY_DISABLED and the reason, not CONFIGURED."""
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    monkeypatch.setenv("VAN_BROWSER_STAGEHAND_BASE_URL", "http://127.0.0.1:9/stagehand")
    monkeypatch.setenv("VAN_BROWSER_STAGEHAND_ZONE", "van-browser-core")
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-Van-Ingress-Token": INGRESS}) as ac:
        async with app.router.lifespan_context(app):
            body = (await ac.get("/v1/browser/health", headers=HEADERS)).json()
    assert body["stagehand"]["state"] == "POLICY_DISABLED"
    assert body["stagehand"]["detail"] == "STAGEHAND_PRODUCTION_DISABLED:STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"
    assert body["production_activation"]["stagehand"]["reason"] == "STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"


async def test_health_stagehand_gate_uses_the_health_settings_not_the_process_default(tmp_path):
    from tests.conftest_automation import make_store
    from van_gateway.automation.health import AutomationHealthApi
    from van_gateway.config import Settings
    from van_gateway.degraded.registry import DegradedRegistry

    store = await make_store(tmp_path)
    settings = Settings(browser_enabled=True, browser_stagehand_zone="van-browser-core",
                        browser_stagehand_base_url="http://127.0.0.1:9/stagehand")
    api = AutomationHealthApi(store, settings, degraded=DegradedRegistry())
    status = await api.stagehand.status()
    assert status.state.value == "POLICY_DISABLED"
    # The process default has the browser fabric off; the reason proves these settings were read.
    assert status.detail == "STAGEHAND_PRODUCTION_DISABLED:STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"
