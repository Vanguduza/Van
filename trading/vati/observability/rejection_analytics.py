"""Descriptive rejection-reason analytics (TRD-REV51-128)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event

CATEGORY_RULES = {
    "KILL_SWITCH": "safety",
    "MARGIN": "safety",
    "MAX_DAILY_LOSS": "safety",
    "MAX_WEEKLY_DRAWDOWN": "safety",
    "DRAWDOWN": "safety",
    "UNPROTECTED_POSITION": "safety",
    "MANDATE": "mandate",
    "STRATEGY": "strategy_eligibility",
    "INSTRUMENT": "strategy_eligibility",
    "STALE": "stale_or_unknown_data",
    "UNKNOWN": "stale_or_unknown_data",
    "ROUTE": "route_failure",
    "PRETRADE": "pretrade_failure",
    "EVENT": "event_blackout",
    "MODEL": "model_abstention",
    "PORTFOLIO_HEAT": "capacity_risk_heat",
    "CURRENCY_LEG": "capacity_risk_heat",
    "MAX_POSITIONS": "capacity_risk_heat",
}


def category_for(reason_code: str) -> str:
    code = reason_code.upper()
    for prefix, category in CATEGORY_RULES.items():
        if code.startswith(prefix):
            return category
    return "other"


@dataclass(frozen=True)
class RejectionAnalytics:
    total: int
    by_reason: tuple[tuple[str, int], ...]
    by_category: tuple[tuple[str, int], ...]
    created_ms: int

    def body(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "by_reason": dict(self.by_reason),
            "by_category": dict(self.by_category),
            "created_ms": self.created_ms,
            "version": "rejection-analytics/5.1.0",
            "may_weaken_guard": False,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


class RejectionAnalyticsEngine:
    def __init__(self, *, ledger=None, producer: str = "vati-rejection-analytics") -> None:
        self._ledger = ledger
        self._producer = producer

    def compile_ledger(self, ledger, *, now_ms: int) -> RejectionAnalytics:
        """Aggregate durable deterministic refusals from the trading ledger."""
        reasons: list[str] = []
        for event in ledger.iter(EventKind.RISK_DECISION):
            decision = (event.payload or {}).get("decision") or {}
            if str(decision.get("decision") or "") == "REJECTED":
                reasons.append(str(decision.get("reason_code") or "RISK_REJECTED"))
        for event in ledger.iter(EventKind.PRETRADE_CONTROL):
            payload = event.payload or {}
            if str(payload.get("verdict") or "") == "REJECT":
                reasons.append(str(payload.get("reason_code") or "PRETRADE_REJECTED"))
        for event in ledger.iter(EventKind.SESSION):
            if (event.payload or {}).get("router_refused"):
                reasons.append("ROUTER_REFUSED")
        return self.compile(reasons, now_ms=now_ms)

    def compile(self, reasons: Iterable[str], *, now_ms: int) -> RejectionAnalytics:
        reason_counts = Counter(str(r) for r in reasons if str(r))
        category_counts = Counter()
        for reason, count in reason_counts.items():
            category_counts[category_for(reason)] += count
        out = RejectionAnalytics(
            total=sum(reason_counts.values()),
            by_reason=tuple(sorted(reason_counts.items())),
            by_category=tuple(sorted(category_counts.items())),
            created_ms=now_ms,
        )
        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.REJECTION_ANALYTICS, self._producer,
                out.body() | {"analytics_hash": out.digest},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id="rejections",
            ))
        return out
