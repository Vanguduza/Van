"""Trade book for the owner surface (Rev 4 Part K.4): past, current and potential
trades assembled from the hash-chained ledger, each with a confidence score.

Everything here is a read model. It classifies what the ledger already
recorded; it cannot create, size, modify or cancel anything."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional

from vati.arbiter.confidence import BASIS, confidence_score
from vati.core.events import Event, EventKind
from vati.core.ledger import Ledger

VIEWS = ("past", "current", "potential", "all")
ENTRY_STATUSES = ("FILLED", "PARTIAL", "ACCEPTED", "OWNER_EXECUTED", "BROKER_CONFIRMED")
POTENTIAL_LABELS = ("TRADE", "REDUCE_SIZE", "WAIT", "REQUIRE_CONFIRMATION", "SKIP")


@dataclass
class _Chain:
    intent_id: str
    decision: Optional[Event] = None
    receipts: list[Event] = field(default_factory=list)
    tca: Optional[Event] = None
    review: Optional[Event] = None
    tickets: list[Event] = field(default_factory=list)
    router_refusal: Optional[str] = None


def _collect(ledger: Ledger) -> tuple[dict[str, _Chain], list[Event]]:
    chains: dict[str, _Chain] = {}
    assessments: list[Event] = []
    for ev in ledger.iter():
        if ev.kind is EventKind.OPPORTUNITY_ASSESSMENT:
            assessments.append(ev)
            continue
        if ev.kind not in (EventKind.RISK_DECISION, EventKind.EXECUTION_RECEIPT, EventKind.TCA_RECORD, EventKind.TRADE_REVIEW, EventKind.OWNER_TICKET, EventKind.SESSION):
            continue
        if ev.kind is EventKind.SESSION and "router_refused" not in ev.payload:
            continue
        c = chains.setdefault(ev.correlation_id, _Chain(ev.correlation_id))
        if ev.kind is EventKind.RISK_DECISION:
            c.decision = ev
        elif ev.kind is EventKind.EXECUTION_RECEIPT:
            c.receipts.append(ev)
        elif ev.kind is EventKind.TCA_RECORD:
            c.tca = ev
        elif ev.kind is EventKind.TRADE_REVIEW:
            c.review = ev
        elif ev.kind is EventKind.OWNER_TICKET:
            c.tickets.append(ev)
        elif ev.kind is EventKind.SESSION:
            c.router_refusal = str(ev.payload.get("router_refused"))
    return chains, assessments


def _intent_conf(intent: dict) -> dict:
    return confidence_score({k: intent.get(k) for k in intent if k.endswith("_multiplier")}).as_dict()


def _base_row(c: _Chain) -> Optional[dict[str, Any]]:
    if c.decision is None:
        return None
    intent = c.decision.payload["inputs"]["intent"]
    d = c.decision.payload["decision"]
    return {
        "trade_intent_id": c.intent_id, "symbol": intent["symbol"], "venue": intent["venue"], "direction": intent["direction"], "strategy_id": intent["strategy_id"],
        "strategy_version": intent.get("strategy_version"), "horizon": intent.get("horizon"), "entry": intent.get("entry"), "stop": intent.get("stop"),
        "expected_gross_move_pct": intent.get("expected_gross_move_pct"), "requested_risk_pct": d.get("requested_risk_pct"), "approved_risk_pct": d.get("approved_risk_pct"),
        "approved_size": d.get("approved_size"), "risk_decision": d.get("decision"), "reason_code": d.get("reason_code"), "decision_hash": d.get("decision_hash"),
        "decided_ms": c.decision.event_time_ms, "confidence": _intent_conf(intent),
    }


def _entry_receipt(c: _Chain) -> Optional[Event]:
    return next((r for r in c.receipts if r.payload.get("status") in ENTRY_STATUSES and not r.payload.get("exit_action")), None)


def past_trades(chains: Iterable[_Chain]) -> list[dict]:
    out = []
    for c in chains:
        if c.review is None:
            continue
        row = _base_row(c)
        if row is None:
            continue
        rv = c.review.payload
        entry = _entry_receipt(c)
        exit_rec = next((r for r in reversed(c.receipts) if r.payload.get("exit_action") == "CLOSE" or r.payload.get("reject_reason") in ("VENUE_STOP", "TARGET", "END_OF_TEST", "TIME_STOP")), None)
        row.update({"state": "CLOSED", "fill": entry.payload.get("average_fill") if entry else None, "exit_price": exit_rec.payload.get("average_fill") if exit_rec else None,
                    "exit_reason": (exit_rec.payload.get("exit_reason") or exit_rec.payload.get("reject_reason")) if exit_rec else None,
                    "pnl": rv.get("pnl"), "r_multiple": rv.get("r_multiple"), "outcome": rv.get("outcome"), "polarity": rv.get("polarity"), "lessons": rv.get("lessons") or [],
                    "closed_ms": c.review.event_time_ms, "cost_ratio": c.tca.payload.get("cost_ratio") if c.tca else None})
        out.append(row)
    return sorted(out, key=lambda r: -r["closed_ms"])


def current_trades(chains: Iterable[_Chain]) -> list[dict]:
    out = []
    for c in chains:
        if c.review is not None or c.decision is None:
            continue
        row = _base_row(c)
        if row is None or row["risk_decision"] not in ("APPROVED", "REDUCED"):
            continue
        entry = _entry_receipt(c)
        if entry is None:
            continue
        ticket = None
        if c.tickets:
            first = c.tickets[0].payload
            confirmed = any(t.payload.get("action") == "CONFIRMED" for t in c.tickets)
            ticket = {"ticket": first.get("ticket"), "status": "CONFIRMED" if confirmed else "OPEN"}
        state = "OPEN" if entry.payload.get("status") in ("FILLED", "PARTIAL", "OWNER_EXECUTED", "BROKER_CONFIRMED") else ("AWAITING_OWNER_TICKET" if ticket and ticket["status"] == "OPEN" else "WORKING")
        row.update({"state": state, "fill": entry.payload.get("average_fill"), "filled_qty": entry.payload.get("filled_qty"), "protective_stop_confirmed": entry.payload.get("protective_stop_confirmed"),
                    "protective_stop_price": entry.payload.get("protective_stop_price"), "execution_channel": entry.payload.get("execution_channel"), "opened_ms": entry.event_time_ms,
                    "owner_ticket": ticket, "cost_ratio": c.tca.payload.get("cost_ratio") if c.tca else None})
        out.append(row)
    return sorted(out, key=lambda r: -r["opened_ms"])


RECENT_REFUSAL_WINDOW_MS = 24 * 3_600_000


def potential_trades(chains: dict[str, _Chain], assessments: list[Event], *, limit: int) -> list[dict]:
    """Latest assessment per symbol: every candidate that produced a signal, plus intents the
    Risk Authority or router refused within the last day of ledger time. Nothing here has a size."""
    out: list[dict] = []
    latest: dict[str, Event] = {}
    for ev in assessments:
        sym = ev.payload.get("symbol") or ev.correlation_id
        latest[sym] = ev   # ledger order is chronological
    newest_ms = max([ev.event_time_ms for ev in latest.values()] + [c.decision.event_time_ms for c in chains.values() if c.decision is not None] + [0])
    horizon_ms = newest_ms - RECENT_REFUSAL_WINDOW_MS
    for sym, ev in latest.items():
        for cand in ev.payload.get("candidates", []):
            if "label" not in cand and "signal" not in cand:
                continue   # ineligible or no signal: not a potential trade
            out.append({"kind": "CANDIDATE", "symbol": cand.get("symbol") or ev.payload.get("symbol") or sym, "strategy_id": cand.get("strategy_id"), "direction": cand.get("direction"),
                        "entry": cand.get("entry"), "stop": cand.get("stop"), "horizon": cand.get("horizon"), "expected_gross_move_pct": cand.get("expected_gross_move_pct"),
                        "label": cand.get("label", "NO_HORIZON"), "reasons": list(cand.get("meta_reasons") or cand.get("reasons") or []), "cost_multiple": cand.get("cost_multiple"),
                        "signal": cand.get("signal"), "confidence": cand.get("confidence") or confidence_score(cand.get("multipliers") or {}).as_dict(), "assessed_ms": ev.event_time_ms,
                        "assessment_hash": ev.payload.get("assessment_hash"), "decision": ev.payload.get("decision")})
    for c in chains.values():
        row = _base_row(c)
        if row is None or row["decided_ms"] < horizon_ms:
            continue   # stale refusals are history, not potential
        if row["risk_decision"] == "REJECTED":
            row.update({"kind": "RISK_REJECTED", "label": f"REJECTED:{row['reason_code']}", "reasons": [c.decision.payload["decision"].get("reason_detail", "")], "assessed_ms": row["decided_ms"]})
            out.append(row)
        elif c.router_refusal and _entry_receipt(c) is None and c.review is None:
            row.update({"kind": "ROUTER_REFUSED", "label": "ROUTER_REFUSED", "reasons": [c.router_refusal], "assessed_ms": row["decided_ms"]})
            out.append(row)
    out.sort(key=lambda r: (-r["assessed_ms"], -Decimal(r["confidence"]["score"])))
    return out[:limit]


def build_trade_book(ledger: Ledger, *, view: str = "all", limit: int = 50) -> dict[str, Any]:
    if view not in VIEWS:
        raise ValueError(f"view must be one of {VIEWS}")
    chains, assessments = _collect(ledger)
    book: dict[str, Any] = {"view": view, "ledger_head": ledger.head(), "confidence_basis": BASIS,
                            "authority": "read model of the VATI ledger; sizes come only from the Risk Authority; nothing here can place or change an order"}
    if view in ("past", "all"):
        book["past"] = past_trades(chains.values())[:limit]
    if view in ("current", "all"):
        book["current"] = current_trades(chains.values())[:limit]
    if view in ("potential", "all"):
        book["potential"] = potential_trades(chains, assessments, limit=limit)
    book["counts"] = {k: len(book[k]) for k in ("past", "current", "potential") if k in book}
    return book
