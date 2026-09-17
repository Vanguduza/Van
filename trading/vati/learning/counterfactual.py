"""Bounded counterfactuals (integration doc §20): six predefined variants
replayed on the same bar path with the same cost model. Output is SIMULATED
evidence with weight 0.2 and is only ever aggregated at capsule level."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

from vati.learning.episodes import CounterfactualResult
from vati.market_data.bars import Bar
from vati.risk.contracts import Direction

ZERO = Decimal("0")


class CounterfactualVariant(str, Enum):
    ENTRY_ONE_BAR_LATER = "ENTRY_ONE_BAR_LATER"
    ENTRY_ONE_BAR_EARLIER = "ENTRY_ONE_BAR_EARLIER"
    STOP_STRUCTURE_INSTEAD_OF_ATR = "STOP_STRUCTURE_INSTEAD_OF_ATR"
    HALF_SIZE = "HALF_SIZE"
    SKIP_TRADE = "SKIP_TRADE"
    REQUIRE_HTF_CONFIRMATION = "REQUIRE_HTF_CONFIRMATION"


def _simulate(bars: Sequence[Bar], *, entry_idx: int, entry: Decimal, stop: Decimal, target: Decimal, direction: Direction, qty: Decimal, vppu: Decimal, cost_per_unit: Decimal) -> tuple[Decimal, Decimal]:
    """Walk bars from entry_idx; stop before target within a bar (conservative)."""
    risk_per_unit = abs(entry - stop)
    for b in bars[entry_idx:]:
        if direction is Direction.LONG:
            if b.low <= stop:
                pnl = (stop - entry) * qty * vppu - cost_per_unit * qty; return pnl, (pnl / (risk_per_unit * qty * vppu)) if risk_per_unit else ZERO
            if b.high >= target:
                pnl = (target - entry) * qty * vppu - cost_per_unit * qty; return pnl, (pnl / (risk_per_unit * qty * vppu)) if risk_per_unit else ZERO
        else:
            if b.high >= stop:
                pnl = (entry - stop) * qty * vppu - cost_per_unit * qty; return pnl, (pnl / (risk_per_unit * qty * vppu)) if risk_per_unit else ZERO
            if b.low <= target:
                pnl = (entry - target) * qty * vppu - cost_per_unit * qty; return pnl, (pnl / (risk_per_unit * qty * vppu)) if risk_per_unit else ZERO
    last = bars[-1].close
    pnl = ((last - entry) if direction is Direction.LONG else (entry - last)) * qty * vppu - cost_per_unit * qty
    return pnl, (pnl / (risk_per_unit * qty * vppu)) if risk_per_unit else ZERO


def run_counterfactuals(*, episode_id: str, bars: Sequence[Bar], entry_idx: int, entry: Decimal, stop: Decimal, target: Decimal, direction: Direction, qty: Decimal, vppu: Decimal,
                        cost_per_unit: Decimal, base_pnl: Decimal, structure_stop: Decimal | None = None, htf_confirms: bool = True) -> list[CounterfactualResult]:
    out: list[CounterfactualResult] = []
    def add(variant, desc, pnl, r):
        out.append(CounterfactualResult(episode_id, variant.value, desc, pnl, r, base_pnl, pnl - base_pnl).sealed())
    if entry_idx + 1 < len(bars):
        e2 = bars[entry_idx + 1].open
        pnl, r = _simulate(bars, entry_idx=entry_idx + 1, entry=e2, stop=stop, target=target, direction=direction, qty=qty, vppu=vppu, cost_per_unit=cost_per_unit)
        add(CounterfactualVariant.ENTRY_ONE_BAR_LATER, f"enter at next open {e2}", pnl, r)
    if entry_idx - 1 >= 0:
        e0 = bars[entry_idx - 1].close
        pnl, r = _simulate(bars, entry_idx=entry_idx, entry=e0, stop=stop, target=target, direction=direction, qty=qty, vppu=vppu, cost_per_unit=cost_per_unit)
        add(CounterfactualVariant.ENTRY_ONE_BAR_EARLIER, f"enter at prior close {e0}", pnl, r)
    if structure_stop is not None:
        pnl, r = _simulate(bars, entry_idx=entry_idx, entry=entry, stop=structure_stop, target=target, direction=direction, qty=qty, vppu=vppu, cost_per_unit=cost_per_unit)
        add(CounterfactualVariant.STOP_STRUCTURE_INSTEAD_OF_ATR, f"structure stop {structure_stop}", pnl, r)
    pnl, r = _simulate(bars, entry_idx=entry_idx, entry=entry, stop=stop, target=target, direction=direction, qty=qty / 2, vppu=vppu, cost_per_unit=cost_per_unit)
    add(CounterfactualVariant.HALF_SIZE, "half size", pnl, r)
    add(CounterfactualVariant.SKIP_TRADE, "skip", ZERO, ZERO)
    if not htf_confirms:
        add(CounterfactualVariant.REQUIRE_HTF_CONFIRMATION, "higher-timeframe confirmation absent → skipped", ZERO, ZERO)
    else:
        add(CounterfactualVariant.REQUIRE_HTF_CONFIRMATION, "higher-timeframe confirmed → same trade", base_pnl, ZERO)
    return out
