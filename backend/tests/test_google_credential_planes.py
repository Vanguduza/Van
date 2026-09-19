"""P2-GOOG-003 — the Google credential planes, reported one by one.

Four credentials reach Google and they expire independently: the owner's refresh token,
the model runtime's entitlement, the cloud project credentials for discoveryengine, and a
browser profile the owner signed in with. `GoogleCredentialPlane` already named all four
and each had a reporter. Nothing composed them, so `/v1/google/status` answered "is Google
connected" with one boolean derived from the refresh token alone.

§421 requires degradation to be scoped, and the two wrong answers here are symmetrical:
everything broken because one credential lapsed, or everything fine because the one
credential that is checked happens to be good. Both are tested.
"""

from __future__ import annotations

import pytest

from van_gateway.google.mesh import GoogleCredentialPlane
from van_gateway.google.planes import (
    PlaneState,
    capabilities_by_plane,
    plane_health,
    summarise,
)


class FakeWorkspace:
    """The refresh-token plane, as GoogleService reports it."""

    def __init__(self, *, connected: bool, ready: bool = True) -> None:
        self._connected = connected
        self._ready = ready

    def ready(self) -> bool:
        return self._ready

    async def status(self):
        class Status:
            connected = self._connected

        return Status()


class FakeProvider:
    """A knowledge provider's status, which is where two of the planes are answered."""

    def __init__(self, state: str, locus: str = "somewhere") -> None:
        self._state = state
        self._locus = locus

    async def status(self):
        class State:
            value = self._state

        class Status:
            state = State()
            credential_locus = self._locus

        return Status()


class FakeBroker:
    def __init__(self, *, registered: bool, status: str = "active") -> None:
        self._registered = registered
        self._status = status

    async def principal_status(self, owner_id: str | None = None):
        class Principal:
            registered = self._registered
            status = self._status

        return Principal()


async def _health(**overrides):
    defaults = dict(
        google=FakeWorkspace(connected=True),
        notebook_enterprise=FakeProvider("READY"),
        notebook_consumer=FakeProvider("READY"),
        broker=FakeBroker(registered=True),
    )
    defaults.update(overrides)
    return await plane_health(**defaults)


@pytest.mark.asyncio
class TestEachPlaneIsAnsweredByItsOwnAuthority:
    async def test_all_four_planes_are_reported(self):
        planes = await _health()
        assert {p.plane for p in planes} == set(GoogleCredentialPlane)

    async def test_every_plane_names_where_its_credential_lives(self):
        """An owner told a plane is broken needs to know where to go and fix it."""
        for plane in await _health():
            assert plane.credential_locus.strip()

    async def test_a_revoked_refresh_token_does_not_take_the_others_down(self):
        """The finding's first wrong answer: everything broken because one lapsed."""
        planes = {p.plane: p for p in await _health(google=FakeWorkspace(connected=False))}
        assert planes[GoogleCredentialPlane.WORKSPACE_OAUTH].usable is False
        assert planes[GoogleCredentialPlane.CLOUD_SERVICE].usable is True
        assert planes[GoogleCredentialPlane.CONSUMER_SESSION].usable is True
        assert planes[GoogleCredentialPlane.GEMINI_RUNTIME].usable is True

    async def test_a_healthy_refresh_token_does_not_vouch_for_the_others(self):
        """The second wrong answer, and the one the old surface actually gave: Google
        reported connected while the cloud credential and the browser profile were dead."""
        planes = {
            p.plane: p
            for p in await _health(
                notebook_enterprise=FakeProvider("UNCONFIGURED"),
                notebook_consumer=FakeProvider("CONFIGURED"),
            )
        }
        assert planes[GoogleCredentialPlane.WORKSPACE_OAUTH].usable is True
        assert planes[GoogleCredentialPlane.CLOUD_SERVICE].usable is False
        assert planes[GoogleCredentialPlane.CONSUMER_SESSION].usable is False

    async def test_configured_is_not_ready(self):
        """CONFIGURED means the credential is present and has not been exercised.

        Reporting it as READY is the optimistic answer the verification discipline exists
        to refuse — and it is the specific shape that would make this surface useless,
        because an unexercised credential is exactly the one about to surprise someone.
        """
        planes = {
            p.plane: p for p in await _health(notebook_enterprise=FakeProvider("CONFIGURED"))
        }
        assert planes[GoogleCredentialPlane.CLOUD_SERVICE].state == PlaneState.AUTH_REQUIRED

    async def test_unconfigured_and_auth_required_are_distinguished(self):
        """They need different actions from the owner, and reporting one as the other
        sends them to the wrong place: set something up, versus sign in again."""
        never_set_up = {p.plane: p for p in await _health(google=FakeWorkspace(connected=False, ready=False))}
        assert never_set_up[GoogleCredentialPlane.WORKSPACE_OAUTH].state == PlaneState.UNCONFIGURED
        revoked = {p.plane: p for p in await _health(google=FakeWorkspace(connected=False, ready=True))}
        assert revoked[GoogleCredentialPlane.WORKSPACE_OAUTH].state == PlaneState.AUTH_REQUIRED

    async def test_an_unregistered_principal_is_not_a_working_runtime(self):
        planes = {p.plane: p for p in await _health(broker=FakeBroker(registered=False))}
        assert planes[GoogleCredentialPlane.GEMINI_RUNTIME].usable is False


@pytest.mark.asyncio
class TestWhatEachPlaneServesComesFromTheRegistry:
    async def test_the_capability_split_is_read_not_kept(self):
        """A second list of which capability uses which credential would drift from the
        registry, and drift here means telling the owner the wrong thing is broken."""
        grouped = capabilities_by_plane()
        assert grouped[GoogleCredentialPlane.WORKSPACE_OAUTH.value] == ("workspace_api",)
        assert "gemini_notebook_enterprise" in grouped[GoogleCredentialPlane.CLOUD_SERVICE.value]
        assert "gemini_notebook" in grouped[GoogleCredentialPlane.CONSUMER_SESSION.value]
        assert "gemini" in grouped[GoogleCredentialPlane.GEMINI_RUNTIME.value]

    async def test_every_declared_capability_is_attributed_to_exactly_one_plane(self):
        import json
        from pathlib import Path

        registry = json.loads(
            (Path(__file__).resolve().parents[2] / "registries" / "google_capabilities.json")
            .read_text(encoding="utf-8")
        )
        declared = {row["id"] for row in registry["capabilities"]}
        grouped = capabilities_by_plane()
        attributed = [c for ids in grouped.values() for c in ids]
        assert sorted(attributed) == sorted(declared)
        assert len(attributed) == len(set(attributed)), "a capability is on two planes"

    async def test_a_failing_plane_names_what_it_takes_with_it(self):
        planes = await _health(notebook_consumer=FakeProvider("UNCONFIGURED"))
        consumer = next(p for p in planes if p.plane is GoogleCredentialPlane.CONSUMER_SESSION)
        assert "gemini_notebook" in consumer.serves


@pytest.mark.asyncio
class TestTheSummaryDoesNotOverstateWhatItKnows:
    async def test_a_ready_credential_is_not_a_working_capability(self):
        """The conflation this surface could most easily cause.

        "capabilities_available" would be read as "VAN can do these". A working credential
        is not a working capability — the runtime can still be unreachable, rate limited or
        uncertified — so the field is named for the question it actually answers.
        """
        body = summarise(await _health())
        assert "capabilities_available" not in body
        assert "capabilities_whose_credential_plane_is_ready" in body
        assert "/v1/capabilities/status" in body["credential_readiness_is_not_capability_readiness"]

    async def test_working_and_blocked_together_cover_everything_declared(self):
        body = summarise(await _health(notebook_consumer=FakeProvider("UNCONFIGURED")))
        both = set(body["capabilities_whose_credential_plane_is_ready"]) | set(
            body["capabilities_blocked_by_their_credential_plane"]
        )
        declared = {c for ids in capabilities_by_plane().values() for c in ids}
        assert both == declared
        # And nothing is in both lists, which would let a reader count it either way.
        assert not set(body["capabilities_whose_credential_plane_is_ready"]) & set(
            body["capabilities_blocked_by_their_credential_plane"]
        )

    async def test_all_planes_ready_means_all_four(self):
        assert summarise(await _health())["all_planes_ready"] is True
        assert summarise(await _health(broker=FakeBroker(registered=False)))["all_planes_ready"] is False


@pytest.mark.asyncio
class TestTheRouteIsReachableThroughTheRealApp:
    """Driven through create_app rather than the module, per the reachability discipline.

    A composer that works when called directly and is not reachable from the running app
    is the defect shape this whole programme is about. The route is on the owner ingress
    surface rather than internal control, because which of the owner's own credentials
    have lapsed is the owner's business and it exposes no runtime identity.
    """

    @pytest.fixture(autouse=True)
    def _settings(self, monkeypatch, tmp_path):
        from cryptography.fernet import Fernet

        from van_gateway.config import get_settings

        monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "planes.sqlite3"))
        monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("VAN_INGRESS_TOKEN", "planes-ingress-token-0123456789")
        monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "planes-internal")
        monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "planes-internal")
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    @staticmethod
    async def _as_owner_device(ac, app):
        """The route is the owner's, so the test authenticates as one.

        `/v1/google/status` is an owner-device route and this is the finer-grained version
        of the same question: which of the owner's own credentials have lapsed is the
        owner's business. Putting it behind internal control would answer the finding for
        an operator and not for the person whose sign-in expired.
        """
        ticket = await app.state.auth.create_pairing_ticket("planes-device")
        enrolled = await app.state.auth.pair_device(
            ticket.token, "planes-device", "s" * 32, "PEM", "planes-device"
        )
        ac.headers.update({"X-Van-Device-Token": enrolled.access_token})

    async def test_the_planes_route_answers_through_the_app(self):
        from httpx import ASGITransport, AsyncClient

        from van_gateway.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test",
            headers={"X-Van-Ingress-Token": "planes-ingress-token-0123456789"},
        ) as ac:
            async with app.router.lifespan_context(app):
                await self._as_owner_device(ac, app)
                response = await ac.get("/v1/google/planes")

        assert response.status_code == 200, response.text
        body = response.json()
        assert {p["plane"] for p in body["planes"]} == {
            "workspace_oauth", "gemini_runtime", "cloud_service", "consumer_session",
        }
        # Nothing is configured in a test environment, so every plane must say so rather
        # than defaulting to ready. A surface that reports health it has not established is
        # the failure this finding is about, one level up.
        assert body["all_planes_ready"] is False
        assert body["capabilities_whose_credential_plane_is_ready"] == []
        assert body["planes_fail_independently"] is True

    async def test_every_plane_in_the_response_says_why_it_is_not_ready(self):
        from httpx import ASGITransport, AsyncClient

        from van_gateway.app import create_app

        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"X-Van-Ingress-Token": "planes-ingress-token-0123456789"},
        ) as ac:
            async with app.router.lifespan_context(app):
                await self._as_owner_device(ac, app)
                body = (await ac.get("/v1/google/planes")).json()

        for plane in body["planes"]:
            if not plane["usable"]:
                assert plane["detail"], f"{plane['plane']} is not ready and does not say why"
