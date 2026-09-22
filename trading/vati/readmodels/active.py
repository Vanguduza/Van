"""Active-trade read models for the owner and reasoning surfaces (GAP-F-003).

GAP-F-003's finding was that nothing outside the trading process could observe
trading state in a form worth reasoning about: the commander returned host and
ledger counts, and the gateway's existing read models answered "what is open"
without ever answering "why", "is it still true" or "what changed".

These five projections answer those. Every one of them is assembled from the
hash-chained VATI ledger and nothing else — no live venue call, no in-memory
session state, no second store. That is not a stylistic preference: the ledger
is the only thing that survives a restart, replays identically and is signed by
its own chain, so a read model built from anything else would be a second
version of the truth (INV-REPLAY-001).

Nothing here can act. There is no code path from this module to
`RiskAuthority`, to `ExecutionRouter` or to an adapter, and no function returns
anything a caller could submit. It classifies what already happened.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from vati.app.tradebook import _collect, _entry_receipt, potential_trades
from vati.core.events import Event, EventKind
from vati.core.ledger import Ledger

READ_MODEL_VERSION = "trading-active-readmodel/5.1.0"

ZERO = Decimal("0")

AUTHORITY_NOTE = (
    "read model of the VATI hash-chained ledger; sizes come only from the Risk "
    "Authority and orders only from the Execution Router"
)


def _d(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _latest_by(ledger: Ledger, kind: EventKind, key) -> dict[str, Event]:
    out: dict[str, Event] = {}
    for event in ledger.iter(kind):
        k = key(event)
        if k:
            out[str(k)] = event
    return out


def _all_by(ledger: Ledger, kind: EventKind, key) -> dict[str, list[Event]]:
    out: dict[str, list[Event]] = defaultdict(list)
    for event in ledger.iter(kind):
        k = key(event)
        if k:
            out[str(k)].append(event)
    return dict(out)


def empty(extra: Optional[dict] = None) -> dict[str, Any]:
    """The shape every projection returns when the ledger is unavailable.

    Same contract as `TradingService.status()`: `ledger_available: False` and
    empty collections, never an exception and never a partial answer that
    looks current. A caller that cannot tell "nothing is open" from "I could
    not look" will eventually act on the wrong one.
    """
    return {
        "ledger_available": False,
        "read_model_version": READ_MODEL_VERSION,
        "authority": AUTHORITY_NOTE,
        **(extra or {}),
    }


# --------------------------------------------------------------------- positions
def positions(ledger: Ledger) -> dict[str, Any]:
    """Open positions with the claim behind each one.

    Per position: the sealed thesis, its latest assessment and the evidence
    that produced it, the deterministic health verdict, exposure and
    protection, unrealised R, the events linked to it, and the most recent
    adjustment proposal. This is the projection `REQ-FLOW-07` ("why is my
    active trade moving") needs in order to be answerable at all.
    """
    chains, _assessments = _collect(ledger)
    theses = _latest_by(ledger, EventKind.TRADE_THESIS,
                        lambda e: e.payload.get("trade_intent_id") or e.correlation_id)
    assessments = _latest_by(ledger, EventKind.THESIS_ASSESSMENT,
                             lambda e: e.payload.get("trade_intent_id") or e.correlation_id)
    healths = _latest_by(ledger, EventKind.TRADE_HEALTH,
                         lambda e: e.payload.get("trade_intent_id") or e.correlation_id)
    proposals = _latest_by(ledger, EventKind.POSITION_ADJUSTMENT,
                           lambda e: e.payload.get("trade_intent_id") or e.correlation_id)
    impacts = _all_by(ledger, EventKind.EVENT_IMPACT, lambda e: e.correlation_id)

    rows: list[dict[str, Any]] = []
    for intent_id, chain in chains.items():
        if chain.decision is None or chain.review is not None:
            continue   # never opened, or already closed
        entry_receipt = _entry_receipt(chain)
        if entry_receipt is None:
            continue
        intent = chain.decision.payload["inputs"]["intent"]
        decision = chain.decision.payload["decision"]
        thesis_ev = theses.get(intent_id)
        assessment_ev = assessments.get(intent_id)
        health_ev = healths.get(intent_id)
        proposal_ev = proposals.get(intent_id)

        entry = _d(entry_receipt.payload.get("average_fill")) or _d(intent.get("entry"))
        stop = _d(entry_receipt.payload.get("protective_stop_price")) or _d(intent.get("stop"))
        quantity = _d(entry_receipt.payload.get("filled_qty")) or ZERO
        unrealised_r = None
        if assessment_ev is not None:
            unrealised_r = assessment_ev.payload.get("current_r")
        elif health_ev is not None:
            unrealised_r = health_ev.payload.get("current_r")

        linked = [
            {
                "headline_id": e.payload.get("headline_id"),
                "headline_title": e.payload.get("headline_title"),
                "materiality": e.payload.get("materiality"),
                "uncertainty": e.payload.get("uncertainty"),
                "concern": e.payload.get("concern"),
                "relevance_basis": e.payload.get("relevance_basis"),
                "at_ms": e.event_time_ms,
            }
            for e in impacts.get(intent_id, ())[-5:]
        ]

        rows.append({
            "trade_intent_id": intent_id,
            "symbol": intent.get("symbol"),
            "venue": intent.get("venue"),
            "account_alias": intent.get("account_alias"),
            "direction": intent.get("direction"),
            "strategy_id": intent.get("strategy_id"),
            "opened_ms": entry_receipt.event_time_ms,
            "exposure": {
                "entry": None if entry is None else str(entry),
                "quantity": str(quantity),
                "approved_size": decision.get("approved_size"),
                "approved_risk_pct": decision.get("approved_risk_pct"),
                "portfolio_heat_after": decision.get("portfolio_heat_after"),
            },
            "protection": {
                "stop": None if stop is None else str(stop),
                "confirmed": bool(entry_receipt.payload.get("protective_stop_confirmed")),
                "at_or_beyond_break_even": (
                    None if (stop is None or entry is None) else (
                        stop >= entry if intent.get("direction") == "LONG" else stop <= entry)),
            },
            "unrealised_r": unrealised_r,
            "thesis": (None if thesis_ev is None else {
                "seal": thesis_ev.payload.get("seal"),
                "statement": thesis_ev.payload.get("statement"),
                "expected_path": thesis_ev.payload.get("expected_path"),
                "invalidation": thesis_ev.payload.get("invalidation"),
                "confirmation": thesis_ev.payload.get("confirmation"),
                "adverse_signals": thesis_ev.payload.get("adverse_signals"),
                "event_sensitivity": thesis_ev.payload.get("event_sensitivity"),
                "original_approved_risk_pct": thesis_ev.payload.get(
                    "original_approved_risk_pct"),
                "created_ms": thesis_ev.payload.get("created_ms"),
            }),
            "thesis_state": (None if assessment_ev is None
                             else assessment_ev.payload.get("state")),
            "latest_assessment": (None if assessment_ev is None else {
                "state": assessment_ev.payload.get("state"),
                "previous_state": assessment_ev.payload.get("previous_state"),
                "reasons": assessment_ev.payload.get("reasons"),
                "reason_detail": assessment_ev.payload.get("reason_detail"),
                "evidence": assessment_ev.payload.get("evidence"),
                "event_materiality": assessment_ev.payload.get("event_materiality"),
                "argues_for_less": assessment_ev.payload.get("argues_for_less"),
                "assessed_ms": assessment_ev.event_time_ms,
            }),
            "health": (None if health_ev is None else {
                "state": health_ev.payload.get("state"),
                "reasons": health_ev.payload.get("reasons"),
                "blocks_scaling": health_ev.payload.get("blocks_scaling"),
                "requires_preservation": health_ev.payload.get("requires_preservation"),
                "assessed_ms": health_ev.event_time_ms,
            }),
            "latest_proposal": (None if proposal_ev is None else {
                "action": proposal_ev.payload.get("action"),
                "rationale": proposal_ev.payload.get("rationale"),
                "reasons": proposal_ev.payload.get("reasons"),
                "requires_authority": proposal_ev.payload.get("requires_authority"),
                "proposed_ms": proposal_ev.event_time_ms,
            }),
            "linked_events": linked,
        })

    rows.sort(key=lambda r: r["opened_ms"], reverse=True)
    return {
        "ledger_available": True,
        "read_model_version": READ_MODEL_VERSION,
        "authority": AUTHORITY_NOTE,
        "count": len(rows),
        "positions": rows,
    }


# ------------------------------------------------------------------------ events
def events(ledger: Ledger, *, limit: int = 50) -> dict[str, Any]:
    """Recorded headlines and calendar releases, newest first.

    Both paths appear because they are different authorities and the owner
    should be able to see which is which: a calendar release can put an
    instrument into a blackout, a headline can only reduce exposure.
    """
    limit = max(1, min(int(limit), 500))
    rows: list[dict[str, Any]] = []
    for event in ledger.iter(EventKind.NEWS_HEADLINE):
        rows.append({
            "kind": "HEADLINE",
            "headline_id": event.payload.get("headline_id"),
            "source_id": event.payload.get("source_id"),
            "trust": event.payload.get("trust"),
            "title": event.payload.get("title"),
            "currencies": event.payload.get("currencies"),
            "symbols": event.payload.get("symbols"),
            "concern": event.payload.get("concern"),
            "severity": event.payload.get("severity"),
            "relayed_by": event.payload.get("relayed_by"),
            "published_ms": event.event_time_ms,
            "authority": "REDUCE_ONLY",
        })
    for event in ledger.iter(EventKind.EVENT_RELEASE):
        rows.append({
            "kind": "CALENDAR_RELEASE",
            "event_key": event.payload.get("event_key"),
            "name": event.payload.get("name"),
            "tier": event.payload.get("tier"),
            "currencies": event.payload.get("currencies"),
            "actual": event.payload.get("actual"),
            "forecast": event.payload.get("forecast"),
            "status": event.payload.get("status"),
            "usable": event.payload.get("usable"),
            "published_ms": event.event_time_ms,
            "authority": "BLACKOUT_AUTHORITY",
        })

    impacts = [
        {
            "headline_id": event.payload.get("headline_id"),
            "subject_kind": event.payload.get("subject_kind"),
            "subject_id": event.payload.get("subject_id"),
            "symbol": event.payload.get("symbol"),
            "materiality": event.payload.get("materiality"),
            "uncertainty": event.payload.get("uncertainty"),
            "concern": event.payload.get("concern"),
            "actionable": event.payload.get("actionable"),
            "at_ms": event.event_time_ms,
        }
        for event in ledger.iter(EventKind.EVENT_IMPACT)
    ]
    rows.sort(key=lambda r: r["published_ms"], reverse=True)
    impacts.sort(key=lambda r: r["at_ms"], reverse=True)
    return {
        "ledger_available": True,
        "read_model_version": READ_MODEL_VERSION,
        "authority": AUTHORITY_NOTE,
        "count": len(rows),
        "events": rows[:limit],
        "impacts": impacts[:limit],
    }


# --------------------------------------------------------------- potential trades
def potential(ledger: Ledger, *, limit: int = 20) -> dict[str, Any]:
    """The candidate pool, with what VAN knows about each candidate.

    `potential_trades` already assembles the pool from opportunity
    assessments. This adds the evidence a reasoning layer needs to say
    anything useful about one: the lessons attached to it, the risk it would
    require, and any event that bears on its instrument.
    """
    limit = max(1, min(int(limit), 100))
    chains, assessments = _collect(ledger)
    rows = potential_trades(chains, assessments, limit=limit)

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for event in ledger.iter(EventKind.EVENT_IMPACT):
        by_symbol[str(event.payload.get("symbol", "")).upper()].append({
            "headline_id": event.payload.get("headline_id"),
            "materiality": event.payload.get("materiality"),
            "concern": event.payload.get("concern"),
            "at_ms": event.event_time_ms,
        })

    latest_candidate: dict[str, Event] = {}
    for event in ledger.iter(EventKind.CANDIDATE_OPPORTUNITY):
        latest_candidate[str(event.payload.get("symbol", "")).upper()] = event

    out = []
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        candidate = latest_candidate.get(symbol)
        enriched = dict(row)
        enriched["linked_events"] = by_symbol.get(symbol, [])[-3:]
        if candidate is not None:
            enriched["evidence_refs"] = candidate.payload.get("evidence_refs", [])
            enriched["risk_requirement"] = {
                "capsule_risk_ceiling": candidate.payload.get("capsule_risk_ceiling"),
                "stop": candidate.payload.get("stop"),
                "entry": candidate.payload.get("entry"),
                "valid_until_ms": candidate.payload.get("valid_until_ms"),
            }
            enriched["invalidation"] = {
                "stop": candidate.payload.get("stop"),
                "expires_ms": candidate.payload.get("valid_until_ms"),
            }
        out.append(enriched)
    return {
        "ledger_available": True,
        "read_model_version": READ_MODEL_VERSION,
        "authority": AUTHORITY_NOTE,
        "count": len(out),
        "potential_trades": out,
    }


# ------------------------------------------------------------------------ history
def history(ledger: Ledger, *, limit: int = 50) -> dict[str, Any]:
    """Closed trades with the quadrant, the attribution and the lesson.

    The quadrant is the part that makes this more than a P&L list: it says
    whether the trade was a good decision, which is the only axis that should
    change what VAN does next.
    """
    limit = max(1, min(int(limit), 200))
    quadrants = _latest_by(ledger, EventKind.DECISION_QUADRANT,
                           lambda e: e.payload.get("trade_intent_id") or e.correlation_id)
    attributions = _latest_by(ledger, EventKind.PNL_ATTRIBUTION,
                              lambda e: e.payload.get("trade_intent_id") or e.correlation_id)
    lessons_by_trade: dict[str, list[dict]] = defaultdict(list)
    for event in ledger.iter(EventKind.TRADE_LESSON):
        for ref in event.payload.get("evidence_refs") or ():
            lessons_by_trade[str(ref)].append(event.payload)

    rows: list[dict[str, Any]] = []
    for event in ledger.iter(EventKind.TRADE_REVIEW):
        intent_id = event.correlation_id or str(event.payload.get("trade_intent_id", ""))
        quadrant_ev = quadrants.get(intent_id)
        attribution_ev = attributions.get(intent_id)
        review_hash = str(event.payload.get("artifact_hash", ""))
        rows.append({
            "trade_intent_id": intent_id,
            "strategy_id": event.payload.get("strategy_id"),
            "outcome": event.payload.get("outcome"),
            "polarity": event.payload.get("polarity"),
            "r_multiple": event.payload.get("r_multiple"),
            "pnl": event.payload.get("pnl"),
            "exit_reason": event.payload.get("exit_reason"),
            "closed_ms": event.event_time_ms,
            "quadrant": (None if quadrant_ev is None else {
                "quadrant": quadrant_ev.payload.get("quadrant"),
                "decision_quality": quadrant_ev.payload.get("decision_quality"),
                "outcome_quality": quadrant_ev.payload.get("outcome_quality"),
                "faults": quadrant_ev.payload.get("faults"),
                "fault_detail": quadrant_ev.payload.get("fault_detail"),
                "is_lucky": quadrant_ev.payload.get("is_lucky"),
                "is_unlucky": quadrant_ev.payload.get("is_unlucky"),
            }),
            "attribution": (None if attribution_ev is None else {
                "realised": attribution_ev.payload.get("realised"),
                "buckets": attribution_ev.payload.get("buckets"),
                "dominant_bucket": attribution_ev.payload.get("dominant_bucket"),
                "counterfactual": attribution_ev.payload.get("counterfactual"),
            }),
            "lessons": [
                {
                    "lesson_id": l.get("lesson_id"),
                    "quadrant": l.get("quadrant"),
                    "keep": l.get("keep"),
                    "avoid": l.get("avoid"),
                    "confidence": l.get("confidence"),
                }
                for l in lessons_by_trade.get(review_hash, ())
            ],
        })
    # The owner UI needs a real history curve, but it must not invent starting balance or
    # extrapolate missing trades. Build cumulative closed-trade series directly from the same
    # authoritative TRADE_REVIEW rows. Points with a missing metric are omitted from that
    # metric's series; timestamps remain the actual close times.
    chronological = sorted(rows, key=lambda r: r["closed_ms"])
    cumulative_r = 0.0
    cumulative_pnl = 0.0
    equity_curve_r: list[dict[str, Any]] = []
    equity_curve_pnl: list[dict[str, Any]] = []
    for row in chronological:
        r_value = row.get("r_multiple")
        if r_value is not None:
            cumulative_r += float(r_value)
            equity_curve_r.append({
                "closed_ms": int(row["closed_ms"]),
                "value": cumulative_r,
                "trade_intent_id": row["trade_intent_id"],
            })
        pnl_value = row.get("pnl")
        if pnl_value is not None:
            cumulative_pnl += float(pnl_value)
            equity_curve_pnl.append({
                "closed_ms": int(row["closed_ms"]),
                "value": cumulative_pnl,
                "trade_intent_id": row["trade_intent_id"],
            })

    rows.sort(key=lambda r: r["closed_ms"], reverse=True)
    counts: dict[str, int] = {}
    for row in rows:
        q = (row.get("quadrant") or {}).get("quadrant")
        if q:
            counts[q] = counts.get(q, 0) + 1
    return {
        "ledger_available": True,
        "read_model_version": READ_MODEL_VERSION,
        "authority": AUTHORITY_NOTE,
        "count": len(rows),
        "by_quadrant": dict(sorted(counts.items())),
        "equity_curve_r": equity_curve_r,
        "equity_curve_pnl": equity_curve_pnl,
        "history": rows[:limit],
    }


# --------------------------------------------------------------------- assessment
def assessment(ledger: Ledger) -> dict[str, Any]:
    """VAN's own reading of the book right now.

    Urgent risks first, because that is what the answer is for: a position
    whose claim has been invalidated, or whose health is FAILING, is the thing
    the owner needs to hear before the portfolio numbers. `available_risk` is
    reported as headroom under the last decision's own ceiling and is
    explicitly a *reading*, not a permission — only `RiskAuthority.evaluate`
    grants risk (INV-AUTH-001).
    """
    pos = positions(ledger)
    open_rows = pos["positions"]

    latest_decision = None
    for event in ledger.iter(EventKind.RISK_DECISION):
        latest_decision = event
    heat = None
    max_heat = None
    if latest_decision is not None:
        heat = latest_decision.payload["decision"].get("portfolio_heat_after")
        mandate = latest_decision.payload.get("inputs", {}).get("mandate") or {}
        max_heat = mandate.get("max_open_stop_risk")

    invoker_state = {"cognition_invoker": "none", "state": "MODEL_INVOKER_UNCONFIGURED"}
    for event in ledger.iter(EventKind.SESSION):
        if event.payload.get("event") == "COGNITION_INVOKER":
            invoker_state = {
                k: v for k, v in event.payload.items() if k != "event"
            }

    kill_active: list[str] = []
    cleared: set[str] = set()
    for event in ledger.iter(EventKind.KILL_SWITCH):
        trigger = str(event.payload.get("trigger", ""))
        if event.payload.get("cleared"):
            cleared.add(trigger)
        elif trigger:
            kill_active.append(trigger)
    kill_active = sorted({t for t in kill_active if t not in cleared})

    urgent: list[dict[str, Any]] = []
    for row in open_rows:
        state = row.get("thesis_state")
        health = (row.get("health") or {}).get("state")
        reasons: list[str] = []
        if state in ("INVALIDATED", "WEAKER", "RISKIER", "OVEREXTENDED"):
            reasons.append(f"thesis {state}")
        if health in ("IMPAIRED", "FAILING"):
            reasons.append(f"health {health}")
        if not (row.get("protection") or {}).get("confirmed"):
            reasons.append("no confirmed protective stop")
        for linked in row.get("linked_events") or ():
            m = _d(linked.get("materiality"))
            if m is not None and m >= Decimal("0.5"):
                reasons.append(
                    f"event materiality {linked.get('materiality')} on "
                    f"{linked.get('headline_title') or linked.get('headline_id')}")
        if reasons:
            urgent.append({
                "trade_intent_id": row["trade_intent_id"],
                "symbol": row["symbol"],
                "strategy_id": row.get("strategy_id"),
                "reasons": reasons,
                "latest_proposal": (row.get("latest_proposal") or {}).get("action"),
            })
    if kill_active:
        urgent.insert(0, {
            "trade_intent_id": None, "symbol": None, "strategy_id": None,
            "reasons": [f"kill switch active: {', '.join(kill_active)}"],
            "latest_proposal": None,
        })

    heat_d, max_heat_d = _d(heat), _d(max_heat)
    available = (None if (heat_d is None or max_heat_d is None)
                 else str(max(ZERO, max_heat_d - heat_d)))

    theses_summary: dict[str, int] = {}
    for row in open_rows:
        state = row.get("thesis_state") or "UNASSESSED"
        theses_summary[state] = theses_summary.get(state, 0) + 1

    return {
        "ledger_available": True,
        "read_model_version": READ_MODEL_VERSION,
        "authority": AUTHORITY_NOTE,
        "urgent_risks": urgent,
        "portfolio_heat": heat,
        "max_open_stop_risk": max_heat,
        "available_risk": available,
        "available_risk_note": (
            "headroom under the last recorded decision's mandate ceiling; a reading, "
            "not a permission — only RiskAuthority.evaluate grants risk"),
        "open_positions": len(open_rows),
        "active_theses": theses_summary,
        "kill_switch_active": kill_active,
        "cognition": invoker_state,
    }


__all__ = [
    "AUTHORITY_NOTE", "READ_MODEL_VERSION", "assessment", "empty", "events",
    "history", "positions", "potential",
]
