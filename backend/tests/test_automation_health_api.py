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


async def test_automation_health_reports_governance_pending(client):
    """§368 — production activation is blocked while decisions are PENDING."""
    ac, _app = client
    body = (await ac.get("/v1/automation/health", headers=HEADERS)).json()
    assert body["capability"] == "automation_fabric"
    assert body["governance"]["production_activation_permitted"] is False
    assert "VAN-ADOPT-N8N-001.yaml" in body["governance"]["owner_decisions_pending"]
    assert "VAN-AMEND-SECURITY-POLICY-001.md" in body["governance"]["owner_decisions_pending"]


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
    assert body["max_autonomy_tier"] == "L3"
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


def test_governance_state_is_read_not_configured():
    """§365 — an agent can read signature status; it cannot set it."""
    state = governance_state()
    assert state["owner_decisions_missing"] == []
    assert state["production_activation_permitted"] is False
