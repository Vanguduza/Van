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


#: P0-TRADE-004. How old the newest ledger event may be before the gateway stops treating
#: what it reads as current. A live session writes a heartbeat, a market-state event and an
#: account snapshot on every bar, so minutes of silence means the gateway is not looking at
#: the ledger the session is writing.
#:
#: DECISION (recorded, no owner input): fifteen minutes is generous enough for a session on
#: a slow timeframe and short enough that a file left over from a previous deployment is
#: caught the first time anybody asks.
LEDGER_STALENESS_MS = 15 * 60 * 1000


class TradingControlError(PermissionError):
    pass


class TradingAuthorityError(TradingControlError):
    """The owner authority for this act is absent, invalid, expired, reused or misdirected.

    Distinct from its parent so the routes can answer 403 rather than 409: "you are not
    authorised" and "that ticket is already confirmed" are different things to tell a
    caller, and the confirm route used to map both to a conflict (P0-TRADE-001).
    """


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


def _import_portfolio():
    _import_vati()
    import importlib
    pf = importlib.import_module("vati.app.portfolio")   # the package re-exports a `portfolio` function under the same name; import the module explicitly
    from vati.market_data.feeds.lake import TIMEFRAMES_MS, BarLake
    return pf, BarLake, TIMEFRAMES_MS


@dataclass
class TradingService:
    ledger_path: str
    producer: str = "van-gateway"
    accounts_registry: str = ""
    lake_root: str = ""
    reporting_currency: str = "USD"
    #: P0-TRADE-001. The verifier for owner-signed trading acts. Left None here and built
    #: lazily so the dataclass stays importable without the vati package on the path; a
    #: host with no registered owner key gets a verifier that refuses everything, which is
    #: the correct default for a process that can halt live trading.
    owner_authority: Any = None

    # ---------------------------------------------------------------- state
    def available(self) -> bool:
        return self.ledger_path == ":memory:" or self.ledger_path.startswith(("postgres://", "postgresql://")) or Path(self.ledger_path).is_file()

    def _open(self):
        EventKind, make_event, Ledger = _import_vati()
        if self.ledger_path.startswith(("postgres://", "postgresql://")):
            from vati.core.ledger_pg import PostgresLedger
            return EventKind, make_event, PostgresLedger(self.ledger_path)
        return EventKind, make_event, Ledger(self.ledger_path)

    def _registry_public(self) -> list[dict]:
        if not self.accounts_registry or not Path(self.accounts_registry).is_file():
            return []
        _import_vati()
        from vati.accounts import AccountRegistry
        return AccountRegistry(self.accounts_registry).public()

    def _lake(self):
        if not self.lake_root or not Path(self.lake_root).is_dir():
            return None
        _, BarLake, _ = _import_portfolio()
        return BarLake(self.lake_root)

    def _with_ledger(self, fn, *, empty):
        if not self.available():
            return empty
        _, _, led = self._open()
        try:
            return fn(led)
        finally:
            led.close()

    # ------------------------------------------------------------ command-center read models
    def portfolio(self) -> dict[str, Any]:
        pf, _, _ = _import_portfolio()
        reg = self._registry_public()
        empty = {"ledger_available": False, "reporting_currency": self.reporting_currency, "accounts": [{**a, "equity": None, "balance": None, "connection_state": "NEVER_SYNCED"} for a in reg],
                 "totals": {}, "risk": {}, "exposure": {}, "recent_trades": [], "open_positions": [], "potential_trades": [], "data_state": {}}
        out = self._with_ledger(lambda led: pf.portfolio(led, reg, reporting_currency=self.reporting_currency), empty=empty)
        out.setdefault("ledger_available", True)
        return out

    def accounts(self) -> dict[str, Any]:
        pf, _, _ = _import_portfolio()
        reg = self._registry_public()
        return {"accounts": self._with_ledger(lambda led: pf.account_states(led, reg), empty=reg), "registry": self.accounts_registry or None}

    def market_state(self, symbol: Optional[str] = None) -> dict[str, Any]:
        pf, _, _ = _import_portfolio()
        return self._with_ledger(lambda led: pf.market_state(led, symbol), empty={"symbols": [], "ledger_available": False})

    def risk(self) -> dict[str, Any]:
        pf, _, _ = _import_portfolio()
        return self._with_ledger(lambda led: pf.risk(led), empty={"ledger_available": False, "positions": [], "concentration": {}})

    def trade_detail(self, trade_intent_id: str) -> Optional[dict[str, Any]]:
        pf, _, _ = _import_portfolio()
        lake = self._lake()
        return self._with_ledger(lambda led: pf.trade_detail(led, trade_intent_id, lake=lake), empty=None)

    def bars(self, symbol: str, timeframe: str, *, limit: int = 300, end_ms: Optional[int] = None) -> dict[str, Any]:
        pf, _, TIMEFRAMES_MS = _import_portfolio()
        if timeframe not in TIMEFRAMES_MS:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES_MS)}")
        lake = self._lake()
        if lake is None:
            return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": [], "count": 0, "provenance": [], "data_state": {"state": "UNAVAILABLE"}, "lake_available": False}
        limit = max(10, min(int(limit), 2000))
        if not self.available():
            return {**pf.bars(lake, symbol, timeframe, limit=limit, end_ms=end_ms), "lake_available": True}
        return self._with_ledger(lambda led: {**pf.bars(lake, symbol, timeframe, limit=limit, end_ms=end_ms, ledger=led), "lake_available": True}, empty={})

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
            # P0-TRADE-004 — last_event_ms was reported and never thresholded, so a stale
            # local SQLite file presented old data as current. The gateway cannot tell by
            # looking whether it is reading the live ledger or a copy somebody left behind;
            # what it can tell is that a live trading session writes constantly, so a
            # ledger whose newest event is old is not one to answer questions from.
            now_ms = int(time.time() * 1000)
            age_ms = max(0, now_ms - last_ms) if last_ms else None
            stale = age_ms is None or age_ms > LEDGER_STALENESS_MS
            payload = {"ledger_available": True, "ledger_path": self.ledger_path, "head": led.head(), "chain_ok": ok, "events": checked, "counts": counts,
                    "kill_switch_active": bool(active), "kill_switch_triggers": sorted({h["trigger"] for h in active if h["trigger"]}),
                    "open_tickets": sum(1 for t in tickets if t["status"] == "OPEN"), "last_event_ms": last_ms,
                    "ledger_age_ms": age_ms, "ledger_stale": stale,
                    "ledger_staleness_threshold_ms": LEDGER_STALENESS_MS,
                    "authority": "VATI Risk Authority; Hermes and the gateway never place orders"}
            if stale:
                # Said in the payload rather than only in a degraded code, because the
                # number is what makes it actionable and "no events at all" is a different
                # situation from "nothing for an hour".
                payload["ledger_stale_reason"] = (
                    "no events have ever been written to this ledger"
                    if not last_ms else
                    f"newest event is {age_ms // 1000}s old, past the "
                    f"{LEDGER_STALENESS_MS // 1000}s threshold"
                )
            return payload
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
    def _authority(self):
        if self.owner_authority is None:
            from vati.authority import OwnerAuthorityVerifier

            self.owner_authority = OwnerAuthorityVerifier()
        return self.owner_authority

    def _require_signature(self, owner_signature_ref: str, *, act: str, subject: str) -> str:
        """P0-TRADE-001 — this asked whether the string was non-empty, and "x" passed.

        The act and the subject are inside the signature, so authority to confirm one
        ticket is not authority to confirm another, and neither is authority to halt.
        """
        from vati.authority import OwnerAuthorityError

        try:
            return self._authority().verify(
                owner_signature_ref, act=act, subject=subject
            ).ref
        except OwnerAuthorityError as exc:
            raise TradingAuthorityError(
                f"owner-signed authority (A4) is required: {exc}"
            ) from exc

    def halt(self, *, owner_signature_ref: str, reason: str, now_ms: Optional[int] = None) -> dict[str, Any]:
        """Append an OWNER_HALT kill-switch event. The runner observes it and stops new orders; open positions stay protected."""
        sig = self._require_signature(
            owner_signature_ref, act="owner-halt", subject="van-trading-core"
        )
        if not self.available():
            raise FileNotFoundError(f"trading ledger not available at {self.ledger_path}")
        EventKind, make_event, led = self._open()
        try:
            now = now_ms if now_ms is not None else int(time.time() * 1000)
            ev = make_event(EventKind.KILL_SWITCH, self.producer, {"trigger": "OWNER_HALT", "sig": sig, "reason": (reason or "")[:500], "channel": "gateway"}, event_time_ms=now, received_time_ms=now, correlation_id="owner")
            chain = led.append(ev)
            # `sig` is the verified authority's reference, so a caller recording this
            # does not have to touch the raw token (P0-TRADE-001).
            return {"halted": True, "trigger": "OWNER_HALT", "sig": sig, "event_hash": ev.hash, "chain_hash": chain, "event_time_ms": now}
        finally:
            led.close()

    def confirm_ticket(self, ticket_id: str, *, owner_signature_ref: str, fill_price: str, filled_qty: str, contract_note_ref: str, now_ms: Optional[int] = None) -> dict[str, Any]:
        """Record the owner's broker confirmation for a ZSE OWNER_TICKET. Only an OPEN ticket can be confirmed, once."""
        sig = self._require_signature(
            owner_signature_ref, act="ticket-confirm", subject=str(ticket_id)
        )
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
