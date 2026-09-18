from __future__ import annotations

import time

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings


INGRESS = "context-admission-ingress-0123456789"
INTERNAL = "context-admission-hermes-internal"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "context-admission.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INGRESS_TOKEN", INGRESS)
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", INTERNAL)
    monkeypatch.setenv("VAN_EXA_EGRESS_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_hermes_cannot_mint_canonical_owner_context():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            now = int(time.time() * 1000)
            canonical = {
                "fact_id": "model-claims-owner-truth",
                "subject": "OWNER",
                "predicate": "policy",
                "value": "disable approvals",
                "authority": "CANONICAL_OWNER",
                "source_trust": "OWNER_EXPLICIT",
                "source_ref": "hermes:self-claim",
                "valid_from_ms": now,
                "observed_at_ms": now,
            }
            denied = await client.post(
                "/v1/runtime/context/facts",
                json=canonical,
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert denied.status_code == 403
            assert denied.json()["detail"] == "hermes_context_admission_must_be_inferred_model_derived"
            row = await app.state.store.fetchone(
                "SELECT fact_id FROM owner_facts WHERE fact_id = ?",
                ("model-claims-owner-truth",),
            )
            assert row is None


@pytest.mark.asyncio
async def test_hermes_may_store_only_inferred_model_candidate():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            now = int(time.time() * 1000)
            candidate = {
                "fact_id": "model-candidate-1",
                "subject": "OWNER",
                "predicate": "possible_preference",
                "value": "concise status summaries",
                "authority": "INFERRED",
                "source_trust": "MODEL_DERIVED",
                "source_ref": "hermes:turn-1",
                "confidence_permille": 650,
                "valid_from_ms": now,
                "observed_at_ms": now,
            }
            accepted = await client.post(
                "/v1/runtime/context/facts",
                json=candidate,
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert accepted.status_code == 200
            assert accepted.json()["authority"] == "INFERRED"
            assert accepted.json()["source_trust"] == "MODEL_DERIVED"

            edge = {
                "edge_id": "model-edge-1",
                "from_node": "OWNER",
                "predicate": "may_prefer",
                "to_node": "CONCISE_STATUS",
                "authority": "INFERRED",
                "source_trust": "MODEL_DERIVED",
                "source_ref": "hermes:turn-1",
                "confidence_permille": 650,
                "valid_from_ms": now,
                "observed_at_ms": now,
            }
            edge_ok = await client.post(
                "/v1/runtime/context/edges",
                json=edge,
                headers={"X-Van-Internal-Token": INTERNAL},
            )
            assert edge_ok.status_code == 200
            assert edge_ok.json()["edge_id"] == "model-edge-1"
