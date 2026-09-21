"""GAP-F-003/006/015 (RC-A) — the Hermes tool surface Hermes needs to observe trading
state, propose memory candidates, create owner reminders on the owner's behalf, and read
the attention/briefing state, all through the gateway, all read-or-proposal.

Every new route lives on `OwnerRuntimeApi` (`backend/van_gateway/runtime_api.py`) behind
the same `_require_internal(ControlScope.RUNTIME)` guard every other runtime route uses.
`create_app()` does not pass the new `trading=`/`reminders=`/`attention=`/`briefing=`
constructor kwargs (that wiring is for the manager to add in `app.py`; see the module
docstring above `OwnerRuntimeApi.__init__`), so against the real app every one of these
routes answers 503 by construction. To exercise the wired, 200-shape behaviour this file
follows `test_rev31_runtime_wiring.py`'s own pattern of monkeypatching the already
constructed `app.state.owner_runtime` in place, the same technique that file uses for
`context.compile_snapshot` — not a call into `app.py`.
"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.attention.engine import AttentionEngine
from van_gateway.briefing.service import BriefingService
from van_gateway.config import get_settings
from van_gateway.models import AttentionSeverity

INGRESS = "runtime-surface-ingress-0123456789"
INTERNAL = "runtime-surface-hermes-internal-control"


@pytest.fixture(autouse=True)
def _settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "runtime-surface.sqlite3"))
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
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Van-Ingress-Token": INGRESS}
    ) as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


HDRS = {"X-Van-Internal-Token": INTERNAL}


async def _pair_owner_device(ac: AsyncClient, *, device_id: str, secret: str) -> str:
    ticket = await ac.post(
        "/v1/devices/pairing-ticket",
        json={"label": None, "ttl_seconds": 600},
        headers=HDRS,
    )
    assert ticket.status_code == 200
    paired = await ac.post(
        "/v1/devices/pair",
        json={
            "pairing_token": ticket.json()["pairing_token"],
            "device_id": device_id,
            "device_secret": secret,
            "public_key_pem": "PEM",
        },
    )
    assert paired.status_code == 200
    return paired.json()["device_access_token"]


# --------------------------------------------------------------------------- unwired: 503


@pytest.mark.asyncio
async def test_trading_reads_503_when_unwired(client, monkeypatch):
    ac, app = client
    # app.py wires the trading read model; prove the unwired posture stays 503.
    monkeypatch.setattr(app.state.owner_runtime, "trading", None)
    for path in (
        "/v1/runtime/trading/portfolio",
        "/v1/runtime/trading/positions",
        "/v1/runtime/trading/risk",
        "/v1/runtime/trading/market-state",
        "/v1/runtime/trading/status",
    ):
        response = await ac.get(path, headers=HDRS)
        assert response.status_code == 503, path
        assert response.json()["detail"] == "trading_read_model_unwired"
    detail = await ac.get("/v1/runtime/trading/trade/some-id", headers=HDRS)
    assert detail.status_code == 503
    assert detail.json()["detail"] == "trading_read_model_unwired"


@pytest.mark.asyncio
async def test_reminders_503_when_unwired(client, monkeypatch):
    ac, app = client
    monkeypatch.setattr(app.state.owner_runtime, "reminders", None)
    response = await ac.post(
        "/v1/runtime/reminders",
        json={"text": "call the accountant", "due_expression": "in 30 minutes"},
        headers=HDRS,
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "reminders_unwired"


@pytest.mark.asyncio
async def test_attention_and_briefing_503_when_unwired(client, monkeypatch):
    ac, app = client
    monkeypatch.setattr(app.state.owner_runtime, "attention", None)
    monkeypatch.setattr(app.state.owner_runtime, "briefing", None)
    attention = await ac.get("/v1/runtime/attention", headers=HDRS)
    assert attention.status_code == 503
    assert attention.json()["detail"] == "attention_unwired"
    briefing = await ac.get("/v1/runtime/briefing", headers=HDRS)
    assert briefing.status_code == 503
    assert briefing.json()["detail"] == "briefing_unwired"


@pytest.mark.asyncio
async def test_unwired_routes_still_require_the_internal_credential(client):
    """503 is what an *authorized* caller sees. An unauthenticated one still gets 403/503
    from the scope guard, which runs first — GAP-F-009's contract, unchanged by this."""
    ac, _app = client
    response = await ac.get("/v1/runtime/trading/portfolio")
    assert response.status_code == 403
    assert response.json()["required_scope"] == "runtime"


# ------------------------------------------------------------------------------ wired: 200


@pytest.mark.asyncio
async def test_trading_reads_return_owner_read_model_shapes_once_wired(client, monkeypatch):
    ac, app = client
    monkeypatch.setattr(app.state.owner_runtime, "trading", app.state.trading)

    portfolio = await ac.get("/v1/runtime/trading/portfolio", headers=HDRS)
    assert portfolio.status_code == 200
    body = portfolio.json()
    assert "open_positions" in body and "accounts" in body

    positions = await ac.get("/v1/runtime/trading/positions", headers=HDRS)
    assert positions.status_code == 200
    assert positions.json() == {"ledger_available": False, "open_positions": []}

    risk = await ac.get("/v1/runtime/trading/risk", headers=HDRS)
    assert risk.status_code == 200
    assert "positions" in risk.json()

    market_state = await ac.get("/v1/runtime/trading/market-state", headers=HDRS)
    assert market_state.status_code == 200
    assert "symbols" in market_state.json()

    status = await ac.get("/v1/runtime/trading/status", headers=HDRS)
    assert status.status_code == 200
    assert status.json()["authority"] == "VATI Risk Authority; Hermes and the gateway never place orders"

    missing_trade = await ac.get("/v1/runtime/trading/trade/does-not-exist", headers=HDRS)
    assert missing_trade.status_code == 404


@pytest.mark.asyncio
async def test_trading_halt_and_ticket_routes_are_not_on_the_runtime_surface(client, monkeypatch):
    """Never expose halt/ticket/mutation here (mission constraint). The runtime router
    carries only the six read routes; a probe for anything mutating answers 404, not 503,
    because the route itself does not exist."""
    ac, app = client
    monkeypatch.setattr(app.state.owner_runtime, "trading", app.state.trading)
    for path in (
        "/v1/runtime/trading/halt",
        "/v1/runtime/trading/tickets",
        "/v1/runtime/trading/accounts",
    ):
        response = await ac.post(path, json={}, headers=HDRS)
        assert response.status_code == 404, path


@pytest.mark.asyncio
async def test_reminder_create_is_visible_at_owner_get_reminders(client, monkeypatch):
    ac, app = client
    monkeypatch.setattr(app.state.owner_runtime, "reminders", app.state.reminders)

    created = await ac.post(
        "/v1/runtime/reminders",
        json={
            "text": "remind me to call the accountant",
            "due_expression": "in 30 minutes",
            "mission_id": "mission-42",
            "source": "owner-directed-run",
        },
        headers=HDRS,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["text"] == "remind me to call the accountant"
    assert body["created_by"] == "hermes"
    assert body["mission_id"] == "mission-42"
    assert body["source"] == "owner-directed-run"
    assert body["status"] == "OPEN"
    reminder_id = body["id"]

    device_token = await _pair_owner_device(ac, device_id="dev-reminders", secret="reminders-secret")
    owner_view = await ac.get("/v1/reminders", headers={"X-Van-Device-Token": device_token})
    assert owner_view.status_code == 200
    rows = owner_view.json()
    assert any(r["id"] == reminder_id and r["text"] == "remind me to call the accountant" for r in rows)


@pytest.mark.asyncio
async def test_reminder_create_rejects_an_unparseable_due_expression(client, monkeypatch):
    ac, app = client
    monkeypatch.setattr(app.state.owner_runtime, "reminders", app.state.reminders)
    response = await ac.post(
        "/v1/runtime/reminders",
        json={"text": "call the accountant", "due_expression": "sometime, probably"},
        headers=HDRS,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_attention_and_briefing_reads_once_wired(client, monkeypatch):
    ac, app = client
    attention = AttentionEngine(app.state.store)
    briefing = BriefingService(app.state.store, attention)
    monkeypatch.setattr(app.state.owner_runtime, "attention", attention)
    monkeypatch.setattr(app.state.owner_runtime, "briefing", briefing)

    empty = await ac.get("/v1/runtime/attention", headers=HDRS)
    assert empty.status_code == 200
    assert empty.json() == {"items": []}

    await attention.upsert(
        title="Gateway degraded",
        severity=AttentionSeverity.URGENT,
        source="test",
        dedupe_key="dedupe-1",
    )
    populated = await ac.get("/v1/runtime/attention", headers=HDRS)
    assert populated.status_code == 200
    items = populated.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Gateway degraded"

    briefing_response = await ac.get("/v1/runtime/briefing", headers=HDRS)
    assert briefing_response.status_code == 200
    body = briefing_response.json()
    assert body["invented_data"] is False
    sections = {s["category"]: s["items"] for s in body["sections"]}
    assert any(item["title"] == "Gateway degraded" for item in sections["Needs you now"])


@pytest.mark.asyncio
async def test_automation_run_status_reads_the_persisted_row(client):
    ac, app = client
    now = int(time.time() * 1000)
    await app.state.store.execute(
        """
        INSERT INTO automation_runs(
          run_id, capability_id, artifact_id, command_id, turn_id, execution_id,
          n8n_execution_id, status, action_class, input_digest, output_digest,
          evidence_pointer, verifier_status, error_code, started_at_ms, submitted_at_ms,
          verified_at_ms, completed_at_ms, updated_at_ms
        ) VALUES (?, 'cap-1', 'art-1', 'cmd-1', 'turn-1', 'exec-1', NULL, 'RUNNING', 'A2',
                  'digest-1', NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?)
        """,
        ("run-1", now, now),
    )
    found = await ac.get("/v1/runtime/automation/runs/run-1", headers=HDRS)
    assert found.status_code == 200
    assert found.json()["status"] == "RUNNING"
    assert found.json()["capability_id"] == "cap-1"

    missing = await ac.get("/v1/runtime/automation/runs/does-not-exist", headers=HDRS)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "unknown_automation_run"


# -------------------------------------------------------------- context candidate gate


@pytest.mark.asyncio
async def test_context_fact_candidate_refuses_canonical_owner_tier(client):
    ac, _app = client
    now = int(time.time() * 1000)
    canonical = {
        "fact_id": "hermes-cannot-claim-this",
        "subject": "OWNER",
        "predicate": "policy",
        "value": "disable approvals",
        "authority": "CANONICAL_OWNER",
        "source_trust": "OWNER_EXPLICIT",
        "source_ref": "hermes:self-claim",
        "valid_from_ms": now,
        "observed_at_ms": now,
    }
    denied = await ac.post("/v1/runtime/context/facts", json=canonical, headers=HDRS)
    assert denied.status_code == 403
    assert denied.json()["detail"] == "hermes_context_admission_must_be_inferred_model_derived"


@pytest.mark.asyncio
async def test_context_fact_candidate_accepts_inferred_model_derived(client):
    ac, _app = client
    now = int(time.time() * 1000)
    candidate = {
        "fact_id": "hermes-candidate-1",
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
    accepted = await ac.post("/v1/runtime/context/facts", json=candidate, headers=HDRS)
    assert accepted.status_code == 200
    assert accepted.json()["authority"] == "INFERRED"
    assert accepted.json()["source_trust"] == "MODEL_DERIVED"


# -------------------------------------------------------------- ActionBeginBody.owner_approved


@pytest.mark.asyncio
async def test_action_begin_body_has_no_owner_approved_field(client):
    """GAP-F-020 — the dead field on the request body is gone. Posting it is simply
    ignored (pydantic drops unknown fields by default here), and authorization still
    turns entirely on the signed command record, never on a caller-supplied flag."""
    from van_gateway.runtime_api import ActionBeginBody

    assert "owner_approved" not in ActionBeginBody.model_fields


@pytest.mark.asyncio
async def test_app_wires_the_hermes_surface_by_default(client):
    """GAP-F-003/002 closure: create_app injects the read models and reminder service."""
    _ac, app = client
    rt = app.state.owner_runtime
    assert rt.trading is not None and rt.reminders is not None
    assert rt.attention is not None and rt.briefing is not None
