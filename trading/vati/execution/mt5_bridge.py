"""MT5 bridge client (Rev 2 §5.2). The Linux core never imports the MetaTrader5
library; it speaks a narrow signed request protocol to the Windows worker over
mTLS. This module holds the contract, request signing and replay protection.
Without a transport it fails closed (VenueUnavailable)."""

from __future__ import annotations

import hmac
import hashlib
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from vati.core.canonical import canonical_json
from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition, VenueUnavailable
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
        self._key, self._transport, self._nonce, self.max_skew_ms = signing_key, transport, 0, max_skew_ms
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
        self._nonce += 1
        req = self.sign(BridgeRequest(op, self._nonce, now_ms, body))
        self.sent.append(req)
        resp = self._transport(req.__dict__)
        if resp.get("nonce") != req.nonce:
            raise VenueUnavailable("bridge response nonce mismatch (replay?)")
        if abs(int(resp.get("worker_time_ms", now_ms)) - now_ms) > self.max_skew_ms:
            raise VenueUnavailable("bridge clock skew beyond limit")
        return resp


@dataclass
class Mt5BridgeAdapter:
    client: Mt5BridgeClient
    account_alias: str = "fx_primary"
    venue: str = "mt5"
    clock: Callable[[], int] = field(default=lambda: int(time.time() * 1000))   # reads are signed with real time too: a worker rejects issued_ms=0 as skew

    def sync_account(self) -> AccountState:
        r = self.client.call("sync_account", {"alias": self.account_alias}, now_ms=self.clock())
        a = r["account"]
        return AccountState(self.account_alias, Decimal(str(a["equity"])), Decimal(str(a["balance"])), a["currency"], bool(a.get("verified")), bool(a.get("hedging", True)), int(a.get("server_time_ms", 0)))

    def positions(self) -> list[VenuePosition]:
        r = self.client.call("positions", {"alias": self.account_alias}, now_ms=self.clock())
        return [VenuePosition(str(p["ticket"]), p["symbol"], Direction.LONG if p["type"] == "BUY" else Direction.SHORT, Decimal(str(p["volume"])), Decimal(str(p["price_open"])),
                              Decimal(str(p["sl"])) if p.get("sl") else None, str(p.get("comment", "")).replace("vati:", ""), LossModel.STOP_DISTANCE) for p in r.get("positions", [])]

    def heartbeat(self, *, now_ms: int) -> Health:
        try:
            r = self.client.call("sync_account", {"alias": self.account_alias}, now_ms=now_ms)
            return Health(True, int(r.get("worker_time_ms", now_ms)) - now_ms, now_ms)
        except VenueUnavailable:
            return Health(False, 0, now_ms)

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        if cmd.protective_stop is None:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="MT5 orders require SL in the same request").sealed()
        body = {"alias": self.account_alias, "symbol": cmd.symbol, "type": "BUY" if cmd.direction is Direction.LONG else "SELL", "volume": str(cmd.quantity), "price": str(cmd.entry_price),
                "sl": str(cmd.protective_stop), "tp": str(cmd.targets[0]) if cmd.targets else None, "deviation": str(cmd.max_slippage) if cmd.max_slippage else None,
                "comment": f"vati:{cmd.trade_intent_id}", "magic": int(cmd.decision_hash[:8], 16) % 2_147_483_647, "order_type": cmd.entry_type}
        chk = self.client.call("order_check", body, now_ms=now_ms)
        if not chk.get("ok"):
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason=str(chk.get("reason", "order_check failed"))).sealed()
        r = self.client.call("order_send", body, now_ms=now_ms)
        filled = Decimal(str(r.get("volume", "0")))
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, r.get("status", "UNKNOWN"), filled, Decimal(str(r["price"])) if r.get("price") else None,
                                cmd.entry_price, Decimal(str(r.get("arrival", cmd.entry_price))), cmd.entry_price, bool(r.get("sl_confirmed")), int(r.get("server_time_ms", now_ms)), now_ms,
                                broker_order_id=str(r.get("order", "")), broker_position_id=str(r.get("position", "")), protective_stop_price=cmd.protective_stop if r.get("sl_confirmed") else None,
                                reject_reason=str(r.get("reason") or r.get("error") or "") if r.get("status", "UNKNOWN") in ("REJECTED", "UNKNOWN") else "").sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        r = self.client.call("modify_sl_tp", {"alias": self.account_alias, "position": position_id, "sl": str(new_stop)}, now_ms=now_ms)
        return ExecutionReceipt("", "", self.venue, "ACCEPTED" if r.get("ok") else "REJECTED", ZERO, None, ZERO, ZERO, ZERO, bool(r.get("ok")), now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop if r.get("ok") else None).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        r = self.client.call("close", {"alias": self.account_alias, "position": position_id, "volume": str(quantity) if quantity else None, "reason": reason}, now_ms=now_ms)
        return ExecutionReceipt("", "", self.venue, r.get("status", "UNKNOWN"), Decimal(str(r.get("volume", "0"))), Decimal(str(r["price"])) if r.get("price") else None, ZERO, ZERO, ZERO, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()
