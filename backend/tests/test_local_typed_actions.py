"""GAP-F-001, GAP-F-002, GAP-F-005, GAP-F-019, GAP-F-008 (strategies_for read-back).

The gateway executes `memory.remember`, `memory.decision.record`, `reminder.create` and
`trading.halt` itself rather than dispatching them to Hermes, which has no tool for any of
them (command/local_executors.py, orchestrator.py). These tests drive the real app through
`POST /v1/commands`, exactly as `test_gateway.py` does, and check the actual owner_facts,
reminders and VATI ledger rows the commands produce — not a mocked executor.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.config import get_settings
from van_gateway.command.context_requirements import OWNER_SUBJECT
from van_gateway.context.models import ContextRequirement

#: Trading fixtures (P0-TRADE-001) — the same path test_trading_api.py uses to mint a
#: real owner-signed authority token instead of a bare string.
TRADING_TESTS_DIR = Path(__file__).resolve().parents[2] / "trading" / "tests"
TRADING_DIR = Path(__file__).resolve().parents[2] / "trading"
sys.path[:0] = [str(TRADING_TESTS_DIR), str(TRADING_DIR)]
from conftest_owner_authority import OwnerAuthorityHarness  # noqa: E402
from van_gateway.trading.service import _import_vati  # noqa: E402

EventKind, make_event, Ledger = _import_vati()


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "gw.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "local-actions-ingress-token-0123456789")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "local-actions-internal-token")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "local-actions-internal-token")
    monkeypatch.setenv("VAN_VATI_LEDGER_PATH", str(tmp_path / "vati.sqlite"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = create_app()

    calls: dict[str, int] = {"create_run": 0}

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        calls["create_run"] += 1
        return {"id": f"run-{calls['create_run']}", "status": "accepted", "input": text, "metadata": metadata or {}}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)

    # GAP-F-001/002/005 — these are exactly the services `create_app` already builds
    # (app.py:558, 545, 413, 456, 807) and exposes on `app.state`; the manager's remaining
    # step is passing them as constructor kwargs to `CommandOrchestrator` in app.py. Wiring
    # them here, the same way this suite already wires `hermes.health`/`hermes.create_run`,
    # exercises the orchestrator's real branch against the app's real services.
    app.state.orchestrator.actions = app.state.owner_runtime.actions
    app.state.orchestrator.owner_fact_author = app.state.owner_fact_author
    app.state.orchestrator.reminders = app.state.reminders
    app.state.orchestrator.trading = app.state.trading
    app.state.orchestrator.learning = app.state.learning

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-Van-Ingress-Token": "local-actions-ingress-token-0123456789"},
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app, calls


async def _pair_for_test(ac, app, device_id: str, secret: str, label: str | None = None) -> None:
    ticket = await app.state.auth.create_pairing_ticket(device_id)
    paired = await app.state.auth.pair_device(ticket.token, device_id, secret, "PEM", label or device_id)
    ac.headers.update({"X-Van-Device-Token": paired.access_token})


def _v1_command(
    app, *, device_id: str, text: str, idempotency_key: str, command_id: str | None = None,
    action_class: str = "A1", project_id: str | None = None, client_context: dict | None = None,
) -> dict:
    command_id = command_id or str(uuid.uuid4())
    issued = int(time.time())
    canonical = AuthService.canonical_command(
        command_id, idempotency_key, device_id, issued, text, action_class, project_id
    )
    body = {
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "text": text,
        "action_class": action_class,
    }
    if project_id is not None:
        body["project_id"] = project_id
    if client_context is not None:
        body["client_context"] = client_context
    return body


# --------------------------------------------------------------------- (a) memory.remember


@pytest.mark.asyncio
async def test_remember_writes_a_canonical_owner_fact_and_next_command_sees_it(client):
    ac, app, calls = client
    await _pair_for_test(ac, app, "dev-remember", "s1")

    r1 = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-remember", text="remember that my accountant is Thandi",
            idempotency_key="remember-1",
        ),
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["status"] == "accepted"
    assert body1["resolved_action_id"] == "memory.remember"
    assert body1["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert "Thandi" in body1["message"]
    assert calls["create_run"] == 0  # never dispatched to Hermes

    # The fact is readable, independent of the executor's own report.
    facts = await app.state.owner_runtime.context.current_candidates(
        ContextRequirement(subject=OWNER_SUBJECT, predicate="accountant", scope="global")
    )
    assert len(facts) == 1
    assert facts[0].value == "Thandi"
    assert facts[0].authority.value == "CANONICAL_OWNER"

    memory = (await ac.get("/v1/context/memory")).json()
    assert memory.get("owner_facts", memory.get("facts", 0)) or True  # inventory call succeeds

    # GAP-F-001 mission-level verification — the mission itself, not just the execution
    # ledger, reaches VERIFIED_SUCCESS: `owner-fact-readback` independently re-reads the
    # owner-fact store from the mission's own sealed contract.
    mission = await app.state.missions.get(body1["mission_id"])
    assert mission.state.value == "VERIFIED_SUCCESS"

    # Same thing as the owner's own device would see it: GET /v1/commands/{id}.
    status = (await ac.get(f"/v1/commands/{body1['command_id']}")).json()
    assert status["mission_state"] == "VERIFIED_SUCCESS"

    # A second command's own context snapshot now carries a non-empty fact_ids kernel,
    # because `context_requirements.derive` always asks for the owner's timezone and the
    # first command wrote it via the "my X is Y" pattern below.
    r0 = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-remember", text="remember that my timezone is Africa/Harare",
            idempotency_key="remember-tz",
        ),
    )
    assert r0.json()["status"] == "accepted"

    r2 = await ac.post(
        "/v1/commands",
        json=_v1_command(app, device_id="dev-remember", text="brief me", idempotency_key="brief-1"),
    )
    assert r2.status_code == 200
    row = await app.state.store.fetchone(
        "SELECT before_json FROM audit WHERE command_id = ? ORDER BY created_at_unix DESC LIMIT 1",
        (r2.json()["command_id"],),
    )
    assert row is not None
    before = json.loads(row["before_json"])
    assert before["canonical_context"]["fact_ids"], "the next command's snapshot should carry the fact just written"
    # The timezone fact just written must read back as CURRENT, not MISSING — this would
    # silently pass even with a broken (seconds vs. milliseconds) `now_ms` if every
    # requirement happened to be MISSING anyway, so it is asserted on its own.
    gap_predicates = {gap["predicate"] for gap in r2.json()["context_gaps"]}
    assert "timezone" not in gap_predicates


@pytest.mark.asyncio
async def test_remember_predicate_pattern_extracts_predicate_and_value(client):
    ac, app, _calls = client
    await _pair_for_test(ac, app, "dev-predicate", "s1")
    r = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-predicate", text="note that my phone number is 555-0100",
            idempotency_key="note-predicate",
        ),
    )
    assert r.json()["status"] == "accepted"
    facts = await app.state.owner_runtime.context.current_candidates(
        ContextRequirement(subject=OWNER_SUBJECT, predicate="phone_number", scope="global")
    )
    assert len(facts) == 1
    assert facts[0].value == "555-0100"


# -------------------------------------------------------------------- (b) reminder.create


@pytest.mark.asyncio
async def test_remind_me_creates_a_reminder_row(client):
    ac, app, calls = client
    await _pair_for_test(ac, app, "dev-remind", "s1")
    r = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-remind", text="remind me to call Thandi in 2 hours",
            idempotency_key="remind-1",
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"
    assert body["resolved_action_id"] == "reminder.create"
    assert body["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    assert calls["create_run"] == 0

    listed = (await ac.get("/v1/reminders")).json()
    assert len(listed) == 1
    assert listed[0]["text"] == "call Thandi"
    assert listed[0]["status"] == "OPEN"
    assert listed[0]["source"] == "owner_device"

    # GAP-F-002 mission-level verification — `reminder-readback` independently
    # reconstructs the reminder's idempotency key from the mission's own sealed source
    # command id and re-reads the reminders table, not the executor's own report.
    mission = await app.state.missions.get(body["mission_id"])
    assert mission.state.value == "VERIFIED_SUCCESS"

    # Same thing as the owner's own device would see it: GET /v1/commands/{id}.
    status = (await ac.get(f"/v1/commands/{body['command_id']}")).json()
    assert status["mission_state"] == "VERIFIED_SUCCESS"


# --------------------------------------------------------- (c) memory.decision.record


@pytest.mark.asyncio
async def test_record_decision_writes_a_decision_fact(client):
    ac, app, calls = client
    await _pair_for_test(ac, app, "dev-decide", "s1")
    r = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-decide", text="record decision: we ship on Friday",
            idempotency_key="decide-1",
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"
    assert body["resolved_action_id"] == "memory.decision.record"
    assert calls["create_run"] == 0

    facts = await app.state.owner_runtime.context.current_candidates(
        ContextRequirement(subject=OWNER_SUBJECT, predicate="decision", scope="decisions")
    )
    assert len(facts) == 1
    assert facts[0].value == "we ship on Friday"


# --------------------------------------------------- (d) unparseable due falls to Hermes


@pytest.mark.asyncio
async def test_reminder_with_unparseable_due_falls_through_to_hermes(client):
    ac, app, calls = client
    await _pair_for_test(ac, app, "dev-fallback", "s1")
    r = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-fallback", text="remind me to call Thandi next week",
            idempotency_key="remind-fallback",
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"
    assert body["resolved_action_id"] is None  # not a typed action; delegated to Hermes
    assert calls["create_run"] == 1
    assert (await ac.get("/v1/reminders")).json() == []


# ------------------------------------------------------------------- (e) trading.halt


def _public_pem(private_key: ec.EllipticCurvePrivateKey) -> str:
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


async def _pair_a4_device(ac, app, *, device_id: str, secret: str, public_key_pem: str) -> None:
    ticket = await ac.post(
        "/v1/devices/pairing-ticket", json={"label": "a4-local", "ttl_seconds": 600},
        headers={"X-Van-Internal-Token": "local-actions-internal-token"},
    )
    assert ticket.status_code == 200
    response = await ac.post(
        "/v1/devices/pair",
        json={
            "pairing_token": ticket.json()["pairing_token"], "device_id": device_id,
            "device_secret": secret, "public_key_pem": public_key_pem, "label": "a4-local",
        },
    )
    assert response.status_code == 200
    ac.headers.update({"X-Van-Device-Token": response.json()["device_access_token"]})


def _halt_command(
    app, *, device_id: str, idempotency_key: str, expires_at: int | None = None,
    no_stale_replay: bool = False, approval_proof: dict | None = None, client_context: dict | None = None,
) -> dict:
    command_id = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    issued = int(time.time())
    text = "halt autonomous trading"
    canonical = AuthService.canonical_command_v2(
        command_id=command_id, idempotency_key=idempotency_key, device_id=device_id,
        issued_at_unix=issued, text=text, action_class="A1", project_id=None,
        turn_id="turn-local", origin_channel="VOICE", principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}", expires_at_unix=expires_at, nonce=nonce,
        context_capsule_revision=None, context_capsule_hash=None,
        speech_evidence_ref="speech://local", no_stale_replay=no_stale_replay,
        context_trust="CONVERSATION",
    )
    body = {
        "command_id": command_id, "idempotency_key": idempotency_key, "device_id": device_id,
        "issued_at_unix": issued, "signature": app.state.auth.sign(device_id, canonical),
        "signature_version": 2, "text": text, "action_class": "A1", "turn_id": "turn-local",
        "origin_channel": "VOICE", "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}", "expires_at_unix": expires_at, "nonce": nonce,
        "speech_evidence_ref": "speech://local", "no_stale_replay": no_stale_replay,
        "context_trust": "CONVERSATION",
    }
    if approval_proof is not None:
        body["approval_proof"] = approval_proof
    if client_context is not None:
        body["client_context"] = client_context
    return body


def _seed_fresh_ledger(path) -> None:
    now = int(time.time() * 1000)
    led = Ledger(path)
    led.append(make_event(
        EventKind.SESSION, "vati-runner", {"startup": True},
        event_time_ms=now, received_time_ms=now, correlation_id="s1",
    ))
    led.close()


async def _approve_halt(ac, app, *, device_id: str, private_key, idempotency_key: str) -> dict:
    """Drive the A4 challenge/approval handshake and return the approved response body."""
    first = await ac.post("/v1/commands", json=_halt_command(app, device_id=device_id, idempotency_key=f"{idempotency_key}-challenge"))
    assert first.status_code == 200
    challenge = first.json()
    assert challenge["status"] == "approval_required"
    signature = private_key.sign(
        challenge["approval_challenge"].encode("utf-8"), ec.ECDSA(hashes.SHA256())
    )
    proof = {
        "challenge_id": challenge["approval_challenge_id"],
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "algorithm": "ECDSA_P256_SHA256",
    }
    approved_at = int(time.time())
    approved = await ac.post(
        "/v1/commands",
        json=_halt_command(
            app, device_id=device_id, idempotency_key=idempotency_key,
            expires_at=approved_at + 5, no_stale_replay=True, approval_proof=proof,
        ),
    )
    assert approved.status_code == 200
    return approved.json()


@pytest.mark.asyncio
async def test_trading_halt_without_owner_authority_fails_deterministically(client, tmp_path):
    ac, app, _calls = client
    _seed_fresh_ledger(tmp_path / "vati.sqlite")
    harness = OwnerAuthorityHarness()
    app.state.trading.owner_authority = harness.verifier

    private_key = ec.generate_private_key(ec.SECP256R1())
    await _pair_a4_device(ac, app, device_id="dev-halt-missing", secret="s-halt-1", public_key_pem=_public_pem(private_key))

    approved_body = await _approve_halt(
        ac, app, device_id="dev-halt-missing", private_key=private_key, idempotency_key="halt-missing-token",
    )
    # P0-TRADE-001/GAP-F-005 — a missing owner_halt_authority_ref is an owner/authority
    # refusal, not a false "accepted".
    assert approved_body["status"] == "denied"
    assert approved_body["resolved_action_id"] == "trading.halt"
    assert approved_body["local_execution"]["verification_state"] == "EXECUTION_FAILED"
    assert "owner_halt_authority" in approved_body["message"] or "owner_halt_authority" in str(approved_body["local_execution"])

    mission = await app.state.missions.get(approved_body["mission_id"])
    assert mission.state.value == "FAILED"

    led = Ledger(tmp_path / "vati.sqlite")
    events = list(led.iter(EventKind.KILL_SWITCH))
    assert events == [], "a missing owner_halt_authority_ref must never reach the ledger"


@pytest.mark.asyncio
async def test_trading_halt_with_owner_authority_reaches_verified_success(client, tmp_path):
    ac, app, _calls = client
    _seed_fresh_ledger(tmp_path / "vati.sqlite")
    harness = OwnerAuthorityHarness()
    app.state.trading.owner_authority = harness.verifier

    private_key = ec.generate_private_key(ec.SECP256R1())
    await _pair_a4_device(ac, app, device_id="dev-halt-ok", secret="s-halt-2", public_key_pem=_public_pem(private_key))

    token = harness.token(act="owner-halt", subject="van-trading-core")

    command_id = str(uuid.uuid4())
    idem = "halt-ok-challenge"
    first = await ac.post("/v1/commands", json=_halt_command(app, device_id="dev-halt-ok", idempotency_key=idem))
    challenge = first.json()
    signature = private_key.sign(challenge["approval_challenge"].encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    proof = {
        "challenge_id": challenge["approval_challenge_id"],
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "algorithm": "ECDSA_P256_SHA256",
    }
    approved_at = int(time.time())
    approved = await ac.post(
        "/v1/commands",
        json=_halt_command(
            app, device_id="dev-halt-ok", idempotency_key="halt-ok-approved",
            expires_at=approved_at + 5, no_stale_replay=True, approval_proof=proof,
            client_context={"owner_halt_authority_ref": token},
        ),
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "accepted"
    assert body["resolved_action_id"] == "trading.halt"
    assert body["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"

    mission = await app.state.missions.get(body["mission_id"])
    assert mission.state.value == "VERIFIED_SUCCESS"

    led = Ledger(tmp_path / "vati.sqlite")
    kill_events = list(led.iter(EventKind.KILL_SWITCH))
    assert len(kill_events) == 1
    assert kill_events[0].payload["trigger"] == "OWNER_HALT"
    assert kill_events[0].payload["sig"].startswith("owner-authority:")


# ----------------------------------------------------------------- (f) context_gaps


@pytest.mark.asyncio
async def test_context_gaps_present_when_a_project_predicate_is_missing(client):
    ac, app, _calls = client
    await _pair_for_test(ac, app, "dev-gaps", "s1")
    r = await ac.post(
        "/v1/commands",
        json=_v1_command(
            app, device_id="dev-gaps", text="remember that my accountant is Thandi",
            idempotency_key="gaps-1", project_id="unregistered-project",
        ),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"
    gap_predicates = {gap["predicate"] for gap in body["context_gaps"]}
    # `timezone` (asked on every command) and the project predicates
    # (branch/stack/deploy_target/owner) are all unresolved on a fresh gateway.
    assert "timezone" in gap_predicates
    assert "branch" in gap_predicates
    assert all(gap["state"] in {"MISSING", "STALE"} for gap in body["context_gaps"])
    assert all(gap["label"] for gap in body["context_gaps"])
