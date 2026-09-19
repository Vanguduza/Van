"""P4-SEC-011: the trading OAuth callback built HTML by interpolation.

Nothing interpolated was attacker-controlled at the time, so it was not exploitable. It was
one parameter away: `broker` is a path segment, and an HTTPException detail can carry a
query parameter back into the page. This is the cheapest finding in the register and the
easiest to leave open until somebody adds a field.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings

INGRESS = "oauth-ingress-token-0123456789abc"
PAYLOAD = '<script>alert(1)</script>'
#: The same attempt without a slash, so it survives being a single path segment.
PATH_PAYLOAD = '<img src=x onerror=alert(1)>'


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "oauth.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "oauth-internal-token")
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "oauth-internal-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


@pytest.mark.asyncio
async def test_a_failure_page_escapes_what_it_reflects(client):
    ac, app = client
    from fastapi import HTTPException

    async def boom(broker, params):
        raise HTTPException(status_code=400, detail=f"unknown broker {broker} {PAYLOAD}")

    app.state.onboarding.oauth_callback = boom
    resp = await ac.get(f"/v1/trading/oauth/{PATH_PAYLOAD}/callback")
    assert resp.status_code == 400, resp.text
    # Both halves: the detail the handler composed, and the path segment inside it.
    assert "<script>" not in resp.text and "<img" not in resp.text
    assert "&lt;script&gt;" in resp.text and "&lt;img" in resp.text


@pytest.mark.asyncio
async def test_a_success_page_escapes_the_broker_it_names(client):
    ac, app = client

    async def linked(broker, params):
        return {"broker": PAYLOAD}

    app.state.onboarding.oauth_callback = linked
    resp = await ac.get("/v1/trading/oauth/deriv/callback")
    assert resp.status_code == 200
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


@pytest.mark.asyncio
async def test_the_callback_is_reachable_without_the_ingress_token(client):
    """It has to be: the browser coming back from the broker carries no VAN credential.

    Which is exactly why the escaping matters here and nowhere else.
    """
    ac, app = client

    async def linked(broker, params):
        return {"broker": "deriv"}

    app.state.onboarding.oauth_callback = linked
    resp = await ac.get("/v1/trading/oauth/deriv/callback")
    assert resp.status_code == 200


def test_the_gateway_has_no_other_unescaped_html_interpolation():
    """A rule that only holds where somebody remembered is not a rule."""
    source = (Path(__file__).resolve().parents[1] / "van_gateway" / "app.py").read_text()
    html_responses = re.findall(r"HTMLResponse\(\s*(?:f?\"[^\"]*\"\s*)+", source)
    assert html_responses, "the callback's responses should have been found"
    for block in html_responses:
        for interpolation in re.findall(r"\{([^}]*)\}", block):
            assert "html.escape" in interpolation, (
                f"unescaped interpolation in an HTML response: {{{interpolation}}}"
            )
