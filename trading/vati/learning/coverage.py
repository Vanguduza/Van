"""StrategyCoverageMap (§25, TRD-ENH-070/071).

Six capsules is a production library, not a strategy universe. The map makes
the gaps visible so research is directed rather than opportunistic.

The discipline that matters: **an uncovered cell is not lost profit.** FX RANGE
is currently uncovered — every FX capsule forbids or fails to list RANGE — and
that is a research space, not a number VAN is entitled to. A cell is measured
before it is researched, and researched before anything trades it. A negative
result is a *result*: RESEARCH_NEGATIVE is a terminal state, not a gap to fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash

COVERED_CERTIFIED = "COVERED_CERTIFIED"
COVERED_LIMITED = "COVERED_LIMITED"
COVERED_RESEARCH = "COVERED_RESEARCH"
INTENTIONALLY_ABSTAIN = "INTENTIONALLY_ABSTAIN"
UNRESEARCHED = "UNRESEARCHED"
RESEARCH_NEGATIVE = "RESEARCH_NEGATIVE"
BLOCKED_DATA = "BLOCKED_DATA"

COVERAGE_STATES = (COVERED_CERTIFIED, COVERED_LIMITED, COVERED_RESEARCH,
                   INTENTIONALLY_ABSTAIN, UNRESEARCHED, RESEARCH_NEGATIVE, BLOCKED_DATA)

#: States that mean "no more research is owed here".
SETTLED_STATES = frozenset({COVERED_CERTIFIED, COVERED_LIMITED,
                            INTENTIONALLY_ABSTAIN, RESEARCH_NEGATIVE})

#: Live capsule states, mapped to coverage.
_STATE_COVERAGE = {
    "CERTIFIED_LIVE": COVERED_CERTIFIED,
    "LIMITED_LIVE": COVERED_LIMITED,
    "SHADOW": COVERED_RESEARCH,
    "DEMO": COVERED_RESEARCH,
    "VALIDATION": COVERED_RESEARCH,
    "BACKTEST": COVERED_RESEARCH,
    "RESEARCH": COVERED_RESEARCH,
}


@dataclass(frozen=True)
class CoverageCell:
    market: str
    instrument: str
    horizon: str
    regime: str
    state: str = UNRESEARCHED
    strategy_ids: tuple[str, ...] = ()
    note: str = ""

    def key(self) -> str:
        return "|".join((self.market, self.instrument, self.horizon, self.regime))

    def as_dict(self) -> dict:
        return {"market": self.market, "instrument": self.instrument, "horizon": self.horizon,
                "regime": self.regime, "state": self.state,
                "strategy_ids": list(self.strategy_ids), "note": self.note}


@dataclass(frozen=True)
class OpportunityCostEstimate:
    """What an uncovered cell might be worth — measured, never assumed."""

    cell_key: str
    share_of_tradable_time: Decimal
    historical_opportunity_count: int
    mean_spread_cost_pct: Decimal
    false_breakout_rate: Optional[Decimal] = None
    hypothetical_expectancy_R: Optional[Decimal] = None
    edge_after_cost_R: Optional[Decimal] = None

    @property
    def worth_researching(self) -> bool:
        """Only when an edge survives costs. A frequent regime with no edge
        after spread is idle time, not foregone profit."""
        return (self.edge_after_cost_R is not None
                and self.edge_after_cost_R > Decimal("0")
                and self.share_of_tradable_time > Decimal("0.05")
                and self.historical_opportunity_count >= 30)

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in self.__dict__.items()} | {
            "worth_researching": self.worth_researching}


class StrategyCoverageMap:
    def __init__(self, cells: Iterable[CoverageCell] = ()) -> None:
        self._cells: dict[str, CoverageCell] = {c.key(): c for c in cells}

    def set(self, cell: CoverageCell) -> None:
        if cell.state not in COVERAGE_STATES:
            raise ValueError(f"unknown coverage state {cell.state}")
        self._cells[cell.key()] = cell

    def get(self, market: str, instrument: str, horizon: str, regime: str) -> CoverageCell:
        key = "|".join((market, instrument, horizon, regime))
        return self._cells.get(key, CoverageCell(market, instrument, horizon, regime))

    def gaps(self) -> tuple[CoverageCell, ...]:
        """Cells that still owe research. Not "cells we are losing money in"."""
        return tuple(sorted((c for c in self._cells.values() if c.state == UNRESEARCHED),
                            key=lambda c: c.key()))

    def cells(self) -> tuple[CoverageCell, ...]:
        return tuple(sorted(self._cells.values(), key=lambda c: c.key()))

    def map_hash(self) -> str:
        return canonical_hash({"cells": [c.as_dict() for c in self.cells()]})

    @classmethod
    def from_capsules(
        cls,
        capsules: Sequence,
        *,
        regimes: Sequence[str] = ("BULL", "BEAR", "RANGE", "TRANSITION"),
        market_fn=lambda c: "ZSE" if str(c.strategy_id).startswith(("ZSE", "VFEX")) else "FX",
    ) -> "StrategyCoverageMap":
        """Derive coverage from what the registry actually declares.

        A capsule covers a regime only when it *lists* it as eligible. A regime
        it forbids, or simply never mentions, is uncovered — which is how FX
        RANGE became invisible.
        """
        m = cls()
        seen: dict[str, CoverageCell] = {}
        for cap in capsules:
            market = market_fn(cap)
            state = _STATE_COVERAGE.get(cap.state.value if hasattr(cap.state, "value") else str(cap.state),
                                        COVERED_RESEARCH)
            for instrument in sorted(cap.instruments):
                for horizon in sorted(cap.horizons):
                    for regime in regimes:
                        cell = CoverageCell(market, instrument, horizon, regime)
                        key = cell.key()
                        if regime in cap.forbidden_regimes:
                            existing = seen.get(key)
                            if existing is None:
                                seen[key] = CoverageCell(market, instrument, horizon, regime,
                                                         INTENTIONALLY_ABSTAIN, (),
                                                         f"{cap.strategy_id} forbids {regime}")
                            continue
                        if cap.eligible_regimes and regime not in cap.eligible_regimes:
                            seen.setdefault(key, cell)     # UNRESEARCHED
                            continue
                        prior = seen.get(key)
                        ids = tuple(sorted(set((prior.strategy_ids if prior else ()) + (cap.strategy_id,))))
                        seen[key] = CoverageCell(market, instrument, horizon, regime, state, ids)
        for c in seen.values():
            m.set(c)
        return m


__all__ = [
    "BLOCKED_DATA", "COVERAGE_STATES", "COVERED_CERTIFIED", "COVERED_LIMITED",
    "COVERED_RESEARCH", "INTENTIONALLY_ABSTAIN", "RESEARCH_NEGATIVE", "SETTLED_STATES",
    "UNRESEARCHED", "CoverageCell", "OpportunityCostEstimate", "StrategyCoverageMap",
]
