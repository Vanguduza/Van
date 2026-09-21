"""GAP-F-009 — a scoped-only privileged credential reaches every router surface.

Before this, six routers compared the presented token to the legacy
`internal_control_token` alone, so a deployment configured with only
`internal_control_scoped_tokens` got 503 on /v1/runtime/*, /v1/automation/*,
/v1/browser/* (mutations), /v1/missions (POST), /v1/understanding/observe and the
automation/browser health routes even with the right scope.
"""
from __future__ import annotations

import httpx
import pytest

from van_gateway.app import create_app
from van_gateway.config import get_settings

RUNTIME = "runtime-scoped-token-0123456789abcdef0123"
AUTOMATION = "automation-scoped-token-0123456789abcdef01"
MISSIONS = "missions-scoped-token-0123456789abcdef0123"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "ingress-token-0123456789abcdef0123456789")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "")
    monkeypatch.setenv(
        "VAN_INTERNAL_CONTROL_SCOPED_TOKENS",
        f"runtime:{RUNTIME}; automation:{AUTOMATION}; missions:{MISSIONS}",
    )
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "scoped.sqlite3"))
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            yield ac
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_runtime_scope_reaches_runtime_status(client):
    r = await client.get("/v1/runtime/status", headers={"X-Van-Internal-Token": RUNTIME})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_runtime_scope_reaches_automation_health(client):
    r = await client.get("/v1/automation/health", headers={"X-Van-Internal-Token": RUNTIME})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_wrong_scope_is_refused_not_unconfigured(client):
    r = await client.get("/v1/runtime/status", headers={"X-Van-Internal-Token": AUTOMATION})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] != "internal_control_token_unconfigured"
