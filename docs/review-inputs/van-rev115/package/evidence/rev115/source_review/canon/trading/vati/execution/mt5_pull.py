"""MT5 pull bridge (Rev 5 route 4): a Windows-free MT5 path.

An MQL5 Expert Advisor (deploy/van-trading-core/mql5/VanBridgeEA.mq5) runs inside the
terminal on a MetaQuotes or broker VPS and *pulls* signed commands from van-trading-core
over HTTPS every second, executes them, and reports results plus a fresh account /
position snapshot. Nothing on the trading VM ever holds the MT5 login or password: the
terminal on the VPS does. Trust is a per-alias 32-byte signing key typed into the EA's
inputs and stored behind the account's credential reference here.

Two processes share one SQLite queue (WAL): the session (`Mt5PullAdapter`) enqueues and
waits; the pull server (`create_pull_app`) hands commands to the EA and stores results.

Wire (EA → server): POST /ea/v1/{alias}/poll   JSON {ts, nonce, account, positions, results}
  headers: X-Van-Ts, X-Van-Nonce, X-Van-Signature = HMAC-SHA256(key, "{ts}\\n{nonce}\\n{alias}\\n{sha256(body)}")
Wire (server → EA): text/plain, one command per line:
  id|op|symbol|type|volume|price|sl|tp|position|comment|magic|deviation
The EA never receives a command whose op is outside ORDER_SEND, MODIFY_SL, CLOSE."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")
OPS = ("ORDER_SEND", "MODIFY_SL", "CLOSE")
SKEW_S = 60
STATE_FRESH_MS = 30_000

# P1-SEC-007. /ea/v1/{alias}/poll is the one internet-reachable route in this deployable
# and it accepted unlimited signature guesses per alias. The counter below is deliberately
# a local twenty lines rather than an import of van_gateway.auth.throttle: the bridge and
# the gateway are separate deployables that share no process and no package, and coupling
# them to share a failure counter would be worse than the duplication.
#
# Same posture as the gateway's live-path surfaces: a correct signature always passes, so
# nobody can take an account's EA offline by hammering its alias. Past the policy, wrong
# signatures are answered 429 and never reach the queue.
POLL_MAX_FAILURES = 10
POLL_WINDOW_S = 300
POLL_LOCKOUT_S = 300


# ------------------------------------------------------------------ shared queue
class BridgeQueue:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._lock = threading.Lock()
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT NOT NULL, op TEXT NOT NULL, body_json TEXT NOT NULL,
                              status TEXT NOT NULL DEFAULT 'QUEUED', result_json TEXT, created_ms INTEGER NOT NULL, taken_ms INTEGER, done_ms INTEGER)""")
        self._conn.execute("CREATE TABLE IF NOT EXISTS state (alias TEXT PRIMARY KEY, account_json TEXT NOT NULL, positions_json TEXT NOT NULL, updated_ms INTEGER NOT NULL, last_nonce TEXT)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS nonces (alias TEXT NOT NULL, nonce TEXT NOT NULL, seen_ms INTEGER NOT NULL, PRIMARY KEY(alias, nonce))")

    def enqueue(self, alias: str, op: str, body: dict, *, now_ms: int) -> int:
        if op not in OPS:
            raise ValueError(f"op {op} not in bridge contract")
        with self._lock:
            cur = self._conn.execute("INSERT INTO commands(alias, op, body_json, created_ms) VALUES (?,?,?,?)", (alias, op, json.dumps(body, sort_keys=True), now_ms))
            return int(cur.lastrowid)

    def take_pending(self, alias: str, *, now_ms: int, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT id, op, body_json FROM commands WHERE alias = ? AND status = 'QUEUED' ORDER BY id LIMIT ?", (alias, limit)).fetchall()
            out = []
            for cid, op, body in rows:
                self._conn.execute("UPDATE commands SET status = 'TAKEN', taken_ms = ? WHERE id = ?", (now_ms, cid))
                out.append({"id": cid, "op": op, **json.loads(body)})
            return out

    def complete(self, alias: str, cid: int, result: dict, *, now_ms: int) -> bool:
        with self._lock:
            n = self._conn.execute("UPDATE commands SET status = 'DONE', result_json = ?, done_ms = ? WHERE id = ? AND alias = ? AND status IN ('TAKEN', 'QUEUED')", (json.dumps(result, sort_keys=True), now_ms, cid, alias)).rowcount
            return n == 1

    def result(self, cid: int) -> Optional[dict]:
        row = self._conn.execute("SELECT status, result_json FROM commands WHERE id = ?", (cid,)).fetchone()
        if row is None or row[0] != "DONE":
            return None
        return json.loads(row[1])

    def set_state(self, alias: str, account: dict, positions: list[dict], *, now_ms: int, nonce: str) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO state(alias, account_json, positions_json, updated_ms, last_nonce) VALUES (?,?,?,?,?) ON CONFLICT(alias) DO UPDATE SET account_json=excluded.account_json, positions_json=excluded.positions_json, updated_ms=excluded.updated_ms, last_nonce=excluded.last_nonce",
                               (alias, json.dumps(account, sort_keys=True), json.dumps(positions, sort_keys=True), now_ms, nonce))

    def state(self, alias: str) -> Optional[dict]:
        row = self._conn.execute("SELECT account_json, positions_json, updated_ms FROM state WHERE alias = ?", (alias,)).fetchone()
        if row is None:
            return None
        return {"account": json.loads(row[0]), "positions": json.loads(row[1]), "updated_ms": row[2]}

    def nonce_fresh(self, alias: str, nonce: str, *, now_ms: int) -> bool:
        with self._lock:
            self._conn.execute("DELETE FROM nonces WHERE seen_ms < ?", (now_ms - 4 * SKEW_S * 1000,))
            try:
                self._conn.execute("INSERT INTO nonces(alias, nonce, seen_ms) VALUES (?,?,?)", (alias, nonce, now_ms))
                return True
            except sqlite3.IntegrityError:
                return False

    def close(self) -> None:
        self._conn.close()


def open_bridge_queue(path: str) -> BridgeQueue:
    return BridgeQueue(path or ":memory:")


# ------------------------------------------------------------------ signing (shared with the EA)
def sign_poll(key: bytes, ts: str, nonce: str, alias: str, body: bytes) -> str:
    return hmac.new(key, f"{ts}\n{nonce}\n{alias}\n{hashlib.sha256(body).hexdigest()}".encode(), hashlib.sha256).hexdigest()


def format_commands(cmds: list[dict]) -> str:
    """Pipe-delimited lines the EA parses with StringSplit. Fields never contain '|' (comments are sanitised)."""
    lines = []
    for c in cmds:
        f = [str(c["id"]), c["op"], c.get("symbol", ""), c.get("type", ""), str(c.get("volume", "")), str(c.get("price", "")), str(c.get("sl", "")), str(c.get("tp", "")), str(c.get("position", "")),
             str(c.get("comment", "")).replace("|", "/")[:31], str(c.get("magic", 0)), str(c.get("deviation", 20))]
        lines.append("|".join(f))
    return "\n".join(lines) + ("\n" if lines else "")


# ------------------------------------------------------------------ adapter (session side)
@dataclass
class Mt5PullAdapter:
    queue: BridgeQueue
    account_alias: str = "mt5_ea"
    venue: str = "mt5"
    timeout_s: float = 15.0
    clock: Callable[[], int] = field(default=lambda: int(time.time() * 1000))
    poll_s: float = 0.2

    def _state(self) -> dict:
        st = self.queue.state(self.account_alias)
        if st is None:
            raise VenueUnavailable("MT5 EA has never reported; fail closed")
        if self.clock() - st["updated_ms"] > STATE_FRESH_MS:
            raise VenueUnavailable(f"MT5 EA snapshot stale ({(self.clock() - st['updated_ms']) // 1000}s); fail closed")
        return st

    def _await(self, cid: int) -> Optional[dict]:
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            r = self.queue.result(cid)
            if r is not None:
                return r
            time.sleep(self.poll_s)
        return None

    def sync_account(self) -> AccountState:
        a = self._state()["account"]
        return AccountState(self.account_alias, Decimal(str(a["equity"])), Decimal(str(a["balance"])), a.get("currency", "USD"), bool(a.get("trade_allowed", True)) and bool(a.get("login")), bool(a.get("hedging", True)), int(a.get("server_time_ms", 0)))

    def positions(self) -> list[VenuePosition]:
        out = []
        for p in self._state()["positions"]:
            out.append(VenuePosition(str(p["ticket"]), p["symbol"], Direction.LONG if p["type"] == "BUY" else Direction.SHORT, Decimal(str(p["volume"])), Decimal(str(p["price_open"])), Decimal(str(p["sl"])) if p.get("sl") else None,
                                     str(p.get("comment", "")).replace("vati:", "") if str(p.get("comment", "")).startswith("vati:") else "", LossModel.STOP_DISTANCE))
        return out

    def heartbeat(self, *, now_ms: int) -> Health:
        st = self.queue.state(self.account_alias)
        fresh = st is not None and now_ms - st["updated_ms"] <= STATE_FRESH_MS
        return Health(fresh, int(st["account"].get("server_time_ms", now_ms)) - now_ms if fresh else 0, now_ms)

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        rej = lambda why, status="REJECTED": ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, status, ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=why).sealed()  # noqa: E731
        if cmd.protective_stop is None:
            return rej("MT5 orders require SL in the same request")
        try:
            self._state()
        except VenueUnavailable as exc:
            return rej(str(exc))
        body = {"symbol": cmd.symbol, "type": "BUY" if cmd.direction is Direction.LONG else "SELL", "volume": str(cmd.quantity), "price": str(cmd.entry_price), "sl": str(cmd.protective_stop), "tp": str(cmd.targets[0]) if cmd.targets else "",
                "comment": f"vati:{cmd.trade_intent_id}"[:31], "magic": int(cmd.decision_hash[:8], 16) % 2_147_483_647, "deviation": str(int((cmd.max_slippage or Decimal("0.0002")) * 10000)), "order_type": cmd.entry_type}
        cid = self.queue.enqueue(self.account_alias, "ORDER_SEND", body, now_ms=now_ms)
        r = self._await(cid)
        if r is None:
            return rej("EA did not report within timeout; reconcile before retrying", "UNKNOWN")
        if r.get("status") != "FILLED":
            return rej(str(r.get("reason", r.get("status", "REJECTED"))), "REJECTED" if r.get("status") != "UNKNOWN" else "UNKNOWN")
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "FILLED", Decimal(str(r.get("volume", cmd.quantity))), Decimal(str(r["price"])), cmd.entry_price, Decimal(str(r.get("arrival", r["price"]))), cmd.entry_price,
                                bool(r.get("sl_confirmed")), int(r.get("server_time_ms", now_ms)), now_ms, broker_order_id=str(r.get("order", "")), broker_position_id=str(r.get("position", "")), protective_stop_price=cmd.protective_stop if r.get("sl_confirmed") else None).sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        try:
            pos = next((p for p in self._state()["positions"] if str(p["ticket"]) == str(position_id)), None)
        except VenueUnavailable as exc:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason=str(exc)).sealed()
        if pos is None:
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason="position not found").sealed()
        old = Decimal(str(pos["sl"])) if pos.get("sl") else None
        if old is not None and ((pos["type"] == "BUY" and new_stop < old) or (pos["type"] == "SELL" and new_stop > old)):
            return ExecutionReceipt("", "", self.venue, "REJECTED", ZERO, None, ZERO, ZERO, ZERO, False, now_ms, now_ms, broker_position_id=position_id, reject_reason="refusing to widen protective stop").sealed()
        cid = self.queue.enqueue(self.account_alias, "MODIFY_SL", {"position": str(position_id), "symbol": pos["symbol"], "sl": str(new_stop), "tp": str(pos.get("tp") or "")}, now_ms=now_ms)
        r = self._await(cid)
        ok = bool(r and r.get("ok"))
        return ExecutionReceipt("", "", self.venue, "ACCEPTED" if ok else "REJECTED", ZERO, None, ZERO, ZERO, ZERO, ok, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop if ok else None, reject_reason="" if ok else str((r or {}).get("reason", "EA timeout"))).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        cid = self.queue.enqueue(self.account_alias, "CLOSE", {"position": str(position_id), "volume": str(quantity) if quantity else "", "comment": f"vati-close:{reason}"[:31]}, now_ms=now_ms)
        r = self._await(cid)
        if r is None:
            return ExecutionReceipt("", "", self.venue, "UNKNOWN", ZERO, None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=f"{reason}; EA timeout").sealed()
        return ExecutionReceipt("", "", self.venue, r.get("status", "UNKNOWN"), Decimal(str(r.get("volume", "0"))), Decimal(str(r["price"])) if r.get("price") else None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()


# ------------------------------------------------------------------ pull server (EA side)
class PollThrottle:
    """Per-alias failed-signature counter for the EA poll route."""

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, alias: str, *, now_s: float) -> int:
        """Seconds the alias must wait, or 0 if it may attempt now."""
        with self._lock:
            until = self._locked_until.get(alias, 0.0)
        return int(until - now_s) + 1 if until > now_s else 0

    def record_failure(self, alias: str, *, now_s: float) -> None:
        with self._lock:
            recent = [f for f in self._failures.get(alias, []) if f > now_s - POLL_WINDOW_S]
            recent.append(now_s)
            if len(recent) >= POLL_MAX_FAILURES:
                self._locked_until[alias] = now_s + POLL_LOCKOUT_S
                recent = []
            self._failures[alias] = recent

    def record_success(self, alias: str) -> None:
        with self._lock:
            self._failures.pop(alias, None)
            self._locked_until.pop(alias, None)


def create_pull_app(queue: BridgeQueue, key_provider: Callable[[str], Optional[bytes]], *, clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> FastAPI:
    app = FastAPI(title="Van MT5 pull bridge", version="1.0.0")
    throttle = PollThrottle()
    app.state.poll_throttle = throttle

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "van-mt5-pull-bridge", "ops": list(OPS)}

    @app.post("/ea/v1/{alias}/poll", response_class=PlainTextResponse)
    async def poll(alias: str, request: Request):
        if not alias.replace("_", "").isalnum():
            raise HTTPException(400, "bad alias")
        key = key_provider(alias)
        if not key:
            raise HTTPException(404, "unknown alias")
        body = await request.body()
        h = {k.lower(): v for k, v in request.headers.items()}
        ts, nonce, sig = h.get("x-van-ts", ""), h.get("x-van-nonce", ""), h.get("x-van-signature", "")
        now = clock()
        now_s = now / 1000

        def refuse(status: int, detail: str) -> HTTPException:
            """Count the failure; once the alias is locked, say so instead."""
            throttle.record_failure(alias, now_s=now_s)
            wait = throttle.retry_after(alias, now_s=now_s)
            if wait:
                return HTTPException(429, "too many failed attempts", headers={"Retry-After": str(wait)})
            return HTTPException(status, detail)

        if not (ts.isdigit() and nonce and sig) or abs(now // 1000 - int(ts)) > SKEW_S:
            raise refuse(401, "bad or stale signature headers")
        if not hmac.compare_digest(sign_poll(key, ts, nonce, alias, body), sig):
            raise refuse(401, "bad signature")
        throttle.record_success(alias)
        if not queue.nonce_fresh(alias, nonce, now_ms=now):
            raise HTTPException(401, "nonce replayed")
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            raise HTTPException(400, "body must be JSON")
        if "account" in data:
            queue.set_state(alias, data.get("account", {}), data.get("positions", []), now_ms=now, nonce=nonce)
        for r in data.get("results", []):
            try:
                queue.complete(alias, int(r["id"]), {k: v for k, v in r.items() if k != "id"}, now_ms=now)
            except (KeyError, ValueError, TypeError):
                continue
        return format_commands(queue.take_pending(alias, now_ms=now))

    return app


def key_provider_from_registry(registry_path: str) -> Callable[[str], Optional[bytes]]:
    """Per-alias EA signing keys from the account registry's secrets (BRIDGE_SIGNING_KEY)."""
    def provider(alias: str) -> Optional[bytes]:
        try:
            from vati.accounts import AccountRegistry
            reg = AccountRegistry(registry_path)
            a = reg.get(alias)
            if a.broker != "MT5_EA":
                return None
            k = reg.credentials(alias).get("BRIDGE_SIGNING_KEY", "")
            return k.encode() if len(k) >= 32 else None
        except Exception:  # noqa: BLE001 — unknown alias / missing secret = 404, never a stack trace to the EA
            return None
    return provider
