"""Multi-timeframe market state over the existing bar lake (§6, TRD-ENH-010/011).

`build_market_state` answers every question from one bar sequence, so a strategy
cannot say "H4 structure, H1 regime, M15 setup, M5 timing" — it can only say
"the indicator on whatever bars I was handed".

This assembles one `TimeframeMarketState` per required timeframe and holds them
together. It does **not** create a second market-data store: the lake already
keeps M1/M5/M15/H1/H4/D1 with slice manifests, and `lake_bar_source` already
takes a timeframe.

Two rules carry the weight:

* **No fusion.** Timeframes answer different questions; averaging an H4 and an
  M5 indicator produces a number that answers neither. A fused feature must be
  its own separately validated definition.
* **As-of discipline.** For a decision at `T`, no constituent may consume a bar
  that closes after `T`. An unfinished H4 bar leaking into an M5 decision is
  look-ahead that backtests cannot detect and live trading cannot reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.intelligence.market_state import MarketState
from vati.market_data.bars import Bar

#: Ordered coarse→fine so a fusion policy can be stated without re-deriving it.
TIMEFRAME_ORDER = ("D1", "H4", "H1", "M15", "M5", "M1")

#: Roles a capsule may bind. `primary` is the single-timeframe capsule's contract.
TIMEFRAME_ROLES = ("structural", "regime", "setup", "execution", "primary")

FUSION_POLICY_VERSION = "mtf-fusion/1.0.0"


class MtfError(ValueError):
    """An MTF assembly that would be unsound rather than merely incomplete."""


@dataclass(frozen=True)
class TimeframeContract:
    """Which timeframe answers which question, for one capsule."""

    roles: Mapping[str, str]

    @staticmethod
    def from_capsule(data: Mapping[str, object]) -> Optional["TimeframeContract"]:
        raw = data.get("timeframe_contract")
        if not isinstance(raw, dict) or not raw:
            return None
        bad = [r for r in raw if r not in TIMEFRAME_ROLES]
        if bad:
            raise MtfError(f"unknown timeframe role(s): {sorted(bad)}")
        bad_tf = [tf for tf in raw.values() if tf not in TIMEFRAME_ORDER]
        if bad_tf:
            raise MtfError(f"unknown timeframe(s): {sorted(bad_tf)}")
        return TimeframeContract(dict(raw))

    @property
    def required_timeframes(self) -> tuple[str, ...]:
        """Deduplicated, coarse→fine, so assembly order is deterministic."""
        wanted = set(self.roles.values())
        return tuple(tf for tf in TIMEFRAME_ORDER if tf in wanted)

    def timeframe_for(self, role: str) -> Optional[str]:
        return self.roles.get(role)


@dataclass(frozen=True)
class TimeframeMarketState:
    """One timeframe's view. Thin wrapper so the constituent is hashable alone."""

    symbol: str
    timeframe: str
    as_of_ms: int
    state: MarketState
    bar_count: int
    timeframe_state_hash: str = ""

    def sealed(self) -> "TimeframeMarketState":
        payload = {
            "symbol": self.symbol, "timeframe": self.timeframe, "as_of_ms": self.as_of_ms,
            "bar_count": self.bar_count, "state_hash": self.state.state_hash,
        }
        return TimeframeMarketState(**{**self.__dict__, "timeframe_state_hash": canonical_hash(payload)})

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe, "as_of_ms": self.as_of_ms,
            "bar_count": self.bar_count, "timeframe_state_hash": self.timeframe_state_hash,
        }


@dataclass(frozen=True)
class MultiTimeframeMarketState:
    symbol: str
    as_of_ms: int
    constituent_states: Mapping[str, TimeframeMarketState]
    required_timeframes: tuple[str, ...]
    missing_timeframes: tuple[str, ...] = ()
    fusion_policy_version: str = FUSION_POLICY_VERSION
    mtf_state_hash: str = ""

    @property
    def complete(self) -> bool:
        return not self.missing_timeframes

    def state_for(self, timeframe: str) -> Optional[MarketState]:
        c = self.constituent_states.get(timeframe)
        return c.state if c else None

    def for_role(self, contract: TimeframeContract, role: str) -> Optional[MarketState]:
        tf = contract.timeframe_for(role)
        return self.state_for(tf) if tf else None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "as_of_ms": self.as_of_ms,
            "required_timeframes": list(self.required_timeframes),
            "missing_timeframes": list(self.missing_timeframes),
            "fusion_policy_version": self.fusion_policy_version,
            # Ordered pairs: the hash must not depend on dict iteration order.
            "constituents": [
                [tf, self.constituent_states[tf].timeframe_state_hash]
                for tf in self.required_timeframes if tf in self.constituent_states
            ],
            "mtf_state_hash": self.mtf_state_hash,
        }

    def sealed(self) -> "MultiTimeframeMarketState":
        d = self.as_dict(); d.pop("mtf_state_hash")
        return MultiTimeframeMarketState(**{**self.__dict__, "mtf_state_hash": canonical_hash(d)})


def closed_bars_at(bars: Sequence[Bar], as_of_ms: int) -> list[Bar]:
    """Only bars that had finished by `as_of_ms`.

    The whole look-ahead question lives in this comparison. A bar whose
    `end_ms` is in the future is still forming; using it means the backtest saw
    a candle the live system could not have.
    """
    return [b for b in bars if b.end_ms <= as_of_ms]


def build_multi_timeframe_state(
    *,
    symbol: str,
    as_of_ms: int,
    required_timeframes: Sequence[str],
    bars_for: Callable[[str], Sequence[Bar]],
    state_builder: Callable[..., MarketState],
    minimum_bars: int = 2,
) -> MultiTimeframeMarketState:
    """Assemble one state per timeframe from the lake, coarse→fine.

    `bars_for(timeframe)` returns that timeframe's history; `state_builder`
    is the existing `build_market_state` bound to everything symbol-specific.
    A timeframe with too little closed history is recorded as missing rather
    than silently built from a short window.
    """
    unknown = [tf for tf in required_timeframes if tf not in TIMEFRAME_ORDER]
    if unknown:
        raise MtfError(f"unknown timeframe(s): {sorted(unknown)}")

    ordered = tuple(tf for tf in TIMEFRAME_ORDER if tf in set(required_timeframes))
    constituents: dict[str, TimeframeMarketState] = {}
    missing: list[str] = []

    for tf in ordered:
        closed = closed_bars_at(bars_for(tf), as_of_ms)
        if len(closed) < minimum_bars:
            missing.append(tf)
            continue
        state = state_builder(bars=closed, timeframe=tf, now_ms=as_of_ms)
        constituents[tf] = TimeframeMarketState(
            symbol=symbol, timeframe=tf, as_of_ms=closed[-1].end_ms,
            state=state, bar_count=len(closed),
        ).sealed()

    return MultiTimeframeMarketState(
        symbol=symbol, as_of_ms=as_of_ms, constituent_states=constituents,
        required_timeframes=ordered, missing_timeframes=tuple(missing),
    ).sealed()


__all__ = [
    "FUSION_POLICY_VERSION",
    "TIMEFRAME_ORDER",
    "TIMEFRAME_ROLES",
    "MtfError",
    "MultiTimeframeMarketState",
    "TimeframeContract",
    "TimeframeMarketState",
    "build_multi_timeframe_state",
    "closed_bars_at",
]
