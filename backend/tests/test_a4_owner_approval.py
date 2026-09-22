from __future__ import annotations

import base64
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

#: GAP-F-005 — the same fixtures test_trading_api.py and test_local_typed_actions.py use to
#: mint a real owner-signed trading-halt authority instead of a bare string, so this test's
#: "approved" A4 command can complete the local execution it now names rather than stopping
#: at a refusal that has nothing to do with what this test is proving (one-time biometric
#: approval and replay rejection).
sys.path[:0] = [
    str(Path(__file__).resolve().parents[2] / "trading" / "tests"),
    str(Path(__file__).resolve().parents[2] / "trading"),
]
from conftest_owner_authority import OwnerAuthorityHarness  # noqa: E402
from van_gateway.trading.service import _import_vati  # noqa: E402

EventKind, make_event, Ledger = _import_vati()


INGRESS = "a4-test-ingress-token-0123456789abcdef"
INTERNAL = "a4-test-hermes-internal"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "a4.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    monkeypatch.setenv("VAN_VATI_LEDGER_PATH", str(tmp_path / "vati.sqlite"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _seed_fresh_ledger(path) -> None:
    now = int(time.time() * 1000)
    led = Ledger(path)
    led.append(make_event(
        EventKind.SESSION, "vati-runner", {"startup": True},
        event_time_ms=now, received_time_ms=now, correlation_id="s1",
    ))
    led.close()


@pytest_asyncio.fixture
async def client_and_app(monkeypatch):
    app = create_app()

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        return {"id": "run-a4", "status": "accepted", "input": text, "metadata": metadata or {}}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Van-Ingress-Token": INGRESS},
        ) as client:
            yield client, app


def _public_pem(private_key: ec.EllipticCurvePrivateKey) -> str:
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


async def _pair(client: AsyncClient, *, device_id: str, secret: str, public_key_pem: str) -> str:
    ticket = await client.post(
        "/v1/devices/pairing-ticket",
        json={"label": "a4-test", "ttl_seconds": 600},
        headers={"X-Van-Internal-Token": INTERNAL},
    )
    assert ticket.status_code == 200
    response = await client.post(
        "/v1/devices/pair",
        json={
            "pairing_token": ticket.json()["pairing_token"],
            "device_id": device_id,
            "device_secret": secret,
            "public_key_pem": public_key_pem,
            "label": "a4-test",
        },
    )
    assert response.status_code == 200
    return response.json()["device_access_token"]


def _signed_command(
    app,
    *,
    device_id: str,
    text: str,
    idempotency_key: str,
    issued_at: int,
    expires_at: int | None = None,
    no_stale_replay: bool = False,
    approval_token: str | None = None,
    approval_proof: dict | None = None,
    client_context: dict | None = None,
) -> dict:
    command_id = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    canonical = AuthService.canonical_command_v2(
        command_id=command_id,
        idempotency_key=idempotency_key,
        device_id=device_id,
        issued_at_unix=issued_at,
        text=text,
        action_class="A1",
        project_id=None,
        turn_id="turn-a4",
        origin_channel="VOICE",
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=expires_at,
        nonce=nonce,
        context_capsule_revision=None,
        context_capsule_hash=None,
        speech_evidence_ref="speech://a4",
        no_stale_replay=no_stale_replay,
        context_trust="CONVERSATION",
    )
    body = {
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "device_id": device_id,
        "issued_at_unix": issued_at,
        "signature": app.state.auth.sign(device_id, canonical),
        "signature_version": 2,
        "text": text,
        "action_class": "A1",
        "turn_id": "turn-a4",
        "origin_channel": "VOICE",
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "expires_at_unix": expires_at,
        "nonce": nonce,
        "speech_evidence_ref": "speech://a4",
        "no_stale_replay": no_stale_replay,
        "context_trust": "CONVERSATION",
    }
    if approval_token is not None:
        body["approval_token"] = approval_token
    if approval_proof is not None:
        body["approval_proof"] = approval_proof
    if client_context is not None:
        body["client_context"] = client_context
    return body


@pytest.mark.asyncio
async def test_a4_requires_one_time_biometric_signature_and_rejects_legacy_token(client_and_app, tmp_path):
    client, app = client_and_app
    _seed_fresh_ledger(tmp_path / "vati.sqlite")
    harness = OwnerAuthorityHarness()
    app.state.trading.owner_authority = harness.verifier

    private_key = ec.generate_private_key(ec.SECP256R1())
    device_id = "device-a4"
    secret = "device-a4-secret"
    device_token = await _pair(
        client,
        device_id=device_id,
        secret=secret,
        public_key_pem=_public_pem(private_key),
    )
    headers = {"X-Van-Device-Token": device_token}
    text = "halt autonomous trading"

    issued = int(time.time())
    first = await client.post(
        "/v1/commands",
        json=_signed_command(
            app,
            device_id=device_id,
            text=text,
            idempotency_key="a4-initial",
            issued_at=issued,
        ),
        headers=headers,
    )
    assert first.status_code == 200
    challenge = first.json()
    assert challenge["status"] == "approval_required"
    assert challenge["effective_action_class"] == "A4"
    assert challenge["resolved_action_id"] == "trading.halt"
    assert challenge["no_stale_replay"] is True
    assert challenge["max_age_seconds"] == 5
    assert challenge["approval_challenge"]

    fake = await client.post(
        "/v1/commands",
        json=_signed_command(
            app,
            device_id=device_id,
            text=text,
            idempotency_key="a4-fake-token",
            issued_at=int(time.time()),
            approval_token="owner-approved",
        ),
        headers=headers,
    )
    assert fake.status_code == 200
    assert fake.json()["status"] == "approval_required"

    signature = private_key.sign(
        challenge["approval_challenge"].encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    proof = {
        "challenge_id": challenge["approval_challenge_id"],
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "algorithm": "ECDSA_P256_SHA256",
    }

    approved_at = int(time.time())
    halt_token = harness.token(act="owner-halt", subject="van-trading-core")
    approved = await client.post(
        "/v1/commands",
        json=_signed_command(
            app,
            device_id=device_id,
            text=text,
            idempotency_key="a4-approved",
            issued_at=approved_at,
            expires_at=approved_at + 5,
            no_stale_replay=True,
            approval_proof=proof,
            client_context={"owner_halt_authority_ref": halt_token},
        ),
        headers=headers,
    )
    assert approved.status_code == 200
    approved_body = approved.json()
    # GAP-F-005 — the biometric approval this test proves is only half the A4 story now
    # that trading.halt executes on the gateway: with a real owner-halt authority alongside
    # it, the command reaches genuine VERIFIED_SUCCESS, not just "approval accepted".
    assert approved_body["status"] == "accepted"
    assert approved_body["effective_action_class"] == "A4"
    assert approved_body["resolved_action_id"] == "trading.halt"
    assert approved_body["local_execution"]["verification_state"] == "VERIFIED_SUCCESS"
    mission = await app.state.missions.get(approved_body["mission_id"])
    assert mission.state.value == "VERIFIED_SUCCESS"

    # The halt is a ledger fact, not just an in-process claim: exactly one OWNER_HALT
    # KILL_SWITCH event, signed by the owner-halt authority this test minted.
    led = Ledger(tmp_path / "vati.sqlite")
    kill_events = list(led.iter(EventKind.KILL_SWITCH))
    assert len(kill_events) == 1
    assert kill_events[0].payload["trigger"] == "OWNER_HALT"
    assert kill_events[0].payload["sig"].startswith("owner-authority:")

    replay_at = int(time.time())
    replay = await client.post(
        "/v1/commands",
        json=_signed_command(
            app,
            device_id=device_id,
            text=text,
            idempotency_key="a4-replay",
            issued_at=replay_at,
            expires_at=replay_at + 5,
            no_stale_replay=True,
            approval_proof=proof,
        ),
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "denied"
