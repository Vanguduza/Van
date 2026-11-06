"""Deterministic paper/simulation adapter. Fills at entry ± half spread ±
slippage; attaches the protective stop atomically unless a stop rejection is
injected (to exercise the flatten path); marks positions against prices so
venue stops and targets fire. No randomness."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, StopMode, VenuePosition
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")


@dataclass
class PaperAdapter:
    venue: str = "paper"
    account_alias: str = "paper_primary"
    equity: Decimal = Decimal("10000")
    currency: str = "USD"
    spread: Decimal = Decimal("0.00010")
    slippage: Decimal = Decimal("0.00002")
    value_per_price_unit_per_lot: Decimal = Decimal("100000")
    inject_reject_stop: bool = False
    inject_disconnect: bool = False
    inject_reject_order: bool = False
    _positions: dict[str, dict] = field(default_factory=dict)
    _seq: int = 0
    realised_pnl: Decimal = ZERO
    closed: list[dict] = field(default_factory=list)
    last_price: dict[str, Decimal] = field(default_factory=dict)

    def sync_account(self) -> AccountState:
        unreal = sum((self._unrealised(p) for p in self._positions.values()), ZERO)
        return AccountState(self.account_alias, self.equity + unreal, self.equity, self.currency, verified=not self.inject_disconnect)

    def _unrealised(self, p: dict) -> Decimal:
        px = self.last_price.get(p["symbol"], p["entry"])
        sign = Decimal(1) if p["direction"] is Direction.LONG else Decimal(-1)
        return (px - p["entry"]) * sign * p["qty"] * p["vppu"]

    def positions(self) -> list[VenuePosition]:
        return [VenuePosition(pid, p["symbol"], p["direction"], p["qty"], p["entry"], p["stop"], p["intent"], p["loss_model"]) for pid, p in self._positions.items()]

    def heartbeat(self, *, now_ms: int) -> Health:
        return Health(not self.inject_disconnect, 0, now_ms)

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        if self.inject_disconnect:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "UNKNOWN", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="disconnected").sealed()
        if self.inject_reject_order:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="injected").sealed()
        half = self.spread / 2
        fill = cmd.entry_price + (half + self.slippage) if cmd.direction is Direction.LONG else cmd.entry_price - (half + self.slippage)
        if cmd.max_slippage is not None and abs(fill - cmd.entry_price) > cmd.max_slippage + half:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="max_slippage").sealed()
        self._seq += 1
        pid = f"P{self._seq}"
        stop_ok = cmd.stop_mode is StopMode.SOFTWARE or (cmd.protective_stop is not None and not self.inject_reject_stop)
        self._positions[pid] = {"symbol": cmd.symbol, "direction": cmd.direction, "qty": cmd.quantity, "entry": fill,
                                "stop": cmd.protective_stop if stop_ok and cmd.stop_mode is StopMode.VENUE else None,
                                "intent": cmd.trade_intent_id, "loss_model": cmd.loss_model, "vppu": self.value_per_price_unit_per_lot if cmd.loss_model is LossModel.STOP_DISTANCE else Decimal(1),
                                "targets": cmd.targets, "opened_ms": now_ms}
        self.last_price[cmd.symbol] = cmd.entry_price
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "FILLED", cmd.quantity, fill, cmd.entry_price, cmd.entry_price, cmd.entry_price,
                                stop_ok, now_ms, now_ms, broker_order_id=f"O{self._seq}", broker_position_id=pid, spread_at_submit=self.spread,
                                protective_stop_price=cmd.protective_stop if stop_ok else None).sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        p = self._positions[position_id]
        p["stop"] = new_stop
        return ExecutionReceipt(p["intent"], "", self.venue, "ACCEPTED", ZERO, None, p["entry"], p["entry"], p["entry"], True, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        p = self._positions[position_id]
        qty = p["qty"] if quantity is None else min(quantity, p["qty"])
        px = self.last_price.get(p["symbol"], p["entry"])
        half = self.spread / 2
        fill = px - (half + self.slippage) if p["direction"] is Direction.LONG else px + (half + self.slippage)
        sign = Decimal(1) if p["direction"] is Direction.LONG else Decimal(-1)
        pnl = (fill - p["entry"]) * sign * qty * p["vppu"]
        self.realised_pnl += pnl; self.equity += pnl
        self.closed.append({"position_id": position_id, "intent": p["intent"], "symbol": p["symbol"], "qty": qty, "entry": p["entry"], "exit": fill, "pnl": pnl, "reason": reason, "closed_ms": now_ms})
        p["qty"] -= qty
        if p["qty"] <= ZERO:
            del self._positions[position_id]
        return ExecutionReceipt(p["intent"], "", self.venue, "FILLED", qty, fill, px, px, px, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()

    def mark(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExecutionReceipt]:
        """Move the market; fire venue stops (and targets) deterministically."""
        self.last_price[symbol] = (bid + ask) / 2
        out = []
        for pid, p in list(self._positions.items()):
            if p["symbol"] != symbol:
                continue
            if p["direction"] is Direction.LONG:
                if p["stop"] is not None and bid <= p["stop"]:
                    self.last_price[symbol] = p["stop"]; out.append(self.close(pid, None, now_ms=now_ms, reason="VENUE_STOP"))
                elif p["targets"] and bid >= p["targets"][0]:
                    self.last_price[symbol] = p["targets"][0]; out.append(self.close(pid, None, now_ms=now_ms, reason="TARGET"))
            else:
                if p["stop"] is not None and ask >= p["stop"]:
                    self.last_price[symbol] = p["stop"]; out.append(self.close(pid, None, now_ms=now_ms, reason="VENUE_STOP"))
                elif p["targets"] and ask <= p["targets"][0]:
                    self.last_price[symbol] = p["targets"][0]; out.append(self.close(pid, None, now_ms=now_ms, reason="TARGET"))
        self.last_price[symbol] = (bid + ask) / 2
        return out
