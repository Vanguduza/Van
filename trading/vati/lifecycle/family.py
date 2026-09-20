"""PositionFamily model (TRD-REV51-106, G7).

A scale-in is not a new trade. Treated as one, it gets its own risk budget,
its own stop and its own line in the book, and the account ends up with three
positions in the same instrument each individually within limits and jointly
well outside them. That is the specific failure this packet exists to make
impossible: a root and everything that grew out of it are one exposure, and
every risk question is asked of the family.

The family is a fold over lifecycle events, in order, with no clock of its
own — the same discipline as the world model, for the same reason. Replaying
an account's lifecycle must reconstruct exactly the families it had
(INV-REPLAY-001).

Accounting is weighted-average cost. A partial exit realises against the
average, not against a chosen lot, because letting the caller choose which lot
closed is letting it choose what the realised number looks like.

Reconciliation divergence is a state, not an exception. When the venue's
quantity disagrees with the family's, the family is DIVERGED and admits no
new risk until the disagreement is resolved — the one safe reading of "we do
not know what we hold".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.risk.contracts import Direction

PRODUCER = "vati-position-family"
FAMILY_VERSION = "position-family/5.1.0"

ZERO = Decimal("0")


class FamilyError(RuntimeError):
    pass


class MemberRole(str, Enum):
    ROOT = "ROOT"                # the position the family started as
    SCALE_IN = "SCALE_IN"        # added exposure in the same direction
    PARTIAL_EXIT = "PARTIAL_EXIT"
    FULL_EXIT = "FULL_EXIT"


class FamilyState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    DIVERGED = "DIVERGED"        # venue disagrees; no new risk until resolved


@dataclass(frozen=True)
class FamilyMember:
    """One lifecycle event in a family's history."""

    member_id: str
    role: MemberRole
    quantity: Decimal            # always positive; the role says which way
    price: Decimal
    occurred_ms: int
    trade_intent_id: str = ""
    stop: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if self.quantity <= ZERO:
            raise FamilyError(f"{self.member_id} has quantity {self.quantity}; the role carries the sign")
        if self.price <= ZERO:
            raise FamilyError(f"{self.member_id} has price {self.price}")

    @property
    def adds(self) -> bool:
        return self.role in (MemberRole.ROOT, MemberRole.SCALE_IN)

    def body(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id, "role": self.role.value,
            "quantity": str(self.quantity), "price": str(self.price),
            "occurred_ms": self.occurred_ms, "trade_intent_id": self.trade_intent_id,
            "stop": None if self.stop is None else str(self.stop),
        }


@dataclass
class PositionFamily:
    """A root position and everything that grew out of it, as one exposure."""

    family_id: str
    account_alias: str
    symbol: str
    direction: Direction
    opened_ms: int
    members: list[FamilyMember] = field(default_factory=list)
    state: FamilyState = FamilyState.OPEN
    current_stop: Optional[Decimal] = None
    original_stop: Optional[Decimal] = None
    closed_ms: Optional[int] = None
    divergence_detail: str = ""

    # ------------------------------------------------------------------ folds
    @property
    def sign(self) -> Decimal:
        return Decimal("1") if self.direction is Direction.LONG else Decimal("-1")

    @property
    def net_quantity(self) -> Decimal:
        qty = ZERO
        for m in self.members:
            qty += m.quantity if m.adds else -m.quantity
        return qty

    @property
    def gross_added(self) -> Decimal:
        return sum((m.quantity for m in self.members if m.adds), ZERO)

    @property
    def average_entry(self) -> Optional[Decimal]:
        """Weighted-average cost of the exposure still open.

        Exits reduce quantity at the average, so the average of what remains
        is the average of what was added — which is the point of not letting a
        caller choose which lot closed.
        """
        added_qty = self.gross_added
        if added_qty <= ZERO:
            return None
        cost = sum((m.quantity * m.price for m in self.members if m.adds), ZERO)
        return cost / added_qty

    @property
    def realised_money(self) -> Decimal:
        """Banked P&L from exits, against the running average at exit time."""
        realised = ZERO
        running_qty = ZERO
        running_cost = ZERO
        for m in self.members:
            if m.adds:
                running_qty += m.quantity
                running_cost += m.quantity * m.price
                continue
            if running_qty <= ZERO:
                continue
            avg = running_cost / running_qty
            closed = min(m.quantity, running_qty)
            realised += self.sign * (m.price - avg) * closed
            running_cost -= avg * closed
            running_qty -= closed
        return realised

    def unrealised_money(self, mark: Decimal) -> Decimal:
        avg = self.average_entry
        if avg is None or self.net_quantity <= ZERO:
            return ZERO
        return self.sign * (dec(mark) - avg) * self.net_quantity

    @property
    def scale_ins(self) -> int:
        return sum(1 for m in self.members if m.role is MemberRole.SCALE_IN)

    @property
    def is_open(self) -> bool:
        return self.state is FamilyState.OPEN and self.net_quantity > ZERO

    @property
    def admits_new_risk(self) -> bool:
        """The one safe reading of 'we do not know what we hold'."""
        return self.state is FamilyState.OPEN

    # ------------------------------------------------------------------ apply
    def add(self, member: FamilyMember) -> "PositionFamily":
        if self.state is FamilyState.CLOSED:
            raise FamilyError(f"{self.family_id} is closed; a new position is a new family")
        if not member.adds and member.quantity > self.net_quantity:
            raise FamilyError(
                f"{member.member_id} closes {member.quantity} of a {self.net_quantity} position")
        self.members.append(member)
        if member.stop is not None:
            self._set_stop(member.stop, member.role)
        if self.net_quantity <= ZERO:
            self.state = FamilyState.CLOSED
            self.closed_ms = member.occurred_ms
        return self

    def _set_stop(self, stop: Decimal, role: MemberRole) -> None:
        if self.original_stop is None:
            self.original_stop = stop
            self.current_stop = stop
            return
        # INV-RISK-001. A family's stop may move toward the position and never
        # away from it, whatever the lifecycle event claims.
        if self.current_stop is None:
            self.current_stop = stop
            return
        tighter = stop > self.current_stop if self.direction is Direction.LONG else stop < self.current_stop
        if tighter:
            self.current_stop = stop

    def tighten_stop(self, stop: Decimal) -> Decimal:
        """Move the stop toward the position. Refuses to move it away."""
        if self.current_stop is None:
            self.current_stop = dec(stop)
            self.original_stop = self.original_stop or dec(stop)
            return self.current_stop
        proposed = dec(stop)
        tighter = (proposed > self.current_stop if self.direction is Direction.LONG
                   else proposed < self.current_stop)
        if not tighter:
            raise FamilyError(
                f"{self.family_id}: {proposed} is not tighter than {self.current_stop}; "
                "stop widening is not available")
        self.current_stop = proposed
        return proposed

    def reconcile(self, *, venue_quantity: Decimal, now_ms: int) -> FamilyState:
        """Compare with the venue. Disagreement is a state, not an exception."""
        venue = dec(venue_quantity)
        if venue == self.net_quantity:
            if self.state is FamilyState.DIVERGED:
                self.state = FamilyState.OPEN if self.net_quantity > ZERO else FamilyState.CLOSED
                self.divergence_detail = ""
            return self.state
        self.state = FamilyState.DIVERGED
        self.divergence_detail = (
            f"venue reports {venue}, family holds {self.net_quantity} at {now_ms}")
        return self.state

    # ------------------------------------------------------------------ state
    def body(self, *, mark: Optional[Decimal] = None) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "account_alias": self.account_alias,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "state": self.state.value,
            "opened_ms": self.opened_ms,
            "closed_ms": self.closed_ms,
            "net_quantity": str(self.net_quantity),
            "gross_added": str(self.gross_added),
            "average_entry": None if self.average_entry is None else str(self.average_entry),
            "realised_money": str(self.realised_money),
            "unrealised_money": None if mark is None else str(self.unrealised_money(mark)),
            "scale_ins": self.scale_ins,
            "current_stop": None if self.current_stop is None else str(self.current_stop),
            "original_stop": None if self.original_stop is None else str(self.original_stop),
            "divergence_detail": self.divergence_detail,
            "members": [m.body() for m in self.members],
            "family_version": FAMILY_VERSION,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class FamilyRegistry:
    """Every family for an account, folded from lifecycle events."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._families: dict[str, PositionFamily] = {}
        self._by_intent: dict[str, str] = {}
        self._ledger = ledger
        self._producer = producer

    def open_family(self, *, family_id: str, account_alias: str, symbol: str,
                    direction: Direction, root: FamilyMember,
                    now_ms: int, emit: bool = True) -> PositionFamily:
        if family_id in self._families:
            raise FamilyError(f"{family_id} already exists")
        if root.role is not MemberRole.ROOT:
            raise FamilyError(f"a family opens with a ROOT member, not {root.role.value}")
        fam = PositionFamily(family_id=family_id, account_alias=account_alias, symbol=symbol,
                             direction=direction, opened_ms=now_ms)
        fam.add(root)
        self._families[family_id] = fam
        if root.trade_intent_id:
            self._by_intent[root.trade_intent_id] = family_id
        if emit:
            self._emit(fam, now_ms)
        return fam

    def apply(self, family_id: str, member: FamilyMember, *, now_ms: int,
              emit: bool = True) -> PositionFamily:
        fam = self.get(family_id)
        fam.add(member)
        if member.trade_intent_id:
            self._by_intent[member.trade_intent_id] = family_id
        if emit:
            self._emit(fam, now_ms)
        return fam

    def tighten_stop(self, family_id: str, stop: Decimal, *, now_ms: int,
                     emit: bool = True) -> PositionFamily:
        fam = self.get(family_id)
        fam.tighten_stop(stop)
        if emit:
            self._emit(fam, now_ms)
        return fam

    def get(self, family_id: str) -> PositionFamily:
        fam = self._families.get(family_id)
        if fam is None:
            raise FamilyError(f"no family {family_id}")
        return fam

    def for_intent(self, trade_intent_id: str) -> Optional[PositionFamily]:
        fid = self._by_intent.get(trade_intent_id)
        return None if fid is None else self._families[fid]

    def open_families(self, *, account_alias: Optional[str] = None,
                      symbol: Optional[str] = None) -> list[PositionFamily]:
        return sorted(
            (f for f in self._families.values()
             if f.is_open
             and (account_alias is None or f.account_alias == account_alias)
             and (symbol is None or f.symbol == symbol)),
            key=lambda f: f.family_id)

    def diverged(self) -> list[PositionFamily]:
        return sorted((f for f in self._families.values() if f.state is FamilyState.DIVERGED),
                      key=lambda f: f.family_id)

    def reconcile(self, family_id: str, *, venue_quantity: Decimal,
                  now_ms: int) -> FamilyState:
        fam = self.get(family_id)
        state = fam.reconcile(venue_quantity=venue_quantity, now_ms=now_ms)
        self._emit(fam, now_ms)
        return state

    def __len__(self) -> int:
        return len(self._families)

    def _emit(self, fam: PositionFamily, now_ms: int) -> None:
        if self._ledger is None:
            return
        self._ledger.append(make_event(
            EventKind.POSITION_FAMILY, self._producer, fam.body(),
            event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=fam.family_id))
