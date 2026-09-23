from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "trading" / "tests"))
from conftest_owner_authority import OWNER_KEY_ID, OwnerAuthorityHarness  # noqa: E402

OWNER = OwnerAuthorityHarness()
RIVE_SHA = "a" * 64
APK_SHA = "b" * 64


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    registry = tmp_path / "owner_authority_keys.json"
    registry.write_text(json.dumps({"keys": {OWNER_KEY_ID: OWNER.pem}}), encoding="utf-8")
    monkeypatch.setenv("VAN_OWNER_AUTHORITY_KEYS", str(registry))
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "gw.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef0123456789")
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "test-device-enrolment-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            ticket = await ac.post(
                "/v1/devices/pairing-ticket",
                json={"label": "visual-test", "ttl_seconds": 600},
                headers={"x-van-internal-token": "test-device-enrolment-token"},
            )
            assert ticket.status_code == 200, ticket.text
            paired = await ac.post(
                "/v1/devices/pair",
                json={
                    "pairing_token": ticket.json()["pairing_token"],
                    "device_id": "visual-test-device",
                    "device_secret": "visual-test-secret",
                    "public_key_pem": OWNER.pem,
                    "label": "visual-test",
                },
            )
            assert paired.status_code == 200, paired.text
            ac.headers.update({
                "X-Van-Ingress-Token": paired.json()["ingress_token"],
                "X-Van-Device-Token": paired.json()["device_access_token"],
            })
            app.state.visual_acceptance.owner_authority = OWNER.verifier
            yield ac, app


def payload(token: str, rive_sha: str = RIVE_SHA):
    return {
        "token": token,
        "rive_sha256": rive_sha,
        "apk_sha256": APK_SHA,
        "device_model": "SM-S928B",
        "android_build": "test-build",
    }


@pytest.mark.asyncio
async def test_valid_visual_acceptance_is_stored_and_read_back(client):
    ac, _ = client
    token = OWNER.token(act="visual-accept", subject=f"sha256:{RIVE_SHA}")
    response = await ac.post("/v1/visual/acceptance", json=payload(token))
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["verified"] is True
    assert record["subject"] == f"sha256:{RIVE_SHA}"
    latest = await ac.get("/v1/visual/acceptance")
    assert latest.status_code == 200
    assert latest.json()["token"] == token


@pytest.mark.asyncio
async def test_wrong_act_is_rejected(client):
    ac, _ = client
    token = OWNER.token(act="owner-halt", subject=f"sha256:{RIVE_SHA}")
    response = await ac.post("/v1/visual/acceptance", json=payload(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_subject_mismatch_is_rejected(client):
    ac, _ = client
    token = OWNER.token(act="visual-accept", subject="sha256:" + "c" * 64)
    response = await ac.post("/v1/visual/acceptance", json=payload(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_same_signed_acceptance_is_idempotent(client):
    ac, app = client
    token = OWNER.token(act="visual-accept", subject=f"sha256:{RIVE_SHA}")
    first = await ac.post("/v1/visual/acceptance", json=payload(token))
    second = await ac.post("/v1/visual/acceptance", json=payload(token))
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    rows = await app.state.store.fetchall("SELECT id FROM visual_acceptances")
    assert len(rows) == 1


def test_visual_acceptance_is_declared_device_proofed():
    source = (Path(__file__).resolve().parents[1] / "van_gateway" / "app.py").read_text(encoding="utf-8")
    predicate = source[source.index("def requires_device_proof"):source.index("async def enforce_device_proof")]
    assert 'path == "/v1/visual/acceptance"' in predicate


@pytest.mark.asyncio
async def test_signed_acceptance_cannot_be_replayed_for_different_apk(client):
    ac, app = client
    token = OWNER.token(act="visual-accept", subject=f"sha256:{RIVE_SHA}")
    first = await ac.post("/v1/visual/acceptance", json=payload(token))
    assert first.status_code == 200, first.text

    changed = payload(token)
    changed["apk_sha256"] = "c" * 64
    replay = await ac.post("/v1/visual/acceptance", json=changed)
    assert replay.status_code == 403
    assert "different_artifact" in replay.text

    rows = await app.state.store.fetchall("SELECT id, apk_sha256 FROM visual_acceptances")
    assert len(rows) == 1
    assert rows[0]["apk_sha256"] == APK_SHA
