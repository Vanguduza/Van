"""P0-SEC-001: one static token was gateway root, and a model-driven runtime held it.

`X-Van-Internal-Token` alone minted a pairing ticket; `/v1/devices/pair` then needed no
authentication at all and returned both the ingress bearer and a device access token. The
same token reached Project Truth injection, device revocation, Google connect and revoke,
the trading halt, every automation route, browser mutations and context scope delete. The
Hermes MCP shim reads it from `~/.config/van/gateway.env`.

Three defects, three sets of tests: the credential is now scoped, device enrolment is its
own credential the shim does not read, and a failed internal check no longer falls through
to owner-device authentication.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.control_scopes import (
    DEFAULT_SCOPES,
    ControlAuthority,
    ControlScope,
    ControlScopeError,
    parse_scoped_credentials,
)
from van_gateway.config import get_settings

ROOT = Path(__file__).resolve().parents[2]
INGRESS = "scope-ingress-token-0123456789abcdef"
INTERNAL = "scope-internal-token-0123456789abcdef"
ENROLMENT = "scope-enrolment-token-0123456789abcd"
AUTOMATION_ONLY = "scope-automation-only-token-0123456789"


class TestTheCredentialIsScoped:
    def test_the_legacy_token_does_not_carry_device_enrolment(self):
        """The one scope that turns a control credential into owner-device authority."""
        assert ControlScope.DEVICE_ENROLMENT not in DEFAULT_SCOPES
        authority = ControlAuthority(legacy_token=INTERNAL)
        assert not authority.permits(INTERNAL, ControlScope.DEVICE_ENROLMENT)
        assert authority.permits(INTERNAL, ControlScope.AUTOMATION)

    def test_a_scoped_credential_reaches_only_its_scopes(self):
        authority = ControlAuthority(scoped=f"automation,browser:{AUTOMATION_ONLY}")
        assert authority.permits(AUTOMATION_ONLY, ControlScope.AUTOMATION)
        assert authority.permits(AUTOMATION_ONLY, ControlScope.BROWSER)
        for denied in (ControlScope.TRADING, ControlScope.GOOGLE, ControlScope.DEVICE_ENROLMENT):
            assert not authority.permits(AUTOMATION_ONLY, denied), denied

    def test_an_unknown_token_holds_nothing(self):
        authority = ControlAuthority(legacy_token=INTERNAL)
        assert authority.granted_scopes("something-else") == frozenset()
        assert authority.granted_scopes("") == frozenset()
        assert authority.granted_scopes(None) == frozenset()

    def test_an_unknown_scope_name_is_a_configuration_error(self):
        """Skipping it would leave an operator believing a surface was reachable."""
        with pytest.raises(ControlScopeError, match="unknown control scope"):
            parse_scoped_credentials(f"automation,teleportation:{AUTOMATION_ONLY}")

    def test_a_credential_with_no_token_or_a_short_one_is_refused(self):
        with pytest.raises(ControlScopeError):
            parse_scoped_credentials("automation")
        with pytest.raises(ControlScopeError, match="shorter than 32"):
            parse_scoped_credentials("automation:short")

    def test_several_credentials_parse_from_one_setting(self):
        creds = parse_scoped_credentials(
            f"automation:{AUTOMATION_ONLY}; trading,google:{INTERNAL}"
        )
        assert len(creds) == 2
        assert {s for c in creds for s in c.scopes} == {
            ControlScope.AUTOMATION, ControlScope.TRADING, ControlScope.GOOGLE
        }

    def test_describe_never_returns_a_token(self):
        authority = ControlAuthority(legacy_token=INTERNAL, device_enrolment_token=ENROLMENT)
        described = authority.describe()
        assert INTERNAL not in str(described) and ENROLMENT not in str(described)
        assert described["device_enrolment_granted"] is True

    def test_collapsing_the_split_is_visible_rather_than_silent(self):
        """An operator who set both to the same string has rebuilt one root token."""
        shared = ControlAuthority(legacy_token=INTERNAL, device_enrolment_token=INTERNAL)
        assert shared.describe()["device_enrolment_shares_a_token"] is True
        split = ControlAuthority(legacy_token=INTERNAL, device_enrolment_token=ENROLMENT)
        assert split.describe()["device_enrolment_shares_a_token"] is False

    def test_no_credentials_means_nothing_is_reachable(self):
        authority = ControlAuthority()
        assert not authority.configured
        for scope in ControlScope:
            assert not authority.permits("anything", scope)


class TestTheHermesShimCannotEnrolADevice:
    def test_the_shim_reads_only_the_internal_control_token(self):
        shim = (ROOT / "hermes/mcp/owner_runtime_stdio.mjs").read_text(encoding="utf-8")
        assert "VAN_INTERNAL_CONTROL_TOKEN" in shim
        assert "VAN_DEVICE_ENROLMENT_TOKEN" not in shim, (
            "the agent runtime must not hold the credential that mints owner authority"
        )

    def test_no_hermes_facing_file_carries_the_enrolment_credential(self):
        for path in (ROOT / "hermes").rglob("*"):
            if path.is_file() and path.suffix in {".mjs", ".js", ".sh", ".json", ".md"}:
                assert "VAN_DEVICE_ENROLMENT_TOKEN" not in path.read_text(
                    encoding="utf-8", errors="replace"
                ), path


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "scopes.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", ENROLMENT)
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


@pytest.mark.asyncio
class TestTheGatewayEnforcesIt:
    async def test_the_internal_token_can_no_longer_mint_a_pairing_ticket(self, client):
        """The audit's first step: one string, and then owner-device authority."""
        ac, _ = client
        resp = await ac.post(
            "/v1/devices/pairing-ticket",
            json={"label": "phone", "ttl_seconds": 600},
            headers={"X-Van-Internal-Token": INTERNAL},
        )
        assert resp.status_code == 403
        assert resp.json()["required_scope"] == "device_enrolment"

    async def test_the_enrolment_credential_can(self, client):
        ac, _ = client
        resp = await ac.post(
            "/v1/devices/pairing-ticket",
            json={"label": "phone", "ttl_seconds": 600},
            headers={"X-Van-Internal-Token": ENROLMENT},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["pairing_token"]

    async def test_the_enrolment_credential_reaches_nothing_else(self, client):
        ac, _ = client
        resp = await ac.get(
            "/v1/runtime/status", headers={"X-Van-Internal-Token": ENROLMENT}
        )
        assert resp.status_code == 403
        assert resp.json()["required_scope"] == "runtime"

    async def test_an_owner_device_cannot_reach_a_hermes_only_route(self, client):
        """The fall-through. A wrong internal credential used to be retried as device auth."""
        ac, app = client
        ticket = await app.state.auth.create_pairing_ticket("scope-dev")
        enrolled = await app.state.auth.pair_device(
            ticket.token, "scope-dev", "s" * 32, "PEM", "scope-dev"
        )
        resp = await ac.get(
            "/v1/runtime/status",
            headers={"X-Van-Device-Token": enrolled.access_token},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "internal_control_unauthorized"

    async def test_a_wrong_internal_token_is_terminal_not_retried(self, client):
        ac, app = client
        ticket = await app.state.auth.create_pairing_ticket("scope-dev2")
        enrolled = await app.state.auth.pair_device(
            ticket.token, "scope-dev2", "s" * 32, "PEM", "scope-dev2"
        )
        resp = await ac.post(
            "/v1/devices/scope-dev2/revoke",
            headers={
                "X-Van-Internal-Token": "wrong-but-long-enough-token-012345",
                "X-Van-Device-Token": enrolled.access_token,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["required_scope"] == "device_enrolment"

    async def test_the_health_surface_reports_the_split(self, client):
        ac, app = client
        described = app.state.control_authority.describe()
        assert described["device_enrolment_granted"] is True
        assert described["device_enrolment_shares_a_token"] is False
        assert INTERNAL not in str(described)
