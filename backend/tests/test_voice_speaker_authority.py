from __future__ import annotations

import time
import uuid

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.auth.service import AuthService
from van_gateway.config import get_settings
from van_gateway.models import ActionClass
from van_gateway.voice.speaker import (
    SpeakerDisposition,
    SpeakerEvidence,
    classify_speaker_evidence,
    speaker_disposition,
)


INGRESS = "speaker-test-ingress-token-0123456789abcdef"
INTERNAL = "speaker-test-hermes-internal"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "speaker.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def stack(monkeypatch):
    app = create_app()

    async def fake_health():
        return {"ok": True, "profile": "van"}

    async def fake_create_run(text, metadata=None):
        return {"id": "run-speaker", "status": "accepted", "input": text, "metadata": metadata or {}}

    monkeypatch.setattr(app.state.orchestrator.hermes, "health", fake_health)
    monkeypatch.setattr(app.state.orchestrator.hermes, "create_run", fake_create_run)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Van-Ingress-Token": INGRESS},
        ) as client:
            private_key = ec.generate_private_key(ec.SECP256R1())
            public_pem = private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")
            device_id = "device-speaker"
            secret = "device-speaker-secret"
            ticket = await client.post(
                "/v1/devices/pairing-ticket",
                json={"label": "speaker-test", "ttl_seconds": 600},
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            paired = await client.post(
                "/v1/devices/pair",
                json={
                    "pairing_token": ticket.json()["pairing_token"],
                    "device_id": device_id,
                    "device_secret": secret,
                    "public_key_pem": public_pem,
                    "label": "speaker-test",
                },
            )
            assert paired.status_code == 200
            yield client, app, device_id, paired.json()["device_access_token"]


def _v3(
    app,
    *,
    device_id: str,
    text: str,
    key: str,
    speaker_milli: int | None,
    origin: str = "VOICE",
    signed_speaker_milli: int | None = None,
) -> dict:
    issued = int(time.time())
    command_id = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    canonical = AuthService.canonical_command_v3(
        command_id=command_id,
        idempotency_key=key,
        device_id=device_id,
        issued_at_unix=issued,
        text=text,
        action_class="A1",
        project_id=None,
        turn_id="turn-speaker",
        origin_channel=origin,
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=None,
        nonce=nonce,
        context_capsule_revision=None,
        context_capsule_hash=None,
        speech_evidence_ref="android://voice/turn-speaker" if origin == "VOICE" else None,
        speaker_evidence_milli=(
            speaker_milli if signed_speaker_milli is None else signed_speaker_milli
        ),
        no_stale_replay=False,
        context_trust="CONVERSATION",
    )
    body = {
        "command_id": command_id,
        "idempotency_key": key,
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "signature_version": 3,
        "text": text,
        "action_class": "A1",
        "turn_id": "turn-speaker",
        "origin_channel": origin,
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "nonce": nonce,
        "no_stale_replay": False,
        "context_trust": "CONVERSATION",
    }
    if origin == "VOICE":
        body["speech_evidence_ref"] = "android://voice/turn-speaker"
    if speaker_milli is not None:
        body["speaker_evidence_milli"] = speaker_milli
    return body


def _v2_without_speaker(app, *, device_id: str, text: str, key: str) -> dict:
    issued = int(time.time())
    command_id = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    canonical = AuthService.canonical_command_v2(
        command_id=command_id,
        idempotency_key=key,
        device_id=device_id,
        issued_at_unix=issued,
        text=text,
        action_class="A1",
        project_id=None,
        turn_id="turn-v2",
        origin_channel="VOICE",
        principal_type="OWNER_DEVICE",
        requested_by=f"device:{device_id}",
        expires_at_unix=None,
        nonce=nonce,
        context_capsule_revision=None,
        context_capsule_hash=None,
        speech_evidence_ref="android://voice/turn-v2",
        no_stale_replay=False,
        context_trust="CONVERSATION",
    )
    return {
        "command_id": command_id,
        "idempotency_key": key,
        "device_id": device_id,
        "issued_at_unix": issued,
        "signature": app.state.auth.sign(device_id, canonical),
        "signature_version": 2,
        "text": text,
        "action_class": "A1",
        "turn_id": "turn-v2",
        "origin_channel": "VOICE",
        "principal_type": "OWNER_DEVICE",
        "requested_by": f"device:{device_id}",
        "nonce": nonce,
        "speech_evidence_ref": "android://voice/turn-v2",
        "context_trust": "CONVERSATION",
    }


def test_speaker_thresholds_are_fixed_and_consequential_only():
    assert classify_speaker_evidence(None) is SpeakerEvidence.UNAVAILABLE
    assert classify_speaker_evidence(350) is SpeakerEvidence.MISMATCH
    assert classify_speaker_evidence(351) is SpeakerEvidence.INCONCLUSIVE
    assert classify_speaker_evidence(719) is SpeakerEvidence.INCONCLUSIVE
    assert classify_speaker_evidence(720) is SpeakerEvidence.MATCH
    assert speaker_disposition(ActionClass.A1, SpeakerEvidence.MISMATCH) is SpeakerDisposition.ALLOW
    assert speaker_disposition(ActionClass.A3, SpeakerEvidence.MATCH) is SpeakerDisposition.ALLOW
    assert (
        speaker_disposition(ActionClass.A3, SpeakerEvidence.UNAVAILABLE)
        is SpeakerDisposition.REQUIRE_OWNER_APPROVAL
    )
    assert (
        speaker_disposition(ActionClass.A4, SpeakerEvidence.MATCH)
        is SpeakerDisposition.REQUIRE_OWNER_APPROVAL
    )


@pytest.mark.asyncio
async def test_resolved_a3_match_may_proceed_but_uncertainty_requires_biometric(stack):
    client, app, device_id, token = stack
    headers = {"X-Van-Device-Token": token}
    text = "create a new note in notebook nb-1 named Speaker Evidence"

    matched = await client.post(
        "/v1/commands",
        headers=headers,
        json=_v3(app, device_id=device_id, text=text, key="sp-a3-match", speaker_milli=900),
    )
    assert matched.status_code == 200
    assert matched.json()["status"] == "accepted"
    assert matched.json()["effective_action_class"] == "A3"

    uncertain = await client.post(
        "/v1/commands",
        headers=headers,
        json=_v3(app, device_id=device_id, text=text, key="sp-a3-uncertain", speaker_milli=500),
    )
    assert uncertain.status_code == 200
    body = uncertain.json()
    assert body["status"] == "approval_required"
    assert body["effective_action_class"] == "A3"
    assert body["resolved_action_id"] == "google.notebook.note.create"


@pytest.mark.asyncio
async def test_resolved_consequential_voice_mismatch_is_refused_before_prompt(stack):
    client, app, device_id, token = stack
    headers = {"X-Van-Device-Token": token}
    for text, key, expected_class in (
        ("create a new note in notebook nb-1 named Refuse Me", "sp-mismatch-a3", "A3"),
        ("halt autonomous trading", "sp-mismatch-a4", "A4"),
    ):
        response = await client.post(
            "/v1/commands",
            headers=headers,
            json=_v3(app, device_id=device_id, text=text, key=key, speaker_milli=100),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "denied"
        assert body["effective_action_class"] == expected_class
        assert body["requires_approval"] is False


@pytest.mark.asyncio
async def test_a4_match_still_requires_biometric_owner_approval(stack):
    client, app, device_id, token = stack
    response = await client.post(
        "/v1/commands",
        headers={"X-Van-Device-Token": token},
        json=_v3(
            app,
            device_id=device_id,
            text="halt autonomous trading",
            key="sp-a4-match",
            speaker_milli=950,
        ),
    )
    body = response.json()
    assert body["status"] == "approval_required"
    assert body["effective_action_class"] == "A4"


@pytest.mark.asyncio
async def test_v3_speaker_tamper_breaks_device_signature(stack):
    client, app, device_id, token = stack
    response = await client.post(
        "/v1/commands",
        headers={"X-Van-Device-Token": token},
        json=_v3(
            app,
            device_id=device_id,
            text="halt autonomous trading",
            key="sp-tamper",
            speaker_milli=100,
            signed_speaker_milli=900,
        ),
    )
    body = response.json()
    assert body["status"] == "denied"
    assert "signature" in body["message"].lower()


@pytest.mark.asyncio
async def test_v2_voice_without_speaker_evidence_cannot_autonomously_mutate_a3(stack):
    client, app, device_id, token = stack
    response = await client.post(
        "/v1/commands",
        headers={"X-Van-Device-Token": token},
        json=_v2_without_speaker(
            app,
            device_id=device_id,
            text="create a new note in notebook nb-1 named Legacy Voice",
            key="sp-v2-no-evidence",
        ),
    )
    body = response.json()
    assert body["status"] == "approval_required"
    assert body["effective_action_class"] == "A3"


@pytest.mark.asyncio
async def test_non_voice_channel_cannot_carry_speaker_evidence(stack):
    client, app, device_id, token = stack
    response = await client.post(
        "/v1/commands",
        headers={"X-Van-Device-Token": token},
        json=_v3(
            app,
            device_id=device_id,
            text="show status",
            key="sp-nonvoice",
            speaker_milli=900,
            origin="TEXT",
        ),
    )
    body = response.json()
    assert body["status"] == "denied"
    assert "voice-origin" in body["message"]
