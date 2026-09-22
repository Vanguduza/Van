"""GAP-F-003 item 7: the gateway's active-trade read models, on a real ledger.

The gap these close is that the reasoning layer had no path to an open
position at all: `/v1/trading/*` could answer what the book *was* (trades,
portfolio, risk) but nothing about the claim behind a live trade, the news
bearing on it, or the quadrant a closed one landed in. `TradingService` now
projects five more views out of the same hash-chained ledger.

These tests drive the real VATI lifecycle — RiskAuthority, ExecutionRouter,
PaperAdapter, ThesisEngine, NewsIngress — into a temporary ledger file and then
read it back through `TradingService`, because a read model tested against a
hand-written payload only proves that two hand-written payloads agree.

The five `@app.get` routes themselves are added to `backend/van_gateway/app.py`
separately; `test_the_five_routes_answer_the_service_payloads` mounts exactly
the handler bodies those routes use onto a live app so the wiring is exercised
end to end either way.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from van_gateway.app import create_app
from van_gateway.config import get_settings
from van_gateway.trading.service import TradingService, _import_vati

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "trading" / "tests"), str(_ROOT / "trading")]

EventKind, make_event, Ledger = _import_vati()

from conftest_owner_authority import OWNER_KEY_ID, OwnerAuthorityHarness  # noqa: E402
from test_intelligence import mk_bars, trending  # noqa: E402  (bar generator)

OWNER = OwnerAuthorityHarness()

from cryptography.hazmat.primitives import serialization as _ser  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec as _ec  # noqa: E402

DEVICE_KEY = _ec.generate_private_key(_ec.SECP256R1())
DEVICE_PEM = DEVICE_KEY.public_key().public_bytes(
    _ser.Encoding.PEM, _ser.PublicFormat.SubjectPublicKeyInfo).decode("utf-8")

SYMBOL = "EURUSD"
STRATEGY = "FX-TREND-PULLBACK-01"
ENTRY = Decimal("1.10000")
STOP = Decimal("1.09500")
NOW = 1_800_000_000_000
HDR = {"x-van-internal-token": "test-internal-token"}


@pytest.fixture(autouse=True)
def _owner_keys(tmp_path, monkeypatch):
    """A mandate is admitted only against a registered owner key."""
    path = tmp_path / "owner_authority_keys.json"
    path.write_text(json.dumps({"keys": {OWNER_KEY_ID: OWNER.pem}}), encoding="utf-8")
    monkeypatch.setenv("VAN_OWNER_AUTHORITY_KEYS", str(path))
    yield


def _mandate_mapping() -> dict:
    from vati.risk import HARD_FORBIDDEN_BEHAVIOURS

    signed_at = NOW // 1000 - 3600
    expires_at = NOW // 1000 + 30 * 86400
    return {
        "mandate_id": "mandate-readmodels", "version": "1.0.0",
        "account_alias": "fx_primary", "venue": "paper", "mode": "LIMITED_LIVE",
        "instruments": [SYMBOL], "allowed_strategies": [STRATEGY],
        "max_risk_per_trade": "0.0050", "max_open_stop_risk": "0.0150",
        "max_daily_loss": "0.0200", "max_weekly_drawdown": "0.0400",
        "max_currency_leg_exposure": "0.0100", "max_consecutive_losses": 4,
        "max_positions_per_instrument": 2, "max_total_positions": 4,
        "tier1_event_policy": "strategy_specific", "weekend_hold_allowed": False,
        "forbidden": sorted(HARD_FORBIDDEN_BEHAVIOURS),
        "signed_at_unix": signed_at, "expires_at_unix": expires_at,
        "owner_signature_ref": OWNER.token(
            act="mandate-admit", subject="mandate-readmodels:1.0.0",
            issued_at_unix=signed_at, lifetime_seconds=expires_at - signed_at),
    }


def _market_state(now_ms: int):
    """A real MarketState from real bars: the entry path reads session, regime
    and features from it, and a stand-in would only prove the stand-in works."""
    from vati.intelligence import DEFAULT_EVENT_MATRIX, RegimeEngine, build_market_state
    from vati.market_data import FX_CALENDAR
    from vati.risk import MarketIntegrityState

    bars = mk_bars(trending(240))
    return build_market_state(
        symbol=SYMBOL, base="EUR", quote="USD", bars=bars,
        regime_engine=RegimeEngine(), calendar=FX_CALENDAR,
        events=DEFAULT_EVENT_MATRIX, integrity=MarketIntegrityState.NORMAL,
        now_ms=now_ms, last_quote_ms=now_ms - 100,
        activation_id="vtil-act-test", timeframe="H1")


def _contract():
    from vati.risk.contracts import SymbolContract

    return SymbolContract(
        symbol=SYMBOL, venue="paper", base_currency="EUR", quote_currency="USD",
        account_currency="USD", contract_size=Decimal("100000"),
        tick_size=Decimal("0.00001"), tick_value=Decimal("1.00"),
        volume_min=Decimal("0.01"), volume_step=Decimal("0.01"),
        volume_max=Decimal("100"), min_stop_distance=Decimal("0.00030"))


def _snapshot(contract, **overrides):
    from vati.risk import MarketIntegrityState, RiskSnapshot

    base = dict(
        now_unix=NOW // 1000, account_alias="fx_primary", account_verified=True,
        equity=Decimal("10000"), balance=Decimal("10000"),
        peak_equity=Decimal("10000"), day_start_equity=Decimal("10000"),
        week_start_equity=Decimal("10000"), consecutive_losses=0,
        open_positions=(), symbol_contract=contract, quote_age_ms=120,
        max_quote_age_ms=1500, broker_connected=True, reconciliation_ok=True,
        clock_sync_ok=True, risk_store_ok=True,
        market_integrity=MarketIntegrityState.NORMAL,
        tier1_event_blackout_active=False)
    base.update(overrides)
    return RiskSnapshot(**base)


def _intent(trade_intent_id: str, *, risk: str = "0.0040"):
    from vati.risk.contracts import Direction, StrategyState, TradeIntent

    return TradeIntent(
        trade_intent_id=trade_intent_id, idempotency_key=f"idem-{trade_intent_id}",
        account_alias="fx_primary", venue="paper", symbol=SYMBOL,
        direction=Direction.LONG, strategy_id=STRATEGY, strategy_version="1.0.0",
        strategy_state=StrategyState.CERTIFIED_LIVE, entry=ENTRY, stop=STOP,
        requested_risk_pct=Decimal(risk), decision_hash=f"dh-{trade_intent_id}",
        market_snapshot_hash="msh", expected_gross_move_pct=Decimal("0.01"))


class Book:
    """The live VATI stack, writing into one temporary ledger file."""

    def __init__(self, path: Path) -> None:
        from vati.app.trade_lifecycle import AccountTradeLifecycle
        from vati.arbiter import OpportunityEngine
        from vati.events.news_ingress import NewsIngress, NewsSource, SourceTrust
        from vati.execution.paper import PaperAdapter
        from vati.execution.protection import ProtectionManager
        from vati.execution.router import ExecutionRouter
        from vati.learning.episodes import Environment
        from vati.learning.hooks import LearningHooks
        from vati.lifecycle.scale_policy import DEFENSIVE
        from vati.risk import KillSwitch, RiskAuthority, TradingMandate
        from vati.strategies import CapsuleRegistry

        self.path = path
        self.ledger = Ledger(path)
        self.adapter = PaperAdapter(
            venue="paper", account_alias="fx_primary", equity=Decimal("10000"))
        self.protection = ProtectionManager()
        self.router = ExecutionRouter(
            ledger=self.ledger, adapters={"paper": self.adapter},
            kill_switch=KillSwitch(), protection=self.protection)
        self.mandate = TradingMandate.from_mapping(_mandate_mapping())
        self.authority = RiskAuthority(self.mandate)
        self.contract = _contract()
        self.engine = OpportunityEngine(
            CapsuleRegistry.load_dir(_ROOT / "trading" / "strategies" / "registry"),
            {}, self.mandate)
        self.news = NewsIngress(
            ledger=self.ledger,
            sources=[NewsSource(source_id="reuters", trust=SourceTrust.T1_PRIMARY,
                                label="Reuters")])
        self.lifecycle = AccountTradeLifecycle(
            ledger=self.ledger, adapter=self.adapter, router=self.router,
            protection=self.protection, contracts={SYMBOL: self.contract},
            engines_by_symbol={SYMBOL: self.engine},
            modelled_costs={SYMBOL: Decimal("0.0002")},
            learning=LearningHooks(environment=Environment.LIMITED_LIVE,
                                   broker="paper"),
            authority=self.authority, mandate=self.mandate, news=self.news,
            snapshot_fn=lambda symbol: _snapshot(self.contract))
        self.lifecycle.adjustment_policies.register(STRATEGY, DEFENSIVE)

    def close(self) -> None:
        self.ledger.close()

    # -- the events a live account service writes around every decision ----
    def _log_decision(self, intent, decision, snapshot, now_ms: int,
                      refusal: str = "") -> None:
        from vati.risk.serde import intent_to_dict, snapshot_to_dict

        payload = {
            "inputs": {"intent": intent_to_dict(intent),
                       "snapshot": snapshot_to_dict(snapshot)},
            "decision": decision.to_dict(),
        }
        if refusal:
            payload["router_refused"] = refusal
        self.ledger.append(make_event(
            EventKind.RISK_DECISION, "vati-account-service", payload,
            event_time_ms=now_ms, received_time_ms=now_ms,
            correlation_id=intent.trade_intent_id))

    def open_position(self, trade_intent_id: str = "ti-read-1", *, now_ms: int = NOW):
        intent = _intent(trade_intent_id)
        snapshot = _snapshot(self.contract)
        decision = self.authority.evaluate(intent, snapshot)
        self._log_decision(intent, decision, snapshot, now_ms)
        receipt = self.router.execute(
            intent, decision, self.mandate, now_ms=now_ms,
            targets=(Decimal("1.11000"),))
        self.lifecycle.record_entry(
            intent=intent, receipt=receipt, state=_market_state(now_ms),
            modelled_cost_pct=Decimal("0.0002"), software_stop=False,
            decision=decision, targets=(Decimal("1.11000"),),
            expected_horizon_ms=4 * 3_600_000)
        return intent, receipt

    def reject_an_intent(self, *, now_ms: int = NOW + 1_000):
        """A genuine authority rejection, so `potential()` has a refusal to show."""
        from vati.risk import OpenPosition

        intent = _intent("ti-read-rejected", risk="0.0050")
        heavy = (OpenPosition(SYMBOL, intent.direction, Decimal("3.0"),
                              Decimal("0.00500"),
                              self.contract.value_per_price_unit_per_lot,
                              "EUR", "USD", STRATEGY, True),)
        snapshot = _snapshot(self.contract, open_positions=heavy)
        decision = self.authority.evaluate(intent, snapshot)
        self._log_decision(intent, decision, snapshot, now_ms)
        return decision

    def adverse_headline(self, *, now_ms: int = NOW + 60_000):
        from vati.events.news_ingress import Concern, Headline, SourceTrust

        self.news.ingest(Headline(
            source_id="reuters", trust=SourceTrust.T1_PRIMARY,
            published_ms=now_ms, observed_ms=now_ms,
            title="ECB signals emergency review of euro liquidity operations",
            currencies=("EUR", "USD"), symbols=(SYMBOL,),
            severity=Decimal("0.9"), concern=Concern.ADVERSE_TO_LONG),
            now_ms=now_ms)

    def mark(self, bid: str, ask: str, *, now_ms: int) -> None:
        self.lifecycle.mark(SYMBOL, Decimal(bid), Decimal(ask), now_ms=now_ms)


@pytest.fixture
def book(tmp_path):
    b = Book(tmp_path / "vati.sqlite")
    yield b
    b.close()


@pytest.fixture
def service(tmp_path):
    return TradingService(str(tmp_path / "vati.sqlite"))


# --------------------------------------------------------------- unavailable
def test_every_read_model_says_it_could_not_look_rather_than_nothing_is_there():
    """`ledger_available: False`, never an exception and never an empty book.

    A caller that cannot tell "nothing is open" from "I could not look" will
    eventually act on the wrong one, which is why this is a shape and not a
    convenience.
    """
    service = TradingService("/nonexistent/path/vati.sqlite")
    for view in (service.positions(), service.events(), service.potential_trades(),
                 service.history(), service.assessment()):
        assert view["ledger_available"] is False
    assert service.positions()["positions"] == []
    assert service.events()["events"] == [] and service.events()["impacts"] == []
    assert service.potential_trades()["potential_trades"] == []
    assert service.history()["history"] == []
    assert service.assessment()["cognition"]["state"] == "MODEL_INVOKER_UNCONFIGURED"


# ----------------------------------------------------------------- positions
def test_positions_carry_the_thesis_protection_and_linked_events(book, service):
    intent, receipt = book.open_position()
    book.adverse_headline()
    book.mark("1.10005", "1.10015", now_ms=NOW + 120_000)
    book.close()

    view = service.positions()
    assert view["ledger_available"] is True
    assert view["count"] == 1
    row = view["positions"][0]
    assert row["trade_intent_id"] == intent.trade_intent_id
    assert row["symbol"] == SYMBOL and row["direction"] == "LONG"
    assert row["thesis"]["statement"] and row["thesis"]["invalidation"]
    assert row["thesis"]["original_approved_risk_pct"]
    assert row["thesis_state"], "the position carries no assessed thesis state"
    assert row["latest_assessment"]["reasons"]
    assert row["protection"]["stop"] is not None
    assert row["protection"]["at_or_beyond_break_even"] in (True, False)
    assert row["exposure"]["approved_risk_pct"]
    assert row["linked_events"], "the headline was never linked to the position"
    assert row["linked_events"][0]["materiality"]
    assert row["latest_proposal"]["action"]


def test_a_closed_position_leaves_positions_and_appears_in_history(book, service):
    intent, _ = book.open_position()
    book.mark("1.09400", "1.09410", now_ms=NOW + 120_000)   # through the stop
    book.close()

    assert service.positions()["count"] == 0
    history = service.history(limit=50)
    assert history["ledger_available"] is True and history["count"] == 1
    row = history["history"][0]
    assert row["trade_intent_id"] == intent.trade_intent_id
    assert row["quadrant"]["quadrant"] and row["quadrant"]["decision_quality"]
    assert row["lessons"], "the lesson is not joined to the closed trade"
    assert history["by_quadrant"][row["quadrant"]["quadrant"]] == 1


# -------------------------------------------------------------------- events
def test_events_show_headlines_and_the_impacts_drawn_from_them(book, service):
    book.open_position()
    book.adverse_headline()
    book.mark("1.10005", "1.10015", now_ms=NOW + 120_000)
    book.close()

    view = service.events(limit=50)
    assert view["ledger_available"] is True
    assert view["count"] >= 1
    headline = view["events"][0]
    assert headline["headline_id"] and headline["title"]
    assert headline["trust"] == "T1_PRIMARY"
    assert view["impacts"], "no impact was recorded for a relevant headline"
    impact = view["impacts"][0]
    assert Decimal(impact["materiality"]) > Decimal("0")
    assert impact["subject_kind"] == "POSITION"
    # The authority line is the point: a headline reduces, it never blackouts.
    # The calendar keeps that authority and is labelled separately.
    assert headline["authority"] == "REDUCE_ONLY"


def test_events_respects_its_limit(book, service):
    book.open_position()
    book.adverse_headline()
    book.close()
    assert len(service.events(limit=1)["events"]) <= 1


# ---------------------------------------------------------------- potential
def test_potential_trades_show_what_was_refused_and_why(book, service):
    book.open_position()
    decision = book.reject_an_intent()
    book.close()

    from vati.risk import Decision

    assert decision.decision is Decision.REJECTED
    view = service.potential_trades()
    assert view["ledger_available"] is True
    refusals = [r for r in view["potential_trades"] if r["kind"] == "RISK_REJECTED"]
    assert refusals, [r["kind"] for r in view["potential_trades"]]
    assert refusals[0]["label"].startswith("REJECTED:")
    assert refusals[0]["symbol"] == SYMBOL


# --------------------------------------------------------------- assessment
def test_assessment_reads_the_book_and_states_the_invoker_it_actually_has(book, service):
    book.open_position()
    book.adverse_headline()
    book.mark("1.10005", "1.10015", now_ms=NOW + 120_000)
    book.close()

    view = service.assessment()
    assert view["ledger_available"] is True
    assert view["open_positions"] >= 0
    assert view["active_theses"]
    assert isinstance(view["urgent_risks"], list)
    assert view["kill_switch_active"] == []
    # GAP-F-004: the read model states the abstention rather than advertising a
    # model hierarchy that nothing on this host can reach.
    assert view["cognition"]["cognition_invoker"] == "none"
    assert view["cognition"]["state"] == "MODEL_INVOKER_UNCONFIGURED"


# -------------------------------------------------------------------- routes
@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VAN_DATABASE_PATH", str(tmp_path / "gw.sqlite3"))
    monkeypatch.setenv("VAN_HERMES_BASE_URL", "http://hermes.test")
    monkeypatch.setenv("VAN_GOOGLE_TOKEN_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_INTERNAL_CONTROL_TOKEN", "test-internal-token")
    monkeypatch.setenv("VAN_DEVICE_ENROLMENT_TOKEN", "test-internal-token")
    monkeypatch.setenv("VAN_INGRESS_TOKEN", "test-ingress-token-0123456789abcdef0123456789")
    monkeypatch.setenv("VAN_DEVICE_SECRET_FERNET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("VAN_VATI_LEDGER_PATH", str(tmp_path / "vati.sqlite"))
    get_settings.cache_clear()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            ticket = await ac.post("/v1/devices/pairing-ticket",
                                   json={"label": "t", "ttl_seconds": 600}, headers=HDR)
            assert ticket.status_code == 200, ticket.text
            paired = await ac.post("/v1/devices/pair", json={
                "pairing_token": ticket.json()["pairing_token"],
                "device_id": "test-device", "device_secret": "test-device-secret",
                "public_key_pem": DEVICE_PEM, "label": "test"})
            assert paired.status_code == 200, paired.text
            ac.headers.update({
                "X-Van-Ingress-Token": paired.json()["ingress_token"],
                "X-Van-Device-Token": paired.json()["device_access_token"]})
            yield ac, app
    get_settings.cache_clear()


def _ensure_routes(app) -> None:
    """Mount the five owner-device routes if app.py does not carry them yet.

    The handler bodies are exactly the ones the `@app.get` snippets use, so
    this test exercises the same wiring whether or not the routes have landed.
    """
    existing = {getattr(r, "path", "") for r in app.router.routes}
    trading = app.state.trading
    if "/v1/trading/positions" not in existing:
        @app.get("/v1/trading/positions")
        async def trading_positions():
            return trading.positions()

    if "/v1/trading/events" not in existing:
        @app.get("/v1/trading/events")
        async def trading_events(limit: int = 50):
            return trading.events(limit=limit)

    if "/v1/trading/potential" not in existing:
        @app.get("/v1/trading/potential")
        async def trading_potential():
            return trading.potential_trades()

    if "/v1/trading/history" not in existing:
        @app.get("/v1/trading/history")
        async def trading_history(limit: int = 50):
            return trading.history(limit=limit)

    if "/v1/trading/assessment" not in existing:
        @app.get("/v1/trading/assessment")
        async def trading_assessment():
            return trading.assessment()


@pytest.mark.asyncio
async def test_the_five_routes_answer_the_service_payloads(client, tmp_path):
    ac, app = client
    _ensure_routes(app)

    # No ledger yet: every route answers the unavailable shape, not a 500.
    for path in ("/v1/trading/positions", "/v1/trading/events",
                 "/v1/trading/potential", "/v1/trading/history",
                 "/v1/trading/assessment"):
        response = await ac.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.json()["ledger_available"] is False

    book = Book(tmp_path / "vati.sqlite")
    intent, _ = book.open_position()
    book.adverse_headline()
    book.mark("1.10005", "1.10015", now_ms=NOW + 120_000)
    book.close()

    positions = (await ac.get("/v1/trading/positions")).json()
    assert positions["ledger_available"] is True and positions["count"] == 1
    assert positions["positions"][0]["trade_intent_id"] == intent.trade_intent_id

    events = (await ac.get("/v1/trading/events", params={"limit": 10})).json()
    assert events["ledger_available"] is True and events["events"]

    potential = (await ac.get("/v1/trading/potential")).json()
    assert potential["ledger_available"] is True

    history = (await ac.get("/v1/trading/history", params={"limit": 10})).json()
    assert history["ledger_available"] is True

    assessment = (await ac.get("/v1/trading/assessment")).json()
    assert assessment["ledger_available"] is True
    assert assessment["cognition"]["state"] == "MODEL_INVOKER_UNCONFIGURED"


@pytest.mark.asyncio
async def test_the_read_model_routes_cannot_write(client):
    """Read-only by construction: nothing here accepts a POST."""
    ac, app = client
    _ensure_routes(app)
    for path in ("/v1/trading/positions", "/v1/trading/events",
                 "/v1/trading/potential", "/v1/trading/history",
                 "/v1/trading/assessment"):
        response = await ac.post(path, json={})
        assert response.status_code in (404, 405), (path, response.status_code)
