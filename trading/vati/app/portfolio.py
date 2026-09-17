"""Owner-surface read models for the Trading Command Center (Rev 5 Part I):
portfolio, accounts, trade detail with a deterministic timeline, market state,
risk and bars. Everything is derived from the ledger, the account registry and
the bar lake; nothing here can act. Values are strings for Decimal fidelity."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from vati.app.tradebook import _collect, _entry_receipt, current_trades, past_trades, potential_trades
from vati.core.events import Event, EventKind
from vati.core.ledger import Ledger

ZERO = Decimal("0")


def _d(v) -> Optional[Decimal]:
    try:
        return None if v is None else Decimal(str(v))
    except Exception:
        return None


def _s(v) -> Optional[str]:
    return None if v is None else str(v)


def _latest_by(ledger: Ledger, kind: EventKind, key) -> dict[str, Event]:
    out: dict[str, Event] = {}
    for ev in ledger.iter(kind):
        k = key(ev)
        if k:
            out[k] = ev
    return out


# ------------------------------------------------------------------ accounts
def account_states(ledger: Ledger, registry_public: list[dict]) -> list[dict[str, Any]]:
    snaps = _latest_by(ledger, EventKind.ACCOUNT_SNAPSHOT, lambda e: e.payload.get("account_alias"))
    sessions = _latest_by(ledger, EventKind.SESSION, lambda e: e.correlation_id.split(":")[0] if ":" in e.correlation_id else None)
    open_by_alias: dict[str, int] = defaultdict(int)
    chains, _ = _collect(ledger)
    for row in current_trades(chains.values()):
        alias = row.get("account_alias") or (chains[row["trade_intent_id"]].decision.payload["inputs"]["intent"].get("account_alias") if chains.get(row["trade_intent_id"]) else None)
        if alias:
            open_by_alias[alias] += 1
    out = []
    known = {a["alias"] for a in registry_public}
    for a in registry_public + [{"alias": al, "broker": "UNKNOWN", "mode": s.payload.get("mode", "?"), "currency": s.payload.get("currency", "?"), "safety_identity": "UNKNOWN", "label": al, "demo": True, "enabled": True} for al, s in snaps.items() if al not in known]:
        s = snaps.get(a["alias"])
        p = s.payload if s else {}
        eq, bal, peak, day0, wk0 = (_d(p.get(k)) for k in ("equity", "balance", "peak_equity", "day_start_equity", "week_start_equity"))
        row = {"alias": a["alias"], "label": a.get("label") or a["alias"], "broker": a["broker"], "mode": p.get("mode") or a.get("mode"), "currency": p.get("currency") or a.get("currency"), "safety_identity": a.get("safety_identity"),
               "demo": a.get("demo"), "enabled": a.get("enabled"), "equity": _s(eq), "balance": _s(bal), "floating_pnl": _s(eq - bal) if eq is not None and bal is not None else None,
               "day_pnl": _s(eq - day0) if eq is not None and day0 else None, "week_pnl": _s(eq - wk0) if eq is not None and wk0 else None,
               "drawdown_pct": _s(((peak - eq) / peak).quantize(Decimal("0.0001"))) if eq is not None and peak and peak > ZERO else None,
               "connected": p.get("connected"), "verified": p.get("verified"), "open_positions": open_by_alias.get(a["alias"], p.get("open_positions", 0)), "kill_switch": p.get("kill_switch", []),
               "last_sync_ms": s.event_time_ms if s else None, "connection_state": ("LIVE" if p.get("connected") else "OFFLINE") if s else "NEVER_SYNCED", "session_event": sessions.get(a["alias"]).payload.get("event") if sessions.get(a["alias"]) else None}
        out.append(row)
    return out


def portfolio(ledger: Ledger, registry_public: list[dict], *, reporting_currency: str = "USD") -> dict[str, Any]:
    accounts = account_states(ledger, registry_public)
    same = [a for a in accounts if a["currency"] == reporting_currency and a["equity"] is not None]
    other = [a["alias"] for a in accounts if a["equity"] is not None and a["currency"] != reporting_currency]
    tot = lambda k: str(sum((Decimal(a[k]) for a in same if a.get(k) is not None), ZERO))  # noqa: E731
    chains, assessments = _collect(ledger)
    cur, past = current_trades(chains.values()), past_trades(chains.values())
    latest_dec = None
    for ev in ledger.iter(EventKind.RISK_DECISION):
        latest_dec = ev
    heat = _d(latest_dec.payload["decision"].get("portfolio_heat_after")) if latest_dec else None
    kills = set()
    for a in accounts:
        kills.update(a.get("kill_switch") or [])
    by_symbol: dict[str, int] = defaultdict(int)
    for t in cur:
        by_symbol[t["symbol"]] += 1
    return {"reporting_currency": reporting_currency, "accounts": accounts, "totals": {"balance": tot("balance"), "equity": tot("equity"), "floating_pnl": tot("floating_pnl"), "day_pnl": tot("day_pnl"), "week_pnl": tot("week_pnl"),
            "accounts_in_reporting_currency": len(same), "accounts_in_other_currencies": other},
            "risk": {"portfolio_heat": _s(heat), "kill_switch_active": sorted(kills), "open_trades": len(cur)}, "exposure": {"by_symbol": dict(by_symbol)},
            "recent_trades": past[:5], "open_positions": cur, "potential_trades": potential_trades(chains, assessments, limit=8),
            "data_state": data_states(ledger), "authority": "read model of the VATI ledger and account registry; sizes come only from the Risk Authority"}


# ------------------------------------------------------------------ market state
def data_states(ledger: Ledger) -> dict[str, dict]:
    out = {}
    for sym, ev in _latest_by(ledger, EventKind.MARKET_DATA_HEALTH, lambda e: e.payload.get("symbol")).items():
        out[sym] = {"state": ev.payload.get("state"), "bar_age_ms": ev.payload.get("bar_age_ms"), "at_ms": ev.event_time_ms}
    return out


def market_state(ledger: Ledger, symbol: Optional[str] = None) -> dict[str, Any]:
    states = _latest_by(ledger, EventKind.MARKET_STATE, lambda e: e.payload.get("state", {}).get("symbol"))
    assessments = _latest_by(ledger, EventKind.OPPORTUNITY_ASSESSMENT, lambda e: e.payload.get("symbol"))
    ds = data_states(ledger)
    out = []
    for sym, ev in states.items():
        if symbol and sym.upper() != symbol.upper():
            continue
        st = ev.payload["state"]
        oa = assessments.get(sym)
        out.append({"symbol": sym, "as_of_ms": st.get("as_of_ms"), "session": st.get("session"), "regime": st.get("regime"), "integrity": st.get("integrity"), "event_window": st.get("event_window"),
                    "minutes_to_next_event": st.get("minutes_to_next_event"), "quote_age_ms": st.get("quote_age_ms"), "cost_pct": ev.payload.get("cost_pct"), "features": st.get("features"),
                    "activation_id": st.get("activation_id"), "data_state": ds.get(sym, {"state": "UNKNOWN"}), "last_decision": {"decision": oa.payload.get("decision"), "reason": oa.payload.get("reason"), "at_ms": oa.event_time_ms} if oa else None,
                    "van_summary": _van_summary(st, ds.get(sym))})
    return {"symbols": out}


def _van_summary(st: dict, ds: Optional[dict]) -> str:
    r = st.get("regime", {})
    bits = [f"{st.get('symbol')}: {r.get('trend', '?').lower()} trend, {r.get('vol', '?').lower()} volatility, phase {r.get('phase', '?')}", f"session {st.get('session', '?')}", f"integrity {st.get('integrity', '?')}"]
    if st.get("event_window") not in (None, "NONE"):
        bits.append(f"event window {st['event_window']}")
    elif st.get("minutes_to_next_event") is not None:
        bits.append(f"next Tier-1 event in {st['minutes_to_next_event']} min")
    if ds and ds.get("state") not in (None, "LIVE"):
        bits.append(f"data {ds['state']}")
    return "; ".join(bits) + "."


# ------------------------------------------------------------------ risk
def risk(ledger: Ledger, mandate: Optional[dict] = None) -> dict[str, Any]:
    latest = None
    for ev in ledger.iter(EventKind.RISK_DECISION):
        latest = ev
    chains, _ = _collect(ledger)
    cur = current_trades(chains.values())
    by_symbol: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_currency: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_direction: dict[str, int] = defaultdict(int)
    for t in cur:
        rp = _d(t.get("approved_risk_pct")) or ZERO
        by_symbol[t["symbol"]] += rp
        by_direction[t["direction"]] += 1
        sym = t["symbol"].upper()
        if len(sym) == 6:
            by_currency[sym[:3]] += rp; by_currency[sym[3:]] += rp
        else:
            by_currency[sym] += rp
    snap = latest.payload["inputs"]["snapshot"] if latest else {}
    dec = latest.payload["decision"] if latest else {}
    m = mandate or (latest.payload["inputs"].get("mandate") if latest else {}) or {}
    eq, peak, day0, wk0 = (_d(snap.get(k)) for k in ("equity", "peak_equity", "day_start_equity", "week_start_equity"))
    return {"as_of_ms": latest.event_time_ms if latest else None, "portfolio_heat": dec.get("portfolio_heat_after"), "last_decision": {"decision": dec.get("decision"), "reason_code": dec.get("reason_code"), "constraints": dec.get("constraints")} if dec else None,
            "equity": _s(eq), "drawdown_from_peak_pct": _s(((peak - eq) / peak).quantize(Decimal("0.0001"))) if eq and peak else None, "day_pnl_pct": _s(((eq - day0) / day0).quantize(Decimal("0.0001"))) if eq and day0 else None,
            "week_pnl_pct": _s(((eq - wk0) / wk0).quantize(Decimal("0.0001"))) if eq and wk0 else None,
            "limits": {k: m.get(k) for k in ("max_risk_per_trade", "max_open_stop_risk", "max_daily_loss", "max_weekly_drawdown", "max_positions_per_instrument", "max_consecutive_losses") if k in m},
            "kill_switch": snap.get("kill_switch_triggers", []), "consecutive_losses": snap.get("consecutive_losses"), "open_trades": len(cur),
            "concentration": {"by_symbol": {k: str(v) for k, v in by_symbol.items()}, "by_currency": {k: str(v) for k, v in by_currency.items()}, "by_direction": dict(by_direction)},
            "positions": [{"trade_intent_id": t["trade_intent_id"], "symbol": t["symbol"], "direction": t["direction"], "approved_risk_pct": t.get("approved_risk_pct"), "approved_size": t.get("approved_size"), "stop": t.get("protective_stop_price") or t.get("stop"), "state": t["state"]} for t in cur]}


# ------------------------------------------------------------------ trade detail
TIMELINE = {EventKind.RISK_DECISION: "RISK_DECISION", EventKind.ORDER_COMMAND: "ORDER_SENT", EventKind.EXECUTION_RECEIPT: "EXECUTION", EventKind.TCA_RECORD: "TCA", EventKind.TRADE_REVIEW: "REVIEW",
            EventKind.TRADE_EXPERIENCE_ARTIFACT: "EXPERIENCE_ARTIFACT", EventKind.OWNER_TICKET: "OWNER_TICKET", EventKind.CAPSULE_STATE: "CAPSULE_STATE", EventKind.KILL_SWITCH: "KILL_SWITCH", EventKind.SESSION: "SESSION"}


def _timeline_entry(ev: Event) -> dict:
    p = ev.payload
    label = TIMELINE.get(ev.kind, ev.kind.value)
    if ev.kind is EventKind.RISK_DECISION:
        d = p.get("decision", {}); text = f"Risk Authority {d.get('decision')} · size {d.get('approved_size')} · risk {d.get('approved_risk_pct')} · heat {d.get('portfolio_heat_before')}→{d.get('portfolio_heat_after')}" + (f" · {d.get('reason_code')}" if d.get("reason_code") else "")
    elif ev.kind is EventKind.ORDER_COMMAND:
        text = f"{p.get('entry_type')} {p.get('direction')} {p.get('quantity')} @ {p.get('entry_price')} · stop {p.get('protective_stop')} ({p.get('stop_mode')})"
    elif ev.kind is EventKind.EXECUTION_RECEIPT:
        if p.get("exit_action"):
            label = "EXIT"; text = f"{p.get('exit_action')} {p.get('exit_reason') or ''} · {p.get('status')} {p.get('filled_qty')} @ {p.get('average_fill')}"
        else:
            text = f"{p.get('status')} {p.get('filled_qty')} @ {p.get('average_fill')} · stop confirmed {p.get('protective_stop_confirmed')}" + (f" · {p.get('reject_reason')}" if p.get("reject_reason") else "")
    elif ev.kind is EventKind.TCA_RECORD:
        text = f"slippage {p.get('slippage')} · cost ratio {p.get('cost_ratio')} · shortfall {p.get('implementation_shortfall')}"
    elif ev.kind is EventKind.TRADE_REVIEW:
        text = f"{p.get('outcome')} · {p.get('r_multiple')}R · P&L {p.get('pnl')} · {p.get('polarity')}"
    elif ev.kind is EventKind.OWNER_TICKET:
        text = f"ticket {p.get('ticket')} {p.get('action') or 'ISSUED'}"
    elif ev.kind is EventKind.CAPSULE_STATE:
        text = f"{p.get('strategy_id')} {p.get('from')}→{p.get('to')} ({p.get('authority')})"
    elif ev.kind is EventKind.SESSION:
        text = str(p.get("router_refused") or p.get("event") or "")
    else:
        text = ""
    return {"at_ms": ev.event_time_ms, "kind": label, "text": text, "hash": ev.hash}


def trade_detail(ledger: Ledger, trade_intent_id: str, *, lake=None, bars_before: int = 60, bars_after: int = 20) -> Optional[dict[str, Any]]:
    chains, _ = _collect(ledger)
    c = chains.get(trade_intent_id)
    if c is None or c.decision is None:
        return None
    rows = {r["trade_intent_id"]: r for r in past_trades([c]) + current_trades([c])}
    row = rows.get(trade_intent_id)
    if row is None:   # a rejected/refused intent still has a detail page
        from vati.app.tradebook import _base_row
        row = _base_row(c); row["state"] = "REJECTED" if row["risk_decision"] == "REJECTED" else "NOT_FILLED"
    events = list(ledger.iter(correlation_id=trade_intent_id))   # ledger sequence is the deterministic order; same-millisecond events keep their causal order
    timeline = [_timeline_entry(e) for e in events if e.kind in TIMELINE]
    intent = c.decision.payload["inputs"]["intent"]
    snapshot = c.decision.payload["inputs"]["snapshot"]
    detail = {**row, "account_alias": intent.get("account_alias"), "strategy_state": intent.get("strategy_state"), "market_snapshot_hash": intent.get("market_snapshot_hash"),
              "multipliers": {k: intent[k] for k in intent if k.endswith("_multiplier")}, "timeline": timeline, "review": c.review.payload if c.review else None,
              "tca": c.tca.payload if c.tca else None, "snapshot": {k: snapshot.get(k) for k in ("equity", "balance", "peak_equity", "consecutive_losses", "quote_age_ms", "market_integrity", "broker_connected")},
              "levels": {"entry": row.get("entry"), "fill": row.get("fill"), "stop": row.get("protective_stop_price") or row.get("stop"), "exit": row.get("exit_price"),
                         "target": _target(intent)}, "van_interpretation": _interpretation(row, c)}
    if lake is not None:
        opened = row.get("opened_ms") or row["decided_ms"]; closed = row.get("closed_ms") or opened
        for tf in ("H1", "M15", "M5", "D1"):
            try:
                bars, used = lake.read(row["symbol"], tf)
            except Exception:
                continue
            if bars:
                step = bars[0].end_ms - bars[0].start_ms
                window = [b for b in bars if opened - bars_before * step <= b.end_ms <= closed + bars_after * step]
                detail["chart"] = {"timeframe": tf, "bars": [{"t": b.start_ms, "o": str(b.open), "h": str(b.high), "l": str(b.low), "c": str(b.close)} for b in window], "slices": used,
                                   "markers": [m for m in ({"at_ms": opened, "kind": "ENTRY", "price": row.get("fill") or row.get("entry")}, {"at_ms": closed, "kind": "EXIT", "price": row.get("exit_price")} if row.get("exit_price") else None) if m]}
                break
    return detail


def _target(intent: dict) -> Optional[str]:
    e, m = _d(intent.get("entry")), _d(intent.get("expected_gross_move_pct"))
    if e is None or m is None:
        return None
    return str((e * (1 + m)) if intent.get("direction") == "LONG" else (e * (1 - m)))


def _interpretation(row: dict, c) -> list[str]:
    out = []
    conf = row.get("confidence", {})
    out.append(f"Confidence {conf.get('score')} ({conf.get('band')}): {conf.get('basis', '').split(':')[0]} — ranking signal, not a probability of profit.")
    if row.get("risk_decision") == "REJECTED":
        out.append(f"The Risk Authority refused this intent: {row.get('reason_code')}. No order existed.")
    if c.review:
        p = c.review.payload
        out.append(f"Review: {p.get('outcome')} with {p.get('polarity')} polarity; " + "; ".join(p.get("lessons") or []))
    if c.tca and _d(c.tca.payload.get("cost_ratio")) and _d(c.tca.payload["cost_ratio"]) > Decimal("1.2"):
        out.append(f"Execution cost ran {c.tca.payload['cost_ratio']}× the model: broker profile evidence.")
    return out


# ------------------------------------------------------------------ bars
def bars(lake, symbol: str, timeframe: str, *, limit: int = 300, end_ms: Optional[int] = None, ledger: Optional[Ledger] = None) -> dict[str, Any]:
    all_bars, used = lake.read(symbol, timeframe, end_ms=end_ms)
    sel = all_bars[-limit:]
    prov = sorted({s.provenance for s in lake.manifest(symbol, timeframe)})
    ds = data_states(ledger).get(symbol.upper(), {"state": "UNKNOWN"}) if ledger is not None else {"state": "UNKNOWN"}
    return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": [{"t": b.start_ms, "o": str(b.open), "h": str(b.high), "l": str(b.low), "c": str(b.close), "v": str(b.volume)} for b in sel],
            "count": len(sel), "provenance": prov, "data_state": ds, "slices": used}
