"""Drawdown governor and kill switch (Rev 2 §27.3–§27.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from vati.risk.contracts import KillSwitchTrigger
from vati.risk.mandate import DrawdownTier

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class DrawdownVerdict:
    drawdown: Decimal
    multiplier: Decimal
    top_tier_only: bool
    suspended: bool
    tier_index: int  # -1 when no tier applies


def drawdown_verdict(peak_equity: Decimal, equity: Decimal, tiers: tuple[DrawdownTier, ...]) -> DrawdownVerdict:
    if peak_equity <= ZERO or equity <= ZERO:
        return DrawdownVerdict(Decimal("Infinity"), ZERO, True, True, len(tiers) - 1)
    dd = max(ZERO, (peak_equity - equity) / peak_equity)
    applied = -1
    multiplier = ONE
    top_only = False
    for i, tier in enumerate(tiers):
        if dd >= tier.threshold:
            applied = i
            multiplier = tier.multiplier
            top_only = top_only or tier.top_tier_only
    return DrawdownVerdict(dd, multiplier, top_only, multiplier == ZERO, applied)


@dataclass
class KillSwitch:
    """Latching kill switch. Any trigger halts new orders. Clearing is an
    owner-signed A4 action and is never performed by this module."""

    active: set[KillSwitchTrigger] = field(default_factory=set)
    history: list[tuple[int, str, KillSwitchTrigger]] = field(default_factory=list)

    def trip(self, trigger: KillSwitchTrigger, now_unix: int) -> None:
        self.active.add(trigger)
        self.history.append((now_unix, "TRIP", trigger))

    def clear(self, trigger: KillSwitchTrigger, now_unix: int, *, owner_signature_ref: str) -> None:
        if not owner_signature_ref or not owner_signature_ref.strip():
            raise PermissionError("kill switch clear requires an owner signature reference (A4)")
        self.active.discard(trigger)
        self.history.append((now_unix, f"CLEAR:{owner_signature_ref}", trigger))

    @property
    def halted(self) -> bool:
        return bool(self.active)
