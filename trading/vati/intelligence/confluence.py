"""Functional confluence (§9, TRD-ENH-014).

`7 bullish indicators vs 3 bearish = BUY` throws away the only thing that makes
agreement informative — *which kind* of evidence agrees — and double-counts
colinear features by construction. Five trend measures outvote one liquidity
warning, and the vote looks like confirmation.

So evidence aggregates by **function**. Each axis reports its own state and the
evidence behind it, including disagreement. The strategy decides which axes
matter to it; this module decides nothing.

It deliberately has no `buy`, `sell`, `size`, `execute` or `approve`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from vati.core.canonical import canonical_hash

#: The functional axes. Not a ranking — a vocabulary.
AXES = ("trend", "momentum", "volatility", "structure",
        "liquidity", "event", "execution", "cross_asset")

#: Axis states. UNKNOWN is distinct from NEUTRAL: "no evidence" is not "balanced".
SUPPORTIVE = "SUPPORTIVE"
OPPOSING = "OPPOSING"
NEUTRAL = "NEUTRAL"
UNKNOWN = "UNKNOWN"
AXIS_STATES = (SUPPORTIVE, OPPOSING, NEUTRAL, UNKNOWN)

CONFLUENCE_POLICY_VERSION = "confluence/1.0.0"


@dataclass(frozen=True)
class ConfluenceAxis:
    name: str
    state: str = UNKNOWN
    evidence_refs: tuple[str, ...] = ()
    disagreement_refs: tuple[str, ...] = ()
    timeframe: Optional[str] = None
    as_of_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "name": self.name, "state": self.state,
            "evidence_refs": list(self.evidence_refs),
            "disagreement_refs": list(self.disagreement_refs),
            "timeframe": self.timeframe, "as_of_ms": self.as_of_ms,
        }


@dataclass(frozen=True)
class ConfluenceState:
    symbol: str
    as_of_ms: int
    axes: Mapping[str, ConfluenceAxis]
    policy_version: str = CONFLUENCE_POLICY_VERSION
    state_hash: str = ""

    def axis(self, name: str) -> ConfluenceAxis:
        return self.axes.get(name, ConfluenceAxis(name))

    @property
    def disagreeing_axes(self) -> tuple[str, ...]:
        """Axes carrying contradictory evidence. The interesting part."""
        return tuple(a for a in AXES if self.axes.get(a) and self.axes[a].disagreement_refs)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "as_of_ms": self.as_of_ms,
            "policy_version": self.policy_version,
            "axes": [self.axes[a].as_dict() for a in AXES if a in self.axes],
        }

    def sealed(self) -> "ConfluenceState":
        return ConfluenceState(**{**self.__dict__, "state_hash": canonical_hash(self.as_dict())})

    def narrate(self) -> tuple[str, ...]:
        """Owner-readable lines, built from stored evidence rather than intuition."""
        out: list[str] = []
        for name in AXES:
            ax = self.axes.get(name)
            if ax is None or ax.state == UNKNOWN:
                continue
            tf = f" on {ax.timeframe}" if ax.timeframe else ""
            line = f"{name}{tf}: {ax.state.lower()}"
            if ax.disagreement_refs:
                line += f" (disagreement: {', '.join(ax.disagreement_refs)})"
            out.append(line)
        return tuple(out)


class ConfluenceEngine:
    """Builds a `ConfluenceState`. Owns no decision method, by construction."""

    def build(self, *, symbol: str, as_of_ms: int, axes: Sequence[ConfluenceAxis]) -> ConfluenceState:
        unknown = sorted({a.name for a in axes} - set(AXES))
        if unknown:
            raise ValueError(f"unknown confluence axis/axes: {unknown}")
        bad = sorted({a.state for a in axes} - set(AXIS_STATES))
        if bad:
            raise ValueError(f"unknown axis state(s): {bad}")
        # One axis per function: two trend readings collapse into one axis with
        # both refs, which is what stops colinear features counting twice.
        merged: dict[str, ConfluenceAxis] = {}
        for a in axes:
            prior = merged.get(a.name)
            if prior is None:
                merged[a.name] = a
                continue
            agree = prior.state == a.state
            merged[a.name] = ConfluenceAxis(
                name=a.name,
                state=prior.state if agree else NEUTRAL,
                evidence_refs=tuple(dict.fromkeys(prior.evidence_refs + a.evidence_refs)),
                disagreement_refs=prior.disagreement_refs if agree else tuple(
                    dict.fromkeys(prior.disagreement_refs + a.disagreement_refs
                                  + prior.evidence_refs + a.evidence_refs)),
                timeframe=prior.timeframe if prior.timeframe == a.timeframe else None,
                as_of_ms=max(prior.as_of_ms, a.as_of_ms),
            )
        return ConfluenceState(symbol=symbol, as_of_ms=as_of_ms, axes=merged).sealed()


__all__ = [
    "AXES", "AXIS_STATES", "CONFLUENCE_POLICY_VERSION",
    "NEUTRAL", "OPPOSING", "SUPPORTIVE", "UNKNOWN",
    "ConfluenceAxis", "ConfluenceEngine", "ConfluenceState",
]
