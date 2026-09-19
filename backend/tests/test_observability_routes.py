"""P2-OBS-001 / P3-OBS-001/002/003 — the operator surface, end to end.

The test that carries the finding is `test_a_command_can_be_traced_end_to_end`:
before this, answering "what happened to the thing I asked for" meant opening
SQLite and doing six joins across five tables, two of them through JSON.
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
from van_gateway.observability.correlation import for_command
from van_gateway.observability.metrics import REGISTRY

INGRESS = "obs-ingress-token-0123456789abc"
INTERNAL = "obs-internal-control-token"
OBSERVABILITY = "obs-operator-token-abcdef"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "obs.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.invalid")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_OBSERVABILITY_TOKEN", OBSERVABILITY)
    # The scheduler has its own tests; leaving it running here would make every
    # assertion in this file race a background task.
    monkeypatch.setenv("VAN_SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()
    REGISTRY.reset()
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


async def _enrol(ac, app, device_id="obs-dev"):
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


OPERATOR = {"X-Van-Internal-Token": OBSERVABILITY}


@pytest.mark.asyncio
async def test_a_command_can_be_traced_end_to_end(client):
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "Remind me at 5pm to call the bank", idempotency_key="trace-1")
    accepted = await ac.post("/v1/commands", json=body)
    assert accepted.status_code == 200, accepted.text
    result = accepted.json()

    # The correlation id is on the result the *device* received, not only in a log.
    assert result["correlation_id"] == for_command(body["command_id"])

    traced = await ac.get(
        f"/v1/observability/trace/{body['command_id']}", headers=OPERATOR
    )
    assert traced.status_code == 200, traced.text
    trace = traced.json()
    assert trace["correlation_id"] == result["correlation_id"]
    # Every leg of the chain the blueprint names, from one call.
    assert trace["audit"], "the authority decision"
    assert trace["missions"], "the durable work record"
    assert trace["missions"][0]["mission_id"] == result["mission_id"]
    assert trace["mission_events"], "the owner-visible timeline"
    assert trace["context_snapshots"], "what VAN knew when it acted"
    assert {event["event_type"] for event in trace["mission_events"]}


@pytest.mark.asyncio
async def test_a_refused_command_is_traceable_too(client):
    """The case an operator most needs. A refusal used to leave a row in `audit`
    and nothing that joined it to anything."""
    ac, app = client
    device_id = await _enrol(ac, app)
    body = _signed(app, device_id, "do a thing", idempotency_key="trace-bad")
    body["signature"] = "not-a-signature"
    denied = await ac.post("/v1/commands", json=body)
    assert denied.json()["status"] == "denied"
    assert denied.json()["correlation_id"] == for_command(body["command_id"])

    trace = await ac.get(f"/v1/observability/trace/{body['command_id']}", headers=OPERATOR)
    assert trace.status_code == 200
    assert trace.json()["audit"][0]["result"] == "denied"


@pytest.mark.asyncio
async def test_a_command_nobody_sent_is_a_404_not_an_empty_trace(client):
    ac, _app = client
    missing = await ac.get("/v1/observability/trace/cmd-never-existed", headers=OPERATOR)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_the_operator_surface_is_not_reachable_by_the_runtime_credential(client):
    """P0-SEC-001's design continued: a trace names device ids, command ids and
    failure reasons across the whole system. The model-driven runtime holds every
    other scope and must not hold this one."""
    ac, _app = client
    for path in ("/v1/observability/metrics", "/v1/observability/alerts",
                 "/v1/observability/health", "/v1/observability/trace/cmd-x"):
        refused = await ac.get(path, headers={"X-Van-Internal-Token": INTERNAL})
        assert refused.status_code == 403, path
        assert refused.json()["required_scope"] == "observability"


@pytest.mark.asyncio
async def test_owner_ingress_alone_does_not_reach_the_operator_surface(client):
    ac, _app = client
    refused = await ac.get("/v1/observability/metrics")
    assert refused.status_code == 403


@pytest.mark.asyncio
async def test_the_scrape_is_prometheus_text_and_names_the_route_template(client):
    """A path label would make one time series per mission id."""
    ac, app = client
    device_id = await _enrol(ac, app)
    await ac.post("/v1/commands",
                  json=_signed(app, device_id, "brief me", idempotency_key="scrape-1"))
    listed = await ac.get("/v1/missions")
    mission_id = listed.json()[0]["mission_id"]
    await ac.get(f"/v1/missions/{mission_id}")

    scrape = await ac.get("/v1/observability/metrics", headers=OPERATOR)
    assert scrape.status_code == 200
    assert scrape.headers["content-type"].startswith("text/plain")
    text = scrape.text
    assert 'route="/v1/missions/{mission_id}"' in text
    assert mission_id not in text, "a mission id in a label is unbounded cardinality"
    assert 'route="/v1/commands"' in text


@pytest.mark.asyncio
async def test_alerts_and_health_answer_without_reading_sqlite(client):
    ac, _app = client
    alerts = await ac.get("/v1/observability/alerts", headers=OPERATOR)
    assert alerts.status_code == 200
    payload = alerts.json()
    assert payload["rules_evaluated"] >= 8
    assert isinstance(payload["firing"], list)

    health = await ac.get("/v1/observability/health", headers=OPERATOR)
    assert health.status_code == 200
    body = health.json()
    assert body["audit_chain"]["ok"] is True
    assert body["scheduler"]["running"] is False  # disabled in this fixture
    assert body["backup"]["configured"] is False
    assert "unobserved_metrics" in body


@pytest.mark.asyncio
async def test_device_telemetry_is_device_authenticated_not_operator_authenticated(client):
    """Its producer is the owner's phone. Requiring an operator credential to
    report a frame time would mean no frame times are ever reported."""
    ac, app = client
    await _enrol(ac, app)
    posted = await ac.post("/v1/observability/device-telemetry", json={
        "samples": [
            {"name": "aura_frame_time_ms", "value": 12.5, "surface": "overlay"},
            {"name": "battery_percent", "value": 71},
            {"name": "cpu_temperature_c", "value": 40},
        ]
    })
    assert posted.status_code == 200, posted.text
    assert posted.json()["accepted"] == 2
    assert posted.json()["refused"] == ["cpu_temperature_c"]

    scrape = await ac.get("/v1/observability/metrics", headers=OPERATOR)
    assert "van_aura_frame_time_ms_count" in scrape.text
    assert "van_device_battery_percent 71" in scrape.text
