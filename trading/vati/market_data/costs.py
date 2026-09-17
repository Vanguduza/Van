"""FX/CFD cost model (Rev 3 D2): spread curve by session and event proximity,
commission, slippage conditioned on volatility, financing for the holding
period. Produces the `round_trip_cost_pct` the Risk Authority gates on."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from vati.market_data.calendars import Session

ZERO = Decimal("0")


@dataclass(frozen=True)
class SpreadCurve:
    """Typical spread (price units) per session; multipliers for event proximity."""
    base: dict[Session, Decimal]
    event_window_multiplier: Decimal = Decimal("4")   # inside a Tier-1 blackout/quiet window
    unverified_multiplier: Decimal = Decimal("6")     # CLOSED/UNVERIFIED sessions: assume the worst

    def spread(self, session: Session, in_event_window: bool) -> Decimal:
        s = self.base.get(session)
        if s is None:
            s = max(self.base.values()) * self.unverified_multiplier
        return s * self.event_window_multiplier if in_event_window else s


@dataclass(frozen=True)
class FxCostModel:
    spread_curve: SpreadCurve
    commission_per_lot_round_trip: Decimal   # account currency
    contract_size: Decimal                   # units per lot
    swap_long_per_lot_day: Decimal           # account currency (negative = cost)
    swap_short_per_lot_day: Decimal
    slippage_base_frac_of_spread: Decimal = Decimal("0.5")   # expected slippage as fraction of spread, normal vol
    slippage_vol_sensitivity: Decimal = Decimal("1.0")       # × volatility percentile above 0.5

    def round_trip_cost_pct(self, *, price: Decimal, session: Session, in_event_window: bool, vol_percentile: Decimal,
                            holding_days: Decimal, direction_long: bool, order_passive: bool = False) -> Decimal:
        if price <= ZERO:
            return Decimal("Infinity")
        spread = self.spread_curve.spread(session, in_event_window)
        spread_cost = spread if not order_passive else spread / Decimal("2")   # passive entry saves half a spread
        vol_extra = max(ZERO, vol_percentile - Decimal("0.5")) * self.slippage_vol_sensitivity
        slippage = spread * (self.slippage_base_frac_of_spread + vol_extra) * Decimal("2")   # in and out
        notional_per_lot = price * self.contract_size
        commission_pct = self.commission_per_lot_round_trip / notional_per_lot if notional_per_lot > ZERO else ZERO
        swap = self.swap_long_per_lot_day if direction_long else self.swap_short_per_lot_day
        financing_pct = max(ZERO, -swap) * holding_days / notional_per_lot if notional_per_lot > ZERO else ZERO
        return (spread_cost + slippage) / price + commission_pct + financing_pct
