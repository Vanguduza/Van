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
    spread_cost: Decimal          # diagnostic half spread × qty × vppu; already embedded in fill cost
    slippage: Decimal             # signed, price units (positive = adverse)
    delay_cost: Decimal           # arrival - decision, adverse-signed
    fees: Decimal
    implementation_shortfall: Decimal  # total adverse cost in account currency
    modelled_cost_pct: Decimal
    realised_cost_pct: Decimal
    cost_ratio: Decimal           # realised / modelled; > 1.2 sustained = cost drift
    submission_cost: Decimal = ZERO  # signed submitted - arrival, price units
    filled_quantity: Decimal | None = None
    contract_value_per_price_unit: Decimal | None = None
    reference_notional: Decimal | None = None
    measurement_version: str = "tca/2.0.0"

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()}


def compute_tca(r: ExecutionReceipt, *, direction: Direction, qty: Decimal, value_per_unit: Decimal, modelled_cost_pct: Decimal) -> TcaRecord:
    values = (r.filled_qty, r.average_fill, r.decision_price, r.arrival_price,
              r.submitted_price, r.spread_at_submit, r.fees, qty, value_per_unit, modelled_cost_pct)
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in values):
        raise ValueError("TCA requires finite Decimal economic inputs")
    if r.average_fill is None or r.filled_qty <= ZERO:
        raise ValueError("TCA requires a filled receipt")
    if qty != r.filled_qty:
        raise ValueError("TCA quantity must equal the receipt's filled quantity")
    if (min(r.decision_price, r.arrival_price, r.submitted_price, r.average_fill, value_per_unit) <= ZERO
        or r.spread_at_submit < ZERO or modelled_cost_pct < ZERO):
        raise ValueError("TCA requires positive prices and contract value, nonnegative spread and modelled cost")
    if not isinstance(direction, Direction):
        raise ValueError("TCA direction must be LONG or SHORT")
    sign = Decimal(1) if direction is Direction.LONG else Decimal(-1)
    slippage = (r.average_fill - r.submitted_price) * sign
    delay = (r.arrival_price - r.decision_price) * sign
    submission = (r.submitted_price - r.arrival_price) * sign
    spread_cost = r.spread_at_submit / 2 * qty * value_per_unit
    # Fill-versus-reference already includes the spread. Keep it as a diagnostic,
    # and retain favorable fills/rebates with their actual negative cost sign.
    shortfall = (r.average_fill - r.decision_price) * sign * qty * value_per_unit + r.fees
    notional = r.decision_price * qty * value_per_unit
    realised_pct = shortfall / notional if notional > ZERO else ZERO
    ratio = realised_pct / modelled_cost_pct if modelled_cost_pct > ZERO else Decimal("Infinity")
    return TcaRecord(r.trade_intent_id, r.decision_price, r.arrival_price, r.submitted_price, r.average_fill, spread_cost, slippage, delay, r.fees, shortfall, modelled_cost_pct, realised_pct, ratio,
        submission, qty, value_per_unit, notional)
