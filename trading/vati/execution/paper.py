"""Deterministic paper/simulation adapter. Fills at entry ± half spread ±
slippage; attaches the protective stop atomically unless a stop rejection is
injected (to exercise the flatten path); marks positions against prices so
venue stops and targets fire. No randomness.

P1-TRADE-EXEC-004: entry orders fill only at prices the market reaches. A LIMIT
that is not marketable against the last mark, and a STOP that has not been
triggered, rest as pending orders (receipt ACCEPTED) and fill in `mark()` when the
quote crosses them, or expire. Before, every LIMIT filled at its requested price
whether or not the market traded there, which made breakout backtests fiction."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import ClassVar, Optional

from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, StopMode, VenuePosition
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")
DAY_MS = 86_400_000


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
    pending: dict[str, dict] = field(default_factory=dict)
    supported_entry_types: ClassVar[tuple] = ("MARKET", "LIMIT", "PASSIVE_LIMIT", "STOP")

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
        mid = self.last_price.get(cmd.symbol)
        long_ = cmd.direction is Direction.LONG
        if cmd.entry_type == "LIMIT" and mid is not None:
            # At-touch LIMIT (a buy at or above the bid, a sell at or below the ask) crosses
            # the spread within the slippage bound, as before; one further away waits.
            if not ((cmd.entry_price >= mid - half) if long_ else (cmd.entry_price <= mid + half)):
                return self._rest(cmd, now_ms=now_ms)
        if cmd.entry_type == "PASSIVE_LIMIT" and mid is not None:
            # Passive: never crosses; fills only once the opposite side reaches the limit.
            if not ((mid + half <= cmd.entry_price) if long_ else (mid - half >= cmd.entry_price)):
                return self._rest(cmd, now_ms=now_ms)
        if cmd.entry_type == "STOP":
            triggered = mid is not None and ((mid + half >= cmd.entry_price) if long_ else (mid - half <= cmd.entry_price))
            if not triggered:
                return self._rest(cmd, now_ms=now_ms)
            ref = (mid + half) if long_ else (mid - half)
            fill = ref + self.slippage if long_ else ref - self.slippage
            return self._open(cmd, fill, now_ms=now_ms, reference=cmd.entry_price)
        fill = cmd.entry_price + (half + self.slippage) if long_ else cmd.entry_price - (half + self.slippage)
        return self._open(cmd, fill, now_ms=now_ms, reference=cmd.entry_price)

    def _rest(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        self._seq += 1
        oid = f"O{self._seq}"
        expires = cmd.expires_at_ms if cmd.expires_at_ms is not None else now_ms + DAY_MS
        self.pending[oid] = {"cmd": cmd, "expires_ms": expires}
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "ACCEPTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price,
                                False, now_ms, now_ms, broker_order_id=oid, reject_reason="PENDING").sealed()

    def _open(self, cmd: OrderCommand, fill: Decimal, *, now_ms: int, reference: Decimal, reason: str = "") -> ExecutionReceipt:
        half = self.spread / 2
        if cmd.max_slippage is not None and abs(fill - reference) > cmd.max_slippage + half:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, reject_reason="max_slippage").sealed()
        self._seq += 1
        pid = f"P{self._seq}"
        stop_ok = cmd.stop_mode is StopMode.SOFTWARE or (cmd.protective_stop is not None and not self.inject_reject_stop)
        self._positions[pid] = {"symbol": cmd.symbol, "direction": cmd.direction, "qty": cmd.quantity, "entry": fill,
                                "stop": cmd.protective_stop if stop_ok and cmd.stop_mode is StopMode.VENUE else None,
                                "intent": cmd.trade_intent_id, "loss_model": cmd.loss_model, "vppu": self.value_per_price_unit_per_lot if cmd.loss_model is LossModel.STOP_DISTANCE else Decimal(1),
                                "targets": cmd.targets, "opened_ms": now_ms}
        if not reason:
            self.last_price[cmd.symbol] = cmd.entry_price
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "FILLED", cmd.quantity, fill, cmd.entry_price, cmd.entry_price, cmd.entry_price,
                                stop_ok, now_ms, now_ms, broker_order_id=f"O{self._seq}", broker_position_id=pid, spread_at_submit=self.spread,
                                protective_stop_price=cmd.protective_stop if stop_ok else None, reject_reason=reason).sealed()

    def _work_pending(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExecutionReceipt]:
        """Fill resting entries the quote now crosses; expire the stale ones."""
        out: list[ExecutionReceipt] = []
        for oid, o in list(self.pending.items()):
            cmd = o["cmd"]
            if cmd.symbol != symbol:
                continue
            if now_ms >= o["expires_ms"]:
                del self.pending[oid]
                out.append(ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "EXPIRED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price,
                                            False, now_ms, now_ms, broker_order_id=oid, reject_reason="PENDING_EXPIRED").sealed())
                continue
            long_ = cmd.direction is Direction.LONG
            fill = None
            if cmd.entry_type == "STOP":
                if long_ and ask >= cmd.entry_price:
                    fill = ask + self.slippage
                elif not long_ and bid <= cmd.entry_price:
                    fill = bid - self.slippage
            else:  # LIMIT / PASSIVE_LIMIT: fills at the limit once the quote reaches it
                if long_ and ask <= cmd.entry_price:
                    fill = cmd.entry_price
                elif not long_ and bid >= cmd.entry_price:
                    fill = cmd.entry_price
            if fill is None:
                continue
            del self.pending[oid]
            rec = self._open(cmd, fill, now_ms=now_ms, reference=cmd.entry_price, reason="PENDING_FILLED")
            if rec.status != "FILLED":
                rec = ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "EXPIRED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price,
                                       False, now_ms, now_ms, broker_order_id=oid, reject_reason=f"PENDING_CANCELLED_{rec.reject_reason}").sealed()
            out.append(rec)
        return out

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        p = self._positions[position_id]
        p["stop"] = new_stop
        return ExecutionReceipt(p["intent"], "", self.venue, "ACCEPTED", ZERO, None, p["entry"], p["entry"], p["entry"], True, now_ms, now_ms, broker_position_id=position_id, protective_stop_price=new_stop).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        p = self._positions[position_id]
        if quantity is not None and (not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= ZERO):
            raise ValueError("paper close quantity must be finite and positive")
        qty = p["qty"] if quantity is None else min(quantity, p["qty"])
        px = self.last_price.get(p["symbol"], p["entry"])
        half = self.spread / 2
        fill = px - (half + self.slippage) if p["direction"] is Direction.LONG else px + (half + self.slippage)
        sign = Decimal(1) if p["direction"] is Direction.LONG else Decimal(-1)
        pnl = (fill - p["entry"]) * sign * qty * p["vppu"]
        self.realised_pnl += pnl; self.equity += pnl
        # Distinct reductions can have equal timestamps and prices. This local
        # identity labels a cash delta; it is not a venue ordering guarantee.
        self.closed.append({"close_id": f"{position_id}:close:{len(self.closed)+1}",
            "pnl_scope": "EXECUTION_DELTA", "position_id": position_id, "intent": p["intent"], "symbol": p["symbol"], "qty": qty, "entry": p["entry"], "exit": fill, "pnl": pnl, "pnl_basis": "GROSS_PRICE_MOVEMENT", "reason": reason, "closed_ms": now_ms})
        p["qty"] -= qty
        if p["qty"] <= ZERO:
            del self._positions[position_id]
        return ExecutionReceipt(p["intent"], "", self.venue, "FILLED", qty, fill, px, px, px, True, now_ms, now_ms, broker_position_id=position_id, reject_reason=reason).sealed()

    def mark(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExecutionReceipt]:
        """Move the market; fill or expire resting entries; fire venue stops (and targets) deterministically."""
        self.last_price[symbol] = (bid + ask) / 2
        out = self._work_pending(symbol, bid, ask, now_ms=now_ms)
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
