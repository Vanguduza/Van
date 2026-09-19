"""P0-EXEC-001: an accepted owner command must produce a durable work record.

The whole-system audit's runtime probe drove ten canonical owner intents through
POST /v1/commands. All ten returned `accepted`. `GET /v1/missions` returned `[]` and
`GET /v1/activity` returned `{"missions": []}`. The system's model of what the owner had
asked for ended at dispatch, which is why nothing downstream — completion, verification,
the needs-you queue, the activity feed — had anything to work from.

This file re-runs that probe as a test and asserts the opposite, then holds the ladder to
its own claims: a mission may only say AUTHORIZED once authority was sealed, and may only
say RUNNING once Hermes actually accepted the run.
"""

from __future__ import annotations

import time
import uuid

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.config import get_settings
from van_gateway.hermes.bridge import HermesBridgeError
from van_gateway.mission.models import MissionState

INGRESS = "mission-ingress-token-0123456789abc"

#: The ten intents from the audit probe, in the owner's own phrasing.
CANONICAL_INTENTS = [
    "Van, brief me.",
    "Remind me at 5pm to call the bank",
    "What is on my plate today?",
    "Draft a reply to the landlord about the deposit",
    "Summarise what changed in the Van project this week",
    "Find me a flight to Cape Town in March",
    "Note that Thandi prefers morning meetings",
    "What did I decide about the trading account last month?",
    "Check whether the deploy finished",
    "Book the dentist appointment for Tuesday",
]


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "mission.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "mission-internal-token")
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "mission-internal-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = create_app()

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        return {"id": f"run-{uuid.uuid4().hex[:8]}", "status": "accepted"}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": INGRESS}
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def _enrol(ac, app, device_id="mission-dev"):
    ticket = await app.state.auth.create_pairing_ticket(device_id)
    enrolled = await app.state.auth.pair_device(ticket.token, device_id, "s" * 32, "PEM", device_id)
    ac.headers.update({"X-Van-Device-Token": enrolled.access_token})
    return device_id


def _signed(app, device_id, text, *, idempotency_key, action_class="A1"):
    issued = int(time.time())
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    canonical = AuthService.canonical_command(
        command_id=command_id,
        idempotency_key=idempotency_key,
        device_id=device_id,
        issued_at_unix=issued,
        text=text,
        action_class=action_class,
        project_id=None,
    )
    return {
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "text": text,
        "action_class": action_class,
    }


@pytest.mark.asyncio
class TestTheAuditProbe:
    async def test_ten_canonical_intents_produce_ten_missions(self, client):
        """The audit's exact probe. It returned ten acceptances and zero missions."""
        ac, app = client
        device_id = await _enrol(ac, app)

        for i, text in enumerate(CANONICAL_INTENTS):
            resp = await ac.post(
                "/v1/commands", json=_signed(app, device_id, text, idempotency_key=f"probe-{i}")
            )
            assert resp.json()["status"] == "accepted", resp.text

        listed = await ac.get("/v1/missions")
        assert listed.status_code == 200
        missions = listed.json()
        assert len(missions) == len(CANONICAL_INTENTS), (
            f"{len(CANONICAL_INTENTS)} owner intents produced {len(missions)} missions"
        )
        assert {m["title"] for m in missions} == {
            text if len(text) <= 80 else text[:79] + "…" for text in CANONICAL_INTENTS
        }

    async def test_the_activity_feed_is_no_longer_empty(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        await ac.post(
            "/v1/commands",
            json=_signed(app, device_id, "Van, brief me.", idempotency_key="feed-1"),
        )

        feed = await ac.get("/v1/activity")
        grouped = feed.json()["missions"]
        assert grouped, "the owner-visible activity feed was empty after an accepted command"
        assert any(e["event_type"] == "mission.created" for e in grouped[0]["events"])

    async def test_the_result_carries_the_mission_id(self, client):
        """Without this the device has an acceptance it cannot follow up on."""
        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="id-1")
        )
        mission_id = resp.json()["mission_id"]
        assert mission_id

        fetched = await ac.get(f"/v1/missions/{mission_id}")
        assert fetched.status_code == 200
        assert fetched.json()["goal"] == "Van, brief me."


@pytest.mark.asyncio
class TestTheLadderIsEarned:
    async def test_an_accepted_command_reaches_running(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="run-1")
        )
        mission = await app.state.missions.get(resp.json()["mission_id"])
        assert mission.state is MissionState.RUNNING

    async def test_the_whole_ladder_is_walked_not_skipped(self, client):
        """Each rung is separately observable, which is why the ladder exists."""
        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="ladder-1")
        )
        events = await app.state.missions.events(resp.json()["mission_id"])
        types = [e.event_type.value for e in events]
        assert types[:4] == [
            "mission.created",
            "mission.understood",
            "mission.planned",
            "mission.started",
        ], types

    async def test_a_mission_authorised_but_never_started_says_so(self, client, monkeypatch):
        """Hermes offline is not a refusal and not a success. The audit found both lies."""
        ac, app = client
        device_id = await _enrol(ac, app)

        async def offline():
            return {"ok": False}

        monkeypatch.setattr(app.state.orchestrator.hermes, "health", offline)
        resp = await ac.post(
            "/v1/commands",
            json=_signed(app, device_id, "Van, brief me.", idempotency_key="offline-1"),
        )
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["mission_id"], "a degraded command still asked for something"

        mission = await app.state.missions.get(body["mission_id"])
        assert mission.state is MissionState.AUTHORIZED, (
            "the mission must stop where it honestly got to, not claim RUNNING"
        )
        events = await app.state.missions.events(mission.mission_id)
        assert any("hermes_offline" in (e.summary or "") for e in events)

    async def test_a_failed_dispatch_does_not_claim_running(self, client, monkeypatch):
        ac, app = client
        device_id = await _enrol(ac, app)

        async def boom(text, metadata=None):
            raise HermesBridgeError("hermes_unreachable", "connection refused")

        monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", boom)
        resp = await ac.post(
            "/v1/commands",
            json=_signed(app, device_id, "Van, brief me.", idempotency_key="boom-1"),
        )
        mission = await app.state.missions.get(resp.json()["mission_id"])
        assert mission.state is MissionState.AUTHORIZED

    async def test_the_mission_carries_the_commands_authority_not_a_default(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands",
            json=_signed(app, device_id, "Summarise the deploy log", idempotency_key="auth-1",
                         action_class="A2"),
        )
        detail = await ac.get(f"/v1/missions/{resp.json()['mission_id']}")
        envelope = detail.json()["authority_envelope"]
        assert envelope["max_action_class"] == "A2"
        assert envelope["source_command_id"] == resp.json()["command_id"]

    async def test_an_empty_success_contract_is_not_a_fabricated_one(self, client):
        """The gateway cannot check an arbitrary instruction, so it claims no postconditions.

        §6: a mission with nothing to check can never reach VERIFIED_SUCCESS. Inventing a
        postcondition here is how a mission ends up 'verified' on nothing, which is finding
        P0-EXEC-002.
        """
        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="sc-1")
        )
        detail = await ac.get(f"/v1/missions/{resp.json()['mission_id']}")
        contract = detail.json()["success_contract"]
        assert contract["postconditions"] == {}
        assert contract["verifier_class"] is None


@pytest.mark.asyncio
class TestExactlyOneMissionPerCommand:
    async def test_a_replayed_command_does_not_open_a_second_mission(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        body = _signed(app, device_id, "Van, brief me.", idempotency_key="once-1")

        first = await ac.post("/v1/commands", json=body)
        second = await ac.post("/v1/commands", json=body)

        assert first.json()["mission_id"]
        missions = (await ac.get("/v1/missions")).json()
        assert len(missions) == 1, f"one command opened {len(missions)} missions"
        assert second.status_code == 200

    async def test_the_database_refuses_a_second_mission_for_one_command(self, client):
        """Not merely intended: the unique index is what makes it true under concurrency."""
        import aiosqlite

        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="uniq-1")
        )
        command_id = resp.json()["command_id"]

        mission = await app.state.missions.get(resp.json()["mission_id"])
        with pytest.raises(aiosqlite.IntegrityError):
            await app.state.missions.create(
                owner_principal_id=mission.owner_principal_id,
                origin=mission.origin,
                origin_channel=mission.origin_channel,
                title="a duplicate",
                goal="a duplicate",
                authority_envelope=mission.authority_envelope.model_copy(
                    update={"source_command_id": command_id}
                ),
            )

    async def test_missions_without_a_source_command_are_not_forced_unique(self, client):
        """The index is partial on purpose: proactive and scheduled missions have no command."""
        ac, app = client
        await _enrol(ac, app)
        from van_gateway.mission.models import MissionOrigin
        from van_gateway.models import OriginChannel

        for i in range(3):
            await app.state.missions.create(
                owner_principal_id="device:mission-dev",
                origin=MissionOrigin.PROACTIVE,
                origin_channel=OriginChannel.SYSTEM_EVENT,
                title=f"proactive {i}",
                goal=f"proactive {i}",
            )
        assert len((await ac.get("/v1/missions")).json()) == 3


@pytest.mark.asyncio
class TestMissionEventsReachTheDevice:
    """The read model is not enough: the phone learns by replaying the event stream."""

    async def test_an_accepted_command_publishes_to_the_device_stream(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        resp = await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="bus-1")
        )
        mission_id = resp.json()["mission_id"]

        stream = await ac.get("/v1/events", params={"device_id": device_id, "after_seq": 0})
        events = stream.json()["events"]
        mission_events = [e for e in events if e["payload"].get("mission_id") == mission_id]
        assert [e["event_type"] for e in mission_events] == [
            "mission.created",
            "mission.understood",
            "mission.planned",
            "mission.started",
        ], mission_events

    async def test_the_started_event_carries_the_run_it_can_be_traced_to(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="bus-2")
        )
        events = (await ac.get("/v1/events", params={"device_id": device_id, "after_seq": 0})).json()["events"]
        started = [e for e in events if e["event_type"] == "mission.started"]
        assert started and started[-1]["payload"]["evidence_ref"].startswith("hermes-run:")

    async def test_internal_events_do_not_reach_the_owner_stream(self, client):
        """The bus is the owner's feed. owner_visibility already records the distinction."""
        ac, app = client
        device_id = await _enrol(ac, app)
        from van_gateway.mission.models import MissionEventType, MissionOrigin
        from van_gateway.models import OriginChannel, PrincipalType

        mission = await app.state.missions.create(
            owner_principal_id="device:mission-dev",
            origin=MissionOrigin.PROACTIVE,
            origin_channel=OriginChannel.SYSTEM_EVENT,
            title="internal",
            goal="internal",
        )
        before = len((await ac.get("/v1/events", params={"device_id": device_id, "after_seq": 0})).json()["events"])
        await app.state.missions.record_event(
            mission_id=mission.mission_id,
            event_type=MissionEventType.ACTIVITY_CHECKPOINTED,
            actor=PrincipalType.SYSTEM,
            summary="internal bookkeeping",
            owner_visibility=False,
        )
        after = len((await ac.get("/v1/events", params={"device_id": device_id, "after_seq": 0})).json()["events"])
        assert after == before


@pytest.mark.asyncio
class TestOwnerStatusIsServed:
    """P2-COH-001. A projection nothing serves is the isolation defect, not a fix."""

    async def test_the_mission_list_carries_the_owner_projection(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="proj-1")
        )
        mission = (await ac.get("/v1/missions")).json()[0]
        assert mission["owner_status"] == "WORKING"
        assert mission["owner_sentence"] == "Working on it"
        assert mission["owner_attention"] is False
        assert mission["finished"] is False

    async def test_the_activity_feed_carries_it_too(self, client):
        ac, app = client
        device_id = await _enrol(ac, app)
        await ac.post(
            "/v1/commands", json=_signed(app, device_id, "Van, brief me.", idempotency_key="proj-2")
        )
        entry = (await ac.get("/v1/activity")).json()["missions"][0]
        assert entry["owner_status"] == "WORKING"
        assert entry["owner_sentence"]

    async def test_a_refused_mission_reads_as_refused_not_as_working(self, client, monkeypatch):
        ac, app = client
        device_id = await _enrol(ac, app)

        async def stale_truth(project_id):
            return {"ok": False, "degraded": "STALE_PROJECT_TRUTH"}

        monkeypatch.setattr(app.state.orchestrator.projects, "load_truth", stale_truth)
        body = _signed(
            app, device_id, "Update the deploy config", idempotency_key="proj-3", action_class="A3"
        )
        # The signature covers project_id, so it has to be signed in, not bolted on.
        canonical = AuthService.canonical_command(
            command_id=body["command_id"],
            idempotency_key=body["idempotency_key"],
            device_id=device_id,
            issued_at_unix=body["issued_at_unix"],
            text=body["text"],
            action_class="A3",
            project_id="van",
        )
        body["project_id"] = "van"
        body["signature"] = app.state.auth.sign(device_id, canonical)

        resp = await ac.post("/v1/commands", json=body)
        assert resp.json()["status"] == "degraded", resp.text

        mission = (await ac.get(f"/v1/missions/{resp.json()['mission_id']}")).json()
        assert mission["owner_status"] == "REFUSED"
        assert mission["owner_attention"] is True
        assert mission["finished"] is True
