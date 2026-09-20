"""Profit expansion engine (TRD-REV51-110, G9/G11).

Proposes adding to a family that has already paid for itself. It runs *after*
preservation (111), never beside it, because a system that weighs an
opportunity and a threat in the same pass will sometimes pick the opportunity.
The first thing `evaluate` does is ask whether preservation had anything to
say, and anything at all stands the proposal down.

What comes out is a proposal, not a position. The engine states a requested
risk percentage and stops; IntentFactory builds the intent, the Risk Authority
sizes it and remains free to refuse it outright, and the router sends it. That
ordering is not a convention here, it is the reason this module is allowed to
exist at all (INV-AUTH-001, INV-EXEC-001).

Mode is the second gate. `EXPANSION_MODE` ships as SHADOW: proposals are
recorded and returned marked `would_propose`, and nothing downstream reads
them as candidates. G11 is where that changes, and only on laboratory evidence
(109) that the policy in force would have helped (INV-LIVE-001).

Every refusal is named. A proposal that does not happen is more common than
one that does, and "the conditions were not met" is useless to an owner
deciding whether the policy is too tight.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.lifecycle.envelope import PositionRiskEnvelope
from vati.lifecycle.family import FamilyState, PositionFamily
from vati.lifecycle.preservation import ActionKind as PreservationKind
from vati.lifecycle.preservation import PreservationAction
from vati.lifecycle.scale_policy import ScalePolicy
from vati.lifecycle.trade_health import HealthState, TradeHealth
from vati.risk.contracts import Direction

PRODUCER = "vati-profit-expansion"
EXPANSION_VERSION = "profit-expansion/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")


class Mode(str, Enum):
    SHADOW = "SHADOW"        # recorded, never a candidate
    LIVE = "LIVE"            # proposals reach the candidate pool


#: INV-LIVE-001. G11 promotes this, on laboratory evidence, as a code change
#: that appears in a diff rather than as a configuration flag.
EXPANSION_MODE = Mode.SHADOW


#: Why a proposal was not made. Closed vocabulary.
DECLINE_REASONS: dict[str, str] = {
    "POLICY_DISABLED": "this strategy has no scale policy, or it is switched off",
    "PRESERVATION_ACTIVE": "preservation had something to say about this family",
    "FAMILY_NOT_OPEN": "the family is closed or diverged",
    "HEALTH_BELOW_REQUIREMENT": "the family is not in the health the policy requires",
    "PROGRESS_BELOW_MINIMUM": "the position has not yet paid for itself",
    "SCALE_INS_EXHAUSTED": "the policy's adds for this family are spent",
    "COOLDOWN_ACTIVE": "not enough time has passed since the last add",
    "STOP_NOT_AT_ENTRY": "the stop is not yet at or better than the entry",
    "FAMILY_RISK_AT_CEILING": "family risk is already at the policy ceiling",
    "EVENT_WINDOW": "an event window is open for this instrument",
    "RISK_UNKNOWN": "the family's risk cannot be computed",
}


@dataclass(frozen=True)
class ExpansionProposal:
    """A request for a smaller second bite, or a named refusal."""

    family_id: str
    strategy_id: str
    symbol: str
    account_alias: str
    direction: Direction
    proposed: bool
    mode: Mode
    #: Set when proposed. A fraction of the root size, and the risk percentage
    #: the intent should *request* — the authority decides what it becomes.
    scale_fraction: Optional[Decimal]
    proposed_quantity: Optional[Decimal]
    requested_risk_pct: Optional[Decimal]
    scale_in_index: int
    decline_reasons: tuple[str, ...]
    detail: str
    decided_ms: int
    expansion_version: str = EXPANSION_VERSION

    @property
    def would_propose(self) -> bool:
        """True when the conditions were met but the mode withheld it."""
        return self.proposed and self.mode is Mode.SHADOW

    @property
    def is_candidate(self) -> bool:
        return self.proposed and self.mode is Mode.LIVE

    def body(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "account_alias": self.account_alias,
            "direction": self.direction.value,
            "proposed": self.proposed,
            "would_propose": self.would_propose,
            "is_candidate": self.is_candidate,
            "mode": self.mode.value,
            "scale_fraction": None if self.scale_fraction is None else str(self.scale_fraction),
            "proposed_quantity": (None if self.proposed_quantity is None
                                  else str(self.proposed_quantity)),
            "requested_risk_pct": (None if self.requested_risk_pct is None
                                   else str(self.requested_risk_pct)),
            "scale_in_index": self.scale_in_index,
            "decline_reasons": list(self.decline_reasons),
            "decline_detail": [DECLINE_REASONS[r] for r in self.decline_reasons],
            "detail": self.detail,
            "decided_ms": self.decided_ms,
            "expansion_version": self.expansion_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class ProfitExpansionEngine:
    """Decides whether a family has earned a smaller second bite."""

    def __init__(self, *, mode: Mode = EXPANSION_MODE, ledger=None,
                 producer: str = PRODUCER) -> None:
        self.mode = mode
        self._ledger = ledger
        self._producer = producer

    def evaluate(self, *, family: PositionFamily, strategy_id: str, policy: ScalePolicy,
                 health: TradeHealth, envelope: PositionRiskEnvelope,
                 preservation: PreservationAction, root_quantity: Decimal,
                 last_scale_ms: Optional[int], in_event_window: bool,
                 now_ms: int) -> ExpansionProposal:
        reasons: list[str] = []

        # Preservation first, always. Weighing a threat and an opportunity in
        # the same pass means sometimes picking the opportunity.
        if preservation.kind is not PreservationKind.NONE:
            reasons.append("PRESERVATION_ACTIVE")
        if not policy.enabled:
            reasons.append("POLICY_DISABLED")
        if family.state is not FamilyState.OPEN or not family.is_open:
            reasons.append("FAMILY_NOT_OPEN")
        if not envelope.risk_is_known:
            reasons.append("RISK_UNKNOWN")
        if health.state is not policy.required_health:
            reasons.append("HEALTH_BELOW_REQUIREMENT")
        if health.current_r < policy.min_progress_r:
            reasons.append("PROGRESS_BELOW_MINIMUM")
        if policy.refuse_in_event_window and in_event_window:
            reasons.append("EVENT_WINDOW")

        index = family.scale_ins
        fraction = policy.fraction_for(index)
        if fraction is None:
            reasons.append("SCALE_INS_EXHAUSTED")

        if last_scale_ms is not None and now_ms - last_scale_ms < policy.cooldown_ms:
            reasons.append("COOLDOWN_ACTIVE")

        if policy.require_stop_at_or_better_than_entry and not self._stop_secured(family):
            reasons.append("STOP_NOT_AT_ENTRY")

        if envelope.risk_is_known and envelope.open_risk_pct is not None:
            if envelope.open_risk_pct >= policy.max_family_risk_pct:
                reasons.append("FAMILY_RISK_AT_CEILING")

        if reasons:
            return self._emit(ExpansionProposal(
                family_id=family.family_id, strategy_id=strategy_id, symbol=family.symbol,
                account_alias=family.account_alias, direction=family.direction,
                proposed=False, mode=self.mode, scale_fraction=None,
                proposed_quantity=None, requested_risk_pct=None, scale_in_index=index,
                decline_reasons=tuple(sorted(set(reasons))), detail="", decided_ms=now_ms))

        assert fraction is not None
        quantity = dec(root_quantity) * fraction
        # Headroom within the policy ceiling. The authority applies its own,
        # which is usually tighter; this never widens it.
        headroom = policy.max_family_risk_pct - (envelope.open_risk_pct or ZERO)
        requested = headroom if headroom > ZERO else ZERO

        return self._emit(ExpansionProposal(
            family_id=family.family_id, strategy_id=strategy_id, symbol=family.symbol,
            account_alias=family.account_alias, direction=family.direction,
            proposed=True, mode=self.mode, scale_fraction=fraction,
            proposed_quantity=quantity, requested_risk_pct=requested,
            scale_in_index=index, decline_reasons=(),
            detail=f"add {index + 1} of {policy.max_scale_ins} at {fraction} of root",
            decided_ms=now_ms))

    @staticmethod
    def _stop_secured(family: PositionFamily) -> bool:
        """Stop at or better than the average entry: the add cannot turn a
        paid-for position back into a losing one on the original risk."""
        entry, stop = family.average_entry, family.current_stop
        if entry is None or stop is None:
            return False
        return stop >= entry if family.direction is Direction.LONG else stop <= entry

    def _emit(self, proposal: ExpansionProposal) -> ExpansionProposal:
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.EXPANSION_ACTION, self._producer, proposal.body(),
                event_time_ms=proposal.decided_ms, received_time_ms=proposal.decided_ms,
                correlation_id=proposal.family_id))
        return proposal
