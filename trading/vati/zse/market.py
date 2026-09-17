"""Market specification with sourced, verification-stated facts.

Research on 2026-09-16 found the primary Zimbabwean sources (zse.co.zw,
seczim.co.zw, rbz.co.zw, zsedirect.co.zw, ctrade.co.zw) unreachable from the
build environment and secondary sources in conflict on several points. A
MarketFact therefore carries its state; the live gate refuses to trade on any
fact that is not VERIFIED against a T0/T1 source at onboarding."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Exchange(str, Enum):
    ZSE = "ZSE"      # Zimbabwe Stock Exchange, ZiG-denominated
    VFEX = "VFEX"    # Victoria Falls Stock Exchange, USD-denominated
    FINSEC = "FINSEC"  # Financial Securities Exchange (Escrow Group), alternative platform


class FactState(str, Enum):
    VERIFIED = "VERIFIED"          # read from a T0/T1 primary source, dated
    SECONDARY = "SECONDARY"        # consistent across ≥2 secondary sources
    CONFLICTING = "CONFLICTING"    # secondary sources disagree
    UNVERIFIED = "UNVERIFIED"      # single source or assumption


@dataclass(frozen=True)
class MarketFact(Generic[T]):
    value: T
    state: FactState
    sources: tuple[str, ...]
    observed: str  # ISO date
    note: str = ""

    def live_ready(self) -> bool:
        return self.state is FactState.VERIFIED


@dataclass(frozen=True)
class MarketSpec:
    exchange: Exchange
    currency: MarketFact[str]
    timezone: MarketFact[str]
    session_open: MarketFact[str]
    session_close: MarketFact[str]
    settlement_days: MarketFact[int]
    board_lot: MarketFact[int]
    counter_circuit_breaker: MarketFact[dict[str, Decimal]]
    index_halt: MarketFact[dict[str, Any]]
    short_selling_allowed: MarketFact[bool]
    stop_orders_supported: MarketFact[bool]
    order_validity: MarketFact[dict[str, int]]
    trading_system: MarketFact[str]
    regulator: MarketFact[str]
    foreign_ownership_limits: MarketFact[dict[str, Decimal]]
    retail_channels: MarketFact[tuple[str, ...]]
    api_available_to_retail: MarketFact[bool]

    def live_blockers(self) -> list[str]:
        """Names of facts a live mandate depends on that are not VERIFIED."""
        required = (
            "currency", "timezone", "session_open", "session_close", "settlement_days", "board_lot",
            "counter_circuit_breaker", "short_selling_allowed", "stop_orders_supported", "order_validity",
        )
        return [name for name in required if not getattr(self, name).live_ready()]

    def assert_live_ready(self) -> None:
        blockers = self.live_blockers()
        if blockers:
            raise RuntimeError(f"{self.exchange.value}: live trading blocked; unverified facts: {blockers}")


_OBS = "2026-09-16"

ZSE_SPEC = MarketSpec(
    exchange=Exchange.ZSE,
    currency=MarketFact("ZiG", FactState.SECONDARY, ("african-markets.com ZSE rebasing notice Apr-2024", "seczim.co.zw ZiG notice Apr-2024"), _OBS,
                        "Prices in ZiG cents since 8 Apr 2024; ZWL→ZiG at 2498.7242; ZWL retired 31 Aug 2024."),
    timezone=MarketFact("Africa/Harare", FactState.SECONDARY, ("tradinghours.com", "mystocks.africa"), _OBS),
    session_open=MarketFact("UNRESOLVED", FactState.CONFLICTING, ("tradinghours.com: 10:00", "tradingbrokers.com: 09:00", "ZSE Facebook: continuous 09:00–13:00", "algotradinglib: 09:00–15:30"), _OBS,
                            "Four secondary sources disagree; ZSE Trading Procedures PDF (zse.co.zw) unreachable at build. Verify with broker."),
    session_close=MarketFact("UNRESOLVED", FactState.CONFLICTING, ("tradinghours.com: 15:00", "tradingbrokers.com: 12:30", "ZSE Facebook: 13:00", "algotradinglib: 15:30"), _OBS),
    settlement_days=MarketFact(3, FactState.SECONDARY, ("mystocks.africa", "tradinghours.com"), _OBS, "T+3 via Chengetedzai CSD."),
    board_lot=MarketFact(100, FactState.SECONDARY, ("mystocks.africa", "ZSE Direct FAQ via search"), _OBS, "Quantities in multiples of 100."),
    counter_circuit_breaker=MarketFact({"above_1_unit": Decimal("0.15"), "below_1_unit": Decimal("0.20")}, FactState.SECONDARY,
                                       ("theexchange.africa", "equityaxis.net"), _OBS, "±15% for counters priced > 1 currency unit, ±20% below; effective 3 May 2022 (quoted in ZWL terms)."),
    index_halt=MarketFact({"threshold": Decimal("0.10"), "cool_off_minutes": 30, "direction": "upside"}, FactState.SECONDARY,
                          ("theexchange.africa", "equityaxis.net"), _OBS, "30-minute cool-off when the All Share Index moves 10% (introduced Apr 2022)."),
    short_selling_allowed=MarketFact(False, FactState.UNVERIFIED, ("assumption: no securities-lending facility documented",), _OBS),
    stop_orders_supported=MarketFact(False, FactState.UNVERIFIED, ("assumption: ZSE Direct/C-Trade document limit orders with DO/GTC validity only",), _OBS,
                                     "Design assumes NO venue stop orders; exits are software-managed with a liquidity haircut."),
    order_validity=MarketFact({"DAY": 1, "GTC": 30}, FactState.SECONDARY, ("ZSE Direct FAQ via search",), _OBS, "GTC expires after 30 calendar days."),
    trading_system=MarketFact("InfoTech Capizar ATS (order-driven, central order book) live since 6 Jul 2015; Capizar OMS offers FIX for brokers",
                              FactState.SECONDARY, ("infotechgroup.com", "africancapitalmarketsnews.com"), _OBS),
    regulator=MarketFact("Securities and Exchange Commission of Zimbabwe (SECZ), Securities Act Ch. 24:25", FactState.SECONDARY, ("seczim.co.zw via search",), _OBS),
    foreign_ownership_limits=MarketFact({"aggregate": Decimal("0.49"), "single": Decimal("0.15")}, FactState.CONFLICTING,
                                        ("RBZ framework (older): 40% aggregate / 10% single", "SECZ/daytrading.com (newer): 49% / 15%"), _OBS,
                                        "Applies to non-residents; non-resident Zimbabweans up to 70% per one source. Verify with broker/RBZ."),
    retail_channels=MarketFact(("ZSE Direct (web/Android/iOS)", "C-Trade (web/Android/iOS/USSD; ZSE+FINSEC+VFEX)", "licensed stockbroker (phone/email)"),
                               FactState.SECONDARY, ("african-markets.com", "startupbiz.co.zw", "ctrade.co.zw via search"), _OBS),
    api_available_to_retail=MarketFact(False, FactState.SECONDARY, ("ZSE Direct FAQ", "C-Trade FAQ via search"), _OBS,
                                       "No retail trading API found. DMA/FIX is institutional via a broker's Capizar OMS."),
)

VFEX_SPEC = MarketSpec(
    exchange=Exchange.VFEX,
    currency=MarketFact("USD", FactState.SECONDARY, ("marketscreener.com", "fpri.org", "maweresibanda.co.zw"), _OBS, "Settled solely in USD or convertible currency; offshore settlement permitted."),
    timezone=MarketFact("Africa/Harare", FactState.SECONDARY, ("tradinghours.com",), _OBS),
    session_open=MarketFact("UNRESOLVED", FactState.UNVERIFIED, ("vfex.exchange unreachable at build",), _OBS),
    session_close=MarketFact("UNRESOLVED", FactState.UNVERIFIED, ("vfex.exchange unreachable at build",), _OBS),
    settlement_days=MarketFact(3, FactState.UNVERIFIED, ("assumed same CSD cycle as ZSE",), _OBS),
    board_lot=MarketFact(100, FactState.UNVERIFIED, ("assumed same as ZSE",), _OBS),
    counter_circuit_breaker=MarketFact({}, FactState.UNVERIFIED, (), _OBS),
    index_halt=MarketFact({}, FactState.UNVERIFIED, (), _OBS),
    short_selling_allowed=MarketFact(False, FactState.UNVERIFIED, ("assumption",), _OBS),
    stop_orders_supported=MarketFact(False, FactState.UNVERIFIED, ("assumption",), _OBS),
    order_validity=MarketFact({"DAY": 1, "GTC": 30}, FactState.UNVERIFIED, ("assumed same as ZSE Direct",), _OBS),
    trading_system=MarketFact("ZSE Holdings subsidiary; shares ZSE ATS lineage", FactState.UNVERIFIED, ("pindula.co.zw via search",), _OBS),
    regulator=MarketFact("Victoria Falls IFSC from 5 May 2026 (SI 62 & 63), previously SECZ", FactState.SECONDARY, ("fpri.org", "thezimbabwean.co"), _OBS),
    foreign_ownership_limits=MarketFact({}, FactState.UNVERIFIED, ("VFEX incentives favour foreign investors; limits not documented in reachable sources",), _OBS),
    retail_channels=MarketFact(("C-Trade", "licensed stockbroker"), FactState.SECONDARY, ("ctrade.co.zw via search",), _OBS),
    api_available_to_retail=MarketFact(False, FactState.SECONDARY, ("C-Trade FAQ via search",), _OBS),
)
