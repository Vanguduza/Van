"""Rev 5 live-ready infrastructure: PostgreSQL ledger, account registry, transports, feeds, lake, calendar, session service."""
from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import threading
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from conftest import mandate_dict
from test_backtest_runner_cli import synthetic_bars
from vati.accounts import Account, AccountRegistry, AccountRegistryError, CredentialRef
from vati.core import EventKind, Ledger, make_event
from vati.core.ledger_pg import PostgresLedger, open_ledger
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_bridge import Mt5BridgeAdapter, Mt5BridgeClient
from vati.execution.transports.deriv_ws import PLACEHOLDER, DerivMarketFeed, DerivWebSocketTransport, DerivWsError
from vati.execution.transports.mt5_http import Mt5HttpTransport, Mt5TransportError
from vati.intelligence.calendar_feed import build_matrix, calendar_report, load_calendar
from vati.intelligence.events import EventWindowState
from vati.market_data.bars import Tick
from vati.market_data.feeds import BarLake, DukascopyDownloader, bars_to_csv, decode_bi5, dukascopy_url
from vati.market_data.feeds.dukascopy import encode_bi5
from vati.risk.serde import contract_to_dict

D = Decimal
PG_DSN = os.environ.get("VATI_TEST_PG_DSN", "postgres://vati@127.0.0.1:54329/postgres")


def _pg_available() -> bool:
    try:
        import psycopg
        psycopg.connect(PG_DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


def _events(n=6):
    out = []
    for i in range(n):
        out.append(make_event(EventKind.SESSION, "t", {"i": i, "note": "x" * i}, event_time_ms=1000 + i, received_time_ms=1000 + i, correlation_id=f"c{i % 2}"))
    return out


# ------------------------------------------------------------- postgres ledger
@pytest.mark.skipif(not _pg_available(), reason="local PostgreSQL not reachable")
def test_postgres_ledger_matches_sqlite_chain_and_detects_tampering():
    import psycopg
    name = f"t{os.getpid()}_{id(object())}"
    pg = PostgresLedger(PG_DSN, ledger_name=name)
    lite = Ledger()
    try:
        for ev in _events():
            assert pg.append(ev) == lite.append(ev)            # byte-identical chain across backends
        assert pg.head() == lite.head() and pg.count() == 6 and pg.count(EventKind.SESSION) == 6
        assert [e.hash for e in pg.iter(correlation_id="c1")] == [e.hash for e in lite.iter(correlation_id="c1")]
        ok, n = pg.verify_chain(); assert ok and n == 6
        with pytest.raises(Exception):
            pg.append(make_event(EventKind.SESSION, "t", {"a": 1}, event_time_ms=1, received_time_ms=1).__class__(**{**_events(1)[0].__dict__, "hash": "f" * 64}))
        # a second writer on its own connection continues the same chain
        pg2 = PostgresLedger(PG_DSN, ledger_name=name)
        ev = make_event(EventKind.KILL_SWITCH, "t2", {"trigger": "OWNER_HALT"}, event_time_ms=2000, received_time_ms=2000)
        h = pg2.append(ev); assert pg.head() == h and pg.verify_chain() == (True, 7)
        pg2.close()
        # tampering with a stored payload breaks verification
        with psycopg.connect(PG_DSN) as c:
            n_upd = c.execute("UPDATE vati.events SET payload_json = '{\"i\":99}' WHERE event_time_ms = 1002 AND producer = 't'").rowcount
        assert n_upd == 1
        ok, n = pg.verify_chain(); assert not ok and n == 2
        assert isinstance(open_ledger(PG_DSN, ledger_name=name), PostgresLedger) and isinstance(open_ledger(":memory:"), Ledger)
    finally:
        with psycopg.connect(PG_DSN) as c:
            c.execute("DELETE FROM vati.events WHERE producer IN ('t','t2')"); c.execute("DELETE FROM vati.chain_head WHERE ledger = %s", (name,))
        pg.close()


# ------------------------------------------------------------- accounts
def test_account_registry_holds_no_secrets_and_enforces_file_mode(tmp_path):
    reg = AccountRegistry(tmp_path / "accounts.json")
    sec = tmp_path / "deriv.env"; sec.write_text("DERIV_API_TOKEN=abc123\n"); sec.chmod(0o600)
    a = reg.add(Account(alias="deriv_demo", broker="DERIV", mode="DEMO_TRADER", currency="USD", server="1089", credential_ref=CredentialRef(secrets_file=str(sec))))
    assert a.safety_identity == "DEMO" and a.router_venue == "deriv"
    pub = reg.public()[0]
    assert pub["credential_ref"] == {"kind": "file"} and "abc123" not in json.dumps(pub) and "abc123" not in (tmp_path / "accounts.json").read_text()
    assert reg.credentials("deriv_demo") == {"DERIV_API_TOKEN": "abc123"}
    sec.chmod(0o644)
    with pytest.raises(AccountRegistryError, match="0600"):
        reg.credentials("deriv_demo")
    with pytest.raises(AccountRegistryError, match="credential-shaped"):
        Account(alias="bad", broker="MT5", mode="DEMO_TRADER", currency="USD", notes="password=hunter2", credential_ref=CredentialRef(env_var="X")).validate()
    with pytest.raises(AccountRegistryError, match="exactly one"):
        Account(alias="bad2", broker="MT5", mode="DEMO_TRADER", currency="USD").validate()
    with pytest.raises(AccountRegistryError, match="mandate_ref"):
        Account(alias="live1", broker="MT5", mode="LIMITED_LIVE", currency="USD", demo=False, credential_ref=CredentialRef(env_var="X")).validate()
    with pytest.raises(AccountRegistryError, match="already registered"):
        reg.add(a)
    assert AccountRegistry(tmp_path / "accounts.json").get("deriv_demo").server == "1089"      # persisted round trip
    paper = Account(alias="paper_lab", broker="PAPER", mode="DEMO_TRADER", currency="USD"); paper.validate()
    assert paper.safety_identity == "PAPER" and Account(alias="obs", broker="PAPER", mode="OBSERVE", currency="USD").safety_identity == "PAPER"
    assert Account(alias="ro", broker="MT5", mode="ADVISOR", currency="USD", credential_ref=CredentialRef(env_var="X")).safety_identity == "READ ONLY"


# ------------------------------------------------------------- mt5 transport
def _make_cert(tmp_path: Path, cn: str) -> tuple[Path, Path]:
    key, crt = tmp_path / f"{cn}.key", tmp_path / f"{cn}.crt"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt), "-days", "2", "-subj", f"/CN={cn}", "-addext", f"subjectAltName=DNS:{cn},IP:127.0.0.1"], check=True, capture_output=True)
    return key, crt


class _BridgeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/bridge/v1/call"
        resp = {"nonce": body["nonce"], "worker_time_ms": body["issued_ms"] + 5, "op": body["op"], "account": {"equity": "1000", "balance": "1000", "currency": "USD", "verified": True}, "positions": [], "ok": True,
                "status": "FILLED", "volume": body["body"].get("volume", "0"), "price": body["body"].get("price"), "sl_confirmed": True, "order": "1", "position": "77"}
        out = json.dumps(resp).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):  # silence
        pass


def test_mt5_http_transport_requires_tls_and_round_trips_signed_requests(tmp_path):
    key, crt = _make_cert(tmp_path, "localhost")
    srv = HTTPServer(("127.0.0.1", 0), _BridgeHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(str(crt), str(key))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    try:
        with pytest.raises(Mt5TransportError, match="https"):
            Mt5HttpTransport(f"http://localhost:{port}", ca_file=str(crt))
        with pytest.raises(Mt5TransportError, match="CA file"):
            Mt5HttpTransport(f"https://localhost:{port}", ca_file=str(tmp_path / "nope.pem"))
        t = Mt5HttpTransport(f"https://localhost:{port}", ca_file=str(crt))
        client = Mt5BridgeClient(signing_key=b"k" * 32, transport=t)
        adapter = Mt5BridgeAdapter(client, account_alias="mt5_demo")
        acct = adapter.sync_account()
        assert acct.equity == D("1000") and acct.verified and t.calls == 1
        assert adapter.heartbeat(now_ms=1_000).connected
        # wrong CA → refused before any request is answered
        _, other = _make_cert(tmp_path, "other")
        bad = Mt5HttpTransport(f"https://localhost:{port}", ca_file=str(other))
        with pytest.raises(VenueUnavailable):
            Mt5BridgeClient(signing_key=b"k" * 32, transport=bad).call("sync_account", {"alias": "x"}, now_ms=1)
    finally:
        srv.shutdown()


# ------------------------------------------------------------- deriv transport
class _FakeDerivSocket:
    """In-memory Deriv server: answers by req_id, sometimes out of order."""
    def __init__(self, url):
        self.url, self.out, self.closed = url, [], False
        self.seen_tokens = []

    def send(self, raw):
        m = json.loads(raw)
        rid = m["req_id"]
        if "authorize" in m:
            self.seen_tokens.append(m["authorize"])
            self.out.append(json.dumps({"req_id": 999, "msg_type": "noise"}))   # unrelated frame first
            self.out.append(json.dumps({"req_id": rid, "authorize": {"loginid": "VRTC1", "balance": "5000.00", "currency": "USD"}, "echo_req": m}))
        elif "ping" in m:
            self.out.append(json.dumps({"req_id": rid, "ping": "pong"}))
        elif "ticks_history" in m:
            g = m.get("granularity", 60)
            self.out.append(json.dumps({"req_id": rid, "candles": [{"epoch": 1_700_000_000 + i * g, "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15"} for i in range(3)]}))
        elif "proposal" in m:
            self.out.append(json.dumps({"req_id": rid, "error": {"message": "Market is closed", "code": "MarketIsClosed"}}))
        else:
            self.out.append(json.dumps({"req_id": rid, "unknown": True}))

    def recv(self):
        return self.out.pop(0)

    def close(self):
        self.closed = True


def test_deriv_ws_transport_correlates_req_ids_and_never_leaks_placeholder_token():
    socks = []
    def connector(url):
        s = _FakeDerivSocket(url); socks.append(s); return s
    t = DerivWebSocketTransport(app_id="1089", token_provider=lambda: "real-token", connector=connector)
    from vati.execution.deriv import DerivAdapter
    ad = DerivAdapter(transport=t)
    acct = ad.sync_account()
    assert acct.verified and acct.equity == D("5000.00") and socks[0].seen_tokens == ["real-token"] and t.authorized_loginid == "VRTC1"
    assert ad.heartbeat(now_ms=1).connected
    assert "?app_id=1089" in socks[0].url
    feed = DerivMarketFeed(t)
    bars = feed.history_bars("frxEURUSD", granularity_s=60, count=3)
    assert len(bars) == 3 and bars[0].end_ms - bars[0].start_ms == 60_000 and bars[0].close == D("1.15")
    # an API error comes back as data and turns into a REJECTED receipt, never an exception on the order path
    from vati.execution.base import OrderCommand, StopMode
    from vati.risk.contracts import Direction, LossModel
    cmd = OrderCommand("i1", "d" * 64, "k", "deriv_primary", "deriv", "frxEURUSD", Direction.LONG, "CONTRACT_BUY", D("10"), D("1.1"), None, StopMode.VENUE, LossModel.FULL_STAKE).sealed()
    rec = ad.submit(cmd, now_ms=5)
    assert rec.status == "REJECTED" and "Market is closed" in rec.reject_reason
    # no token → fail closed before anything is sent
    t2 = DerivWebSocketTransport(app_id="1089", token_provider=lambda: PLACEHOLDER, connector=connector)
    with pytest.raises(DerivWsError, match="fail closed"):
        t2({"authorize": PLACEHOLDER})
    with pytest.raises(DerivWsError):
        DerivWebSocketTransport(app_id="", token_provider=lambda: "x")


def test_deriv_ws_transport_over_a_real_websocket_server():
    from websockets.sync.server import serve
    def handler(ws):
        for raw in ws:
            m = json.loads(raw)
            ws.send(json.dumps({"req_id": m["req_id"], "ping": "pong"} if "ping" in m else {"req_id": m["req_id"], "error": {"message": "nope", "code": "X"}}))
    with serve(handler, "127.0.0.1", 0) as server:
        port = server.socket.getsockname()[1]
        th = threading.Thread(target=server.serve_forever, daemon=True); th.start()
        t = DerivWebSocketTransport(app_id="1089", token_provider=lambda: "tok", endpoint=f"ws://127.0.0.1:{port}/websockets/v3", timeout_s=5)
        assert t({"ping": 1})["ping"] == "pong" and t({"foo": 1})["error"] == "nope" and t.calls == 2
        t.close()
        server.shutdown()
    dead = DerivWebSocketTransport(app_id="1089", token_provider=lambda: "tok", endpoint="ws://127.0.0.1:1/websockets/v3", timeout_s=1)
    with pytest.raises(DerivWsError, match="connect failed"):
        dead({"ping": 1})


# ------------------------------------------------------------- dukascopy + lake
def test_dukascopy_format_roundtrip_and_zero_based_month_url():
    h = datetime(2024, 1, 2, 10, tzinfo=timezone.utc)
    assert dukascopy_url("eurusd", h) == "https://datafeed.dukascopy.com/datafeed/EURUSD/2024/00/02/10h_ticks.bi5"
    ticks = [Tick(int(h.timestamp() * 1000) + i * 250, D("1.10000") + D(i) / D(100000), D("1.10010") + D(i) / D(100000)) for i in range(50)]
    raw = encode_bi5(ticks, symbol="EURUSD", hour_start_utc=h)
    back = decode_bi5(raw, symbol="EURUSD", hour_start_utc=h)
    assert back == ticks and decode_bi5(b"", symbol="EURUSD", hour_start_utc=h) == []
    gold = [Tick(int(h.timestamp() * 1000), D("2031.123"), D("2031.456"))]
    assert decode_bi5(encode_bi5(gold, symbol="XAUUSD", hour_start_utc=h), symbol="XAUUSD", hour_start_utc=h) == gold
    with pytest.raises(ValueError):
        decode_bi5(__import__("lzma").compress(b"123"), symbol="EURUSD", hour_start_utc=h)
    fetched = {}
    def fake_fetch(url):
        hour = int(url.rsplit("/", 1)[1][:2]); hh = h.replace(hour=hour)
        fetched[url] = 1
        return encode_bi5([Tick(int(hh.timestamp() * 1000) + i * 1000, D("1.1"), D("1.1002")) for i in range(120)], symbol="EURUSD", hour_start_utc=hh)
    dl = DukascopyDownloader(fetch=fake_fetch)
    bars = dl.bars("EURUSD", h, h.replace(hour=13), interval_ms=3_600_000)
    assert len(dl.fetched) == 3 and len(bars) == 3 and all(b.ticks == 120 for b in bars)
    assert list(dl.hours("EURUSD", datetime(2024, 1, 6, 0, tzinfo=timezone.utc), datetime(2024, 1, 8, 0, tzinfo=timezone.utc)))[0] == datetime(2024, 1, 7, 21, tzinfo=timezone.utc)   # weekend skipped until Sunday 21:00


def test_bar_lake_hashes_slices_and_refuses_tampered_bytes(tmp_path):
    lake = BarLake(tmp_path / "lake")
    bars = synthetic_bars()
    s = lake.write(bars[:100], symbol="eurusd", timeframe="H1", source="test", provenance="SYNTHETIC")
    s2 = lake.write(bars[100:], symbol="EURUSD", timeframe="H1", source="test", provenance="SYNTHETIC")
    assert s.bars == 100 and len(s.sha256) == 64 and lake.symbols() == {"EURUSD": ["H1"]}
    got, used = lake.read("EURUSD", "H1")
    assert got == list(bars) and used == [s.sha256, s2.sha256]
    part, used1 = lake.read("EURUSD", "H1", end_ms=bars[50].end_ms)
    assert len(part) == 51 and used1 == [s.sha256]
    assert lake.write(bars[:100], symbol="EURUSD", timeframe="H1", source="test", provenance="SYNTHETIC").sha256 == s.sha256   # deterministic bytes
    d = lake.resample(bars[:48], to="H4")
    assert len(d) == 12 and d[0].high == max(b.high for b in bars[:4]) and d[0].close == bars[3].close
    with pytest.raises(ValueError, match="timeframe"):
        lake.write(bars[:10], symbol="EURUSD", timeframe="M5", source="t", provenance="SYNTHETIC")
    p = tmp_path / "lake" / "EURUSD" / "H1" / s.path
    raw = bytearray(p.read_bytes()); raw[-1] ^= 0xFF; p.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="manifest hash"):
        lake.read("EURUSD", "H1")
    csv_path = tmp_path / "b.csv.gz"; assert bars_to_csv(bars[:5], csv_path) == 5
    from vati.market_data.feeds import bars_from_csv
    assert bars_from_csv(csv_path) == list(bars[:5])


# ------------------------------------------------------------- calendar
def test_calendar_needs_two_sources_for_live_eligibility(tmp_path):
    p = tmp_path / "cal.json"
    p.write_text(json.dumps({"events": [
        {"name": "NFP", "release": "2026-10-02T12:30:00Z", "currencies": "USD", "source": "bls"},
        {"name": "NFP", "release": "2026-10-02T12:30:00Z", "currencies": "USD", "source": "vendor"},
        {"name": "CPI", "release": "2026-10-14T12:30:00Z", "currencies": "USD", "source": "bls"},
        {"name": "Coffee talk", "release": "2026-10-14T12:30:00Z", "currencies": "USD", "source": "x", "tier": "3"},
    ]}))
    evs = load_calendar(p)
    assert [e.name for e in evs] == ["NFP", "CPI"] and evs[0].verified_sources == 2 and evs[1].verified_sources == 1
    m = build_matrix(p)
    nfp, cpi = evs
    assert m.state_at(nfp.release_ms - 2 * 60_000, "EUR", "USD")[0] is EventWindowState.PRE_BLACKOUT
    assert m.state_at(nfp.release_ms - 30 * 60_000, "EUR", "USD")[0] is EventWindowState.NONE          # verified: only the 5-minute blackout applies
    assert m.state_at(nfp.release_ms + 60 * 60_000, "EUR", "USD")[0] is EventWindowState.DRIFT
    assert m.state_at(cpi.release_ms - 4 * 60_000, "GBP", "USD")[0] is EventWindowState.PRE_BLACKOUT     # unverified: fails closed
    rep = calendar_report(evs, now_ms=nfp.release_ms - 3_600_000)
    assert rep == {"events": 2, "upcoming": 2, "live_eligible": 1, "unverified": [cpi.event_id], "next": {"event_id": nfp.event_id, "in_minutes": 60}}
    csvp = tmp_path / "cal.csv"; csvp.write_text("name,release,currencies,source\nFOMC,1790000000,USD,fed\n")
    assert load_calendar(csvp)[0].release_ms == 1_790_000_000_000


# ------------------------------------------------------------- session service
def test_session_service_runs_paper_account_from_lake_and_logs_portfolio_truth(tmp_path, eurusd):
    from vati.app.service import ServiceConfig, SessionService, lake_bar_source
    reg = AccountRegistry(tmp_path / "accounts.json")
    reg.add(Account(alias="paper_lab", broker="PAPER", mode="DEMO_TRADER", currency="USD"))
    lake = BarLake(tmp_path / "lake"); bars = synthetic_bars(); lake.write(bars, symbol="EURUSD", timeframe="H1", source="t", provenance="SYNTHETIC")
    cfg = ServiceConfig(account_alias="paper_lab", symbol="EURUSD", base="EUR", quote="USD", timeframe="H1", contract=contract_to_dict(eurusd), mandate=mandate_dict(venue="paper", mode="DEMO_TRADER", account_alias="paper_lab", allowed_strategies=["FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"]),
                        capsules=["FX-TREND-PULLBACK-01", "FX-LONDON-BREAKOUT-01"], registry_path=str(tmp_path / "accounts.json"), ledger=str(tmp_path / "l.sqlite"), lake_root=str(tmp_path / "lake"), heartbeat_path=str(tmp_path / "hb.json"))
    clock = {"now": bars[100].end_ms}
    svc = SessionService(cfg, lake_bar_source(lake, "EURUSD", "H1"), clock=lambda: clock["now"]).build()
    svc.start()
    hb = json.loads((tmp_path / "hb.json").read_text()); assert hb["status"] == "STARTED" and hb["permit_new_orders"] is True
    decisions = []
    for i in range(101, 160):
        clock["now"] = bars[i].end_ms + 1000
        decisions.append(svc.step_once())
        assert svc.step_once() is None          # same bar again → waits, no double stepping
    assert svc.cycles == 59 and all(d is not None for d in decisions)
    led = Ledger(tmp_path / "l.sqlite")
    assert led.count(EventKind.ACCOUNT_SNAPSHOT) == 60 and led.count(EventKind.MARKET_DATA_HEALTH) >= 59 and led.verify_chain()[0]
    snap = list(led.iter(EventKind.ACCOUNT_SNAPSHOT))[-1].payload
    assert snap["account_alias"] == "paper_lab" and D(snap["equity"]) > 0 and snap["mode"] == "DEMO_TRADER" and snap["connected"] is True
    states = {e.payload["state"] for e in led.iter(EventKind.MARKET_DATA_HEALTH)}
    assert states == {"LIVE"}
    clock["now"] = bars[-1].end_ms + 10 * 3_600_000      # ten hours after the last bar the lake holds
    svc.last_bar_end_ms = 0
    svc.step_once()
    assert list(led.iter(EventKind.MARKET_DATA_HEALTH))[-1].payload["state"] == "STALE"        # a stale feed is named, never shown as live
    hb = json.loads((tmp_path / "hb.json").read_text()); assert hb["data_state"] == "STALE" and hb["cycles"] == 60
    # safety identity mismatch refuses to start
    bad = ServiceConfig(**{**cfg.__dict__, "mandate": mandate_dict(venue="paper", mode="LIMITED_LIVE", account_alias="mt5_demo", allowed_strategies=["FX-TREND-PULLBACK-01"])})
    reg.add(Account(alias="mt5_demo", broker="MT5", mode="LIMITED_LIVE", currency="USD", credential_ref=CredentialRef(env_var="NOPE"), demo=True))
    with pytest.raises(RuntimeError, match="safety identity"):
        SessionService(ServiceConfig(**{**bad.__dict__, "account_alias": "mt5_demo"}), lake_bar_source(lake, "EURUSD", "H1")).build()
    with pytest.raises(RuntimeError, match="ACCOUNT_MISMATCH"):
        SessionService(ServiceConfig(**{**cfg.__dict__, "mandate": mandate_dict(venue="paper", mode="DEMO_TRADER", account_alias="someone_else", allowed_strategies=["FX-TREND-PULLBACK-01"])}), lake_bar_source(lake, "EURUSD", "H1")).build()


def test_cli_accounts_lake_calendar_serve(tmp_path, eurusd, capsys):
    from vati.__main__ import main
    reg = str(tmp_path / "accounts.json")
    assert main(["accounts", "add", "--registry", reg, "--alias", "paper_lab", "--broker", "PAPER"]) == 0
    assert main(["accounts", "add", "--registry", reg, "--alias", "deriv_demo", "--broker", "DERIV", "--server", "1089", "--env-var", "DERIV_TOKEN_DEMO"]) == 0
    assert main(["accounts", "verify", "--registry", reg, "--alias", "deriv_demo"]) == 1          # env var not set → MISSING, exit 1
    os.environ["DERIV_TOKEN_DEMO"] = "t0k"
    try:
        assert main(["accounts", "verify", "--registry", reg, "--alias", "deriv_demo"]) == 0
        out = capsys.readouterr().out
        assert "t0k" not in out and '"keys": ["TOKEN"]' in out
    finally:
        del os.environ["DERIV_TOKEN_DEMO"]
    assert main(["accounts", "list", "--registry", reg]) == 0
    bars = synthetic_bars(); csvp = tmp_path / "b.csv"; bars_to_csv(bars, csvp)
    assert main(["lake", "import-csv", "--root", str(tmp_path / "lake"), "--symbol", "EURUSD", "--timeframe", "H1", "--file", str(csvp), "--provenance", "SYNTHETIC"]) == 0
    assert main(["lake", "list", "--root", str(tmp_path / "lake")]) == 0
    cal = tmp_path / "cal.json"; cal.write_text(json.dumps({"events": [{"name": "NFP", "release": "2099-01-08T13:30:00Z", "currencies": "USD", "source": "a"}]}))
    assert main(["calendar", "--file", str(cal)]) == 0
    cfg = {"account_alias": "paper_lab", "symbol": "EURUSD", "base": "EUR", "quote": "USD", "timeframe": "H1", "contract": contract_to_dict(eurusd),
           "mandate": mandate_dict(venue="paper", mode="DEMO_TRADER", account_alias="paper_lab", allowed_strategies=["FX-TREND-PULLBACK-01"]), "capsules": ["FX-TREND-PULLBACK-01"], "registry_path": reg,
           "ledger": str(tmp_path / "l.sqlite"), "lake_root": str(tmp_path / "lake"), "heartbeat_path": str(tmp_path / "hb.json")}
    (tmp_path / "svc.json").write_text(json.dumps(cfg))
    assert main(["serve", "--config", str(tmp_path / "svc.json"), "--once"]) == 0
    assert json.loads((tmp_path / "hb.json").read_text())["status"] in ("RUNNING", "NO_DATA", "WAITING_FOR_BAR")
