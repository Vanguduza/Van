"""Durable uncertainty fence for protective-close transport.

The account ledger is the existing single writer/transaction owner. A request
is committed before transport, then its original receipt and disposition are
committed together. A crash between those boundaries remains unresolved. This
journal never queries a venue, retries, clears a kill switch or grants authority.
"""
from decimal import Decimal

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import LedgerError


VERSION = "protective-exit-journal/1"
TERMINAL = frozenset({"CONFIRMED", "PARTIAL_CONFIRMED", "NOT_EXECUTED"})


class ExitPending(RuntimeError):
    pass


class ExitJournal:
    def __init__(self, ledger, producer):
        self.ledger, self.producer = ledger, producer

    @staticmethod
    def scope(venue, position_id):
        return canonical_hash({"venue": venue, "position_id": position_id})

    def _events(self, venue=None, position_id=None):
        correlation = None if venue is None else self.scope(venue, position_id)
        for event in self.ledger.iter(EventKind.EXIT_ATTEMPT, correlation_id=correlation):
            if event.producer != self.producer:
                continue
            p = event.payload
            if (event.hash != canonical_hash(event.body()) or p.get("version") != VERSION
                or event.correlation_id != self.scope(p.get("venue"), p.get("position_id"))
                or p.get("state") not in {"REQUESTED", "ACCEPTED", "UNKNOWN", *TERMINAL}):
                raise LedgerError("invalid native protective-exit journal; reconciliation required")
            yield event

    def latest(self, venue, position_id):
        return next(reversed(list(self._events(venue, position_id))), None)

    def pending(self, venue, position_id):
        legacy = self.legacy_uncertain(venue, position_id)
        if legacy is not None:
            return legacy
        row = self.latest(venue, position_id)
        return row if row is not None and row.payload["state"] not in TERMINAL else None

    def legacy_uncertain(self, venue, position_id):
        """Old UNKNOWN close facts must not disappear on a software upgrade.

        No source revision/request binding existed in those records. A later
        arrival cannot silently settle them; native reconciliation is needed.
        """
        return next((e for e in self._legacy_unknowns()
                     if e.payload.get("venue") == venue and e.payload.get("broker_position_id") == position_id), None)

    def _legacy_unknowns(self):
        for event in self.ledger.iter(EventKind.EXECUTION_RECEIPT):
            p = event.payload
            if (event.producer == self.producer and p.get("exit_action") == "CLOSE"
                and p.get("status") == "UNKNOWN" and not p.get("exit_request_ref")):
                if event.hash != canonical_hash(event.body()) or not p.get("venue") or not p.get("broker_position_id"):
                    raise LedgerError("unbound legacy unknown close; native reconciliation required")
                yield event

    def unresolved(self):
        rows = {}
        for event in self._events():
            rows[event.correlation_id] = event
        return tuple(e for e in rows.values() if e.payload["state"] not in TERMINAL) + tuple(self._legacy_unknowns())

    def begin(self, *, venue, position_id, trade_intent_id, action, quantity, reason, now_ms):
        if not venue or not position_id or action not in {"FULL_CLOSE", "PARTIAL_CLOSE"}:
            raise ValueError("protective exit requires an exact venue, position and action")
        if action == "PARTIAL_CLOSE" and (not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0):
            raise ValueError("partial close quantity must be finite and positive")
        with self.ledger.atomic():
            if self.legacy_uncertain(venue, position_id) is not None:
                raise ExitPending("legacy protective exit outcome unknown; native reconciliation required before retry")
            previous = self.latest(venue, position_id)
            if previous is not None and previous.payload["state"] not in TERMINAL:
                raise ExitPending("protective exit pending; reconcile its original outcome before retry")
            if previous is not None and previous.payload["state"] == "CONFIRMED" and previous.payload["action"] == "FULL_CLOSE":
                raise ExitPending("full close already confirmed; reconcile conflicting position state before another send")
            payload = {"version": VERSION, "state": "REQUESTED", "venue": venue,
                "position_id": position_id, "trade_intent_id": trade_intent_id,
                "action": action, "quantity": None if quantity is None else str(quantity),
                "reason": reason, "previous_state_ref": previous.hash if previous else None}
            event = make_event(EventKind.EXIT_ATTEMPT, self.producer, payload,
                event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=self.scope(venue, position_id))
            self.ledger.append(event)
        return event

    def finish(self, request, *, state, receipt_event_ref, now_ms):
        """Caller holds the ledger transaction that also appends the receipt."""
        if state not in {"ACCEPTED", "UNKNOWN", *TERMINAL}:
            raise ValueError("invalid exit disposition")
        with self.ledger.atomic():
            current = self.latest(request.payload["venue"], request.payload["position_id"])
            if current is None or current.payload.get("request_ref", current.hash) != request.hash:
                raise LedgerError("exit receipt does not bind the current transport attempt")
            if current.payload["state"] in TERMINAL:
                raise LedgerError("exit attempt already terminal; a stale receipt cannot reopen it")
            event = make_event(EventKind.EXIT_ATTEMPT, self.producer,
                {**request.payload, "state": state, "request_ref": request.hash,
                 "receipt_event_ref": receipt_event_ref},
                event_time_ms=now_ms, received_time_ms=now_ms, correlation_id=request.correlation_id)
            self.ledger.append(event)
        return event

    @staticmethod
    def receipt_state(receipt, *, venue, position_id, trade_intent_id):
        body = {k:v for k,v in receipt.__dict__.items() if k != "receipt_hash"}
        bound = (receipt.receipt_hash == canonical_hash(body) and receipt.venue == venue
            and receipt.broker_position_id == position_id
            and (not receipt.trade_intent_id or not trade_intent_id or receipt.trade_intent_id == trade_intent_id))
        qty = receipt.filled_qty
        if not bound or not isinstance(qty, Decimal) or not qty.is_finite() or qty < 0:
            return "UNKNOWN"
        if receipt.status in {"FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"}:
            price = receipt.average_fill
            return "CONFIRMED" if qty > 0 and isinstance(price, Decimal) and price.is_finite() else "UNKNOWN"
        if receipt.status in {"REJECTED", "CANCELLED", "EXPIRED"} and qty == 0:
            return "NOT_EXECUTED"
        return "ACCEPTED" if receipt.status == "ACCEPTED" and qty == 0 else "UNKNOWN"
