"""P0-EXEC-002 — an owner can find out what happened, and silence is detectable.

The audit's probe drove ten intents through POST /v1/commands, got `accepted` for all ten,
and then had nowhere to ask what became of them: `GET /v1/commands/{id}` was a 404 and the
terminal owner-visible status was "accepted" forever. `create_run` returned a run id that
nothing polled, no callback was keyed to it, and no deadline existed, so a Hermes that
never called back left the mission at RUNNING and the owner reading "working on it".
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
from van_gateway.coherence.owner_status import FINISHED, NEEDS_OWNER, SENTENCE, OwnerWorkStatus
from van_gateway.config import get_settings
from van_gateway.mission.models import MissionState

INGRESS = "exec-ingress-token-0123456789abc"
INTERNAL = "exec-internal-control-token"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
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
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"X-Van-Ingress-Token": INGRESS},
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


async def _enrol(ac, app, device_id="exec-dev"):
    ticket = await app.state.auth.create_pairing_ticket(device_id)
    enrolled = await app.state.auth.pair_device(ticket.token, device_id, "s" * 32, "PEM", device_id)
    ac.headers.update({"X-Van-Device-Token": enrolled.access_token})
    return device_id


def _signed(app, device_id, text, *, idempotency_key, action_class="A1"):
    issued = int(time.time())
    command_id = f"cmd-{uuid.uuid4().hex[:10]}"
    canonical = AuthService.canonical_command(
        command_id=command_id, idempotency_key=idempotency_key, device_id=device_id,
        issued_at_unix=issued, text=text, action_class=action_class, project_id=None,
    )
    return {
        "command_id": command_id, "idempotency_key": idempotency_key, "device_id": device_id,
        "issued_at_unix": issued, "signature": app.state.auth.sign(device_id, canonical),
        "text": text, "action_class": action_class,
    }


@pytest.mark.asyncio
async def test_an_accepted_command_can_be_asked_about(client):
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "brief me", idempotency_key="exec-1")
    accepted = await ac.post("/v1/commands", json=body)
    assert accepted.status_code == 200

    status = await ac.get(f"/v1/commands/{body['command_id']}")
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["mission_id"] == accepted.json()["mission_id"]
    assert payload["mission_state"] == MissionState.RUNNING.value
    assert payload["owner_status"] == OwnerWorkStatus.WORKING.value
    assert payload["sentence"] == "Working on it"
    assert payload["finished"] is False
    # P0-EXEC-002 — the deadline set at dispatch, which is what makes silence detectable.
    assert payload["deadline_ms"] is not None
    assert payload["deadline_ms"] > int(time.time() * 1000)


@pytest.mark.asyncio
async def test_a_command_nobody_sent_is_404(client):
    ac, app = client
    await _enrol(ac, app)
    assert (await ac.get("/v1/commands/cmd-never-existed")).status_code == 404


@pytest.mark.asyncio
async def test_a_refusal_is_answerable_too(client):
    """A denied command never opens a mission, and used to leave the owner with nothing
    to read but the synchronous response they may have navigated away from."""
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "do a thing", idempotency_key="exec-bad")
    body["signature"] = "not-a-signature"
    assert (await ac.post("/v1/commands", json=body)).json()["status"] == "denied"

    status = await ac.get(f"/v1/commands/{body['command_id']}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["mission_id"] is None
    assert payload["owner_status"] == OwnerWorkStatus.REFUSED.value
    assert payload["needs_you"] is True


@pytest.mark.asyncio
async def test_another_device_cannot_read_this_one_s_command(client):
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "brief me", idempotency_key="exec-mine")
    await ac.post("/v1/commands", json=body)

    other = await app.state.auth.create_pairing_ticket("exec-other")
    enrolled = await app.state.auth.pair_device(other.token, "exec-other", "s" * 32, "PEM", "other")
    ac.headers.update({"X-Van-Device-Token": enrolled.access_token})
    refused = await ac.get(f"/v1/commands/{body['command_id']}")
    # 404 rather than 403: a 403 would confirm the command exists.
    assert refused.status_code == 404


@pytest.mark.asyncio
async def test_a_dispatch_that_never_comes_back_stops_reading_as_working(client):
    """The finding itself. Hermes accepts the run and never calls back."""
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "check whether the deploy finished", idempotency_key="exec-silent")
    accepted = await ac.post("/v1/commands", json=body)
    mission_id = accepted.json()["mission_id"]

    before = (await ac.get(f"/v1/commands/{body['command_id']}")).json()
    assert before["owner_status"] == OwnerWorkStatus.WORKING.value

    # Move the deadline into the past: the fifteen minutes have passed.
    await app.state.store.execute(
        "UPDATE missions SET deadline_ms = ? WHERE mission_id = ?",
        (int(time.time() * 1000) - 1, mission_id),
    )
    expired = await app.state.missions.expire_overdue()
    assert expired == [mission_id]

    after = (await ac.get(f"/v1/commands/{body['command_id']}")).json()
    assert after["mission_state"] == MissionState.EXPIRED.value
    assert after["owner_status"] == OwnerWorkStatus.NEVER_HEARD_BACK.value
    assert after["sentence"] == "VAN handed this over and never heard back"
    # The whole point: it reaches the owner's attention queue. STOPPED would not.
    assert after["needs_you"] is True
    assert after["finished"] is True


@pytest.mark.asyncio
async def test_never_heard_back_is_not_failed_and_not_stopped():
    """Three different things to tell an owner, and three different things to do."""
    assert OwnerWorkStatus.NEVER_HEARD_BACK in NEEDS_OWNER
    assert OwnerWorkStatus.NEVER_HEARD_BACK in FINISHED
    assert OwnerWorkStatus.STOPPED not in NEEDS_OWNER
    for status in (OwnerWorkStatus.FAILED, OwnerWorkStatus.STOPPED):
        assert SENTENCE[status] != SENTENCE[OwnerWorkStatus.NEVER_HEARD_BACK]


@pytest.mark.asyncio
async def test_a_mission_that_finished_in_time_is_not_expired(client):
    """The sweeper must not reach into work that completed."""
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "brief me", idempotency_key="exec-done")
    mission_id = (await ac.post("/v1/commands", json=body)).json()["mission_id"]
    await app.state.missions.transition(
        mission_id=mission_id, target=MissionState.CANCELLED, summary="owner cancelled",
    )
    await app.state.store.execute(
        "UPDATE missions SET deadline_ms = ? WHERE mission_id = ?",
        (int(time.time() * 1000) - 1, mission_id),
    )
    assert await app.state.missions.expire_overdue() == []
    assert (await app.state.missions.get(mission_id)).state is MissionState.CANCELLED


@pytest.mark.asyncio
async def test_a_mission_with_no_deadline_is_never_swept(client):
    """Only work VAN handed to something external carries a deadline. A mission still
    being planned inside the gateway is not silence, it is progress."""
    ac, app = client
    await _enrol(ac, app)
    mission = await app.state.missions.create(
        owner_principal_id="owner",
        origin=__import__("van_gateway.mission.models", fromlist=["MissionOrigin"]).MissionOrigin.OWNER_UI,
        origin_channel=__import__("van_gateway.models", fromlist=["OriginChannel"]).OriginChannel.UI,
        title="planning", goal="planning",
    )
    assert mission.deadline_ms is None
    assert await app.state.missions.expire_overdue() == []
