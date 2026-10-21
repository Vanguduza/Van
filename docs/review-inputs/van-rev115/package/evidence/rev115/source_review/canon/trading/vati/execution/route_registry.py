"""Symbol, route and quantisation registry (TRD-REV51-104, G5b).

Every venue has its own name for an instrument, its own lot step, its own tick
and its own idea of what "minimum" means, and all of it changes without
telling anyone. The existing SymbolContract already insists those facts come
from the venue rather than from a constant. What is missing is the thing that
holds them per account, notices when they have gone stale, and answers the two
questions the order path actually asks: *where does this go*, and *what size
is expressible there*.

Both answers fail closed. An unresolved route is not a warning to proceed
past — `resolve` raises, and the pre-trade layer (105) turns that into a
rejection. A contract older than its refresh window is STALE and therefore
unresolved, because a lot step from last week is a guess.

Quantisation has one rule worth stating out loud: **rounding is always
downward in risk**. Volume rounds down to the step, never up — rounding up
means placing more risk than the Risk Authority approved, which would make
this module a second sizer (INV-AUTH-001). A stop rounds toward the entry,
never away, because rounding a stop outward is stop widening by arithmetic
(INV-RISK-001). A size that rounds below the venue minimum is refused rather
than rounded up to it: the honest outcome is "this venue cannot express the
approved size", not "here, have a bigger one".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.risk.contracts import Direction, LossModel, SymbolContract

PRODUCER = "vati-route-registry"
REGISTRY_VERSION = "route-registry/5.1.0"

ZERO = Decimal("0")

#: A venue contract older than this is a guess. Routes refresh at account
#: service startup and on a timer; this is the timer's contract with the
#: order path, not a suggestion.
DEFAULT_MAX_ROUTE_AGE_MS = 3_600_000


class RouteState(str, Enum):
    RESOLVED = "RESOLVED"
    STALE = "STALE"              # contract older than the refresh window
    CLOSE_ONLY = "CLOSE_ONLY"    # venue permits exits only
    DISABLED = "DISABLED"        # venue or operator has closed this symbol
    UNRESOLVED = "UNRESOLVED"    # never synced


class RouteUnresolved(RuntimeError):
    """No usable route. The order path turns this into a rejection."""


class QuantisationRefused(RuntimeError):
    """The approved size cannot be expressed on this venue."""


@dataclass(frozen=True)
class Route:
    account_alias: str
    symbol: str
    venue: str
    adapter_id: str
    contract: SymbolContract
    state: RouteState
    resolved_ms: int
    source: str = "venue_sync"

    def age_ms(self, now_ms: int) -> int:
        return max(0, now_ms - self.resolved_ms)

    def usable_for(self, direction: Direction) -> bool:
        if self.state is not RouteState.RESOLVED:
            return False
        return self.contract.allows(direction)

    def body(self) -> dict[str, Any]:
        return {
            "account_alias": self.account_alias, "symbol": self.symbol,
            "venue": self.venue, "adapter_id": self.adapter_id,
            "state": self.state.value, "resolved_ms": self.resolved_ms,
            "source": self.source,
            "contract": {
                "tick_size": str(self.contract.tick_size),
                "tick_value": str(self.contract.tick_value),
                "volume_min": str(self.contract.volume_min),
                "volume_step": str(self.contract.volume_step),
                "volume_max": str(self.contract.volume_max),
                "min_stop_distance": str(self.contract.min_stop_distance),
                "trade_mode": self.contract.trade_mode,
                "loss_model": self.contract.loss_model.value,
            },
            "registry_version": REGISTRY_VERSION,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


@dataclass(frozen=True)
class QuantisedOrder:
    """A size and prices the venue can actually accept."""

    quantity: Decimal
    entry_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    #: How much of the approved size was lost to the lot step. Reported rather
    #: than swallowed: a venue that can only express 60% of an approved size
    #: is a fact worth seeing in the ledger.
    quantity_shortfall: Decimal
    notes: tuple[str, ...] = ()

    def body(self) -> dict[str, Any]:
        return {
            "quantity": str(self.quantity),
            "entry_price": None if self.entry_price is None else str(self.entry_price),
            "stop_price": None if self.stop_price is None else str(self.stop_price),
            "quantity_shortfall": str(self.quantity_shortfall),
            "notes": list(self.notes),
        }


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= ZERO:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _round_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    if tick <= ZERO:
        return value
    return (value / tick).to_integral_value(rounding=ROUND_HALF_EVEN) * tick


def quantise_volume(contract: SymbolContract, quantity: Decimal) -> tuple[Decimal, Decimal]:
    """Round down to the lot step. Returns (quantity, shortfall).

    Never rounds up. Rounding up places more risk than was approved, which is
    what a second sizer looks like in practice.
    """
    if quantity <= ZERO:
        raise QuantisationRefused(f"quantity {quantity} is not positive")
    capped = min(quantity, contract.volume_max) if contract.volume_max > ZERO else quantity
    stepped = _floor_to_step(capped, contract.volume_step)
    if stepped < contract.volume_min:
        raise QuantisationRefused(
            f"approved size {quantity} rounds to {stepped}, below the venue minimum "
            f"{contract.volume_min}; this venue cannot express the approved size")
    return stepped, quantity - stepped


def quantise_stop(contract: SymbolContract, *, entry: Decimal, stop: Decimal,
                  direction: Direction) -> Decimal:
    """Round a stop to the tick, always toward the entry.

    Rounding a stop away from entry is stop widening by arithmetic, and
    INV-RISK-001 does not carve out an exception for rounding.
    """
    rounded = _round_to_tick(stop, contract.tick_size)
    if direction is Direction.LONG:
        # A long's stop sits below entry; tighter means higher.
        if rounded < stop:
            rounded = rounded + contract.tick_size
        return min(rounded, entry)
    if rounded > stop:
        rounded = rounded - contract.tick_size
    return max(rounded, entry)


class RouteRegistry:
    """Per-account routes, refreshed from venue truth and aged out."""

    def __init__(self, *, max_age_ms: int = DEFAULT_MAX_ROUTE_AGE_MS, ledger=None,
                 producer: str = PRODUCER) -> None:
        self.max_age_ms = max_age_ms
        self._ledger = ledger
        self._producer = producer
        self._routes: dict[tuple[str, str], Route] = {}
        self._disabled: set[tuple[str, str]] = set()

    # ---------------------------------------------------------------- refresh
    def refresh(self, *, account_alias: str, adapter_id: str,
                contracts: Mapping[str, SymbolContract], now_ms: int,
                source: str = "venue_sync") -> list[Route]:
        out: list[Route] = []
        for symbol, contract in sorted(contracts.items()):
            key = (account_alias, symbol)
            if key in self._disabled:
                state = RouteState.DISABLED
            elif contract.trade_mode == "DISABLED":
                state = RouteState.DISABLED
            elif contract.trade_mode == "CLOSE_ONLY":
                state = RouteState.CLOSE_ONLY
            else:
                state = RouteState.RESOLVED
            route = Route(account_alias=account_alias, symbol=symbol, venue=contract.venue,
                          adapter_id=adapter_id, contract=contract, state=state,
                          resolved_ms=now_ms, source=source)
            self._routes[key] = route
            out.append(route)
            if self._ledger is not None:
                self._ledger.append(make_event(
                    EventKind.ROUTE_REGISTRY, self._producer, route.body(),
                    event_time_ms=now_ms, received_time_ms=now_ms,
                    correlation_id=f"{account_alias}:{symbol}"))
        return out

    def disable(self, account_alias: str, symbol: str, *, disabled: bool = True) -> None:
        key = (account_alias, symbol)
        if disabled:
            self._disabled.add(key)
            if key in self._routes:
                self._routes[key] = Route(**{**self._routes[key].__dict__,
                                             "state": RouteState.DISABLED})
        else:
            self._disabled.discard(key)

    # ---------------------------------------------------------------- resolve
    def state_of(self, account_alias: str, symbol: str, *, now_ms: int) -> RouteState:
        route = self._routes.get((account_alias, symbol))
        if route is None:
            return RouteState.UNRESOLVED
        if route.state is RouteState.RESOLVED and route.age_ms(now_ms) > self.max_age_ms:
            return RouteState.STALE
        return route.state

    def resolve(self, account_alias: str, symbol: str, *, now_ms: int,
                direction: Optional[Direction] = None) -> Route:
        state = self.state_of(account_alias, symbol, now_ms=now_ms)
        if state is not RouteState.RESOLVED:
            raise RouteUnresolved(
                f"{account_alias}/{symbol} is {state.value}; no order may be built from it")
        route = self._routes[(account_alias, symbol)]
        if direction is not None and not route.contract.allows(direction):
            raise RouteUnresolved(
                f"{account_alias}/{symbol} trade mode {route.contract.trade_mode} "
                f"does not permit {direction.value}")
        return route

    def quantise(self, route: Route, *, quantity: Decimal, entry: Optional[Decimal] = None,
                 stop: Optional[Decimal] = None,
                 direction: Optional[Direction] = None) -> QuantisedOrder:
        notes: list[str] = []
        c = route.contract
        if c.volume_max > ZERO and quantity > c.volume_max:
            notes.append(f"capped at venue maximum {c.volume_max}")
        qty, shortfall = quantise_volume(c, quantity)
        if shortfall > ZERO:
            notes.append(f"lot step gave up {shortfall}")

        q_entry = None if entry is None else _round_to_tick(entry, c.tick_size)
        q_stop = None
        if stop is not None:
            if entry is None or direction is None:
                raise QuantisationRefused("a stop cannot be quantised without entry and direction")
            q_stop = quantise_stop(c, entry=entry, stop=stop, direction=direction)
            distance = abs((q_entry if q_entry is not None else entry) - q_stop)
            if c.min_stop_distance > ZERO and distance < c.min_stop_distance:
                # Widening to reach the venue minimum is exactly the move
                # INV-RISK-001 forbids, so the trade is not placeable instead.
                raise QuantisationRefused(
                    f"stop distance {distance} is inside the venue minimum "
                    f"{c.min_stop_distance}, and widening it is not available")
        return QuantisedOrder(qty, q_entry, q_stop, shortfall, tuple(notes))

    # ------------------------------------------------------------------ report
    def report(self, *, now_ms: int) -> dict[str, Any]:
        by_state: dict[str, int] = {}
        for (alias, symbol) in sorted(self._routes):
            s = self.state_of(alias, symbol, now_ms=now_ms).value
            by_state[s] = by_state.get(s, 0) + 1
        return {
            "registry_version": REGISTRY_VERSION,
            "routes": len(self._routes),
            "max_age_ms": self.max_age_ms,
            "by_state": dict(sorted(by_state.items())),
            "unusable": sorted(
                f"{a}/{s}" for (a, s) in self._routes
                if self.state_of(a, s, now_ms=now_ms) is not RouteState.RESOLVED),
        }
