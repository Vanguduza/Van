"""MT5 bridge worker — runs on the Windows host next to the MetaTrader 5 terminal.

Serves the narrow signed protocol `vati.execution.mt5_bridge` speaks:
  POST /bridge/v1/call  {op, nonce, issued_ms, body, signature}
over HTTPS with **mutual TLS** (the worker presents mt5-worker.crt, requires the
vati-core client certificate signed by the same private CA). On top of TLS every
request is HMAC-signed with the shared signing key; nonces are single-use and
issued_ms must be within the skew window. The worker never decides size, never
widens a stop, and refuses an order without SL in the same request.

    python mt5_bridge_worker.py --config C:\\van-mt5\\worker.json

worker.json (0600-equivalent ACL: owner only):
  {"listen": "0.0.0.0", "port": 9443, "cert": "mt5-worker.crt", "key": "mt5-worker.key", "ca": "ca.crt",
   "signing_key_file": "bridge.key", "accounts": {"fx_primary": {"login": 12345678, "server": "Broker-Demo", "password_file": "fx_primary.pw"}}}

The MetaTrader5 Python package is imported lazily so this file also runs under
tests on Linux with an injected fake terminal."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

OPS = ("sync_account", "sync_symbols", "order_check", "order_send", "positions", "orders", "history", "modify_sl_tp", "close")
SKEW_MS = 5000


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class NonceStore:
    def __init__(self) -> None:
        self._seen: dict[int, int] = {}
        self._lock = threading.Lock()

    def accept(self, nonce: int, now_ms: int) -> bool:
        with self._lock:
            for k, t in list(self._seen.items()):
                if now_ms - t > 10 * SKEW_MS:
                    del self._seen[k]
            if nonce in self._seen:
                return False
            self._seen[nonce] = now_ms
            return True


class Terminal:
    """Thin wrapper over the MetaTrader5 module; every venue effect goes through here."""

    def __init__(self, mt5=None) -> None:
        if mt5 is None:
            import MetaTrader5 as mt5  # type: ignore  # Windows only
        self.mt5 = mt5
        self.logged_in: Optional[int] = None

    def login(self, login: int, server: str, password: str) -> bool:
        if self.logged_in == login:
            return True
        if not self.mt5.initialize():
            return False
        ok = bool(self.mt5.login(login, password=password, server=server))
        self.logged_in = login if ok else None
        return ok

    def account(self) -> dict:
        a = self.mt5.account_info()
        if a is None:
            raise RuntimeError("account_info unavailable")
        return {"login": a.login, "equity": str(a.equity), "balance": str(a.balance), "currency": a.currency, "margin_free": str(a.margin_free), "leverage": a.leverage, "hedging": getattr(a, "margin_mode", 2) == 2, "trade_allowed": bool(getattr(a, "trade_allowed", True))}

    def symbol(self, symbol: str) -> dict:
        s = self.mt5.symbol_info(symbol)
        if s is None:
            raise RuntimeError(f"unknown symbol {symbol}")
        return {"symbol": symbol, "volume_min": str(s.volume_min), "volume_step": str(s.volume_step), "volume_max": str(s.volume_max), "trade_stops_level": s.trade_stops_level, "point": str(s.point), "digits": s.digits,
                "trade_contract_size": str(s.trade_contract_size), "trade_tick_value": str(s.trade_tick_value), "trade_tick_size": str(s.trade_tick_size), "spread": s.spread, "trade_mode": s.trade_mode}

    def _request(self, b: dict) -> dict:
        m = self.mt5
        is_buy = b["type"] == "BUY"
        market = b.get("order_type", "MARKET") in ("MARKET",)
        req = {"action": m.TRADE_ACTION_DEAL if market else m.TRADE_ACTION_PENDING, "symbol": b["symbol"], "volume": float(b["volume"]), "sl": float(b["sl"]), "magic": int(b.get("magic", 0)), "comment": str(b.get("comment", ""))[:31],
               "type_time": m.ORDER_TIME_GTC if not market else m.ORDER_TIME_GTC, "type_filling": m.ORDER_FILLING_IOC}
        if market:
            tick = m.symbol_info_tick(b["symbol"])
            req["type"] = m.ORDER_TYPE_BUY if is_buy else m.ORDER_TYPE_SELL
            req["price"] = tick.ask if is_buy else tick.bid
            req["deviation"] = int(float(b["deviation"]) / float(m.symbol_info(b["symbol"]).point)) if b.get("deviation") else 10
        else:
            req["type"] = m.ORDER_TYPE_BUY_LIMIT if is_buy else m.ORDER_TYPE_SELL_LIMIT
            req["price"] = float(b["price"])
        if b.get("tp"):
            req["tp"] = float(b["tp"])
        return req

    def order_check(self, b: dict) -> dict:
        if not b.get("sl"):
            return {"ok": False, "reason": "protective stop (sl) required in the same request"}
        r = self.mt5.order_check(self._request(b))
        return {"ok": r is not None and r.retcode == 0, "retcode": getattr(r, "retcode", None), "reason": getattr(r, "comment", ""), "margin": str(getattr(r, "margin", "")), "margin_free": str(getattr(r, "margin_free", ""))}

    def order_send(self, b: dict) -> dict:
        if not b.get("sl"):
            return {"status": "REJECTED", "reason": "protective stop (sl) required in the same request"}
        m = self.mt5
        r = m.order_send(self._request(b))
        if r is None:
            return {"status": "REJECTED", "reason": "order_send returned None"}
        done = r.retcode in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL, m.TRADE_RETCODE_PLACED)
        status = "FILLED" if r.retcode == m.TRADE_RETCODE_DONE else ("PARTIAL" if r.retcode == m.TRADE_RETCODE_DONE_PARTIAL else ("ACCEPTED" if r.retcode == m.TRADE_RETCODE_PLACED else "REJECTED"))
        sl_confirmed = False
        if done and getattr(r, "order", 0):
            pos = [p for p in (m.positions_get(ticket=r.order) or []) if p.ticket == r.order] if hasattr(m, "positions_get") else []
            sl_confirmed = bool(pos and float(pos[0].sl) > 0) or (r.retcode == m.TRADE_RETCODE_PLACED)
        return {"status": status, "retcode": r.retcode, "reason": getattr(r, "comment", ""), "order": getattr(r, "order", 0), "position": getattr(r, "order", 0), "volume": str(getattr(r, "volume", 0)), "price": str(getattr(r, "price", 0)) if getattr(r, "price", 0) else None,
                "arrival": str(getattr(r, "price", 0)) if getattr(r, "price", 0) else None, "sl_confirmed": sl_confirmed, "server_time_ms": int(time.time() * 1000)}

    def positions(self) -> list[dict]:
        m = self.mt5
        return [{"ticket": p.ticket, "symbol": p.symbol, "type": "BUY" if p.type == m.ORDER_TYPE_BUY else "SELL", "volume": str(p.volume), "price_open": str(p.price_open), "sl": str(p.sl) if p.sl else None, "tp": str(p.tp) if p.tp else None, "comment": p.comment, "magic": p.magic, "profit": str(p.profit)} for p in (m.positions_get() or [])]

    def orders(self) -> list[dict]:
        return [{"ticket": o.ticket, "symbol": o.symbol, "type": o.type, "volume": str(o.volume_current), "price": str(o.price_open), "sl": str(o.sl) if o.sl else None, "comment": o.comment} for o in (self.mt5.orders_get() or [])]

    def history(self, from_s: int, to_s: int) -> list[dict]:
        from datetime import datetime, timezone
        deals = self.mt5.history_deals_get(datetime.fromtimestamp(from_s, timezone.utc), datetime.fromtimestamp(to_s, timezone.utc)) or []
        return [{"ticket": d.ticket, "order": d.order, "position": d.position_id, "symbol": d.symbol, "type": d.type, "entry": d.entry, "volume": str(d.volume), "price": str(d.price), "profit": str(d.profit), "commission": str(d.commission), "swap": str(d.swap), "time_ms": int(d.time) * 1000, "comment": d.comment} for d in deals]

    def modify_sl_tp(self, position: int, sl: Optional[str], tp: Optional[str]) -> dict:
        m = self.mt5
        pos = [p for p in (m.positions_get(ticket=int(position)) or []) if p.ticket == int(position)]
        if not pos:
            return {"ok": False, "reason": "position not found"}
        p = pos[0]
        new_sl = float(sl) if sl else float(p.sl)
        # tighten-only: a stop may only move toward profit
        if p.sl and ((p.type == m.ORDER_TYPE_BUY and new_sl < float(p.sl)) or (p.type == m.ORDER_TYPE_SELL and new_sl > float(p.sl))):
            return {"ok": False, "reason": "refusing to widen protective stop"}
        r = m.order_send({"action": m.TRADE_ACTION_SLTP, "position": int(position), "symbol": p.symbol, "sl": new_sl, "tp": float(tp) if tp else float(p.tp)})
        return {"ok": r is not None and r.retcode == m.TRADE_RETCODE_DONE, "retcode": getattr(r, "retcode", None), "reason": getattr(r, "comment", "")}

    def close(self, position: int, volume: Optional[str], reason: str) -> dict:
        m = self.mt5
        pos = [p for p in (m.positions_get(ticket=int(position)) or []) if p.ticket == int(position)]
        if not pos:
            return {"status": "UNKNOWN", "reason": "position not found"}
        p = pos[0]
        tick = m.symbol_info_tick(p.symbol)
        is_buy = p.type == m.ORDER_TYPE_BUY
        req = {"action": m.TRADE_ACTION_DEAL, "position": int(position), "symbol": p.symbol, "volume": float(volume) if volume else float(p.volume), "type": m.ORDER_TYPE_SELL if is_buy else m.ORDER_TYPE_BUY,
               "price": tick.bid if is_buy else tick.ask, "deviation": 20, "magic": p.magic, "comment": f"vati-close:{reason}"[:31], "type_filling": m.ORDER_FILLING_IOC}
        r = m.order_send(req)
        ok = r is not None and r.retcode in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL)
        return {"status": "FILLED" if ok else "REJECTED", "retcode": getattr(r, "retcode", None), "reason": getattr(r, "comment", reason), "volume": str(getattr(r, "volume", 0)), "price": str(getattr(r, "price", 0)) if ok else None}


class Worker:
    def __init__(self, config: dict, terminal: Terminal, signing_key: bytes, *, clock=lambda: int(time.time() * 1000)) -> None:
        self.cfg, self.t, self.key, self.clock = config, terminal, signing_key, clock
        self.nonces = NonceStore()
        self.audit: list[dict] = []

    def _account(self, alias: str) -> dict:
        a = self.cfg["accounts"].get(alias)
        if not a:
            raise PermissionError(f"alias {alias} not configured on this worker")
        pw = Path(a["password_file"]).read_text().strip() if a.get("password_file") else a.get("password", "")
        if not self.t.login(int(a["login"]), a["server"], pw):
            raise RuntimeError(f"MT5 login failed for {alias}")
        return a

    def verify(self, req: dict) -> tuple[bool, str]:
        for k in ("op", "nonce", "issued_ms", "body", "signature"):
            if k not in req:
                return False, f"missing {k}"
        payload = {"op": req["op"], "nonce": req["nonce"], "issued_ms": req["issued_ms"], "body": req["body"]}
        sig = hmac.new(self.key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, str(req["signature"])):
            return False, "bad signature"
        now = self.clock()
        if abs(now - int(req["issued_ms"])) > SKEW_MS:
            return False, "clock skew"
        if not self.nonces.accept(int(req["nonce"]), now):
            return False, "nonce replayed"
        if req["op"] not in OPS:
            return False, "op not in contract"
        return True, "ok"

    def handle(self, req: dict) -> dict:
        ok, why = self.verify(req)
        if not ok:
            return {"error": why, "nonce": req.get("nonce"), "worker_time_ms": self.clock()}
        op, b = req["op"], req["body"]
        try:
            acc = self._account(str(b.get("alias", "")))
            a = self.t.account()
            if int(a["login"]) != int(acc["login"]):
                return {"error": "terminal logged into a different account; refusing", "nonce": req["nonce"], "worker_time_ms": self.clock()}
            if op == "sync_account":
                out = {"account": {**a, "verified": True, "server_time_ms": self.clock()}}
            elif op == "sync_symbols":
                out = {"symbols": [self.t.symbol(s) for s in b.get("symbols", [])]}
            elif op == "order_check":
                out = self.t.order_check(b)
            elif op == "order_send":
                if not a.get("trade_allowed", True):
                    out = {"status": "REJECTED", "reason": "terminal trade not allowed"}
                else:
                    out = self.t.order_send(b)
            elif op == "positions":
                out = {"positions": self.t.positions()}
            elif op == "orders":
                out = {"orders": self.t.orders()}
            elif op == "history":
                out = {"deals": self.t.history(int(b.get("from_s", 0)), int(b.get("to_s", time.time())))}
            elif op == "modify_sl_tp":
                out = self.t.modify_sl_tp(int(b["position"]), b.get("sl"), b.get("tp"))
            elif op == "close":
                out = self.t.close(int(b["position"]), b.get("volume"), str(b.get("reason", "")))
            else:
                out = {"error": "unreachable"}
        except Exception as exc:  # noqa: BLE001 — venue faults become data for the client's fail-closed path
            out = {"error": str(exc)[:200]}
        self.audit.append({"ts": self.clock(), "op": op, "alias": b.get("alias"), "result": "error" if "error" in out else (out.get("status") or "ok")})
        return {**out, "nonce": req["nonce"], "worker_time_ms": self.clock()}


def make_handler(worker: Worker):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/bridge/v1/call":
                self.send_response(404); self.end_headers(); return
            n = int(self.headers.get("Content-Length", "0"))
            if n > 65536:
                self.send_response(413); self.end_headers(); return
            try:
                req = json.loads(self.rfile.read(n))
            except ValueError:
                self.send_response(400); self.end_headers(); return
            out = json.dumps(worker.handle(req)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

        def log_message(self, fmt, *args):  # never log request bodies
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))
    return H


def serve(config_path: str, terminal: Optional[Terminal] = None) -> None:
    cfg = json.loads(Path(config_path).read_text())
    key = Path(cfg["signing_key_file"]).read_text().strip().encode()
    if len(key) < 32:
        raise SystemExit("signing key must be ≥ 32 bytes")
    worker = Worker(cfg, terminal or Terminal(), key)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cfg["cert"], cfg["key"])
    ctx.load_verify_locations(cfg["ca"])
    ctx.verify_mode = ssl.CERT_REQUIRED          # mTLS: only vati-core's client certificate is accepted
    srv = ThreadingHTTPServer((cfg.get("listen", "0.0.0.0"), int(cfg.get("port", 9443))), make_handler(worker))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(json.dumps({"listening": srv.server_address, "accounts": sorted(cfg["accounts"]), "mtls": True}))
    srv.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    serve(ap.parse_args().config)
