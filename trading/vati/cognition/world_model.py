"""TradingWorldModel and persistent cognition store (TRD-REV51-092, G3).

A model asked "should this trade be smaller?" needs to know what the system
already knows: what is open, what has been rejected lately and why, which
strategies are degrading, what the calendar says. Today that lives scattered
across the ledger as forty-odd event kinds in arrival order. Reading it raw at
every invocation would be slow, and — worse — would make each invocation's view
depend on how the reader happened to scan.

So this is a projector: it folds the ledger into one bounded state, in ledger
order, with no clock of its own. Two properties matter more than what it
contains.

**It is a fold, not a cache.** `rebuild(ledger)` from scratch and incremental
`apply(event)` produce the same state, and `digest()` proves it. That is the
whole of INV-REPLAY-001 for this component: a context compiled in March can be
recompiled in September from the same ledger prefix and come out identical.

**It projects, it never decides.** Nothing here sizes, approves or rejects.
The counters are descriptive. A strategy with a poor recent record shows up as
a number, and what to do about that number is the Risk Authority's business,
not this module's.

The store beside it is append-only for the same reason the ledger is: a
cognition artifact whose payload can be edited after its outcome is known is
not evidence of anything (INV-EVID-001).
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from vati.core.canonical import canonical_hash, canonical_json
from vati.core.events import Event, EventKind

WORLD_MODEL_VERSION = "trading-world-model/5.1.0"

#: How many recent decisions to keep per symbol. Bounded on purpose: an
#: unbounded projection would make the context size depend on uptime.
RECENT_DECISIONS_PER_SYMBOL = 20
RECENT_REJECTIONS = 200


class StoreError(RuntimeError):
    pass


@dataclass
class InstrumentView:
    symbol: str
    last_bar_ms: int = 0
    last_decision: str = ""
    last_decision_ms: int = 0
    last_reason_code: str = ""
    integrity: str = "NORMAL"
    open_intents: set[str] = field(default_factory=set)
    decisions: list[tuple[int, str, str]] = field(default_factory=list)  # (ms, decision, reason)

    def body(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "last_bar_ms": self.last_bar_ms,
            "last_decision": self.last_decision,
            "last_decision_ms": self.last_decision_ms,
            "last_reason_code": self.last_reason_code,
            "integrity": self.integrity,
            "open_intents": sorted(self.open_intents),
            "recent_decisions": [list(d) for d in self.decisions[-RECENT_DECISIONS_PER_SYMBOL:]],
        }


@dataclass
class StrategyView:
    strategy_id: str
    approved: int = 0
    reduced: int = 0
    rejected: int = 0
    reviews: int = 0
    drift_alarms: int = 0
    state: str = ""

    @property
    def admitted(self) -> int:
        return self.approved + self.reduced

    @property
    def rejection_rate(self) -> float:
        total = self.admitted + self.rejected
        return 0.0 if total == 0 else round(self.rejected / total, 6)

    def body(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id, "approved": self.approved, "reduced": self.reduced,
            "rejected": self.rejected, "reviews": self.reviews, "drift_alarms": self.drift_alarms,
            "state": self.state, "rejection_rate": self.rejection_rate,
        }


class TradingWorldModel:
    """A deterministic fold of the VATI event stream."""

    def __init__(self) -> None:
        self.events_applied = 0
        self.last_event_hash = ""
        self.instruments: dict[str, InstrumentView] = {}
        self.strategies: dict[str, StrategyView] = {}
        self.rejection_reasons: Counter[str] = Counter()
        self.recent_rejections: list[tuple[int, str, str]] = []  # (ms, symbol, reason)
        self.calendar: dict[str, str] = {}          # event_key -> status
        self.kill_switch_triggers: set[str] = set()
        self.open_intents: dict[str, dict[str, Any]] = {}
        self.account_equity: dict[str, str] = {}    # alias -> equity as string
        self.market_data_health: dict[str, str] = {}

    # --------------------------------------------------------------- folding
    def _instrument(self, symbol: str) -> InstrumentView:
        return self.instruments.setdefault(symbol, InstrumentView(symbol))

    def _strategy(self, sid: str) -> StrategyView:
        return self.strategies.setdefault(sid, StrategyView(sid))

    def apply(self, ev: Event) -> None:
        p = ev.payload or {}
        k = ev.kind
        self.events_applied += 1
        self.last_event_hash = ev.hash

        if k is EventKind.MARKET_BAR:
            sym = str(p.get("symbol", ""))
            if sym:
                self._instrument(sym).last_bar_ms = max(self._instrument(sym).last_bar_ms,
                                                        int(p.get("end_ms", ev.event_time_ms) or 0))
        elif k is EventKind.INTEGRITY_STATE_CHANGE:
            sym = str(p.get("symbol", ""))
            if sym:
                self._instrument(sym).integrity = str(p.get("state", "NORMAL"))
        elif k is EventKind.TRADE_INTENT:
            sym, sid = str(p.get("symbol", "")), str(p.get("strategy_id", ""))
            self.open_intents[ev.correlation_id] = {"symbol": sym, "strategy_id": sid,
                                                    "opened_ms": ev.event_time_ms}
            if sym:
                self._instrument(sym).open_intents.add(ev.correlation_id)
            if sid:
                self._strategy(sid).state = str(p.get("strategy_state", "")) or self._strategy(sid).state
        elif k is EventKind.RISK_DECISION:
            self._apply_risk_decision(ev, p)
        elif k is EventKind.POSITION_CHANGE:
            self._apply_position_change(ev, p)
        elif k is EventKind.TRADE_REVIEW:
            sid = str(p.get("strategy_id", ""))
            if sid:
                self._strategy(sid).reviews += 1
        elif k in (EventKind.FEATURE_DRIFT, EventKind.EDGE_DRIFT):
            sid = str(p.get("strategy_id", ""))
            if sid:
                self._strategy(sid).drift_alarms += 1
        elif k is EventKind.KILL_SWITCH:
            self._apply_kill_switch(p)
        elif k is EventKind.CALENDAR_SCHEDULE:
            self.calendar.setdefault(str(p.get("event_key", "")), "SCHEDULED")
        elif k is EventKind.CALENDAR_RELEASE:
            key = str(p.get("event_key", ""))
            if key:
                # The recorder owns the verdict; the projection only records
                # that something was observed for this key.
                self.calendar[key] = "OBSERVED"
        elif k is EventKind.ACCOUNT_SNAPSHOT:
            alias = str(p.get("account_alias", ""))
            if alias:
                self.account_equity[alias] = str(p.get("equity", ""))
        elif k is EventKind.MARKET_DATA_HEALTH:
            sym = str(p.get("symbol", ""))
            if sym:
                self.market_data_health[sym] = str(p.get("state", ""))

    def _apply_risk_decision(self, ev: Event, p: dict) -> None:
        d = p.get("decision") if isinstance(p.get("decision"), dict) else p
        verdict = str(d.get("decision", "")).upper()
        reason = str(d.get("reason_code", ""))
        intent = self.open_intents.get(ev.correlation_id, {})
        sym = str(p.get("symbol") or intent.get("symbol", ""))
        sid = str(p.get("strategy_id") or intent.get("strategy_id", ""))
        if sym:
            iv = self._instrument(sym)
            iv.last_decision, iv.last_decision_ms, iv.last_reason_code = verdict, ev.event_time_ms, reason
            iv.decisions.append((ev.event_time_ms, verdict, reason))
            if len(iv.decisions) > RECENT_DECISIONS_PER_SYMBOL:
                del iv.decisions[:-RECENT_DECISIONS_PER_SYMBOL]
        if sid:
            sv = self._strategy(sid)
            if verdict == "APPROVED":
                sv.approved += 1
            elif verdict == "REDUCED":
                sv.reduced += 1
            elif verdict == "REJECTED":
                sv.rejected += 1
        if verdict == "REJECTED" and reason:
            self.rejection_reasons[reason] += 1
            self.recent_rejections.append((ev.event_time_ms, sym, reason))
            if len(self.recent_rejections) > RECENT_REJECTIONS:
                del self.recent_rejections[:-RECENT_REJECTIONS]

    def _apply_position_change(self, ev: Event, p: dict) -> None:
        state = str(p.get("state", "")).upper()
        if state in ("CLOSED", "FLAT", "EXITED"):
            info = self.open_intents.pop(ev.correlation_id, None)
            if info and info.get("symbol") in self.instruments:
                self.instruments[info["symbol"]].open_intents.discard(ev.correlation_id)

    def _apply_kill_switch(self, p: dict) -> None:
        trigger = str(p.get("trigger", ""))
        active = bool(p.get("active", True))
        if not trigger:
            return
        if active:
            self.kill_switch_triggers.add(trigger)
        else:
            self.kill_switch_triggers.discard(trigger)

    # -------------------------------------------------------------- rebuilding
    def rebuild(self, events: Iterable[Event]) -> "TradingWorldModel":
        for ev in events:
            self.apply(ev)
        return self

    @classmethod
    def from_ledger(cls, ledger) -> "TradingWorldModel":
        return cls().rebuild(ledger.iter())

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        """The whole projection, canonically ordered."""
        return {
            "world_model_version": WORLD_MODEL_VERSION,
            "events_applied": self.events_applied,
            "instruments": {s: v.body() for s, v in sorted(self.instruments.items())},
            "strategies": {s: v.body() for s, v in sorted(self.strategies.items())},
            "rejection_reasons": dict(sorted(self.rejection_reasons.items())),
            "recent_rejections": [list(r) for r in self.recent_rejections[-RECENT_REJECTIONS:]],
            "calendar": dict(sorted(self.calendar.items())),
            "kill_switch_triggers": sorted(self.kill_switch_triggers),
            "open_intents": {k: v for k, v in sorted(self.open_intents.items())},
            "account_equity": dict(sorted(self.account_equity.items())),
            "market_data_health": dict(sorted(self.market_data_health.items())),
        }

    def digest(self) -> str:
        """Content hash of the projection. Two folds of the same prefix match."""
        return canonical_hash(self.state())

    # ----------------------------------------------------------------- queries
    def degrading_strategies(self, *, min_decisions: int = 10,
                             rejection_rate_above: float = 0.5) -> list[str]:
        """Descriptive only. Nothing acts on this list; the context carries it
        so a model can see what the deterministic path has been refusing."""
        out = []
        for sid, sv in sorted(self.strategies.items()):
            if sv.admitted + sv.rejected >= min_decisions and sv.rejection_rate > rejection_rate_above:
                out.append(sid)
        return out

    def top_rejection_reasons(self, n: int = 5) -> list[tuple[str, int]]:
        return sorted(self.rejection_reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


class CognitionStore:
    """Append-only persistence for cognition artifacts, keyed by context.

    Rewriting an artifact under an existing key with a different payload is
    refused rather than versioned away, because the caller that wants to do
    that has almost always confused 'a correction' with 'a new observation'.
    Corrections are new rows with a new key, exactly as in the ledger.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS cognition_artifacts (
                 artifact_key TEXT PRIMARY KEY,
                 kind TEXT NOT NULL,
                 context_hash TEXT NOT NULL,
                 payload_json TEXT NOT NULL,
                 seal TEXT NOT NULL,
                 created_ms INTEGER NOT NULL)"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_artifacts_ctx ON cognition_artifacts(context_hash)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_artifacts_kind ON cognition_artifacts(kind)")

    def put(self, *, artifact_key: str, kind: str, context_hash: str,
            payload: dict[str, Any], created_ms: int) -> str:
        blob = canonical_json(payload)
        seal = canonical_hash(payload)
        row = self._conn.execute(
            "SELECT payload_json FROM cognition_artifacts WHERE artifact_key = ?",
            (artifact_key,)).fetchone()
        if row is not None:
            if row[0] != blob:
                raise StoreError(
                    f"{artifact_key} already stored with a different payload; "
                    "a correction is a new artifact, not an edit")
            return seal
        self._conn.execute(
            "INSERT INTO cognition_artifacts(artifact_key, kind, context_hash, payload_json, seal, created_ms)"
            " VALUES (?,?,?,?,?,?)",
            (artifact_key, kind, context_hash, blob, seal, created_ms))
        return seal

    def get(self, artifact_key: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT payload_json FROM cognition_artifacts WHERE artifact_key = ?",
            (artifact_key,)).fetchone()
        return None if row is None else json.loads(row[0])

    def for_context(self, context_hash: str, *, kind: Optional[str] = None) -> list[dict[str, Any]]:
        q = "SELECT payload_json FROM cognition_artifacts WHERE context_hash = ?"
        args: list[Any] = [context_hash]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        q += " ORDER BY created_ms, artifact_key"
        return [json.loads(r[0]) for r in self._conn.execute(q, args)]

    def count(self, kind: Optional[str] = None) -> int:
        if kind is None:
            return self._conn.execute("SELECT COUNT(*) FROM cognition_artifacts").fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM cognition_artifacts WHERE kind = ?", (kind,)).fetchone()[0]

    def close(self) -> None:
        self._conn.close()
