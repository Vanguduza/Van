"""Typed acquisition API tests."""

from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest_automation import make_store
from van_gateway.browser.api import BrowserApi
from van_gateway.config import get_settings

INTERNAL = "test-internal-token"
HEADERS = {"X-Van-Internal-Token": INTERNAL}


@pytest.fixture(autouse=True)
def _settings(monkeypatch, tmp_path):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "browser.sqlite3"))
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef")
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_BROWSER_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _client(tmp_path):
    store = await make_store(tmp_path)
    api = BrowserApi(store, get_settings())
    app = FastAPI()
    app.include_router(api.router)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), store


async def test_acquisition_api_requires_internal_browser_scope(tmp_path):
    client, _store = await _client(tmp_path)
    async with client:
        response = await client.post(
            "/v1/browser/acquisition/items",
            json={"url": "https://example.com/catalog"},
        )
    assert response.status_code in {401, 403}


async def test_acquisition_api_enqueue_claim_renew_complete(tmp_path):
    client, store = await _client(tmp_path)
    async with client:
        created = await client.post(
            "/v1/browser/acquisition/items",
            headers=HEADERS,
            json={"url": "https://example.com/catalog", "priority": 80},
        )
        assert created.status_code == 200
        item = created.json()

        claimed = await client.post(
            "/v1/browser/acquisition/claim",
            headers=HEADERS,
            json={"worker_id": "worker-a", "lease_seconds": 120},
        )
        assert claimed.status_code == 200
        claim = claimed.json()
        assert claim["item_id"] == item["item_id"]

        started = await client.post(
            f"/v1/browser/acquisition/items/{item['item_id']}/start",
            headers=HEADERS,
            json={"worker_id": "worker-a", "lease_token": claim["lease_token"]},
        )
        assert started.status_code == 200

        renewed = await client.post(
            f"/v1/browser/acquisition/items/{item['item_id']}/renew",
            headers=HEADERS,
            json={
                "worker_id": "worker-a",
                "lease_token": claim["lease_token"],
                "lease_seconds": 120,
            },
        )
        assert renewed.status_code == 200
        assert renewed.json()["lease_token"] == claim["lease_token"]

        completed = await client.post(
            f"/v1/browser/acquisition/items/{item['item_id']}/complete",
            headers=HEADERS,
            json={
                "worker_id": "worker-a",
                "lease_token": claim["lease_token"],
                "checkpoint_ref": "checkpoint://final",
            },
        )
        assert completed.status_code == 200

    row = await store.fetchone(
        "SELECT state, checkpoint_ref FROM web_acquisition_items WHERE item_id=?",
        (item["item_id"],),
    )
    assert row["state"] == "COMPLETED"
    assert row["checkpoint_ref"] == "checkpoint://final"


async def test_acquisition_api_jev_hint_cannot_escalate_route(tmp_path):
    client, _store = await _client(tmp_path)
    async with client:
        created = await client.post(
            "/v1/browser/acquisition/items",
            headers=HEADERS,
            json={"url": "https://example.com/"},
        )
        item = created.json()
        claimed = await client.post(
            "/v1/browser/acquisition/claim",
            headers=HEADERS,
            json={"worker_id": "worker-a"},
        )
        claim = claimed.json()

        routed = await client.post(
            f"/v1/browser/acquisition/items/{item['item_id']}/route",
            headers=HEADERS,
            json={
                "worker_id": "worker-a",
                "lease_token": claim["lease_token"],
                "signals": {"jev_hint": "STAGEHAND"},
            },
        )
        assert routed.status_code == 200
        assert routed.json()["route"] == "SCRAPLING_HTTP"


async def test_domain_skill_api_falls_back_after_quarantine(tmp_path):
    client, _store = await _client(tmp_path)
    async with client:
        first = await client.post(
            "/v1/browser/acquisition/skills",
            headers=HEADERS,
            json={
                "domain": "example.com",
                "goal_class": "catalog",
                "route": "HARNESS",
                "artifact_ref": "artifact://skill/v1",
                "golden_case_refs": ["golden://catalog/v1"],
            },
        )
        first_skill = first.json()
        q1 = await client.post(
            f"/v1/browser/acquisition/skills/{first_skill['skill_id']}/qualify",
            headers=HEADERS,
            json={"replay_passed": True, "evidence_refs": ["evidence://v1"]},
        )
        assert q1.status_code == 200

        second = await client.post(
            "/v1/browser/acquisition/skills",
            headers=HEADERS,
            json={
                "domain": "example.com",
                "goal_class": "catalog",
                "route": "HARNESS",
                "artifact_ref": "artifact://skill/v2",
                "golden_case_refs": ["golden://catalog/v2"],
            },
        )
        second_skill = second.json()
        q2 = await client.post(
            f"/v1/browser/acquisition/skills/{second_skill['skill_id']}/qualify",
            headers=HEADERS,
            json={"replay_passed": True, "evidence_refs": ["evidence://v2"]},
        )
        assert q2.status_code == 200

        quarantine = await client.post(
            f"/v1/browser/acquisition/skills/{second_skill['skill_id']}/quarantine",
            headers=HEADERS,
            json={"reason": "site drift", "evidence_ref": "evidence://drift"},
        )
        assert quarantine.status_code == 200

        hot = await client.get(
            "/v1/browser/acquisition/skills/hot/example.com/catalog",
            headers=HEADERS,
        )
        assert hot.status_code == 200
        assert hot.json()["skill_id"] == first_skill["skill_id"]


async def test_public_execute_records_evidence_and_completes(tmp_path):
    client, store = await _client(tmp_path)
    # Inject a deterministic loopback worker response; this tests the assembled API
    # without requiring a live Scrapling runtime in unit tests.
    api = None
    # ASGITransport owns the app, so build a dedicated stack here to reach the adapter.
    from van_gateway.browser.api import BrowserApi
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    api = BrowserApi(store, get_settings())
    api.acquisition_runtime.transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "ok": True,
                "status": 200,
                "final_url": "https://example.com/catalog",
                "representation": "MARKDOWN_MAIN_CONTENT",
                "content": "item one",
                "content_digest": "sha256:" + "a" * 64,
                "byte_size": 8,
                "contains_secrets": False,
            },
        )
    )
    app = FastAPI()
    app.include_router(api.router)
    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    async with ac:
        created = await ac.post(
            "/v1/browser/acquisition/items",
            headers=HEADERS,
            json={"url": "https://example.com/catalog"},
        )
        assert created.status_code == 200
        item = created.json()
        claimed = await ac.post(
            "/v1/browser/acquisition/claim",
            headers=HEADERS,
            json={"worker_id": "worker-a"},
        )
        claim = claimed.json()
        executed = await ac.post(
            f"/v1/browser/acquisition/items/{item['item_id']}/execute",
            headers=HEADERS,
            json={
                "worker_id": "worker-a",
                "lease_token": claim["lease_token"],
                "signals": {},
            },
        )
        assert executed.status_code == 200
        assert executed.json()["route"] == "SCRAPLING_HTTP"
        assert executed.json()["evidence_ref"].startswith("web-acquisition-evidence://")

        verified = await ac.get(
            "/v1/browser/acquisition/evidence/verify", headers=HEADERS
        )
        assert verified.status_code == 200
        assert verified.json()["ok"] is True

    row = await store.fetchone(
        "SELECT state FROM web_acquisition_items WHERE item_id=?", (item["item_id"],)
    )
    assert row["state"] == "COMPLETED"
    evidence = await store.fetchone(
        "SELECT content_digest, manifest_digest FROM web_acquisition_evidence WHERE item_id=?",
        (item["item_id"],),
    )
    assert evidence["content_digest"] == "sha256:" + "a" * 64
    assert str(evidence["manifest_digest"]).startswith("sha256:")


async def test_authenticated_execute_requires_managed_browser(tmp_path):
    client, store = await _client(tmp_path)
    async with client:
        created = await client.post(
            "/v1/browser/acquisition/items",
            headers=HEADERS,
            json={
                "url": "https://example.com/account",
                "profile_alias": "authenticated_owner",
            },
        )
        assert created.status_code == 200
        item = created.json()
        claimed = await client.post(
            "/v1/browser/acquisition/claim",
            headers=HEADERS,
            json={"worker_id": "worker-a"},
        )
        claim = claimed.json()
        executed = await client.post(
            f"/v1/browser/acquisition/items/{item['item_id']}/execute",
            headers=HEADERS,
            json={
                "worker_id": "worker-a",
                "lease_token": claim["lease_token"],
                "signals": {},
            },
        )
        assert executed.status_code == 409
        assert executed.json()["detail"]["code"] == "ACQUISITION_MANAGED_BROWSER_REQUIRED"

    row = await store.fetchone(
        "SELECT state, route FROM web_acquisition_items WHERE item_id=?", (item["item_id"],)
    )
    assert row["state"] == "CLAIMED"
    assert row["route"] is None
