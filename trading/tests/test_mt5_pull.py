"""MT5 pull bridge: session adapter ↔ shared queue ↔ pull server ↔ (simulated) MQL5 Expert Advisor."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from vati.execution.base import OrderCommand, StopMode, VenueUnavailable
from vati.execution.mt5_pull import (
    OPS,
    POLL_MAX_FAILURES,
    BridgeQueue,
    Mt5PullAdapter,
    create_pull_app,
    format_commands,
    sign_poll,
)
from vati.risk.contracts import Direction, LossModel

D = Decimal
KEY = b"e" * 32


class EaSimulator:
    """Does exactly what VanBridgeEA.mq5 does: sign, POST snapshot+results, parse pipe lines, execute against a toy terminal."""
    def __init__(self, client: TestClient, alias: str, key: bytes, clock):
        self.client, self.alias, self.key, self.clock = client, alias, key, clock
        self.positions: dict[int, dict] = {}
        self.next_ticket = 900
        self.results: list[dict] = []
        self.balance = 10_000.0
        self.n = 0
        self.trade_allowed = True
        self.log: list[str] = []

    def snapshot(self):
        eq = self.balance + sum(p["profit"] for p in self.positions.values())
        return {"login": 12345678, "equity": eq, "balance": self.balance, "currency": "USD", "trade_allowed": self.trade_allowed, "hedging": True, "server_time_ms": self.clock()}

    def poll(self, key=None, nonce=None, ts=None):
        self.n += 1
        body = json.dumps({"account": self.snapshot(), "positions": list(self.positions.values()), "results": self.results}).encode()
        self.results = []
        ts = ts or str(self.clock() // 1000); nonce = nonce or f"n{self.n}"
        sig = sign_poll(key or self.key, ts, nonce, self.alias, body)
        r = self.client.post(f"/ea/v1/{self.alias}/poll", content=body, headers={"x-van-ts": ts, "x-van-nonce": nonce, "x-van-signature": sig, "content-type": "application/json"})
        if r.status_code != 200:
            self.log.append(f"{r.status_code} {r.text}"); return r
        for line in r.text.splitlines():
            f = line.split("|")
            cid, op = int(f[0]), f[1]
            if op == "ORDER_SEND":
                if not f[6]:
                    self.results.append({"id": cid, "status": "REJECTED", "reason": "no sl"}); continue
                t = self.next_ticket; self.next_ticket += 1
                px = 1.10008 if f[3] == "BUY" else 1.10000
                self.positions[t] = {"ticket": t, "symbol": f[2], "type": f[3], "volume": float(f[4]), "price_open": px, "sl": float(f[6]), "tp": float(f[7]) if f[7] else 0.0, "comment": f[9], "magic": int(f[10]), "profit": 0.0}
                self.results.append({"id": cid, "status": "FILLED", "order": t, "position": t, "volume": f[4], "price": px, "sl_confirmed": True, "server_time_ms": self.clock()})
            elif op == "MODIFY_SL":
                p = self.positions.get(int(f[8]))
                if p: p["sl"] = float(f[6]); self.results.append({"id": cid, "ok": True})
                else: self.results.append({"id": cid, "ok": False, "reason": "no position"})
            elif op == "CLOSE":
                p = self.positions.pop(int(f[8]), None)
                self.results.append({"id": cid, "status": "FILLED" if p else "UNKNOWN", "volume": p["volume"] if p else 0, "price": 1.1050 if p else None})
            else:
                self.log.append(f"unknown op {op}")
        return r


@pytest.fixture
def bridge(tmp_path):
    clock = {"ms": 1_700_000_000_000}
    q = BridgeQueue(tmp_path / "bridge.sqlite")
    app = create_pull_app(q, lambda alias: KEY if alias == "mt5_ea" else None, clock=lambda: clock["ms"])
    client = TestClient(app)
    ea = EaSimulator(client, "mt5_ea", KEY, lambda: clock["ms"])
    adapter = Mt5PullAdapter(BridgeQueue(tmp_path / "bridge.sqlite"), account_alias="mt5_ea", clock=lambda: clock["ms"], timeout_s=3, poll_s=0.02)
    return q, client, ea, adapter, clock


def test_adapter_fails_closed_until_the_ea_reports(bridge):
    q, client, ea, adapter, clock = bridge
    with pytest.raises(VenueUnavailable, match="never reported"):
        adapter.sync_account()
    assert not adapter.heartbeat(now_ms=clock["ms"]).connected
    assert ea.poll().status_code == 200
    acct = adapter.sync_account()
    assert acct.equity == D("10000.0") and acct.verified and adapter.heartbeat(now_ms=clock["ms"]).connected
    clock["ms"] += 60_000
    with pytest.raises(VenueUnavailable, match="stale"):
        adapter.positions()
    assert client.get("/health").json()["ops"] == list(OPS)


def test_signature_nonce_skew_and_unknown_alias(bridge):
    q, client, ea, adapter, clock = bridge
    assert ea.poll(key=b"x" * 32).status_code == 401
    assert ea.poll(ts=str(clock["ms"] // 1000 - 600)).status_code == 401
    assert ea.poll(nonce="dup").status_code == 200 and ea.poll(nonce="dup").status_code == 401
    ea.alias = "ghost"; assert ea.poll().status_code == 404; ea.alias = "mt5_ea"
    assert q.state("ghost") is None


def test_round_trip_order_stop_close_through_the_ea(bridge):
    q, client, ea, adapter, clock = bridge
    ea.poll()
    stop = threading.Event()
    def pump():
        while not stop.is_set():
            ea.poll(); time.sleep(0.05)
    th = threading.Thread(target=pump, daemon=True); th.start()
    try:
        cmd = OrderCommand("intent-7", "d" * 64, "k", "mt5_ea", "mt5", "EURUSD", Direction.LONG, "MARKET", D("0.10"), D("1.10008"), D("1.09808"), StopMode.VENUE, LossModel.STOP_DISTANCE, targets=(D("1.10608"),), max_slippage=D("0.0002")).sealed()
        rec = adapter.submit(cmd, now_ms=clock["ms"])
        assert rec.status == "FILLED" and rec.protective_stop_confirmed and rec.protective_stop_price == D("1.09808") and rec.broker_position_id == "900" and rec.average_fill == D("1.10008")
        assert ea.positions[900]["comment"] == "vati:intent-7" and ea.positions[900]["sl"] == 1.09808 and ea.positions[900]["tp"] == 1.10608
        time.sleep(0.1)
        pos = adapter.positions()
        assert len(pos) == 1 and pos[0].trade_intent_id == "intent-7" and pos[0].stop_price == D("1.09808")
        assert adapter.modify_stop("900", D("1.09900"), now_ms=clock["ms"]).status == "ACCEPTED"
        time.sleep(0.1)
        assert adapter.modify_stop("900", D("1.09000"), now_ms=clock["ms"]).reject_reason == "refusing to widen protective stop"
        assert adapter.modify_stop("111", D("1.1"), now_ms=clock["ms"]).reject_reason == "position not found"
        closed = adapter.close("900", None, now_ms=clock["ms"], reason="TARGET")
        assert closed.status == "FILLED" and closed.average_fill == D("1.105")
        time.sleep(0.1)
        assert adapter.positions() == []
        no_sl = OrderCommand(**{**cmd.__dict__, "protective_stop": None, "command_hash": ""}).sealed()
        assert adapter.submit(no_sl, now_ms=clock["ms"]).reject_reason == "MT5 orders require SL in the same request"
        assert not ea.log
    finally:
        stop.set(); th.join(timeout=1)
    # an EA that stops polling → orders time out as UNKNOWN, never as silent success
    fast = Mt5PullAdapter(q, account_alias="mt5_ea", clock=lambda: clock["ms"], timeout_s=0.2, poll_s=0.02)
    r = fast.submit(cmd, now_ms=clock["ms"])
    assert r.status == "UNKNOWN" and "reconcile" in r.reject_reason


def test_command_lines_are_parseable_and_never_carry_pipes():
    txt = format_commands([{"id": 5, "op": "ORDER_SEND", "symbol": "EURUSD", "type": "BUY", "volume": "0.1", "price": "1.1", "sl": "1.09", "tp": "", "comment": "vati:a|b", "magic": 7, "deviation": 20}])
    assert txt == "5|ORDER_SEND|EURUSD|BUY|0.1|1.1|1.09|||vati:a/b|7|20\n" and format_commands([]) == ""
    assert sign_poll(KEY, "1", "n", "a", b"{}") == sign_poll(KEY, "1", "n", "a", b"{}") and sign_poll(KEY, "1", "n", "a", b"{}") != sign_poll(KEY, "2", "n", "a", b"{}")
    q = BridgeQueue()
    with pytest.raises(ValueError):
        q.enqueue("a", "SHELL", {}, now_ms=1)


def test_signature_guessing_on_the_poll_route_is_throttled(bridge):
    """P1-SEC-007: the one internet-reachable route here took unlimited signature guesses."""
    q, client, ea, adapter, clock = bridge
    codes = [ea.poll(key=b"x" * 32).status_code for _ in range(POLL_MAX_FAILURES + 1)]
    assert codes[0] == 401, "the first wrong signature is simply refused"
    assert codes[-1] == 429, f"guessing was never throttled: {codes}"


def test_a_throttled_poll_names_the_wait(bridge):
    q, client, ea, adapter, clock = bridge
    for _ in range(POLL_MAX_FAILURES + 1):
        r = ea.poll(key=b"x" * 32)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_a_correctly_signed_poll_still_works_while_the_alias_is_throttled(bridge):
    """Nobody may take an account's EA offline by hammering its alias."""
    q, client, ea, adapter, clock = bridge
    for _ in range(POLL_MAX_FAILURES + 1):
        ea.poll(key=b"x" * 32)
    assert client.app.state.poll_throttle.retry_after("mt5_ea", now_s=clock["ms"] / 1000) > 0
    assert ea.poll().status_code == 200, "a genuine EA was locked out by an attacker"


def test_a_successful_poll_clears_the_counter(bridge):
    q, client, ea, adapter, clock = bridge
    for _ in range(POLL_MAX_FAILURES - 1):
        ea.poll(key=b"x" * 32)
    assert ea.poll().status_code == 200
    assert ea.poll(key=b"x" * 32).status_code == 401, "the counter did not reset after a success"


def test_one_alias_cannot_throttle_another(bridge, tmp_path):
    q, client, ea, adapter, clock = bridge
    app = create_pull_app(
        q,
        lambda alias: KEY if alias in {"mt5_ea", "mt5_other"} else None,
        clock=lambda: clock["ms"],
    )
    other = TestClient(app)
    attacked = EaSimulator(other, "mt5_ea", KEY, lambda: clock["ms"])
    for _ in range(POLL_MAX_FAILURES + 1):
        attacked.poll(key=b"x" * 32)
    assert app.state.poll_throttle.retry_after("mt5_ea", now_s=clock["ms"] / 1000) > 0
    assert app.state.poll_throttle.retry_after("mt5_other", now_s=clock["ms"] / 1000) == 0


def test_a_replayed_nonce_is_not_counted_as_a_credential_guess(bridge):
    """The signature was genuine, so a replay must not push the real EA toward a lockout."""
    q, client, ea, adapter, clock = bridge
    assert ea.poll(nonce="same").status_code == 200
    for _ in range(POLL_MAX_FAILURES + 2):
        assert ea.poll(nonce="same").status_code == 401
    assert client.app.state.poll_throttle.retry_after("mt5_ea", now_s=clock["ms"] / 1000) == 0
