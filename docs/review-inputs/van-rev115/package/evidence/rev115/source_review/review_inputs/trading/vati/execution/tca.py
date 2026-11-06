"""Transaction cost analysis per fill (Rev 2 §30)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from vati.execution.base import ExecutionReceipt
from vati.risk.contracts import Direction

ZERO = Decimal("0")


@dataclass(frozen=True)
class TcaRecord:
    trade_intent_id: str
    decision_price: Decimal
    arrival_price: Decimal
    submitted_price: Decimal
    fill_price: Decimal
    spread_cost: Decimal          # half spread × qty × vppu
    slippage: Decimal             # signed, price units (positive = adverse)
    delay_cost: Decimal           # arrival - decision, adverse-signed
    fees: Decimal
    implementation_shortfall: Decimal  # total adverse cost in account currency
    modelled_cost_pct: Decimal
    realised_cost_pct: Decimal
    cost_ratio: Decimal           # realised / modelled; > 1.2 sustained = cost drift

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}


def compute_tca(r: ExecutionReceipt, *, direction: Direction, qty: Decimal, value_per_unit: Decimal, modelled_cost_pct: Decimal) -> TcaRecord:
    if r.average_fill is None or r.filled_qty <= ZERO:
        raise ValueError("TCA requires a filled receipt")
    sign = Decimal(1) if direction is Direction.LONG else Decimal(-1)
    slippage = (r.average_fill - r.submitted_price) * sign
    delay = (r.arrival_price - r.decision_price) * sign
    spread_cost = r.spread_at_submit / 2 * qty * value_per_unit
    shortfall = (slippage + delay) * qty * value_per_unit + spread_cost + r.fees
    notional = r.decision_price * qty * value_per_unit
    realised_pct = shortfall / notional if notional > ZERO else ZERO
    ratio = realised_pct / modelled_cost_pct if modelled_cost_pct > ZERO else Decimal("Infinity")
    return TcaRecord(r.trade_intent_id, r.decision_price, r.arrival_price, r.submitted_price, r.average_fill, spread_cost, slippage, delay, r.fees, shortfall, modelled_cost_pct, realised_pct, ratio)
