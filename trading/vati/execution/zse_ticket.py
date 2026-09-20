"""OWNER_TICKET channel for ZSE/VFEX (Rev 3 D.6). VAN prepares a ticket from a
sealed decision; the owner enters it on ZSE Direct / C-Trade (A4) and confirms
the contract note; VAN records the fill and reconciles against CSD holdings.
VAN never operates the apps."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.core.canonical import canonical_hash
from vati.execution.base import AccountState, ExecutionReceipt, Health, OrderCommand, VenuePosition
from vati.risk.contracts import Direction, LossModel

ZERO = Decimal("0")


@dataclass(frozen=True)
class OwnerTicket:
    ticket_id: str
    trade_intent_id: str
    decision_hash: str
    exchange: str
    symbol: str
    side: str
    quantity_shares: Decimal
    limit_price: Decimal
    time_in_force: str
    software_stop: Optional[Decimal]
    instructions: str
    source_position_id: str = ""
    ticket_hash: str = ""

    def render(self) -> str:
        return (f"VAN OWNER TICKET {self.ticket_id}\n{self.exchange}: {self.side} {self.quantity_shares} {self.symbol} @ limit {self.limit_price} ({self.time_in_force})\n"
                f"Software stop (VAN-managed exit, no venue stop): {self.software_stop}\nDecision hash: {self.decision_hash}\n{self.instructions}\n"
                f"Confirm with: fill price, filled quantity, contract-note reference. Do not exceed the quantity or price above.")


@dataclass
class OwnerTicketAdapter:
    venue: str = "zse"
    account_alias: str = "zse_primary"
    equity: Decimal = Decimal("0")
    currency: str = "ZiG"
    csd_verified: bool = False
    tickets: dict[str, OwnerTicket] = field(default_factory=dict)
    _positions: dict[str, dict] = field(default_factory=dict)
    _confirmed_tickets: set[str] = field(default_factory=set)
    _seq: int = 0

    def sync_account(self) -> AccountState:
        return AccountState(self.account_alias, self.equity, self.equity, self.currency, verified=self.csd_verified, hedging_mode=False)

    def positions(self) -> list[VenuePosition]:
        return [VenuePosition(pid, p["symbol"], Direction.LONG, p["qty"], p["entry"], None, p["intent"], LossModel.ILLIQUID_EQUITY) for pid, p in self._positions.items()]

    def heartbeat(self, *, now_ms: int) -> Health:
        return Health(True, 0, now_ms)

    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt:
        if cmd.direction is not Direction.LONG:
            return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "REJECTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, False, now_ms, now_ms, "OWNER_TICKET", reject_reason="long only").sealed()
        self._seq += 1
        tid = f"T{self._seq}-{cmd.decision_hash[:8]}"
        t = OwnerTicket(tid, cmd.trade_intent_id, cmd.decision_hash, self.venue.upper(), cmd.symbol, "BUY", cmd.quantity, cmd.entry_price, cmd.time_in_force, cmd.protective_stop,
                        "Enter exactly this order on ZSE Direct or C-Trade, or instruct your licensed stockbroker. This is an owner action (A4).")
        t = OwnerTicket(**{**t.__dict__, "ticket_hash": canonical_hash({k: v for k, v in t.__dict__.items() if k != "ticket_hash"})})
        self.tickets[tid] = t
        return ExecutionReceipt(cmd.trade_intent_id, cmd.decision_hash, self.venue, "ACCEPTED", ZERO, None, cmd.entry_price, cmd.entry_price, cmd.entry_price, True, now_ms, now_ms,
                                "OWNER_TICKET", broker_order_id=tid).sealed()

    def confirm(self, ticket_id: str, *, fill_price: Decimal, filled_qty: Decimal, contract_note_ref: str, now_ms: int) -> ExecutionReceipt:
        t = self.tickets[ticket_id]
        if ticket_id in self._confirmed_tickets:
            raise ValueError(f"ticket {ticket_id} is already confirmed")
        if not contract_note_ref.strip():
            raise ValueError("contract note reference required")
        if fill_price <= ZERO or filled_qty <= ZERO:
            raise ValueError("fill price and quantity must be positive")
        if filled_qty > t.quantity_shares:
            raise ValueError("confirmation exceeds ticket quantity")
        if t.side == "BUY":
            if t.limit_price > ZERO and fill_price > t.limit_price:
                raise ValueError("confirmation exceeds ticket quantity or limit price")
            pid = f"CSD-{ticket_id}"
            self._positions[pid] = {
                "symbol": t.symbol, "qty": filled_qty, "entry": fill_price,
                "intent": t.trade_intent_id,
            }
        elif t.side == "SELL":
            pid = t.source_position_id
            if not pid:
                matches = [
                    position_id for position_id, position in self._positions.items()
                    if position["symbol"] == t.symbol
                    and position["intent"] == t.trade_intent_id
                ]
                if len(matches) != 1:
                    raise ValueError("SELL ticket cannot be joined to exactly one open position")
                pid = matches[0]
            position = self._positions.get(pid)
            if position is None:
                raise ValueError(f"SELL ticket source position {pid!r} is not open")
            if filled_qty > position["qty"]:
                raise ValueError("SELL confirmation exceeds open position quantity")
            if t.limit_price > ZERO and fill_price < t.limit_price:
                raise ValueError("SELL confirmation is below ticket limit price")
            remaining = position["qty"] - filled_qty
            if remaining == ZERO:
                del self._positions[pid]
            else:
                position["qty"] = remaining
        else:
            raise ValueError(f"unsupported owner ticket side {t.side!r}")

        self._confirmed_tickets.add(ticket_id)
        return ExecutionReceipt(
            t.trade_intent_id, t.decision_hash, self.venue, "OWNER_EXECUTED",
            filled_qty, fill_price, t.limit_price, t.limit_price, t.limit_price,
            True, now_ms, now_ms, "OWNER_TICKET",
            broker_order_id=ticket_id, broker_position_id=pid,
            reject_reason=f"contract_note:{contract_note_ref}",
        ).sealed()

    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt:
        p = self._positions[position_id]
        return ExecutionReceipt(p["intent"], "", self.venue, "ACCEPTED", ZERO, None, p["entry"], p["entry"], p["entry"], True, now_ms, now_ms, "OWNER_TICKET", broker_position_id=position_id, protective_stop_price=new_stop).sealed()

    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt:
        p = self._positions[position_id]
        qty = p["qty"] if quantity is None else min(quantity, p["qty"])
        self._seq += 1
        tid = f"T{self._seq}-SELL"
        ticket = OwnerTicket(
            ticket_id=tid,
            trade_intent_id=p["intent"],
            decision_hash="",
            exchange=self.venue.upper(),
            symbol=p["symbol"],
            side="SELL",
            quantity_shares=qty,
            limit_price=ZERO,
            time_in_force="DAY",
            software_stop=None,
            instructions=f"Exit ticket ({reason}). Sell at best available limit.",
            source_position_id=position_id,
        )
        ticket = OwnerTicket(**{
            **ticket.__dict__,
            "ticket_hash": canonical_hash({
                k: v for k, v in ticket.__dict__.items() if k != "ticket_hash"
            }),
        })
        self.tickets[tid] = ticket
        return ExecutionReceipt(
            p["intent"], "", self.venue, "ACCEPTED", ZERO, None,
            p["entry"], p["entry"], p["entry"], True, now_ms, now_ms,
            "OWNER_TICKET", broker_order_id=tid,
            broker_position_id=position_id, reject_reason=reason,
        ).sealed()
