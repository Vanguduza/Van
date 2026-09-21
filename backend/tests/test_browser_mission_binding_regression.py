"""Rev 1.5 §23 (RB-044) — the interactive browser session attaches to a Mission; it
never manufactures one.

This is the regression proof the matrix asks for, and it is a regression proof rather
than a feature test because the defect it guards against is one VAN already had once:
P0-EXEC-001 was a command path where execution happened without a Mission, and the
correction was that the *command* creates the Mission. §23 extends the same rule to the
browser, from the other direction — now that Missions exist, the risk is a second one.

Three distinct claims, each of which can be true while the others are false:

* §23.1 — command-originated work binds **by reference** to the Mission the command
  already created. Not a copy, not a child, not a new Mission with the same title;
* §23.2 — manual browsing has no Mission at all. Opening a web page is not a unit of
  agent work, and a system that mints a Mission for it fills the owner's Missions page
  with things they never asked VAN to do;
* §23.4 — a browser worker saying it finished does not make the Mission
  `VERIFIED_SUCCESS`. PR #48's contract applies unchanged.

The counterexample this file is written against: a binder that calls
`MissionService.create` when the mission_id it was handed does not resolve. Every
assertion about activities would still pass — the session would be bound to *a* Mission,
with the right executor_ref and the right capability — and the owner would have two
Missions for one request, the second of which nobody authorised.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from conftest_automation import make_store
from van_gateway.automation.external_runtime import (
    ExternalRuntimeRegistry,
    ReadinessEvidence,
)
from van_gateway.browser.control_lease import ControlLeaseService
from van_gateway.browser.interactive_models import Viewport
from van_gateway.browser.interactive_service import InteractiveSessionService
from van_gateway.browser.service import BrowserSessionBroker
from van_gateway.capability.models import ReadinessSource
from van_gateway.capability.readiness import (
    AutomationReadiness,
    ExternalRuntimeReadiness,
)
from van_gateway.capability.registry import CapabilityRegistry
from van_gateway.config import get_settings
from van_gateway.mission.binding import (
    INTERACTIVE_BROWSER_CAPABILITY,
    MissionBinder,
)
from van_gateway.mission.models import (
    ActivityState,
    AuthorityEnvelope,
    MissionOrigin,
    MissionState,
)
from van_gateway.mission.service import MissionError, MissionService
from van_gateway.models import ActionClass, OriginChannel

INGRESS = "rb044-ingress-token-0123456789"
INTERNAL = "rb044-internal-token-0123456789"


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "rb044.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def stack(tmp_path):
    store = await make_store(tmp_path)
    runtime = ExternalRuntimeRegistry(store)
    # §23.1's activity is declared against `browser_stream_host`, and an unproven host is
    # not ready. Recording evidence here is staging the *world*, not the verdict: the
    # readiness ladder still decides, and the refusal path is asserted in its own class
    # below against a stack with no evidence at all.
    await runtime.record_evidence(
        ReadinessEvidence(
            capability="browser_stream_host",
            evidence_pointer="gateway://stream-host/cert/1",
            runtime_version="1.0.0",
        )
    )
    registry = CapabilityRegistry(
        store,
        probes={
            ReadinessSource.AUTOMATION_REGISTRY: AutomationReadiness(store, enabled=True),
            ReadinessSource.EXTERNAL_RUNTIME: ExternalRuntimeReadiness(runtime, enabled=True),
        },
    )
    registry.load()
    await registry.sync()
    missions = MissionService(store, capabilities=registry)
    binder = MissionBinder(store, missions)
    broker = BrowserSessionBroker(store)
    await broker.register_profile(profile_alias="authenticated_owner")
    sessions = InteractiveSessionService(store, broker, ControlLeaseService(store))
    return store, missions, binder, sessions


async def _mission(missions):
    return await missions.create(
        owner_principal_id="owner",
        origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,
        title="Explain this page",
        goal="search this page and explain it",
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2),
    )


async def _mission_count(store) -> int:
    row = await store.fetchone("SELECT COUNT(*) AS n FROM missions", ())
    return int(row["n"])


async def _session(sessions, *, mission_id=None, alias="authenticated_owner"):
    return await sessions.create(
        owner_device_id="dev_owner",
        profile_alias=alias,
        viewport=Viewport(width=1080, height=2016, device_scale_factor=1.0),
        requested_fps=60,
        mission_id=mission_id,
    )


@pytest.mark.asyncio
class TestBindingIsByReference:

    async def test_binding_a_session_adds_no_mission(self, stack):
        """§23.1. The count is the assertion, not the activity.

        Asserting that the activity points at the right mission_id would pass against a
        binder that created a second Mission and bound the session to that one.
        """
        store, missions, binder, sessions = stack
        mission = await _mission(missions)
        before = await _mission_count(store)

        session = await _session(sessions, mission_id=mission.mission_id)
        activity_id = await binder.bind_browser_session(
            mission_id=mission.mission_id, session_id=session.session_id
        )

        assert activity_id is not None
        assert await _mission_count(store) == before
        activities = await missions.activities(mission.mission_id)
        assert [a.executor_ref for a in activities] == [session.session_id]
        assert activities[0].capability_id == INTERACTIVE_BROWSER_CAPABILITY

    async def test_an_unknown_mission_is_refused_not_created(self, stack):
        """The counterexample in the docstring, asserted directly.

        A binder that treated an unresolvable mission_id as "then make one" would satisfy
        every other test in this file.
        """
        store, _missions, binder, sessions = stack
        session = await _session(sessions, mission_id="mis_does_not_exist")
        before = await _mission_count(store)

        with pytest.raises(MissionError):
            await binder.bind_browser_session(
                mission_id="mis_does_not_exist", session_id=session.session_id
            )

        assert await _mission_count(store) == before

    async def test_binding_the_same_session_twice_binds_once(self, stack):
        """Idempotent, because a reconnect re-runs the attach and the owner must not
        watch their Missions page grow an activity per reconnection."""
        _store, missions, binder, sessions = stack
        mission = await _mission(missions)
        session = await _session(sessions, mission_id=mission.mission_id)

        first = await binder.bind_browser_session(
            mission_id=mission.mission_id, session_id=session.session_id
        )
        second = await binder.bind_browser_session(
            mission_id=mission.mission_id, session_id=session.session_id
        )

        assert first is not None
        assert second is None
        assert len(await missions.activities(mission.mission_id)) == 1

    async def test_the_binder_never_reaches_mission_creation(self, stack):
        """§23.3 states it as a prohibition on the method, so it is asserted on the method.

        The two tests above prove no Mission appears; this proves the code path is not
        even available to it, which survives a future refactor that makes creation cheap.
        """
        _store, missions, binder, sessions = stack
        mission = await _mission(missions)
        session = await _session(sessions, mission_id=mission.mission_id)

        async def _explode(*args, **kwargs):
            raise AssertionError("MissionBinder called MissionService.create")

        missions.create = _explode  # type: ignore[method-assign]
        await binder.bind_browser_session(
            mission_id=mission.mission_id, session_id=session.session_id
        )


@pytest.mark.asyncio
class TestManualBrowsingHasNoMission:

    async def test_a_session_without_a_mission_creates_none(self, stack):
        """§23.2 — opening a web page is not a unit of agent work."""
        store, _missions, _binder, sessions = stack
        before = await _mission_count(store)
        session = await _session(sessions)
        assert session.mission_id is None
        assert await _mission_count(store) == before

    async def test_a_manual_session_produces_no_activity_anywhere(self, stack):
        """The weaker version of this test — "no Mission was created" — is already above.

        This one catches the other half: an Activity attached to some pre-existing
        Mission, which would put manual browsing into the owner's record of a task they
        asked for.
        """
        store, missions, _binder, sessions = stack
        mission = await _mission(missions)
        session = await _session(sessions)

        row = await store.fetchone(
            "SELECT COUNT(*) AS n FROM mission_activities WHERE executor_ref = ?",
            (session.session_id,),
        )
        assert int(row["n"]) == 0
        assert await missions.activities(mission.mission_id) == []


@pytest.mark.asyncio
class TestCompletionIsNotVerification:

    async def test_a_completed_browser_activity_does_not_verify_the_mission(self, stack):
        """§23.4, and the reason the whole programme has a verifier contract.

        The activity is the executor's own account of itself. Marking it COMPLETED is the
        browser worker saying it finished, and §23.4's `executor says complete ≠ verified
        success` is exactly the inference forbidden here.
        """
        _store, missions, binder, sessions = stack
        mission = await _mission(missions)
        session = await _session(sessions, mission_id=mission.mission_id)
        activity_id = await binder.bind_browser_session(
            mission_id=mission.mission_id, session_id=session.session_id
        )

        for target in (MissionState.UNDERSTOOD, MissionState.PLANNED,
                       MissionState.AUTHORIZED, MissionState.RUNNING):
            await missions.transition(mission.mission_id, target=target)
        await missions.set_activity_state(activity_id, state=ActivityState.COMPLETED)

        assert (await missions.get(mission.mission_id)).state is MissionState.RUNNING

        await missions.transition(mission.mission_id, target=MissionState.VERIFYING)
        with pytest.raises(MissionError):
            # No verifier is registered on this stack, so there is no observation to
            # stand behind the claim. The refusal is the point: a browser session that
            # ran to completion supplies no postcondition evidence by itself.
            await missions.transition(
                mission.mission_id, target=MissionState.VERIFIED_SUCCESS
            )
        assert (await missions.get(mission.mission_id)).state is MissionState.VERIFYING


# --------------------------------------------------------------- through the real route

@pytest.fixture
def _app_settings(tmp_path, monkeypatch):
    from van_gateway.browser.stream_grants import generate_signing_key

    key = generate_signing_key("rb044-signing")
    key_path = tmp_path / "rb044-signing.pem"
    key_path.write_text(key.private_pem)
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KEY_FILE", str(key_path))
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNING_KID", "rb044-signing")
    monkeypatch.setenv("VAN_BROWSER_STREAM_SIGNAL_URL", "https://stream.example/rtc")
    monkeypatch.setenv("VAN_BROWSER_STREAM_ICE_SERVERS", "[]")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def app_client(_app_settings):
    from van_gateway.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            await app.state.browser.broker.register_profile(
                profile_alias="authenticated_owner"
            )
            yield ac, app


async def _owner_headers(app):
    ticket = await app.state.auth.create_pairing_ticket("owner-phone")
    enrolled = await app.state.auth.pair_device(
        ticket.token, "owner-phone", "s" * 32, "PEM", "owner-phone"
    )
    return {
        "X-Van-Ingress-Token": INGRESS,
        "X-Van-Device-Token": enrolled.access_token,
    }


async def _app_mission(app):
    return await app.state.missions.create(
        owner_principal_id="owner",
        origin=MissionOrigin.OWNER_VOICE,
        origin_channel=OriginChannel.VOICE,
        title="Explain this page",
        goal="search this page and explain it",
        authority_envelope=AuthorityEnvelope(max_action_class=ActionClass.A2),
    )


async def _create(ac, headers, **extra):
    body = {
        "profile_alias": "authenticated_owner",
        "viewport": {"width": 1080, "height": 2016, "device_scale_factor": 1.0},
    }
    body.update(extra)
    return await ac.post("/v1/browser/interactive-sessions", json=body, headers=headers)


@pytest.mark.asyncio
class TestBindingThroughTheRoute:
    """The half the service-level tests above cannot see.

    Before this checkpoint `create_session` called `bind_browser_session` unguarded, and
    `browser.interactive.session` was named by the binder and declared in no registry. So
    the binder raised `MISSION_CAPABILITY_NOT_PERMITTED:NOT_DECLARED` straight out of the
    route: **every** attempt to open a browser session for a Mission was a 500, and §23.1
    — the blueprint's own worked example, "Van, search this page and explain it" — had
    never worked once. Nothing above would have caught it, because the binder is correct
    in isolation; what was missing was a declaration and a caller that handles refusal.
    """

    async def test_an_unproven_stream_host_refuses_the_session_and_says_why(self, app_client):
        """No readiness evidence for the host, so no Activity claiming one was used.

        This is the state of a fresh deployment, and the refusal is correct rather than a
        gap: recording that a Mission used a remote browser, when no remote browser has
        ever been proven to exist, is precisely the kind of unearned claim this programme
        exists to prevent.
        """
        ac, app = app_client
        mission = await _app_mission(app)

        response = await _create(ac, await _owner_headers(app), mission_id=mission.mission_id)

        assert response.status_code == 409, response.text
        assert response.json()["detail"].startswith("mission_binding_refused:")
        assert "browser_stream_host" in response.json()["detail"]

    async def test_a_refused_binding_does_not_strand_the_profile(self, app_client):
        """The unwind, which is the part a 409 alone would not give.

        A session left holding the authenticated profile would make the *next* attempt —
        including a perfectly ordinary manual one — fail as "leased", and the owner would
        have a browser they cannot open with no visible reason.
        """
        ac, app = app_client
        headers = await _owner_headers(app)
        mission = await _app_mission(app)

        refused = await _create(ac, headers, mission_id=mission.mission_id)
        assert refused.status_code == 409

        manual = await _create(ac, headers)
        if manual.status_code != 200:
            profile = await app.state.store.fetchone(
                "SELECT * FROM browser_profiles WHERE profile_alias = 'authenticated_owner'",
                (),
            )
            sessions = await app.state.store.fetchall(
                "SELECT session_id, state, profile_lease_id, final_reason "
                "FROM browser_interactive_sessions", (),
            )
            raise AssertionError(
                f"{manual.text}\nprofile={dict(profile)}\n"
                + "\n".join(str(dict(row)) for row in sessions)
            )
        assert manual.json()["mission_id"] is None

    async def test_a_proven_host_binds_the_session_to_the_existing_mission(self, app_client):
        """§23.1 end to end, and the reason the refusal above is not the whole story."""
        ac, app = app_client
        await app.state.automation_health.runtime.record_evidence(
            ReadinessEvidence(
                capability="browser_stream_host",
                evidence_pointer="gateway://stream-host/cert/1",
                runtime_version="1.0.0",
            )
        )
        await app.state.capability_registry.sync()
        mission = await _app_mission(app)
        before = await _mission_count(app.state.store)

        response = await _create(
            ac, await _owner_headers(app), mission_id=mission.mission_id
        )

        assert response.status_code == 200, response.text
        session_id = response.json()["session_id"]
        activities = await app.state.missions.activities(mission.mission_id)
        assert [a.executor_ref for a in activities] == [session_id]
        # The claim §23.1 actually makes: one Mission, the one the command created.
        assert await _mission_count(app.state.store) == before
