from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings


INGRESS = "resolver-test-ingress-0123456789"
INTERNAL = "resolver-test-hermes-internal"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "resolver.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_resolver_is_internal_only_and_returns_registry_policy():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Van-Ingress-Token": INGRESS},
        ) as client:
            # P0-SEC-001 — public ingress is refused by the scope check, not by the
            # device-auth boundary. The old order meant a paired owner device would have
            # reached this Hermes-only route.
            denied = await client.post("/v1/runtime/resolve", json={"text": "halt autonomous trading"})
            assert denied.status_code == 403
            assert denied.json()["required_scope"] == "runtime"

            resolved = await client.post(
                "/v1/runtime/resolve",
                json={"text": "halt autonomous trading"},
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert resolved.status_code == 200
            body = resolved.json()
            assert body["mode"] == "EXACT_ACTION"
            assert body["action_id"] == "trading.halt"
            assert body["canonical_action_class"] == "A4"
            assert body["no_stale_replay"] is True
            assert body["max_age_seconds"] == 5


@pytest.mark.asyncio
async def test_ambiguous_command_remains_hermes_interpretation_task():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Van-Internal-Token": INTERNAL},
        ) as client:
            response = await client.post("/v1/runtime/resolve", json={"text": "resume that thing from yesterday"})
            assert response.status_code == 200
            body = response.json()
            assert body["mode"] == "HERMES_INTERPRETATION_REQUIRED"
            assert body["action_id"] is None