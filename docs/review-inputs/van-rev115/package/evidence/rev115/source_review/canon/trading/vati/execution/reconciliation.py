"""Reconciliation (Rev 2 §44). Ledger view vs venue view; classifies every
difference; decides whether new orders are permitted."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable

from vati.execution.base import VenuePosition


class ReconciliationClass(str, Enum):
    MATCH = "MATCH"
    VENUE_PARTIAL_CLOSE = "VENUE_PARTIAL_CLOSE"
    VENUE_STOP_HIT = "VENUE_STOP_HIT"
    OWNER_OVERRIDE = "OWNER_OVERRIDE"
    ORPHAN_VENUE_POSITION = "ORPHAN_VENUE_POSITION"
    ORPHAN_LEDGER_POSITION = "ORPHAN_LEDGER_POSITION"
    STOP_MISSING = "STOP_MISSING"


@dataclass(frozen=True)
class LedgerPosition:
    trade_intent_id: str
    symbol: str
    quantity: Decimal
    stop_price: Decimal | None
    software_stop: bool = False


@dataclass(frozen=True)
class ReconciliationResult:
    items: tuple[tuple[str, ReconciliationClass, str], ...]   # (intent or position id, class, detail)
    permit_new_orders: bool
    account_verified: bool

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for _, c, _ in self.items:
            out[c.value] = out.get(c.value, 0) + 1
        return out


def reconcile(ledger: Iterable[LedgerPosition], venue: Iterable[VenuePosition], *, account_verified: bool, closed_by_venue_stop: set[str] = frozenset(), owner_closed: set[str] = frozenset()) -> ReconciliationResult:
    L = {p.trade_intent_id: p for p in ledger}
    V = {p.trade_intent_id: p for p in venue if p.trade_intent_id}
    orphans_v = [p for p in venue if not p.trade_intent_id]
    items: list[tuple[str, ReconciliationClass, str]] = []
    block = not account_verified
    for iid, lp in L.items():
        vp = V.get(iid)
        if vp is None:
            if iid in closed_by_venue_stop:
                items.append((iid, ReconciliationClass.VENUE_STOP_HIT, "venue stop closed position; ledger to record exit"))
            elif iid in owner_closed:
                items.append((iid, ReconciliationClass.OWNER_OVERRIDE, "owner closed position in terminal; learning event, never re-opened"))
            else:
                items.append((iid, ReconciliationClass.ORPHAN_LEDGER_POSITION, "ledger open, venue flat; mark closed-unknown, escalate")); block = True
            continue
        if vp.quantity < lp.quantity:
            items.append((iid, ReconciliationClass.VENUE_PARTIAL_CLOSE, f"venue {vp.quantity} < ledger {lp.quantity}"))
        elif vp.quantity > lp.quantity:
            items.append((iid, ReconciliationClass.ORPHAN_VENUE_POSITION, f"venue {vp.quantity} > ledger {lp.quantity}")); block = True
        else:
            items.append((iid, ReconciliationClass.MATCH, ""))
        if not lp.software_stop and vp.stop_price is None:
            items.append((iid, ReconciliationClass.STOP_MISSING, "venue position without protective stop; restore or flatten")); block = True
    # A venue position with an intent id is still an orphan when the caller
    # cannot reconstruct that intent as open ledger state.  The previous
    # implementation only classified positions whose trade_intent_id was empty,
    # so reconcile([], [attributed_position]) incorrectly returned green.
    for iid, vp in V.items():
        if iid not in L:
            items.append((
                iid,
                ReconciliationClass.ORPHAN_VENUE_POSITION,
                f"venue position {vp.position_id} attributes intent {iid}, but no open ledger position was supplied",
            ))
            block = True
    for p in orphans_v:
        items.append((p.position_id, ReconciliationClass.ORPHAN_VENUE_POSITION, "venue position with no intent attribution; protect with hard stop, block, escalate")); block = True
    return ReconciliationResult(tuple(items), permit_new_orders=not block, account_verified=account_verified)
