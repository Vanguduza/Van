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


async def test_automation_health_reports_governance_approved(client):
    """§368 — the owner signed all four decisions on 2026-09-18.

    Governance is now satisfied, so this asserts the *other* half of §368: approval
    unblocks activation but does not by itself make anything READY. That still needs
    live canary evidence, which `test_automation_health_does_not_claim_ready` covers.
    """
    ac, _app = client
    body = (await ac.get("/v1/automation/health", headers=HEADERS)).json()
    assert body["capability"] == "automation_fabric"
    assert body["governance"]["owner_decisions_pending"] == []
    assert body["governance"]["owner_decisions_missing"] == []
    assert body["governance"]["production_activation_permitted"] is True


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
    assert state["production_activation_permitted"] is True


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
