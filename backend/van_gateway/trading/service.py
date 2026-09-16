"""Owner-facing trading surface (Rev 4 Part K). Reads the VATI hash-chained
ledger for status and open ZSE owner tickets; writes exactly two owner-signed
(A4) events: OWNER_HALT and OWNER_TICKET confirmation. It never creates,
sizes, modifies or cancels an order, and it never holds broker credentials.

The `vati` package lives under <repo>/trading; it is imported lazily so the
gateway still starts (degraded: TRADING_LEDGER_UNAVAILABLE) without it."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

READ_KINDS = ("SESSION", "OPPORTUNITY_ASSESSMENT", "RISK_DECISION", "ORDER_COMMAND", "EXECUTION_RECEIPT", "TRADE_REVIEW", "TRADE_EXPERIENCE_ARTIFACT", "KILL_SWITCH", "OWNER_TICKET", "CAPSULE_STATE")


class TradingControlError(PermissionError):
    pass


def _import_vati():
    try:
        import vati  # noqa: F401
    except ImportError:
        trading_dir = Path(__file__).resolve().parents[3] / "trading"
        if trading_dir.is_dir() and str(trading_dir) not in sys.path:
            sys.path.append(str(trading_dir))
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    return EventKind, make_event, Ledger


def _import_trade_book():
    _import_vati()
    from vati.app.tradebook import VIEWS, build_trade_book
    return VIEWS, build_trade_book


@dataclass
class TradingService:
    ledger_path: str
    producer: str = "van-gateway"

    # ---------------------------------------------------------------- state
    def available(self) -> bool:
        return self.ledger_path == ":memory:" or Path(self.ledger_path).is_file()

    def _open(self):
        EventKind, make_event, Ledger = _import_vati()
        return EventKind, make_event, Ledger(self.ledger_path)

    def status(self) -> dict[str, Any]:
        if not self.available():
            return {"ledger_available": False, "ledger_path": self.ledger_path, "chain_ok": None, "events": 0, "kill_switch_active": None, "open_tickets": 0,
                    "authority": "VATI Risk Authority; Hermes and the gateway never place orders"}
        EventKind, _, led = self._open()
        try:
            ok, checked = led.verify_chain()
            counts = {k: led.count(EventKind(k)) for k in READ_KINDS}
            last_ms = 0
            halts: list[dict] = []
            for ev in led.iter(EventKind.KILL_SWITCH):
                last_ms = max(last_ms, ev.event_time_ms)
                halts.append({"trigger": ev.payload.get("trigger"), "event_time_ms": ev.event_time_ms, "hash": ev.hash, "cleared": bool(ev.payload.get("cleared"))})
            for ev in led.iter(EventKind.SESSION):
                last_ms = max(last_ms, ev.event_time_ms)
            tripped = [h for h in halts if not h["cleared"]]
            cleared = {h["trigger"] for h in halts if h["cleared"]}
            active = [h for h in tripped if h["trigger"] not in cleared or h["event_time_ms"] > max((x["event_time_ms"] for x in halts if x["cleared"] and x["trigger"] == h["trigger"]), default=-1)]
            tickets = self._tickets(led, EventKind)
            return {"ledger_available": True, "ledger_path": self.ledger_path, "head": led.head(), "chain_ok": ok, "events": checked, "counts": counts,
                    "kill_switch_active": bool(active), "kill_switch_triggers": sorted({h["trigger"] for h in active if h["trigger"]}),
                    "open_tickets": sum(1 for t in tickets if t["status"] == "OPEN"), "last_event_ms": last_ms,
                    "authority": "VATI Risk Authority; Hermes and the gateway never place orders"}
        finally:
            led.close()

    # -------------------------------------------------------------- tickets
    @staticmethod
    def _tickets(led, EventKind) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for ev in led.iter(EventKind.OWNER_TICKET):
            tid = str(ev.payload.get("ticket") or "")
            if not tid:
                continue
            if ev.payload.get("action") == "CONFIRMED":
                t = by_id.setdefault(tid, {"ticket": tid, "status": "OPEN"})
                t.update({"status": "CONFIRMED", "confirmed_ms": ev.event_time_ms, "fill_price": ev.payload.get("fill_price"), "filled_qty": ev.payload.get("filled_qty"),
                          "contract_note_ref": ev.payload.get("contract_note_ref"), "confirmation_hash": ev.hash})
            else:
                t = by_id.setdefault(tid, {"ticket": tid, "status": "OPEN"})
                t.update({"symbol": ev.payload.get("symbol"), "qty": ev.payload.get("qty"), "issued_ms": ev.event_time_ms, "trade_intent_id": ev.correlation_id, "ticket_hash": ev.hash})
        return sorted(by_id.values(), key=lambda t: t.get("issued_ms", 0))

    def tickets(self, *, status: Optional[str] = None) -> list[dict[str, Any]]:
        if not self.available():
            return []
        EventKind, _, led = self._open()
        try:
            out = self._tickets(led, EventKind)
        finally:
            led.close()
        return [t for t in out if status is None or t["status"] == status]

    # ------------------------------------------------------------ trade book
    def trade_book(self, *, view: str = "all", limit: int = 50) -> dict[str, Any]:
        """Past / current / potential trades with confidence scores, read from the ledger (Rev 4 K.4)."""
        views, build = _import_trade_book()
        if view not in views:
            raise ValueError(f"view must be one of {views}")
        limit = max(1, min(int(limit), 200))
        if not self.available():
            book = {"view": view, "ledger_available": False, "ledger_path": self.ledger_path, "counts": {}}
            for k in ("past", "current", "potential"):
                if view in (k, "all"):
                    book[k] = []; book["counts"][k] = 0
            return book
        _, _, led = self._open()
        try:
            book = build(led, view=view, limit=limit)
        finally:
            led.close()
        book["ledger_available"] = True
        return book

    # --------------------------------------------------------- owner writes
    @staticmethod
    def _require_signature(owner_signature_ref: str) -> str:
        sig = (owner_signature_ref or "").strip()
        if not sig:
            raise TradingControlError("owner-signed authority (A4) is required: owner_signature_ref is empty")
        return sig

    def halt(self, *, owner_signature_ref: str, reason: str, now_ms: Optional[int] = None) -> dict[str, Any]:
        """Append an OWNER_HALT kill-switch event. The runner observes it and stops new orders; open positions stay protected."""
        sig = self._require_signature(owner_signature_ref)
        if not self.available():
            raise FileNotFoundError(f"trading ledger not available at {self.ledger_path}")
        EventKind, make_event, led = self._open()
        try:
            now = now_ms if now_ms is not None else int(time.time() * 1000)
            ev = make_event(EventKind.KILL_SWITCH, self.producer, {"trigger": "OWNER_HALT", "sig": sig, "reason": (reason or "")[:500], "channel": "gateway"}, event_time_ms=now, received_time_ms=now, correlation_id="owner")
            chain = led.append(ev)
            return {"halted": True, "trigger": "OWNER_HALT", "event_hash": ev.hash, "chain_hash": chain, "event_time_ms": now}
        finally:
            led.close()

    def confirm_ticket(self, ticket_id: str, *, owner_signature_ref: str, fill_price: str, filled_qty: str, contract_note_ref: str, now_ms: Optional[int] = None) -> dict[str, Any]:
        """Record the owner's broker confirmation for a ZSE OWNER_TICKET. Only an OPEN ticket can be confirmed, once."""
        sig = self._require_signature(owner_signature_ref)
        if not (contract_note_ref or "").strip():
            raise ValueError("a broker contract note reference is required")
        try:
            px, qty = Decimal(str(fill_price)), Decimal(str(filled_qty))
        except InvalidOperation as exc:
            raise ValueError("fill_price and filled_qty must be decimal strings") from exc
        if px <= 0 or qty <= 0:
            raise ValueError("fill_price and filled_qty must be positive")
        if not self.available():
            raise FileNotFoundError(f"trading ledger not available at {self.ledger_path}")
        EventKind, make_event, led = self._open()
        try:
            known = {t["ticket"]: t for t in self._tickets(led, EventKind)}
            t = known.get(ticket_id)
            if t is None:
                raise KeyError(f"unknown ticket {ticket_id}")
            if t["status"] != "OPEN":
                raise TradingControlError(f"ticket {ticket_id} is already {t['status']}")
            if t.get("qty") is not None and qty > Decimal(str(t["qty"])):
                raise ValueError(f"filled_qty {qty} exceeds ticket quantity {t['qty']}")
            now = now_ms if now_ms is not None else int(time.time() * 1000)
            ev = make_event(EventKind.OWNER_TICKET, self.producer, {"ticket": ticket_id, "action": "CONFIRMED", "fill_price": str(px), "filled_qty": str(qty), "contract_note_ref": contract_note_ref.strip(), "sig": sig},
                            event_time_ms=now, received_time_ms=now, correlation_id=t.get("trade_intent_id") or ticket_id)
            chain = led.append(ev)
            return {"ticket": ticket_id, "status": "CONFIRMED", "event_hash": ev.hash, "chain_hash": chain, "event_time_ms": now}
        finally:
            led.close()
