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
from copy import deepcopy
from fractions import Fraction
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Optional, Sequence

from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event
from vati.core.ledger import committed_source_snapshot
from vati.risk.contracts import Direction
from vati.execution.exit_journal import VERSION as EXIT_JOURNAL_VERSION
from vati.risk.arithmetic import fraction, decimal

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
        if fraction(self.quantity) <= 0:
            raise FamilyError(f"{self.member_id} has quantity {self.quantity}; the role carries the sign")
        if fraction(self.price) <= 0:
            raise FamilyError(f"{self.member_id} has price {self.price}")
        if not isinstance(self.member_id, str) or not self.member_id:
            raise FamilyError("family member identity is required")
        if type(self.occurred_ms) is not int or self.occurred_ms < 0:
            raise FamilyError("family member time must be a nonnegative integer")
        if self.stop is not None and fraction(self.stop) <= 0:
            raise FamilyError("family stop must be finite and positive")

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

    def accounting(self) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        """Exact remaining quantity/cost, lifetime additions and realised P&L.

        Exits remove cost at the running weighted average. A later addition
        weights only the remaining cost, never already exited quantities.
        Fractions remain internal; Decimal conversion is a reporting boundary.
        """
        quantity = cost = gross = realised = Fraction(0)
        sign = 1 if self.direction is Direction.LONG else -1
        for member in self.members:
            q, price = fraction(member.quantity), fraction(member.price)
            if member.adds:
                quantity += q
                gross += q
                cost += q * price
            else:
                if quantity <= 0 or q > quantity:
                    raise FamilyError("family history exits more than original exposure")
                removed_cost = cost * q / quantity
                realised += sign * (price * q - removed_cost)
                cost -= removed_cost
                quantity -= q
        return quantity, cost, gross, realised

    @property
    def net_quantity(self) -> Decimal:
        return decimal(self.accounting()[0])

    @property
    def gross_added(self) -> Decimal:
        return decimal(self.accounting()[2])

    @property
    def average_entry_exact(self) -> Optional[Fraction]:
        quantity, cost, _, _ = self.accounting()
        return cost / quantity if quantity else None

    @property
    def average_entry(self) -> Optional[Decimal]:
        value = self.average_entry_exact
        return None if value is None else decimal(value)

    @property
    def realised_money(self) -> Decimal:
        return decimal(self.accounting()[3])

    def unrealised_exact(self, mark: Decimal) -> Fraction:
        quantity, cost, _, _ = self.accounting()
        sign = 1 if self.direction is Direction.LONG else -1
        return sign * (fraction(mark) * quantity - cost)

    def unrealised_money(self, mark: Decimal) -> Decimal:
        return decimal(self.unrealised_exact(dec(mark)))

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
        previous = next((m for m in self.members if m.member_id == member.member_id), None)
        if previous is not None:
            if previous == member:
                return self
            raise FamilyError("conflicting original family member identity")
        if self.members and member.occurred_ms < self.members[-1].occurred_ms:
            raise FamilyError("family members must retain original chronology")
        if self.members and member.role is MemberRole.ROOT:
            raise FamilyError("family already has its original root")
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
        if root.trade_intent_id and root.trade_intent_id in self._by_intent:
            raise FamilyError("original root intent already belongs to a family")
        fam = PositionFamily(family_id=family_id, account_alias=account_alias, symbol=symbol,
                             direction=direction, opened_ms=now_ms)
        fam.add(root)
        if emit:
            self._emit(fam, now_ms)
        self._families[family_id] = fam
        if root.trade_intent_id:
            self._by_intent[root.trade_intent_id] = family_id
        return fam

    def apply(self, family_id: str, member: FamilyMember, *, now_ms: int,
              emit: bool = True) -> PositionFamily:
        original = self.get(family_id)
        owner = self._by_intent.get(member.trade_intent_id)
        if owner is not None and owner != family_id:
            raise FamilyError("original member intent already belongs to another family")
        fam = deepcopy(original)
        fam.add(member)
        if emit:
            self._emit(fam, now_ms)
        original.__dict__.update(fam.__dict__)
        if member.trade_intent_id:
            self._by_intent[member.trade_intent_id] = family_id
        return original

    def tighten_stop(self, family_id: str, stop: Decimal, *, now_ms: int,
                     emit: bool = True) -> PositionFamily:
        original = self.get(family_id)
        fam = deepcopy(original)
        fam.tighten_stop(stop)
        if emit:
            self._emit(fam, now_ms)
        original.__dict__.update(fam.__dict__)
        return original

    def restore(self, history, *, family_id: str, trade_intent_id: str,
                symbol: str, direction: Direction, position_id: str) -> Optional[PositionFamily]:
        """Read original family membership, never trust historical projections.

        The history has independently verified the durable chain and original
        account commands. Members additionally join sealed execution facts;
        later snapshots must extend the original membership without rewriting it.
        No event is emitted and no current venue observation becomes an entry.
        """
        snapshots = [event for event in history.rows
                     if event.kind is EventKind.POSITION_FAMILY
                     and event.correlation_id == family_id]
        if not snapshots:
            return None
        receipts = tuple(history.events(EventKind.EXECUTION_RECEIPT))
        previous = []
        latest = None
        for event in snapshots:
            payload = event.payload
            if (event.producer != PRODUCER or event.hash != canonical_hash(event.body())
                    or payload.get("family_id") != family_id
                    or payload.get("account_alias") != history.account_alias
                    or payload.get("symbol") != symbol
                    or payload.get("direction") != direction.value
                    or payload.get("family_version") != FAMILY_VERSION):
                raise FamilyError("original family snapshot scope is invalid")
            raw_members = payload.get("members")
            if not isinstance(raw_members, list) or not raw_members or raw_members[:len(previous)] != previous:
                raise FamilyError("original family membership was rewritten")
            family = PositionFamily(family_id, history.account_alias, symbol, direction,
                                    payload["opened_ms"])
            used = set()
            for index, raw in enumerate(raw_members):
                member = FamilyMember(
                    member_id=raw["member_id"], role=MemberRole(raw["role"]),
                    quantity=Decimal(raw["quantity"]), price=Decimal(raw["price"]),
                    occurred_ms=raw["occurred_ms"], trade_intent_id=raw["trade_intent_id"],
                    stop=None if raw["stop"] is None else Decimal(raw["stop"]))
                if (index == 0 and (member.role is not MemberRole.ROOT
                                   or member.trade_intent_id != trade_intent_id)):
                    raise FamilyError("original family root is not bound")
                if member.occurred_ms > event.event_time_ms:
                    raise FamilyError("family member is from the future")
                if member.role is MemberRole.SCALE_IN:
                    child = history.commands.get(member.trade_intent_id)
                    if (child is None or member.trade_intent_id == trade_intent_id
                            or child[0].get("symbol") != symbol
                            or child[0].get("direction") != direction.value):
                        raise FamilyError("scale member lacks its original child command")
                    ancestry = [row for row in history.rows
                                if row.kind is EventKind.RISK_DECISION
                                and row.producer == "vati-account-lifecycle"
                                and row.correlation_id == member.trade_intent_id
                                and row.hash == canonical_hash(row.body())
                                and row.event_time_ms <= member.occurred_ms
                                and row.payload.get("parent_trade_intent_id") == trade_intent_id
                                and row.payload.get("inputs", {}).get("intent", {}).get("decision_hash")
                                    == child[0].get("decision_hash")]
                    if not ancestry:
                        raise FamilyError("scale member lacks original parent ancestry")
                matches = set()
                for receipt_event in receipts:
                    r = receipt_event.payload
                    if (r.get("trade_intent_id") != member.trade_intent_id
                            or r.get("status") not in {"FILLED", "PARTIAL"}
                            or receipt_event.received_time_ms > member.occurred_ms
                            or bool(r.get("exit_action")) == member.adds
                            or (member.role is MemberRole.ROOT
                                and r.get("broker_position_id") != position_id)):
                        continue
                    if not member.adds:
                        request = next((row for row in history.rows
                            if row.kind is EventKind.EXIT_ATTEMPT
                            and row.hash == r.get("exit_request_ref")
                            and row.producer == "vati-execution-router"
                            and row.hash == canonical_hash(row.body())
                            and row.payload.get("version") == EXIT_JOURNAL_VERSION
                            and row.payload.get("state") == "REQUESTED"
                            and row.payload.get("venue") == history.venue
                            and row.payload.get("position_id") == r.get("broker_position_id")
                            and row.payload.get("position_id") == position_id
                            and row.payload.get("trade_intent_id") == member.trade_intent_id
                            and row.received_time_ms <= receipt_event.received_time_ms), None)
                        if request is None or not any(
                            row.kind is EventKind.EXIT_ATTEMPT
                            and row.producer == "vati-execution-router"
                            and row.hash == canonical_hash(row.body())
                            and row.payload.get("request_ref") == request.hash
                            and row.payload.get("receipt_event_ref") == receipt_event.hash
                            and row.payload.get("state") in {"CONFIRMED", "PARTIAL_CONFIRMED", "UNKNOWN"}
                            for row in history.rows):
                            continue
                    try:
                        if (Decimal(str(r.get("filled_qty"))) == member.quantity
                                and Decimal(str(r.get("average_fill"))) == member.price):
                            matches.add(r["receipt_hash"])
                    except (ValueError, ArithmeticError):
                        continue
                if len(matches) != 1 or matches & used:
                    raise FamilyError("family member lacks an unambiguous original fill")
                used.update(matches)
                family.add(member)
            if (len(family.members) != len(raw_members)
                    or family.net_quantity != Decimal(payload["net_quantity"])
                    or family.gross_added != Decimal(payload["gross_added"])
                    or family.scale_ins != payload["scale_ins"]):
                raise FamilyError("family membership counters are inconsistent")
            # Historic average/P&L projections are deliberately not copied.
            # Stops are checked against current native protection by the caller.
            previous = raw_members
            latest = family
        assert latest is not None
        for member in latest.members:
            if member.trade_intent_id:
                mapped = self._by_intent.get(member.trade_intent_id)
                if mapped is not None and mapped != family_id:
                    raise FamilyError("original intent belongs to another family")
        self._families[family_id] = latest
        for member in latest.members:
            if member.trade_intent_id:
                self._by_intent[member.trade_intent_id] = family_id
        return latest

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
                  now_ms: int, emit: bool = True) -> FamilyState:
        original = self.get(family_id)
        fam = deepcopy(original)
        state = fam.reconcile(venue_quantity=venue_quantity, now_ms=now_ms)
        if emit:
            self._emit(fam, now_ms)
        original.__dict__.update(fam.__dict__)
        return state

    def __len__(self) -> int:
        return len(self._families)

    def _emit(self, fam: PositionFamily, now_ms: int) -> None:
        if self._ledger is None:
            return
        event = make_event(EventKind.POSITION_FAMILY, self._producer, fam.body(),
            event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=fam.family_id)
        append_error = None
        try:
            self._ledger.append(event)
        except Exception as error:
            append_error = error
        try:
            with committed_source_snapshot(self._ledger):
                if not self._ledger.verify_incremental()[0] or not any(
                    row.hash == event.hash and row.body() == event.body()
                    for row in self._ledger.iter(EventKind.POSITION_FAMILY,
                                                 correlation_id=fam.family_id)):
                    raise FamilyError("original family write is not durably readable")
        except Exception as error:
            original = self._families.get(fam.family_id)
            if original is not None:
                original.state = FamilyState.DIVERGED
                original.divergence_detail = "original family persistence unresolved"
            raise FamilyError("original family persistence unresolved") from (append_error or error)
