"""Dynamic position sizing (Rev 2 §27.1).

Rules that Rev 1 left implicit and Rev 2 makes law:

* every multiplier is clamped into [0, 1] — intelligence may only *reduce*
  risk below the mandate, never amplify it;
* a non-finite or missing multiplier is 0 (fail closed);
* lot rounding is always DOWN to the venue volume step; if the rounded size is
  below the venue minimum the answer is NO_TRADE, never "round up";
* the realised risk of the rounded size is recomputed and re-checked;
* Deriv fixed-payout / multiplier contracts use stake sizing, where the stake
  *is* the maximum loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from vati.risk.contracts import Direction, LossModel, SymbolContract

ZERO = Decimal("0")
ONE = Decimal("1")


class SizingRejected(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def clamp_multiplier(value: Any) -> Decimal:
    """Bound a multiplier into [0, 1]; anything unparseable or non-finite is 0."""
    try:
        d = Decimal(str(value))
    except Exception:  # noqa: BLE001 — any parse failure is fail-closed
        return ZERO
    if not d.is_finite():
        return ZERO
    if d < ZERO:
        return ZERO
    if d > ONE:
        return ONE
    return d


@dataclass(frozen=True)
class Multipliers:
    regime: Decimal = ONE
    confidence: Decimal = ONE
    volatility: Decimal = ONE
    liquidity: Decimal = ONE
    event_risk: Decimal = ONE
    correlation: Decimal = ONE
    drawdown: Decimal = ONE

    def clamped(self) -> "Multipliers":
        return Multipliers(
            regime=clamp_multiplier(self.regime),
            confidence=clamp_multiplier(self.confidence),
            volatility=clamp_multiplier(self.volatility),
            liquidity=clamp_multiplier(self.liquidity),
            event_risk=clamp_multiplier(self.event_risk),
            correlation=clamp_multiplier(self.correlation),
            drawdown=clamp_multiplier(self.drawdown),
        )

    def product(self) -> Decimal:
        c = self.clamped()
        p = c.regime * c.confidence * c.volatility * c.liquidity * c.event_risk * c.correlation * c.drawdown
        return clamp_multiplier(p)


@dataclass(frozen=True)
class SizingResult:
    size: Decimal  # lots (STOP_DISTANCE) or stake in account currency (FULL_STAKE)
    risk_amount: Decimal  # account currency at risk if the protective level is hit
    risk_pct: Decimal  # risk_amount / equity
    raw_size: Decimal
    multiplier_product: Decimal
    loss_model: LossModel


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= ZERO:
        raise SizingRejected("VENUE_STEP_INVALID", f"volume_step must be > 0, got {step}")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def size_stop_contract(
    *,
    equity: Decimal,
    allowed_risk_pct: Decimal,
    entry: Decimal,
    stop: Decimal,
    direction: Direction,
    contract: SymbolContract,
    multipliers: Multipliers,
) -> SizingResult:
    """Size a stop-protected position. Raises SizingRejected on any fail-closed path."""
    if contract.loss_model is not LossModel.STOP_DISTANCE:
        raise SizingRejected("LOSS_MODEL_MISMATCH", "contract is not stop-distance protected")
    if equity <= ZERO:
        raise SizingRejected("EQUITY_NON_POSITIVE", f"equity={equity}")
    if allowed_risk_pct <= ZERO:
        raise SizingRejected("RISK_NON_POSITIVE", f"allowed_risk_pct={allowed_risk_pct}")
    if direction is Direction.LONG and not stop < entry:
        raise SizingRejected("STOP_WRONG_SIDE", "LONG stop must be below entry")
    if direction is Direction.SHORT and not stop > entry:
        raise SizingRejected("STOP_WRONG_SIDE", "SHORT stop must be above entry")

    stop_distance = abs(entry - stop)
    if stop_distance < contract.min_stop_distance:
        raise SizingRejected(
            "STOP_TOO_TIGHT",
            f"stop distance {stop_distance} < venue minimum {contract.min_stop_distance}",
        )

    vppu = contract.value_per_price_unit_per_lot
    if vppu <= ZERO:
        raise SizingRejected("VENUE_VALUE_INVALID", "value per price unit per lot must be > 0")

    risk_capital = equity * allowed_risk_pct
    raw_size = risk_capital / (stop_distance * vppu)
    product = multipliers.product()
    adjusted = raw_size * product
    rounded = _round_down(adjusted, contract.volume_step)

    if rounded > contract.volume_max:
        rounded = _round_down(contract.volume_max, contract.volume_step)
    if rounded < contract.volume_min or rounded <= ZERO:
        raise SizingRejected(
            "SIZE_BELOW_VENUE_MIN",
            f"rounded size {rounded} < volume_min {contract.volume_min}; NO_TRADE rather than round up",
        )

    risk_amount = rounded * stop_distance * vppu
    risk_pct = risk_amount / equity
    if risk_amount > risk_capital:
        # Cannot happen with round-down, but the check is the contract, not the arithmetic.
        raise SizingRejected("RISK_EXCEEDS_ALLOWED", f"{risk_amount} > {risk_capital}")
    return SizingResult(rounded, risk_amount, risk_pct, raw_size, product, LossModel.STOP_DISTANCE)


def size_stake_contract(
    *,
    equity: Decimal,
    allowed_risk_pct: Decimal,
    requested_stake: Decimal | None,
    contract: SymbolContract,
    multipliers: Multipliers,
) -> SizingResult:
    """Size a fixed-payout / capped-loss contract. The stake is the maximum loss."""
    if contract.loss_model is not LossModel.FULL_STAKE:
        raise SizingRejected("LOSS_MODEL_MISMATCH", "contract is not stake-protected")
    if equity <= ZERO:
        raise SizingRejected("EQUITY_NON_POSITIVE", f"equity={equity}")
    if allowed_risk_pct <= ZERO:
        raise SizingRejected("RISK_NON_POSITIVE", f"allowed_risk_pct={allowed_risk_pct}")

    risk_capital = equity * allowed_risk_pct
    product = multipliers.product()
    raw_stake = risk_capital * product
    cap = raw_stake if requested_stake is None else min(raw_stake, requested_stake)
    if contract.max_stake is not None:
        cap = min(cap, contract.max_stake)
    stake = _round_down(cap, contract.volume_step)
    if stake < contract.volume_min or stake <= ZERO:
        raise SizingRejected("STAKE_BELOW_VENUE_MIN", f"stake {stake} < min {contract.volume_min}")
    if stake > risk_capital:
        raise SizingRejected("RISK_EXCEEDS_ALLOWED", f"{stake} > {risk_capital}")
    return SizingResult(stake, stake, stake / equity, raw_stake, product, LossModel.FULL_STAKE)


def size_illiquid_equity(
    *,
    equity: Decimal,
    allowed_risk_pct: Decimal,
    entry: Decimal,
    stop: Decimal,
    contract: SymbolContract,
    multipliers: Multipliers,
) -> SizingResult:
    """Size a long position on an order-driven exchange without stop orders.

    Per-share maximum loss = entry × (stop_fraction + liquidity_haircut).
    Shares are rounded DOWN to the board lot and capped at
    max_adv_participation × adv_20d (also rounded down to the board lot).
    Below one board lot, or ADV unknown, is NO_TRADE.
    """
    if contract.loss_model is not LossModel.ILLIQUID_EQUITY:
        raise SizingRejected("LOSS_MODEL_MISMATCH", "contract is not an illiquid-equity contract")
    if equity <= ZERO:
        raise SizingRejected("EQUITY_NON_POSITIVE", f"equity={equity}")
    if allowed_risk_pct <= ZERO:
        raise SizingRejected("RISK_NON_POSITIVE", f"allowed_risk_pct={allowed_risk_pct}")
    if entry <= ZERO or not stop < entry:
        raise SizingRejected("STOP_WRONG_SIDE", "illiquid equity is long-only; stop must be below entry")
    if contract.board_lot <= ZERO:
        raise SizingRejected("VENUE_STEP_INVALID", "board_lot must be > 0")
    if contract.adv_20d <= ZERO:
        raise SizingRejected("ADV_UNKNOWN", "average daily volume unknown; cannot bound participation")
    if contract.liquidity_haircut < ZERO or contract.max_adv_participation <= ZERO:
        raise SizingRejected("VENUE_VALUE_INVALID", "haircut/participation invalid")

    stop_fraction = (entry - stop) / entry
    if stop_fraction < contract.min_stop_distance / entry if contract.min_stop_distance > ZERO else False:
        raise SizingRejected("STOP_TOO_TIGHT", "stop inside venue minimum")
    per_share_risk = entry * (stop_fraction + contract.liquidity_haircut)
    risk_capital = equity * allowed_risk_pct
    raw_shares = risk_capital / per_share_risk
    product = multipliers.product()
    shares = _round_down(raw_shares * product, contract.board_lot)
    adv_cap = _round_down(contract.adv_20d * contract.max_adv_participation, contract.board_lot)
    if shares > adv_cap:
        shares = adv_cap
    if shares < contract.board_lot or shares <= ZERO:
        raise SizingRejected("SIZE_BELOW_VENUE_MIN", f"{shares} shares < one board lot ({contract.board_lot}) or ADV cap {adv_cap}")
    risk_amount = shares * per_share_risk
    if risk_amount > risk_capital:
        raise SizingRejected("RISK_EXCEEDS_ALLOWED", f"{risk_amount} > {risk_capital}")
    return SizingResult(shares, risk_amount, risk_amount / equity, raw_shares, product, LossModel.ILLIQUID_EQUITY)
