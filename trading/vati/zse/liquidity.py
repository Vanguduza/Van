"""Liquidity model for thin, order-driven markets.

Evidence: after Econet delisted on 31 Mar 2026 (about one third of ZSE market
cap, its most traded counter) monthly turnover fell 84%; on 3 Sep 2026 only 27
counters traded (103 deals). Small orders move prices; a software stop can be
gapped through by a single print. The haircut and the participation cap bound
that risk deterministically."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class LiquidityProfile:
    adv_20d_shares: Decimal
    adv_20d_value: Decimal          # in trading currency
    trading_days_of_20: int         # sessions with ≥1 trade in the last 20
    median_spread_pct: Decimal      # (ask-bid)/mid from the price sheet where available
    circuit_band: Decimal           # per-counter limit fraction (0.15 / 0.20)


def liquidity_haircut(profile: LiquidityProfile) -> Decimal:
    """Fraction of price to add to the stop distance as gap/impact loss.

    Components: half the median spread (crossing to exit), a thin-trading
    penalty rising as fewer of the last 20 sessions traded, and a floor of one
    circuit band when the counter traded on fewer than half the sessions
    (an exit may take more than one session and can gap the full band).
    """
    if profile.adv_20d_shares <= ZERO or profile.trading_days_of_20 <= 0:
        return Decimal("Infinity")
    spread_leg = profile.median_spread_pct / Decimal("2")
    thin = Decimal(20 - profile.trading_days_of_20) / Decimal(20)  # 0 (always trades) → 0.95
    penalty = thin * profile.circuit_band
    haircut = spread_leg + penalty
    if profile.trading_days_of_20 < 10:
        haircut = max(haircut, profile.circuit_band)
    return haircut


def participation_cap(profile: LiquidityProfile, board_lot: Decimal, max_participation: Decimal = Decimal("0.10")) -> Decimal:
    """Largest order in shares that stays within max_participation of ADV, in whole board lots."""
    if board_lot <= ZERO or max_participation <= ZERO:
        return ZERO
    raw = profile.adv_20d_shares * max_participation
    return (raw / board_lot).to_integral_value(rounding=ROUND_DOWN) * board_lot
