"""Gateway trading surface (Rev 4 Part K): status/tickets are read from the
VATI ledger; halt and ticket confirmation need the internal control token AND
an owner signature reference (A4), and only ever append events."""
from __future__ import annotations

from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.trading.service import _import_vati

EventKind, make_event, Ledger = _import_vati()   # resolves <repo>/trading without a pytest path entry

HDR = {"x-van-internal-token": "test-internal-token"}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "gw.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
    monkeypatch.setenv("VAN_VATI_LEDGER_PATH", str(tmp_path / "vati.sqlite"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def seed_ledger(path) -> Ledger:
    led = Ledger(path)
    led.append(make_event(EventKind.SESSION, "vati-runner", {"startup": True}, event_time_ms=1_000, received_time_ms=1_000, correlation_id="s1"))
    led.append(make_event(EventKind.OWNER_TICKET, "vati-router", {"ticket": "ZSE-T-1", "symbol": "DELTA", "qty": "1200"}, event_time_ms=2_000, received_time_ms=2_000, correlation_id="intent-1"))
    led.append(make_event(EventKind.KILL_SWITCH, "vati-runner", {"trigger": "STALE_DATA"}, event_time_ms=3_000, received_time_ms=3_000, correlation_id="s1"))
    led.append(make_event(EventKind.KILL_SWITCH, "vati-runner", {"trigger": "STALE_DATA", "cleared": True, "sig": "owner:1"}, event_time_ms=4_000, received_time_ms=4_000, correlation_id="s1"))
    return led


@pytest.fixture
async def client(tmp_path):
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac, app


@pytest.mark.asyncio
async def test_status_without_ledger_is_degraded_not_fatal(client):
    ac, app = client
    r = await ac.get("/v1/trading/status")
    assert r.status_code == 200 and r.json()["ledger_available"] is False and "TRADING_LEDGER_UNAVAILABLE" in r.json()["degraded"]
    assert (await ac.get("/v1/trading/tickets")).json() == {"tickets": []}
    r = await ac.post("/v1/trading/halt", json={"owner_signature_ref": "owner:sig", "reason": "x"}, headers=HDR)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_status_and_tickets_read_from_chained_ledger(client, tmp_path):
    ac, app = client
    seed_ledger(tmp_path / "vati.sqlite").close()
    st = (await ac.get("/v1/trading/status")).json()
    assert st["ledger_available"] and st["chain_ok"] and st["events"] == 4 and st["counts"]["OWNER_TICKET"] == 1 and st["open_tickets"] == 1
    assert st["kill_switch_active"] is False and st["degraded"] == []           # STALE_DATA was cleared by the owner
    tk = (await ac.get("/v1/trading/tickets")).json()["tickets"]
    assert tk == [{"ticket": "ZSE-T-1", "status": "OPEN", "symbol": "DELTA", "qty": "1200", "issued_ms": 2_000, "trade_intent_id": "intent-1", "ticket_hash": tk[0]["ticket_hash"]}]


@pytest.mark.asyncio
async def test_halt_requires_internal_token_and_owner_signature_and_appends_event(client, tmp_path):
    ac, app = client
    seed_ledger(tmp_path / "vati.sqlite").close()
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": "owner:sig"})).status_code == 403          # no internal token
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": ""}, headers=HDR)).status_code == 422       # empty signature (schema)
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": "   "}, headers=HDR)).status_code == 403    # blank signature (A4)
    r = await ac.post("/v1/trading/halt", json={"owner_signature_ref": "owner:sig-7", "reason": "news shock"}, headers=HDR)
    assert r.status_code == 200 and r.json()["trigger"] == "OWNER_HALT"
    led = Ledger(tmp_path / "vati.sqlite")
    ok, n = led.verify_chain()
    assert ok and n == 5 and led.head() == r.json()["chain_hash"]
    last = list(led.iter(EventKind.KILL_SWITCH))[-1]
    assert last.payload == {"trigger": "OWNER_HALT", "sig": "owner:sig-7", "reason": "news shock", "channel": "gateway"} and last.producer == "van-gateway"
    st = (await ac.get("/v1/trading/status")).json()
    assert st["kill_switch_active"] is True and st["kill_switch_triggers"] == ["OWNER_HALT"]
    rows = await app.state.store.fetchall("SELECT result, capability, approval, evidence_pointer FROM audit ORDER BY created_at_unix DESC LIMIT 1")
    assert tuple(rows[0]) == ("owner_halt_recorded", "trading.owner_halt", "owner:sig-7", r.json()["event_hash"])


@pytest.mark.asyncio
async def test_ticket_confirmation_is_once_bounded_and_owner_signed(client, tmp_path):
    ac, app = client
    seed_ledger(tmp_path / "vati.sqlite").close()
    body = {"owner_signature_ref": "owner:sig", "fill_price": "25.10", "filled_qty": "1200", "contract_note_ref": "CN-2026-09-16-001"}
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body)).status_code == 403
    assert (await ac.post("/v1/trading/tickets/ZSE-T-9/confirm", json=body, headers=HDR)).status_code == 404
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json={**body, "filled_qty": "1300"}, headers=HDR)).status_code == 422   # more than the ticket
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json={**body, "fill_price": "abc"}, headers=HDR)).status_code == 422
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json={**body, "fill_price": "-1"}, headers=HDR)).status_code == 422
    r = await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json={**body, "filled_qty": "1100"}, headers=HDR)
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body, headers=HDR)).status_code == 409           # once only
    tk = (await ac.get("/v1/trading/tickets?status=CONFIRMED")).json()["tickets"]
    assert len(tk) == 1 and tk[0]["filled_qty"] == "1100" and tk[0]["contract_note_ref"] == "CN-2026-09-16-001" and tk[0]["trade_intent_id"] == "intent-1"
    assert (await ac.get("/v1/trading/tickets?status=OPEN")).json()["tickets"] == []
    led = Ledger(tmp_path / "vati.sqlite")
    assert led.verify_chain() == (True, 5) and list(led.iter(correlation_id="intent-1"))[-1].payload["action"] == "CONFIRMED"


def test_service_never_exposes_an_order_path():
    """The gateway trading surface has no method that could create, size, modify or cancel an order."""
    from van_gateway.trading import TradingService
    names = {n for n in dir(TradingService) if not n.startswith("_")}
    assert names == {"available", "status", "tickets", "halt", "confirm_ticket", "producer"}
    for banned in ("order", "submit", "size", "cancel", "modify", "credential", "token"):
        assert not any(banned in n.lower() for n in names), banned
