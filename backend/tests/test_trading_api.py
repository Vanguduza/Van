"""Gateway trading surface (Rev 4 Part K): status/tickets are read from the
VATI ledger; halt and ticket confirmation need the internal control token AND
an owner signature reference (A4), and only ever append events."""
from __future__ import annotations

import json
from decimal import Decimal

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
import sys as _sys, pathlib as _pl
_sys.path[:0] = [str(_pl.Path(__file__).resolve().parents[2] / "trading" / "tests"), str(_pl.Path(__file__).resolve().parents[2] / "trading")]
from van_gateway.trading.service import _import_vati

EventKind, make_event, Ledger = _import_vati()   # resolves <repo>/trading without a pytest path entry

HDR = {"x-van-internal-token": "test-internal-token"}

#: P0-TRADE-001 fixtures. The trading suite holds the owner's key because trading writes
#: now need a signature that is checked; before this, every one of them accepted "owner:sig".
import sys as _sys

_sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "trading" / "tests"))
from conftest_owner_authority import OwnerAuthorityHarness  # noqa: E402

OWNER = OwnerAuthorityHarness()


def _halt_token():
    return OWNER.token(act="owner-halt", subject="van-trading-core")


#: P1-SEC-004. Account and credential changes now need a CryptoObject-bound A4 proof, so
#: the paired test device has a real keystore key rather than the string "test".
from cryptography.hazmat.primitives import hashes as _hashes, serialization as _ser  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec as _ec  # noqa: E402

DEVICE_KEY = _ec.generate_private_key(_ec.SECP256R1())
DEVICE_PEM = DEVICE_KEY.public_key().public_bytes(
    _ser.Encoding.PEM, _ser.PublicFormat.SubjectPublicKeyInfo
).decode("utf-8")


def _approval_proof(challenge_body: dict) -> dict:
    """What the device produces inside onAuthenticationSucceeded, not before it."""
    import base64

    signature = DEVICE_KEY.sign(
        challenge_body["approval_challenge"].encode("utf-8"),
        _ec.ECDSA(_hashes.SHA256()),
    )
    return {
        "challenge_id": challenge_body["approval_challenge_id"],
        "signature_b64": base64.b64encode(signature).decode("ascii"),
        "algorithm": "ECDSA_P256_SHA256",
    }




@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "gw.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
    # P0-SEC-001 — device enrolment is its own credential now.
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "test-internal-token")
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef0123456789")
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
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
            ticket = await ac.post("/v1/devices/pairing-ticket", json={"label": "test", "ttl_seconds": 600}, headers=HDR)
            assert ticket.status_code == 200, ticket.text
            paired = await ac.post("/v1/devices/pair", json={"pairing_token": ticket.json()["pairing_token"], "device_id": "test-device", "device_secret": "test-device-secret", "public_key_pem": DEVICE_PEM, "label": "test"})
            assert paired.status_code == 200, paired.text
            ac.headers.update({"X-Van-Ingress-Token": paired.json()["ingress_token"], "X-Van-Device-Token": paired.json()["device_access_token"]})
            # P0-TRADE-001 — trading writes now need a real owner signature, so the
            # suite holds the owner's key and signs for real. Passing "owner:sig" is the
            # defect these tests exist to keep closed.
            app.state.trading.owner_authority = OWNER.verifier
            yield ac, app


@pytest.mark.asyncio
async def test_status_without_ledger_is_degraded_not_fatal(client):
    ac, app = client
    r = await ac.get("/v1/trading/status")
    assert r.status_code == 200 and r.json()["ledger_available"] is False and "TRADING_LEDGER_UNAVAILABLE" in r.json()["degraded"]
    assert (await ac.get("/v1/trading/tickets")).json() == {"tickets": []}
    r = await ac.post(
        "/v1/trading/halt",
        json={"owner_signature_ref": _halt_token(), "reason": "x"},
        headers=HDR,
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_status_and_tickets_read_from_chained_ledger(client, tmp_path):
    ac, app = client
    seed_ledger(tmp_path / "vati.sqlite").close()
    st = (await ac.get("/v1/trading/status")).json()
    assert st["ledger_available"] and st["chain_ok"] and st["events"] == 4 and st["counts"]["OWNER_TICKET"] == 1 and st["open_tickets"] == 1
    assert st["kill_switch_active"] is False                                    # STALE_DATA was cleared by the owner
    # P0-TRADE-004 — this fixture's newest event is at 4_000ms, which is 1970. The gateway
    # now says so instead of presenting it as current, which is the whole finding: nothing
    # here can tell by looking whether it is reading the live ledger or a leftover copy.
    assert st["ledger_stale"] is True
    assert st["degraded"] == ["TRADING_LEDGER_UNAVAILABLE"]
    assert "old" in st["ledger_stale_reason"]
    tk = (await ac.get("/v1/trading/tickets")).json()["tickets"]
    assert tk == [{
        "ticket": "ZSE-T-1",
        "status": "OPEN",
        "symbol": "DELTA",
        "qty": "1200",
        "side": "BUY",
        "limit_price": None,
        "software_stop": None,
        "position_id": None,
        "exit_reason": None,
        "issued_ms": 2_000,
        "trade_intent_id": "intent-1",
        "ticket_hash": tk[0]["ticket_hash"],
    }]


@pytest.mark.asyncio
async def test_a_current_ledger_is_not_reported_stale(client, tmp_path):
    """The threshold must not condemn a ledger a live session is actually writing."""
    import time as _t

    from vati.core import EventKind, Ledger, make_event

    now = int(_t.time() * 1000)
    led = Ledger(tmp_path / "vati.sqlite")
    led.append(make_event(EventKind.SESSION, "vati-runner", {"startup": True},
                          event_time_ms=now, received_time_ms=now, correlation_id="s1"))
    led.close()

    st = (await ac_of(client).get("/v1/trading/status")).json()
    assert st["ledger_available"] and st["ledger_stale"] is False
    assert st["ledger_age_ms"] < st["ledger_staleness_threshold_ms"]
    assert st["degraded"] == []


def ac_of(client):
    return client[0]


@pytest.mark.asyncio
async def test_halt_requires_internal_token_and_owner_signature_and_appends_event(client, tmp_path):
    ac, app = client
    seed_ledger(tmp_path / "vati.sqlite").close()
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": _halt_token()})).status_code == 403   # no internal token
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": ""}, headers=HDR)).status_code == 422       # empty signature (schema)
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": "   "}, headers=HDR)).status_code == 403    # blank signature (A4)
    # P0-TRADE-001 — this exact string used to halt live trading.
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": "owner:sig-7"}, headers=HDR)).status_code == 403
    # ...and so did anything, including authority granted for a different act.
    wrong_act = OWNER.token(act="ticket-confirm", subject="van-trading-core")
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": wrong_act}, headers=HDR)).status_code == 403
    halt_token = _halt_token()
    r = await ac.post("/v1/trading/halt", json={"owner_signature_ref": halt_token, "reason": "news shock"}, headers=HDR)
    assert r.status_code == 200 and r.json()["trigger"] == "OWNER_HALT"
    led = Ledger(tmp_path / "vati.sqlite")
    ok, n = led.verify_chain()
    assert ok and n == 5 and led.head() == r.json()["chain_hash"]
    last = list(led.iter(EventKind.KILL_SWITCH))[-1]
    # The ledger records the verified authority's reference, not the raw token.
    assert last.payload["trigger"] == "OWNER_HALT" and last.payload["reason"] == "news shock"
    assert last.payload["channel"] == "gateway" and last.producer == "van-gateway"
    assert last.payload["sig"].startswith("owner-authority:")
    st = (await ac.get("/v1/trading/status")).json()
    assert st["kill_switch_active"] is True and st["kill_switch_triggers"] == ["OWNER_HALT"]
    rows = await app.state.store.fetchall("SELECT result, capability, approval, evidence_pointer FROM audit ORDER BY created_at_unix DESC LIMIT 1")
    assert rows[0]["result"] == "owner_halt_recorded"
    assert rows[0]["capability"] == "trading.owner_halt"
    assert str(rows[0]["approval"]).startswith("owner-authority:")
    assert rows[0]["evidence_pointer"] == r.json()["event_hash"]

    # Single use: the token is in the ledger now, in the clear.
    assert (await ac.post("/v1/trading/halt", json={"owner_signature_ref": halt_token}, headers=HDR)).status_code == 403


@pytest.mark.asyncio
async def test_ticket_confirmation_is_once_bounded_and_owner_signed(client, tmp_path):
    ac, app = client
    seed_ledger(tmp_path / "vati.sqlite").close()
    def body(ticket="ZSE-T-1", **over):
        base = {
            "owner_signature_ref": OWNER.token(act="ticket-confirm", subject=ticket),
            "fill_price": "25.10", "filled_qty": "1200",
            "contract_note_ref": "CN-2026-09-16-001",
        }
        base.update(over)
        return base

    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body())).status_code == 403
    # P0-TRADE-001 — "owner:sig" used to confirm a broker fill.
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(owner_signature_ref="owner:sig"), headers=HDR)).status_code == 403
    # Authority to confirm one ticket is not authority to confirm another.
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(ticket="ZSE-T-9"), headers=HDR)).status_code == 403
    assert (await ac.post("/v1/trading/tickets/ZSE-T-9/confirm", json=body("ZSE-T-9"), headers=HDR)).status_code == 404
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(filled_qty="1300"), headers=HDR)).status_code == 422   # more than the ticket
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(fill_price="abc"), headers=HDR)).status_code == 422
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(fill_price="-1"), headers=HDR)).status_code == 422
    r = await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(filled_qty="1100"), headers=HDR)
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"
    assert (await ac.post("/v1/trading/tickets/ZSE-T-1/confirm", json=body(), headers=HDR)).status_code == 409           # once only
    tk = (await ac.get("/v1/trading/tickets?status=CONFIRMED")).json()["tickets"]
    assert len(tk) == 1 and tk[0]["filled_qty"] == "1100" and tk[0]["contract_note_ref"] == "CN-2026-09-16-001" and tk[0]["trade_intent_id"] == "intent-1"
    assert (await ac.get("/v1/trading/tickets?status=OPEN")).json()["tickets"] == []
    led = Ledger(tmp_path / "vati.sqlite")
    assert led.verify_chain() == (True, 5) and list(led.iter(correlation_id="intent-1"))[-1].payload["action"] == "CONFIRMED"


def test_service_never_exposes_an_order_path():
    """The gateway trading surface has no method that could create, size, modify or cancel an order."""
    from van_gateway.trading import TradingService
    names = {n for n in dir(TradingService) if not n.startswith("_")}
    # GAP-F-003 added five read models (positions, events, potential_trades,
    # history, assessment). Each is a projection of the ledger; none of them is
    # a capability, which the banned-substring check below still proves.
    assert names == {"available", "status", "tickets", "halt", "confirm_ticket", "trade_book", "portfolio", "accounts", "market_state", "risk", "cognition", "trade_detail", "bars", "producer", "accounts_registry", "lake_root", "reporting_currency", "owner_authority",
                     "positions", "events", "potential_trades", "history", "assessment"}
    for banned in ("order", "submit", "size", "cancel", "modify", "credential", "token"):
        assert not any(banned in n.lower() for n in names), banned
    # P0-TRADE-001 — the one field added since is the verifier for owner-signed acts, and
    # it is a checker, not a capability: it cannot cause an order to exist.
    assert "owner_authority" in names


@pytest.mark.asyncio
async def test_trade_book_views_without_and_with_ledger(client, tmp_path):
    ac, app = client
    empty = (await ac.get("/v1/trading/trades?view=potential")).json()
    assert empty["ledger_available"] is False and empty["potential"] == [] and empty["counts"] == {"potential": 0}
    assert (await ac.get("/v1/trading/trades?view=bogus")).status_code == 422
    led = seed_ledger(tmp_path / "vati.sqlite")
    intent = {"trade_intent_id": "intent-1", "symbol": "DELTA", "venue": "zse", "direction": "LONG", "strategy_id": "ZSE-VALUE-ROTATION-01", "strategy_version": "1.0.0", "horizon": "POSITION",
              "entry": "25.00", "stop": "23.50", "expected_gross_move_pct": "0.12", "regime_multiplier": "0.8", "volatility_multiplier": "1", "liquidity_multiplier": "0.9", "event_risk_multiplier": "1", "confidence_multiplier": "0.9"}
    dec = {"decision": "REDUCED", "reason_code": "", "requested_risk_pct": "0.01", "approved_risk_pct": "0.008", "approved_size": "1200", "decision_hash": "d" * 64}
    led.append(make_event(EventKind.RISK_DECISION, "vati-cycle", {"inputs": {"intent": intent, "snapshot": {}, "mandate": {}}, "decision": dec}, event_time_ms=1_500, received_time_ms=1_500, correlation_id="intent-1"))
    led.append(make_event(EventKind.EXECUTION_RECEIPT, "vati-router", {"status": "ACCEPTED", "average_fill": None, "filled_qty": "0", "protective_stop_confirmed": True, "protective_stop_price": "23.50", "execution_channel": "OWNER_TICKET"},
                          event_time_ms=1_900, received_time_ms=1_900, correlation_id="intent-1"))
    led.close()
    book = (await ac.get("/v1/trading/trades?view=all")).json()
    assert book["ledger_available"] and book["counts"] == {"past": 0, "current": 1, "potential": 0}
    cur = book["current"][0]
    assert cur["state"] == "AWAITING_OWNER_TICKET" and cur["owner_ticket"] == {"ticket": "ZSE-T-1", "status": "OPEN"} and cur["confidence"] == {"score": "0.65", "band": "MEDIUM", "basis": book["confidence_basis"]}
    assert "never a size" in book["confidence_basis"] and cur["approved_size"] == "1200"


@pytest.mark.asyncio
async def test_command_center_read_models_without_and_with_data(client, tmp_path, monkeypatch):
    ac, app = client
    pf = (await ac.get("/v1/trading/portfolio")).json()
    assert pf["ledger_available"] is False and pf["accounts"] == [] and pf["open_positions"] == []
    assert (await ac.get("/v1/trading/accounts")).json() == {"accounts": [], "registry": "data/vati_accounts.json"}
    assert (await ac.get("/v1/trading/market-state")).json()["symbols"] == [] and (await ac.get("/v1/trading/risk")).json()["positions"] == []
    assert (await ac.get("/v1/trading/trades/nope")).status_code == 404
    b = (await ac.get("/v1/trading/bars?symbol=EURUSD&timeframe=H1")).json()
    assert b["lake_available"] is False and b["data_state"] == {"state": "UNAVAILABLE"} and b["bars"] == []
    assert (await ac.get("/v1/trading/bars?symbol=EURUSD&timeframe=W1")).status_code == 422
    # with a registry, a lake and a ledger from a real paper session
    reg_path = tmp_path / "accounts.json"; lake_root = tmp_path / "lake"
    from vati.accounts import Account, AccountRegistry
    AccountRegistry(reg_path).add(Account(alias="paper_lab", broker="PAPER", mode="DEMO_TRADER", currency="USD", label="Paper Lab"))
    from test_backtest_runner_cli import synthetic_bars
    from vati.market_data.feeds import BarLake
    lake = BarLake(lake_root); bars = synthetic_bars(); lake.write(bars, symbol="EURUSD", timeframe="H1", source="t", provenance="SYNTHETIC")
    app.state.trading.accounts_registry = str(reg_path); app.state.trading.lake_root = str(lake_root)
    seed_ledger(tmp_path / "vati.sqlite").close()
    pf = (await ac.get("/v1/trading/portfolio")).json()
    assert pf["ledger_available"] and pf["accounts"][0]["alias"] == "paper_lab" and pf["accounts"][0]["safety_identity"] == "PAPER" and pf["accounts"][0]["connection_state"] == "NEVER_SYNCED"
    acc = (await ac.get("/v1/trading/accounts")).json()["accounts"]
    assert acc[0]["label"] == "Paper Lab" and "credential" not in json.dumps(acc).lower().replace("credential_ref", "")
    b = (await ac.get("/v1/trading/bars?symbol=eurusd&timeframe=H1&limit=20")).json()
    assert b["count"] == 20 and b["provenance"] == ["SYNTHETIC"] and b["lake_available"] and set(b["bars"][0]) == {"t", "o", "h", "l", "c", "v"}


def _sign_action(secret: str, device_id: str, issued: int, action: str, args: dict) -> str:
    import hashlib, hmac
    from van_gateway.trading.accounts import canonical_action
    return hmac.new(secret.encode(), canonical_action(device_id, issued, action, args).encode(), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_strategy_promotion_requires_exact_device_signature_and_a4_proof(client):
    import time as _time
    from van_gateway.trading.strategies import canonical_strategy_promotion

    ac, app = client
    now = int(_time.time())
    certificate = {
        "certificate_id": "svc-test",
        "strategy_id": "FX-TREND-PULLBACK-01",
        "validation_hash": "v" * 64,
    }
    authority_placeholder = "owner-authority-input"
    evidence = ["artifact:test-validation"]

    class FakePromotions:
        def __init__(self):
            self.calls = []
            self.enrollments = []
        def candidates(self):
            return {
                "candidates": [{
                    "strategy_id": "FX-TREND-PULLBACK-01",
                    "current_state": "DEMO",
                    "target_state": "SHADOW",
                    "validation_hash": "v" * 64,
                }],
                "authority": "OWNER_DECISION_REQUIRED",
            }
        def ensure_owner_authority(self, **kw):
            self.enrollments.append(kw)
            return {"enrolled": True, "key_id": "device-test"}
        def promote(self, **kw):
            self.calls.append(kw)
            return {
                "promoted": True, "strategy_id": kw["strategy_id"],
                "from": "DEMO", "to": kw["target_state"],
                "capsule_hash": "c" * 64,
                "validation_hash": kw["certificate"]["validation_hash"],
                "owner_authority_ref": "owner-authority:test-ref",
                "event_hash": "e" * 64, "registry_projection": "WRITTEN",
            }

    fake = FakePromotions()
    app.state.strategy_promotions = fake

    candidates = await ac.get("/v1/trading/strategies/promotion-candidates")
    assert candidates.status_code == 200, candidates.text
    assert candidates.json()["candidates"][0]["target_state"] == "SHADOW"

    paired_key = await app.state.store.fetchone(
        "SELECT public_key_pem FROM devices WHERE device_id = ?",
        ("test-device",),
    )
    assert paired_key is not None and "BEGIN PUBLIC KEY" in paired_key["public_key_pem"]

    def body(*, target="SHADOW", proof=None):
        canonical = canonical_strategy_promotion(
            "test-device", now,
            strategy_id="FX-TREND-PULLBACK-01", target_state=target,
            owner_signature_ref=authority_placeholder, certificate=certificate,
            evidence_refs=evidence,
        )
        out = {
            "device_id": "test-device", "issued_at_unix": now,
            "signature": app.state.auth.sign("test-device", canonical),
            "strategy_id": "FX-TREND-PULLBACK-01", "target_state": target,
            "owner_signature_ref": authority_placeholder,
            "certificate": certificate, "evidence_refs": evidence,
        }
        if proof is not None:
            out["approval_proof"] = proof
        return out

    no_proof = await ac.post("/v1/trading/strategies/promote", json=body())
    assert no_proof.status_code == 403 and fake.calls == [] and fake.enrollments == []

    challenge = await ac.post(
        "/v1/trading/strategies/promotion-challenge", json=body())
    assert challenge.status_code == 200, challenge.text
    proof = _approval_proof(challenge.json())
    tampered = await ac.post(
        "/v1/trading/strategies/promote",
        json=body(target="CERTIFIED_LIVE", proof=proof),
    )
    assert tampered.status_code == 403 and fake.calls == [] and fake.enrollments == []

    challenge2 = await ac.post(
        "/v1/trading/strategies/promotion-challenge", json=body())
    proof2 = _approval_proof(challenge2.json())
    promoted = await ac.post(
        "/v1/trading/strategies/promote", json=body(proof=proof2))
    assert promoted.status_code == 200, promoted.text
    assert len(fake.calls) == 1
    assert len(fake.enrollments) == 1
    assert fake.enrollments[0]["device_id"] == "test-device"
    assert fake.enrollments[0]["public_key_pem"] == paired_key["public_key_pem"]
    assert fake.calls[0]["target_state"] == "SHADOW"
    assert fake.calls[0]["certificate"]["validation_hash"] == "v" * 64

    replay = await ac.post(
        "/v1/trading/strategies/promote", json=body(proof=proof2))
    assert replay.status_code == 403 and len(fake.calls) == 1 and len(fake.enrollments) == 1

@pytest.mark.asyncio
async def test_account_onboarding_is_device_signed_and_forwards_without_storing_secrets(client, tmp_path, monkeypatch):
    import time as _time
    ac, app = client
    # Use the schema-4 paired test device and point local trading control at temp storage.
    from van_gateway.trading.accounts import LocalAccountControl
    from test_commander_accounts import FakeDeriv
    deriv = FakeDeriv()
    app.state.onboarding.control = LocalAccountControl(str(tmp_path / "accounts.json"), str(tmp_path / "secrets"), deriv_connector=deriv.connector)
    app.state.trading.accounts_registry = str(tmp_path / "accounts.json")
    now = int(_time.time())
    from van_gateway.trading.accounts import requires_owner_approval

    async def act(action, args, device="test-device", secret="test-device-secret", issued=None,
                  approve=True):
        """Do what the device does: sign, and for a mutating action, get a challenge and
        sign it under the biometric before sending (P1-SEC-004)."""
        issued = issued or now
        body = {"device_id": device, "issued_at_unix": issued,
                "signature": _sign_action(secret, device, issued, action, args),
                "action": action, "args": args}
        if approve and requires_owner_approval(action) and secret == "test-device-secret":
            challenge = await ac.post("/v1/trading/accounts/challenge", json=body)
            if challenge.status_code == 200:
                body["approval_proof"] = _approval_proof(challenge.json())
        return await ac.post("/v1/trading/accounts/action", json=body)
    assert (await act("account_upsert", {"alias": "paper_lab", "broker": "PAPER"}, secret="wrong")).status_code == 403
    assert (await act("account_upsert", {"alias": "paper_lab", "broker": "PAPER"}, issued=now - 3600)).status_code == 403
    assert (await act("shell", {})).status_code == 404
    # P1-SEC-004 — a correctly device-signed credential change with no biometric proof is
    # refused. This is exactly what the weak prompt used to allow through.
    unapproved = await act("account_upsert", {"alias": "paper_lab", "broker": "PAPER"}, approve=False)
    assert unapproved.status_code == 403 and "approval proof" in unapproved.json()["detail"]
    r = await act("account_upsert", {"alias": "paper_lab", "broker": "PAPER", "label": "Paper Lab"})
    assert r.status_code == 200 and r.json()["account"]["safety_identity"] == "PAPER"
    # tampering with args after signing is refused (signature binds the exact bytes)
    body = {"device_id": "test-device", "issued_at_unix": now, "signature": _sign_action("test-device-secret", "test-device", now, "account_upsert", {"alias": "x_one", "broker": "PAPER"}), "action": "account_upsert", "args": {"alias": "x_two", "broker": "PAPER"}}
    assert (await ac.post("/v1/trading/accounts/action", json=body)).status_code == 403
    # Deriv demo creation end to end through the gateway
    assert (await act("deriv_verify_email", {"email": "owner@example.com"})).json()["sent"] is True
    r = await act("deriv_create_demo", {"alias": "deriv_demo", "verification_code": "ABC123", "client_password": "Pa55word!", "residence": "zw"})
    assert r.status_code == 200 and r.json()["client_id"] == "VRTC900" and "Pa55word" not in r.text and "virtualtoken" not in r.text
    assert "a1-virtualtoken" in (tmp_path / "secrets" / "deriv_demo.env").read_text()
    accts = (await ac.get("/v1/trading/accounts")).json()["accounts"]
    assert {a["alias"] for a in accts} == {"deriv_demo", "paper_lab"} and "virtualtoken" not in json.dumps(accts)
    # audit never carries the password or token
    rows = await app.state.store.fetchall("SELECT before_json, after_json, capability FROM audit WHERE capability LIKE 'trading.account.%'")
    blob = json.dumps([tuple(r) for r in rows])
    assert "Pa55word" not in blob and "virtualtoken" not in blob and "trading.account.deriv_create_demo" in blob and "[REDACTED]" in blob
    # OAuth: start → callback → pending → link, tokens only ever in the encrypted pending row and the VM secrets
    st = (await act("oauth_start", {"broker": "deriv"})).json()
    assert st["url"].startswith("https://oauth.deriv.com/oauth2/authorize?app_id=1089") and st["callback"].endswith("/v1/trading/oauth/deriv/callback")
    assert (await act("oauth_pending", {"state": st["state"]})).json() == {"ready": False}
    cb = await ac.get(f"/v1/trading/oauth/deriv/callback?state={st['state']}&acct1=VRTC900&token1=a1-linked&cur1=USD&acct2=CR777&token2=a1-real&cur2=USD")
    assert cb.status_code == 200 and "linked" in cb.text
    pend = (await act("oauth_pending", {"state": st["state"]})).json()
    assert pend["ready"] and pend["accounts"] == [{"loginid": "VRTC900", "currency": "USD", "demo": True}, {"loginid": "CR777", "currency": "USD", "demo": False}] and "a1-" not in json.dumps(pend)
    row = await app.state.store.fetchone("SELECT payload_enc FROM trading_oauth_pending WHERE state = ?", (st["state"],))
    assert "a1-linked" not in row["payload_enc"]                       # encrypted at rest
    r = await act("deriv_oauth_link", {"state": st["state"], "loginid": "CR777", "alias": "deriv_real"})
    assert r.status_code == 200 and r.json()["account"]["safety_identity"] == "READ ONLY"
    assert "DERIV_API_TOKEN=a1-real" in (tmp_path / "secrets" / "deriv_real.env").read_text()
    assert (await act("oauth_pending", {"state": st["state"]})).json()["expired"] is True   # consumed
    assert (await ac.get("/v1/trading/oauth/deriv/callback?state=nope&acct1=X&token1=Y")).status_code == 400
    # cTrader start needs the owner's application credentials and builds the authorize URL with our callback
    ct = (await act("oauth_start", {"broker": "ctrader", "client_id": "cid", "client_secret": "csec"})).json()
    assert "openapi.ctrader.com/apps/auth?client_id=cid" in ct["url"] and "state=" in ct["url"]
    assert (await act("oauth_start", {"broker": "ctrader"})).status_code == 422
    # MT5-EA key issue returns the key once to the app, stores it on the VM
    k = (await act("mt5_ea_issue_key", {"alias": "mt5_ea", "login": "1", "server": "Demo"})).json()
    assert len(k["signing_key"]) == 64 and (await act("account_remove", {"alias": "mt5_ea"})).json()["removed"]
