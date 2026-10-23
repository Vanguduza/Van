"""MT5 bridge client (Rev 2 §5.2). The Linux core never imports the MetaTrader5
library; it speaks a narrow signed request protocol to the Windows worker over
mTLS. This module holds the contract, request signing and replay protection.
Without a transport it fails closed (VenueUnavailable)."""

from __future__ import annotations

import hmac
import hashlib
import time
import secrets
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional, ClassVar

from vati.core.canonical import canonical_json
from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
from vati.execution.mt5_identity import Mt5Identity
from vati.risk.contracts import Direction, LossModel

OPS = ("sync_account", "sync_symbols", "order_check", "order_send", "positions", "orders", "history", "modify_sl_tp", "close")
ZERO = Decimal("0")


@dataclass(frozen=True)
class BridgeRequest:
    op: str
    nonce: int
    issued_ms: int
    body: dict[str, Any]
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {"op": self.op, "nonce": self.nonce, "issued_ms": self.issued_ms, "body": self.body}


class Mt5BridgeClient:
    def __init__(self, *, signing_key: bytes, transport: Optional[Callable[[dict], dict]] = None, max_skew_ms: int = 5000) -> None:
        if not signing_key:
            raise ValueError("signing key required")
        self._key, self._transport, self.max_skew_ms = signing_key, transport, max_skew_ms
        # Worker replay protection spans connections and process restarts.
        # A fresh connection gets its own random namespace; calls keep a
        # locked local sequence rather than reusing another client's nonce 1.
        self._nonce = secrets.randbits(96) << 32
        self._nonce_lock = threading.Lock()
        self.sent: list[BridgeRequest] = []

    def sign(self, req: BridgeRequest) -> BridgeRequest:
        sig = hmac.new(self._key, canonical_json(req.payload()).encode(), hashlib.sha256).hexdigest()
        return BridgeRequest(req.op, req.nonce, req.issued_ms, req.body, sig)

    def verify(self, req: BridgeRequest) -> bool:
        return hmac.compare_digest(self.sign(BridgeRequest(req.op, req.nonce, req.issued_ms, req.body)).signature, req.signature)

    def call(self, op: str, body: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        if op not in OPS:
            raise ValueError(f"op not in bridge contract: {op}")
        if self._transport is None:
            raise VenueUnavailable("MT5 bridge transport not configured; fail closed")
        with self._nonce_lock:
            self._nonce += 1
            nonce = self._nonce
        req = self.sign(BridgeRequest(op, nonce, now_ms, body))
        self.sent.append(req)
        resp = self._transport(req.__dict__)
        if resp.get("nonce") != req.nonce:
            raise VenueUnavailable("bridge response nonce mismatch (replay?)")
        if abs(int(resp.get("worker_time_ms", now_ms)) - now_ms) > self.max_skew_ms:
            raise VenueUnavailable("bridge clock skew beyond limit")
        return resp


@dataclass
class Mt5BridgeAdapter:
    #: P1-TRADE-EXEC-004: the entry types this venue really executes (the worker sends MARKET as a deal and every other type as a pending limit).
    #: The router refuses anything else instead of sending it as a different order.
    supported_entry_types: ClassVar[tuple] = ("MARKET", "LIMIT", "PASSIVE_LIMIT")
    client: Mt5BridgeClient
    account_alias: str = "fx_primary"
    venue: str = "mt5"
    clock: Callable[[], int] = field(default=lambda: int(time.time() * 1000))   # reads are signed with real time too: a worker rejects issued_ms=0 as skew
    identity: Mt5Identity | None = None

    def _call(self, op, body, *, now_ms):
        if self.identity is not None:
            # A legacy worker must refuse admission before an effectful call.
            # Every new worker also verifies this same binding inside its lock.
            if op != 'sync_account':
                self._call('sync_account', {'alias': self.account_alias}, now_ms=now_ms)
            body = {**body, 'expected_account': self.identity.as_dict()}
        response = self.client.call(op, body, now_ms=now_ms)
        if not isinstance(response, dict) or 'error' in response:
            raise VenueUnavailable('MT5 worker account operation refused or unavailable')
        if self.identity is not None:
            if response.get('identity_binding') != self.identity.as_dict():
                raise VenueUnavailable('MT5 worker did not acknowledge the registered physical account binding')
            if op == 'sync_account':
                self.identity.validate(response.get('account'))
        return response

    def sync_account(self) -> AccountState:
        r = self._call("sync_account", {"alias": self.account_alias}, now_ms=self.clock())
        a = r["account"]
        verified=a.get('verified',False);hedging=a.get('hedging',True)
        if type(verified) is not bool or type(hedging) is not bool:
            raise VenueUnavailable('MT5 account verification and topology require explicit boolean facts')
        return AccountState(self.account_alias, Decimal(str(a["equity"])), Decimal(str(a["balance"])), a["currency"], verified, hedging, int(a.get("server_time_ms", 0)))

    def positions(self) -> list[VenuePosition]:
        r = self._call("positions", {"alias": self.account_alias}, now_ms=self.clock())
        return [VenuePosition(str(p["ticket"]), p["symbol"], Direction.LONG if p["type"] == "BUY" else Direction.SHORT, Decimal(str(p["volume"])), Decimal(str(p["price_open"])),
                              Decimal(str(p["sl"])) if p.get("sl") else None, str(p.get("comment", "")).replace("vati:", ""), LossModel.STOP_DISTANCE) for p in r.get("positions", [])]

    def heartbeat(self, *, now_ms: int) -> Health:
        try:
            r = self._call("sync_account", {"alias": self.account_alias}, now_ms=now_ms)
            return Health(True, int(r.get("worker_time_ms", now_ms)) - now_ms, now_ms)
        except VenueUnavailable:
            return Health(False, 0, now_ms)

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        if cmd.protective_stop is None:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="MT5 orders require SL in the same request").sealed()
        body = {"alias": self.account_alias, "symbol": cmd.symbol, "type": "BUY" if cmd.direction is Direction.LONG else "SELL", "volume": str(cmd.quantity), "price": str(cmd.entry_price),
                "sl": str(cmd.protective_stop), "tp": str(cmd.targets[0]) if cmd.targets else None, "deviation": str(cmd.max_slippage) if cmd.max_slippage else None,
                "comment": f"vati:{cmd.trade_intent_id}", "magic": int(cmd.decision_hash[:8], 16) % 2_147_483_647, "order_type": cmd.entry_type}
        chk = self._call("order_check", body, now_ms=now_ms)
        if chk.get("ok") is not True:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=str(chk.get("reason", "order_check failed"))).sealed()
        r = self._call("order_send", body, now_ms=now_ms)
        filled = Decimal(str(r.get("volume", "0")))
        stop_confirmed=r.get('sl_confirmed') is True
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, r.get("status", "UNKNOWN"), filled, Decimal(str(r["price"])) if r.get("price") else None,
                                cmd.entry_price, Decimal(str(r.get("arrival", cmd.entry_price))), cmd.entry_price, stop_confirmed, int(r.get("server_time_ms", now_ms)), now_ms,
                                broker_order_id=str(r.get("order", "")), broker_position_id=str(r.get("position", "")), protective_stop_price=cmd.protective_stop if stop_confirmed else None,
                                reject_reason=str(r.get("reason") or r.get("error") or "") if r.get("status", "UNKNOWN") in ("REJECTED", "UNKNOWN") else "").sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        r = self._call("modify_sl_tp", {"alias": self.account_alias, "position": position_id, "sl": str(new_stop)}, now_ms=now_ms)
        ok=r.get('ok');status='ACCEPTED' if ok is True else 'REJECTED' if ok is False else 'UNKNOWN'
        return ExecutionReceipt("", "", self.venue, status, ZERO, None, ZERO, ZERO, ZERO, ok is True, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop if ok is True else None).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        r = self._call("close", {"alias": self.account_alias, "position": position_id, "volume": str(quantity) if quantity else None, "reason": reason}, now_ms=now_ms)
        return ExecutionReceipt("", "", self.venue, r.get("status", "UNKNOWN"), Decimal(str(r.get("volume", "0"))), Decimal(str(r["price"])) if r.get("price") else None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()
