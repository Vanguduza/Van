"""Windows MT5 bridge worker protocol, exercised on Linux with a fake terminal, and the full
mTLS + HMAC round trip from the Linux client through the worker's own HTTPS server."""
from __future__ import annotations

import importlib.util
import json
import ssl
import subprocess
import threading
import time
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from vati.execution.base import OrderCommand, StopMode, VenueUnavailable
from vati.execution.mt5_bridge import Mt5BridgeAdapter, Mt5BridgeClient
from vati.execution.transports.mt5_http import Mt5HttpTransport
from vati.risk.contracts import Direction, LossModel

WORKER = Path(__file__).resolve().parents[2] / "deploy" / "van-trading-core" / "windows" / "mt5_worker" / "mt5_bridge_worker.py"
spec = importlib.util.spec_from_file_location("mt5_bridge_worker", WORKER); worker_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker_mod)  # type: ignore[union-attr]
D = Decimal
KEY = b"k" * 32


class FakeMt5:
    """Enough of the MetaTrader5 module surface for the worker's code paths."""
    TRADE_ACTION_DEAL, TRADE_ACTION_PENDING, TRADE_ACTION_SLTP = 1, 5, 6
    ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT = 0, 1, 2, 3
    ORDER_TIME_GTC, ORDER_FILLING_IOC = 1, 1
    TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL, TRADE_RETCODE_PLACED = 10009, 10010, 10008

    def __init__(self):
        self.login_calls, self.sent = [], []
        self.pos = {}
        self.trade_allowed = True
        self._login = 12345678

    def initialize(self): return True
    def login(self, login, password=None, server=None): self.login_calls.append((login, server, "pw-redacted")); return login == self._login and password == "s3cret"
    def account_info(self): return NS(login=self._login, equity=10_250.5, balance=10_000.0, currency="USD", margin_free=9_000.0, leverage=30, margin_mode=2, trade_allowed=self.trade_allowed)
    def symbol_info(self, s): return NS(volume_min=0.01, volume_step=0.01, volume_max=100.0, trade_stops_level=5, point=0.00001, digits=5, trade_contract_size=100000.0, trade_tick_value=1.0, trade_tick_size=0.00001, spread=8, trade_mode=4)
    def symbol_info_tick(self, s): return NS(bid=1.10000, ask=1.10008)
    def order_check(self, req): return NS(retcode=0, comment="ok", margin=33.0, margin_free=8967.0)
    def order_send(self, req):
        self.sent.append(req)
        if req["action"] == self.TRADE_ACTION_SLTP:
            p = self.pos[req["position"]]; p.sl = req["sl"]; return NS(retcode=self.TRADE_RETCODE_DONE, comment="sltp")
        if req["action"] == self.TRADE_ACTION_DEAL and req.get("position"):
            self.pos.pop(req["position"]); return NS(retcode=self.TRADE_RETCODE_DONE, comment="closed", volume=req["volume"], price=req["price"])
        ticket = 700 + len(self.pos)
        self.pos[ticket] = NS(ticket=ticket, symbol=req["symbol"], type=req["type"], volume=req["volume"], price_open=req["price"], sl=req["sl"], tp=req.get("tp", 0.0), comment=req["comment"], magic=req["magic"], profit=0.0)
        return NS(retcode=self.TRADE_RETCODE_DONE, comment="done", order=ticket, volume=req["volume"], price=req["price"])
    def positions_get(self, ticket=None): return [p for p in self.pos.values() if ticket is None or p.ticket == ticket]
    def orders_get(self): return []
    def history_deals_get(self, a, b): return []


def make_worker(tmp_path, clock):
    pw = tmp_path / "fx.pw"; pw.write_text("s3cret\n")
    cfg = {"accounts": {"fx_primary": {"login": 12345678, "server": "Broker-Demo", "password_file": str(pw)}}}
    return worker_mod.Worker(cfg, worker_mod.Terminal(FakeMt5()), KEY, clock=clock), cfg


def test_worker_verifies_signature_nonce_skew_and_serves_the_contract(tmp_path):
    now = {"ms": 1_000_000}
    w, _ = make_worker(tmp_path, lambda: now["ms"])
    client = Mt5BridgeClient(signing_key=KEY, transport=w.handle, max_skew_ms=5000)
    adapter = Mt5BridgeAdapter(client, account_alias="fx_primary", clock=lambda: now["ms"])
    acct = adapter.sync_account()
    assert acct.equity == D("10250.5") and acct.verified and acct.currency == "USD"
    assert w.t.mt5.login_calls == [(12345678, "Broker-Demo", "pw-redacted")]
    # the same signed request replayed is refused; a forged signature is refused; an unknown op is refused; skew is refused
    req = client.sent[-1].__dict__
    assert w.handle(req)["error"] == "nonce replayed"
    assert w.handle({**req, "nonce": 99, "signature": "0" * 64})["error"] == "bad signature"
    bad = client.sign(worker_mod.__dict__["Worker"] and __import__("vati.execution.mt5_bridge", fromlist=["BridgeRequest"]).BridgeRequest("shell", 98, now["ms"], {}))
    assert w.handle(bad.__dict__)["error"] == "op not in contract"
    late = client.sign(__import__("vati.execution.mt5_bridge", fromlist=["BridgeRequest"]).BridgeRequest("positions", 97, now["ms"] - 60_000, {"alias": "fx_primary"}))
    assert w.handle(late.__dict__)["error"] == "clock skew"
    # unknown alias → error as data; the client raises VenueUnavailable only on transport/nonce faults
    r = client.call("positions", {"alias": "ghost"}, now_ms=now["ms"])
    assert "not configured" in r["error"]
    # order without SL refused by the worker even if a client tried
    r = client.call("order_send", {"alias": "fx_primary", "symbol": "EURUSD", "type": "BUY", "volume": "0.1", "price": "1.1", "sl": None, "order_type": "MARKET"}, now_ms=now["ms"])
    assert r["status"] == "REJECTED" and "sl" in r["reason"]
    cmd = OrderCommand("intent-1", "d" * 64, "k", "fx_primary", "mt5", "EURUSD", Direction.LONG, "MARKET", D("0.10"), D("1.10008"), D("1.09800"), StopMode.VENUE, LossModel.STOP_DISTANCE, targets=(D("1.10600"),), max_slippage=D("0.0002")).sealed()
    rec = adapter.submit(cmd, now_ms=now["ms"])
    assert rec.status == "FILLED" and rec.protective_stop_confirmed and rec.protective_stop_price == D("1.09800") and rec.broker_position_id == "700"
    sent = w.t.mt5.sent[-1]
    assert sent["sl"] == 1.098 and sent["tp"] == 1.106 and sent["comment"] == "vati:intent-1" and sent["deviation"] == 20 and sent["type"] == FakeMt5.ORDER_TYPE_BUY
    pos = adapter.positions()
    assert len(pos) == 1 and pos[0].trade_intent_id == "intent-1" and pos[0].stop_price == D("1.098")
    # stops only tighten
    assert adapter.modify_stop("700", D("1.09900"), now_ms=now["ms"]).status == "ACCEPTED"
    assert adapter.modify_stop("700", D("1.09000"), now_ms=now["ms"]).status == "REJECTED"
    closed = adapter.close("700", None, now_ms=now["ms"], reason="TARGET")
    assert closed.status == "FILLED" and adapter.positions() == []
    # trading disabled at the terminal → orders refused, reads still work
    w.t.mt5.trade_allowed = False
    rec2 = adapter.submit(cmd, now_ms=now["ms"])
    assert rec2.status == "REJECTED" and "not allowed" in rec2.reject_reason
    assert adapter.sync_account().verified
    assert all(a["op"] in worker_mod.OPS for a in w.audit) and not any("s3cret" in json.dumps(a) for a in w.audit)


def _cert(tmp_path, name, san, ca=None):
    key, crt = tmp_path / f"{name}.key", tmp_path / f"{name}.crt"
    if ca is None:
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt), "-days", "2", "-subj", f"/CN={name}", "-addext", "basicConstraints=critical,CA:TRUE"], check=True, capture_output=True)
        return key, crt
    csr = tmp_path / f"{name}.csr"; ext = tmp_path / f"{name}.ext"
    subprocess.run(["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(csr), "-subj", f"/CN={name}"], check=True, capture_output=True)
    ext.write_text(f"subjectAltName={san}\nextendedKeyUsage=serverAuth,clientAuth\n")
    subprocess.run(["openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca[1]), "-CAkey", str(ca[0]), "-CAcreateserial", "-out", str(crt), "-days", "2", "-extfile", str(ext)], check=True, capture_output=True)
    return key, crt


def test_full_mtls_round_trip_client_transport_to_worker_https_server(tmp_path):
    ca = _cert(tmp_path, "van-trading-bridge-ca", "")
    skey, scrt = _cert(tmp_path, "mt5-worker", "DNS:localhost,IP:127.0.0.1", ca)
    ckey, ccrt = _cert(tmp_path, "vati-core-client", "DNS:vati-core-client", ca)
    now = {"ms": int(time.time() * 1000)}
    w, _ = make_worker(tmp_path, lambda: int(time.time() * 1000))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(scrt), str(skey)); ctx.load_verify_locations(str(ca[1])); ctx.verify_mode = ssl.CERT_REQUIRED
    srv = ThreadingHTTPServer(("127.0.0.1", 0), worker_mod.make_handler(w)); srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    port = srv.server_address[1]; th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    try:
        # without a client certificate the worker's TLS handshake rejects us
        no_cert = Mt5HttpTransport(f"https://localhost:{port}", ca_file=str(ca[1]))
        with pytest.raises(VenueUnavailable):
            Mt5BridgeClient(signing_key=KEY, transport=no_cert).call("sync_account", {"alias": "fx_primary"}, now_ms=now["ms"])
        t = Mt5HttpTransport(f"https://localhost:{port}", ca_file=str(ca[1]), client_cert=str(ccrt), client_key=str(ckey))
        adapter = Mt5BridgeAdapter(Mt5BridgeClient(signing_key=KEY, transport=t), account_alias="fx_primary")
        assert adapter.heartbeat(now_ms=int(time.time() * 1000)).connected
        assert adapter.sync_account().equity == D("10250.5")
        # wrong signing key on the client side → the worker answers "bad signature" and the adapter's sync raises KeyError→ treated as fault by callers
        bad = Mt5BridgeClient(signing_key=b"x" * 32, transport=t)
        assert bad.call("positions", {"alias": "fx_primary"}, now_ms=int(time.time() * 1000))["error"] == "bad signature"
    finally:
        srv.shutdown()
