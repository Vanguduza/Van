"""Transaction-cost schedule for ZSE and VFEX equities.

Buy-side ZSE (mystocks.africa / ZSE Investors Guide as quoted 2026-09-16):
brokerage 0.92%, VAT on brokerage 0.138%, CSD levy 0.10%, stamp duty 0.25%,
ZSE levy 0.10%, SECZ levy 0.16%, investor-protection levy 0.025% = 1.693%.
Sell-side: same without stamp duty, plus capital-gains withholding tax on
gross proceeds. The CGWT rate is CONFLICTING across sources (1%; 2% announced
"effective 28 June"; 4% if held < 270 days / 1.5% if ≥ 270 days). The schedule
takes the rate as a parameter and defaults to the most punitive short-hold
figure so that expectancy is never flattered."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class CostSchedule:
    exchange: str
    brokerage: Decimal
    vat_on_brokerage: Decimal
    csd_levy: Decimal
    stamp_duty_buy: Decimal
    exchange_levy: Decimal
    regulator_levy: Decimal
    investor_protection_levy: Decimal
    cgwt_short_hold: Decimal      # capital-gains withholding on gross proceeds, short holding
    cgwt_long_hold: Decimal       # after long_hold_days
    long_hold_days: int
    dividend_wht_resident: Decimal
    dividend_wht_non_resident: Decimal
    imtt_on_transfer: Decimal     # intermediated money transfer tax on funding legs
    fact_state: str

    @property
    def common(self) -> Decimal:
        return self.brokerage + self.vat_on_brokerage + self.csd_levy + self.exchange_levy + self.regulator_levy + self.investor_protection_levy

    def buy_pct(self) -> Decimal:
        return self.common + self.stamp_duty_buy

    def sell_pct(self, holding_days: int) -> Decimal:
        cgwt = self.cgwt_long_hold if holding_days >= self.long_hold_days else self.cgwt_short_hold
        return self.common + cgwt


ZSE_EQUITY_COSTS = CostSchedule(
    exchange="ZSE",
    brokerage=Decimal("0.0092"), vat_on_brokerage=Decimal("0.00138"), csd_levy=Decimal("0.0010"), stamp_duty_buy=Decimal("0.0025"),
    exchange_levy=Decimal("0.0010"), regulator_levy=Decimal("0.0016"), investor_protection_levy=Decimal("0.00025"),
    cgwt_short_hold=Decimal("0.04"), cgwt_long_hold=Decimal("0.015"), long_hold_days=270,
    dividend_wht_resident=Decimal("0.10"), dividend_wht_non_resident=Decimal("0.10"),
    imtt_on_transfer=Decimal("0.02"),  # ZiG electronic transfers
    fact_state="SECONDARY; CGWT CONFLICTING (1% / 2% / 4%-1.5% by holding period) — verify with broker contract note",
)

VFEX_EQUITY_COSTS = CostSchedule(
    exchange="VFEX",
    brokerage=Decimal("0.0092"), vat_on_brokerage=Decimal("0.00138"), csd_levy=Decimal("0.0010"), stamp_duty_buy=Decimal("0.0025"),
    exchange_levy=Decimal("0.0010"), regulator_levy=Decimal("0.0016"), investor_protection_levy=Decimal("0.00025"),
    cgwt_short_hold=ZERO, cgwt_long_hold=ZERO, long_hold_days=0,  # VFEX incentive: exempt from CGWT
    dividend_wht_resident=Decimal("0.10"), dividend_wht_non_resident=Decimal("0.05"),  # 5% for foreign investors
    imtt_on_transfer=Decimal("0.01"),  # USD electronic transfers
    fact_state="UNVERIFIED for levies (assumed ZSE schedule; VFEX advertises lower fees); CGWT exemption and 5% non-resident dividend WHT SECONDARY",
)


@dataclass(frozen=True)
class CostBreakdown:
    buy_pct: Decimal
    sell_pct: Decimal
    round_trip_pct: Decimal
    breakeven_move_pct: Decimal  # price must rise this fraction just to exit flat


def round_trip(schedule: CostSchedule, holding_days: int) -> CostBreakdown:
    b = schedule.buy_pct()
    s = schedule.sell_pct(holding_days)
    # Buy at P paying P(1+b); sell at P(1+m) receiving P(1+m)(1-s). Breakeven m solves (1+m)(1-s) = 1+b.
    m = (Decimal("1") + b) / (Decimal("1") - s) - Decimal("1")
    return CostBreakdown(b, s, b + s, m)


def breakeven_move(schedule: CostSchedule, holding_days: int) -> Decimal:
    return round_trip(schedule, holding_days).breakeven_move_pct
