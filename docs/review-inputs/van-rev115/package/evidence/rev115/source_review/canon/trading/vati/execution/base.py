"""Venue adapter contract (Rev 2 §29, §41). Adapters translate a sealed
OrderCommand into venue calls and venue truth into ExecutionReceipts. They
never decide size and never see a model."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol

from vati.core.canonical import canonical_hash
from vati.risk.contracts import Direction, LossModel


class VenueUnavailable(RuntimeError):
    pass


class StopMode(str, Enum):
    VENUE = "VENUE"        # protective stop held by the venue (MT5/Deriv CFD)
    SOFTWARE = "SOFTWARE"  # no venue stop exists (ZSE/VFEX); ProtectionManager owns the exit


@dataclass(frozen=True)
class OrderCommand:
    trade_intent_id: str
    decision_hash: str
    idempotency_key: str
    account_alias: str
    venue: str
    symbol: str
    direction: Direction
    entry_type: str            # MARKET | LIMIT | STOP | PASSIVE_LIMIT | CONTRACT_BUY
    quantity: Decimal          # lots, shares or stake
    entry_price: Decimal
    protective_stop: Optional[Decimal]
    stop_mode: StopMode
    loss_model: LossModel
    targets: tuple[Decimal, ...] = ()
    time_in_force: str = "DAY"  # DAY | GTC30
    max_slippage: Optional[Decimal] = None
    expires_at_ms: Optional[int] = None
    strategy_id: str = ""
    strategy_version: str = ""
    #: Cross-host account runtime fence. None is allowed only on paths whose
    #: router was not configured with a lease fence.
    lease_epoch: Optional[int] = None
    command_hash: str = ""

    def sealed(self) -> "OrderCommand":
        body = {k: v for k, v in self.__dict__.items() if k != "command_hash"}
        return OrderCommand(**{**self.__dict__, "command_hash": canonical_hash(body)})


@dataclass(frozen=True)
class ExecutionReceipt:
    trade_intent_id: str
    decision_hash: str
    venue: str
    status: str                       # ACCEPTED | PARTIAL | FILLED | REJECTED | CANCELLED | EXPIRED | UNKNOWN | OWNER_EXECUTED | BROKER_CONFIRMED
    filled_qty: Decimal
    average_fill: Optional[Decimal]
    decision_price: Decimal
    arrival_price: Decimal
    submitted_price: Decimal
    protective_stop_confirmed: bool
    broker_time_unix_ms: int
    received_time_unix_ms: int
    execution_channel: str = "ADAPTER"
    broker_order_id: str = ""
    broker_position_id: str = ""
    reject_reason: str = ""
    spread_at_submit: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    protective_stop_price: Optional[Decimal] = None
    receipt_hash: str = ""

    def sealed(self) -> "ExecutionReceipt":
        body = {k: v for k, v in self.__dict__.items() if k != "receipt_hash"}
        return ExecutionReceipt(**{**self.__dict__, "receipt_hash": canonical_hash(body)})


@dataclass(frozen=True)
class VenuePosition:
    position_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    entry_price: Decimal
    stop_price: Optional[Decimal]
    trade_intent_id: str        # from magic/comment/passthrough; "" if unknown → orphan
    loss_model: LossModel = LossModel.STOP_DISTANCE


@dataclass(frozen=True)
class AccountState:
    """What the venue says about the account.

    P0-TRADE-006 — this carried equity and balance only. There was no margin, no free
    margin and no margin level anywhere in the stack, so the Risk Authority sized by stop
    distance with no visibility of what the broker would actually allow. A position sized
    correctly for risk can still be refused, or can trigger a margin call, and VAN could
    not see either coming.

    The three margin fields are optional and default to None rather than to a comfortable
    number. None means "the venue did not tell us", which the margin gate treats as
    unknown; defaulting to, say, a 1000% margin level would be the hardcoded-healthy
    defect this sits next to (P0-TRADE-002).
    """

    account_alias: str
    equity: Decimal
    balance: Decimal
    currency: str
    verified: bool
    hedging_mode: bool = True
    server_time_unix_ms: int = 0
    #: Margin currently committed to open positions.
    used_margin: Optional[Decimal] = None
    #: Equity not committed: what a new position can draw on.
    free_margin: Optional[Decimal] = None
    #: equity / used_margin as a percentage. Below the broker's margin call level,
    #: positions start being closed by the venue rather than by VAN.
    margin_level_pct: Optional[Decimal] = None


@dataclass(frozen=True)
class Health:
    connected: bool
    server_offset_ms: int
    last_heartbeat_ms: int


class VenueAdapter(Protocol):
    venue: str

    def sync_account(self) -> AccountState: ...
    def positions(self) -> list[VenuePosition]: ...
    def submit(self, cmd: OrderCommand, *, now_ms: int) -> ExecutionReceipt: ...
    def modify_stop(self, position_id: str, new_stop: Decimal, *, now_ms: int) -> ExecutionReceipt: ...
    def close(self, position_id: str, quantity: Optional[Decimal], *, now_ms: int, reason: str) -> ExecutionReceipt: ...
    def heartbeat(self, *, now_ms: int) -> Health: ...
