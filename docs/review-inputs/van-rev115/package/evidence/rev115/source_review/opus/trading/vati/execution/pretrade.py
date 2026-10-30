"""Pre-trade control layer (TRD-REV51-105, G5b).

The last deterministic gate before an ORDER_COMMAND exists. It runs on every
order-sending intent, root or child, and it has exactly one power: to refuse.

That limitation is the design. The Risk Authority decided how much risk this
trade may carry, and nothing here may revisit that number upward or downward —
this layer checks that the approved decision can be *expressed* at the venue
and that nothing about the request is obviously wrong. The single quantity
change it may make is rounding down to the venue's lot step, which is a fact
about the venue rather than an opinion about risk (INV-AUTH-001).

Checks run in a fixed order and the first failure names the reason, exactly as
the Risk Authority does, so a rejection always cites its highest-priority
cause rather than whichever check happened to run first. The order is
deliberate: identity and seal before market data, market data before
heuristics. A fat-finger check that fires on a tampered decision would hide
the tampering.

Two checks deserve their names. **Stop integrity** compares the quantised stop
to the distance the authority approved and refuses anything wider — including
wider by one tick of rounding, because arithmetic is a perfectly good way to
widen a stop. **Off-market price** refuses an entry far from the last mark:
the usual cause is a stale decision, and a stale decision filling at market is
the single most expensive ordinary bug in this kind of system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Sequence

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.execution.route_registry import (
    QuantisationRefused,
    QuantisedOrder,
    Route,
    RouteRegistry,
    RouteUnresolved,
)
from vati.risk.contracts import Direction, LossModel, TradeIntent

PRODUCER = "vati-pretrade-control"
PRETRADE_VERSION = "pretrade-control/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: An entry further than this from the last mark is refused. Wide enough not
#: to fire on an ordinary spread, narrow enough that a decision minutes stale
#: cannot reach the venue.
MAX_PRICE_DEVIATION_PCT = Decimal("0.005")     # 0.5%

#: A request more than this multiple of the account's recent typical order is
#: refused pending a human look. It is a shape check, not a risk check: the
#: Risk Authority has already sized this, so a trip here means the inputs to
#: that sizing were probably wrong.
FAT_FINGER_MULTIPLE = Decimal("10")

#: Below this many prior orders there is no "typical", so the check abstains
#: rather than inventing a baseline from three samples.
MIN_ORDERS_FOR_FAT_FINGER = 20

#: Orders per rolling window per account. A reject storm and a runaway loop
#: look identical from here, and both want the same answer.
MAX_ORDERS_PER_WINDOW = 30
ORDER_WINDOW_MS = 60_000


class Verdict(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"


#: Every way this layer may refuse. Closed, ordered by the sequence below.
PRETRADE_REASONS: dict[str, str] = {
    "DECISION_NOT_APPROVED": "the risk decision did not approve this intent",
    "DECISION_INTENT_MISMATCH": "the decision belongs to a different intent",
    "DECISION_SEAL_INVALID": "the decision hash does not recompute",
    "APPROVED_SIZE_EMPTY": "the approved size is zero or negative",
    "IDEMPOTENCY_REPLAY": "this idempotency key has already been sent",
    "ROUTE_UNRESOLVED": "no usable venue route for this account and symbol",
    "DIRECTION_NOT_PERMITTED": "the venue trade mode forbids this direction",
    "SIZE_NOT_EXPRESSIBLE": "the approved size cannot be expressed at this venue",
    "SIZE_EXCEEDS_APPROVED": "the quantised size is larger than the approved size",
    "STOP_MISSING": "this loss model requires a stop and none was supplied",
    "STOP_WIDER_THAN_APPROVED": "the stop is further from entry than the approved distance",
    "PRICE_OFF_MARKET": "the entry price is far from the last mark",
    "NOTIONAL_CAP": "order notional exceeds the per-order cap",
    "FAT_FINGER": "order size is far outside this account's recent range",
    "ORDER_RATE_LIMIT": "too many orders for this account in the window",
    "MARK_STALE": "the reference mark is older than its useful life",
}


class PreTradeConfigError(ValueError):
    pass


@dataclass(frozen=True)
class MarketReference:
    """The venue's own last word on price, and how old it is."""

    last_price: Decimal
    mark_age_ms: int
    max_mark_age_ms: int = 30_000

    @property
    def fresh(self) -> bool:
        return 0 <= self.mark_age_ms <= self.max_mark_age_ms


@dataclass(frozen=True)
class PreTradeResult:
    verdict: Verdict
    reason_code: str
    reason_detail: str
    quantised: Optional[QuantisedOrder]
    trade_intent_id: str
    checks_run: tuple[str, ...]
    pretrade_version: str = PRETRADE_VERSION

    @property
    def passed(self) -> bool:
        return self.verdict is Verdict.PASS

    def body(self) -> dict[str, Any]:
        return {
            "trade_intent_id": self.trade_intent_id,
            "verdict": self.verdict.value,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "quantised": None if self.quantised is None else self.quantised.body(),
            "checks_run": list(self.checks_run),
            "pretrade_version": PRETRADE_VERSION,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class PreTradeControls:
    """Deterministic refusal gate. Validates; never sizes."""

    def __init__(self, *, routes: RouteRegistry,
                 max_notional: Optional[Decimal] = None,
                 max_orders_per_window: int = MAX_ORDERS_PER_WINDOW,
                 order_window_ms: int = ORDER_WINDOW_MS,
                 ledger=None, producer: str = PRODUCER) -> None:
        if max_orders_per_window <= 0:
            raise PreTradeConfigError("an order limit of zero is a halt, not a limit")
        self.routes = routes
        self.max_notional = max_notional
        self.max_orders_per_window = max_orders_per_window
        self.order_window_ms = order_window_ms
        self._ledger = ledger
        self._producer = producer
        self._sent_keys: set[str] = set()
        self._order_times: dict[str, list[int]] = {}
        self._recent_sizes: dict[str, list[Decimal]] = {}

    # ---------------------------------------------------------------- history
    def note_sent(self, *, account_alias: str, idempotency_key: str,
                  quantity: Decimal, now_ms: int) -> None:
        """Called by the order path once a command has actually been built."""
        self._sent_keys.add(idempotency_key)
        self._order_times.setdefault(account_alias, []).append(now_ms)
        sizes = self._recent_sizes.setdefault(account_alias, [])
        sizes.append(quantity)
        if len(sizes) > 500:
            del sizes[:-500]

    def _orders_in_window(self, account_alias: str, now_ms: int) -> int:
        times = self._order_times.get(account_alias, [])
        cutoff = now_ms - self.order_window_ms
        keep = [t for t in times if t >= cutoff]
        self._order_times[account_alias] = keep
        return len(keep)

    def _typical_size(self, account_alias: str) -> Optional[Decimal]:
        sizes = sorted(self._recent_sizes.get(account_alias, []))
        if len(sizes) < MIN_ORDERS_FOR_FAT_FINGER:
            return None
        return sizes[len(sizes) // 2]

    # ------------------------------------------------------------------ check
    def check(self, *, intent: TradeIntent, decision, mark: Optional[MarketReference],
              now_ms: int) -> PreTradeResult:
        """Run every control in order. The first failure names the reason."""
        ran: list[str] = []

        def fail(code: str, detail: str, quantised=None) -> PreTradeResult:
            return self._emit(PreTradeResult(Verdict.REJECT, code, detail, quantised,
                                             intent.trade_intent_id, tuple(ran)), now_ms)

        # --- identity and seal, before anything that could hide tampering ---
        ran.append("DECISION_NOT_APPROVED")
        if str(getattr(decision, "decision", "")).upper() not in ("APPROVED", "REDUCED") and \
           getattr(getattr(decision, "decision", None), "value", "") not in ("APPROVED", "REDUCED"):
            return fail("DECISION_NOT_APPROVED",
                        f"decision is {getattr(decision, 'decision', None)}")

        ran.append("DECISION_INTENT_MISMATCH")
        if getattr(decision, "trade_intent_id", None) != intent.trade_intent_id:
            return fail("DECISION_INTENT_MISMATCH",
                        f"decision names {getattr(decision, 'trade_intent_id', None)!r}")

        ran.append("DECISION_SEAL_INVALID")
        if not _seal_recomputes(decision):
            return fail("DECISION_SEAL_INVALID", "recomputed hash does not match")

        approved = Decimal(str(getattr(decision, "approved_size", ZERO)))
        ran.append("APPROVED_SIZE_EMPTY")
        if approved <= ZERO:
            return fail("APPROVED_SIZE_EMPTY", f"approved size is {approved}")

        ran.append("IDEMPOTENCY_REPLAY")
        if intent.idempotency_key in self._sent_keys:
            return fail("IDEMPOTENCY_REPLAY", f"key {intent.idempotency_key} already sent")

        # --- route and expressibility ---
        ran.append("ROUTE_UNRESOLVED")
        try:
            route = self.routes.resolve(intent.account_alias, intent.symbol,
                                        now_ms=now_ms, direction=intent.direction)
        except RouteUnresolved as exc:
            code = ("DIRECTION_NOT_PERMITTED" if "does not permit" in str(exc)
                    else "ROUTE_UNRESOLVED")
            ran[-1] = code
            return fail(code, str(exc))

        ran.append("SIZE_NOT_EXPRESSIBLE")
        try:
            quantised = self.routes.quantise(
                route, quantity=approved, entry=intent.entry, stop=intent.stop,
                direction=intent.direction)
        except QuantisationRefused as exc:
            return fail("SIZE_NOT_EXPRESSIBLE", str(exc))

        ran.append("SIZE_EXCEEDS_APPROVED")
        if quantised.quantity > approved:
            # Cannot happen while quantisation floors, which is why it is
            # checked: this is the assertion that keeps that true.
            return fail("SIZE_EXCEEDS_APPROVED",
                        f"quantised {quantised.quantity} > approved {approved}", quantised)

        # --- protection integrity ---
        ran.append("STOP_MISSING")
        if route.contract.loss_model is LossModel.STOP_DISTANCE and quantised.stop_price is None:
            return fail("STOP_MISSING", "STOP_DISTANCE loss model requires a stop", quantised)

        ran.append("STOP_WIDER_THAN_APPROVED")
        if intent.stop is not None and quantised.stop_price is not None:
            approved_distance = abs(intent.entry - intent.stop)
            actual_distance = abs((quantised.entry_price or intent.entry) - quantised.stop_price)
            if actual_distance > approved_distance:
                return fail("STOP_WIDER_THAN_APPROVED",
                            f"{actual_distance} > approved {approved_distance}", quantised)

        # --- market sanity ---
        if mark is not None:
            ran.append("MARK_STALE")
            if not mark.fresh:
                return fail("MARK_STALE", f"mark is {mark.mark_age_ms}ms old", quantised)
            ran.append("PRICE_OFF_MARKET")
            entry = quantised.entry_price or intent.entry
            if mark.last_price > ZERO:
                deviation = abs(entry - mark.last_price) / mark.last_price
                if deviation > MAX_PRICE_DEVIATION_PCT:
                    return fail("PRICE_OFF_MARKET",
                                f"entry {entry} is {deviation} from mark {mark.last_price}",
                                quantised)

        # --- shape checks ---
        if self.max_notional is not None:
            ran.append("NOTIONAL_CAP")
            notional = quantised.quantity * route.contract.contract_size * (
                quantised.entry_price or intent.entry)
            if notional > self.max_notional:
                return fail("NOTIONAL_CAP", f"notional {notional} > cap {self.max_notional}",
                            quantised)

        typical = self._typical_size(intent.account_alias)
        if typical is not None and typical > ZERO:
            ran.append("FAT_FINGER")
            if quantised.quantity > typical * FAT_FINGER_MULTIPLE:
                return fail("FAT_FINGER",
                            f"{quantised.quantity} is over {FAT_FINGER_MULTIPLE}x the "
                            f"recent typical {typical}", quantised)

        ran.append("ORDER_RATE_LIMIT")
        if self._orders_in_window(intent.account_alias, now_ms) >= self.max_orders_per_window:
            return fail("ORDER_RATE_LIMIT",
                        f"{self.max_orders_per_window} orders already in "
                        f"{self.order_window_ms}ms", quantised)

        return self._emit(PreTradeResult(Verdict.PASS, "OK", "", quantised,
                                         intent.trade_intent_id, tuple(ran)), now_ms)

    def _emit(self, result: PreTradeResult, now_ms: int) -> PreTradeResult:
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.PRETRADE_CONTROL, self._producer, result.body(),
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=result.trade_intent_id))
        return result


def _seal_recomputes(decision) -> bool:
    """Recompute the decision hash the same way the router does."""
    to_dict = getattr(decision, "to_dict", None)
    stored = getattr(decision, "decision_hash", "")
    if not callable(to_dict) or not stored:
        return False
    body = to_dict()
    body.pop("decision_hash", None)
    return canonical_hash(body) == stored
