"""Drawdown governor and kill switch (Rev 2 §27.3–§27.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from vati.risk.contracts import KillSwitchTrigger
from vati.risk.mandate import DrawdownTier
from vati.authority import OwnerAuthorityVerifier

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

    def clear(
        self,
        trigger: KillSwitchTrigger,
        now_unix: int,
        *,
        owner_signature_ref: str,
        authority: OwnerAuthorityVerifier,
        subject: str,
    ) -> None:
        """P0-TRADE-001 — this took any non-empty string and turned the kill switch off.

        The act and the subject are inside the signature, so a token authorising a halt
        cannot be replayed to clear one, and a token for another session cannot clear this
        one. The verifier is required rather than defaulted: a caller that has not been
        given one cannot clear a kill switch, which is the correct failure.
        """
        verified = authority.verify(
            owner_signature_ref, act="kill-switch-clear", subject=subject, now_unix=now_unix
        )
        self.active.discard(trigger)
        self.history.append((now_unix, f"CLEAR:{verified.ref}", trigger))

    @property
    def halted(self) -> bool:
        return bool(self.active)
