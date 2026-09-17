"""Daily / weekly / monthly learning reports (integration doc §30–§32) computed
deterministically from the ledger and trackers. Hermes narrates; it does not
compute the numbers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.learning.broker import BrokerLearner
from vati.learning.health import StrategyHealthTracker

ZERO = Decimal("0")


@dataclass(frozen=True)
class LearningReport:
    cadence: str
    window_start_ms: int
    window_end_ms: int
    cycles: int
    decisions: dict[str, int]
    rejections: dict[str, int]
    trades_closed: int
    outcomes: dict[str, int]
    net_pnl: Decimal
    no_trade_share: Decimal
    strategy_health: dict[str, str]
    demotion_recommendations: dict[str, str]
    broker_states: dict[str, str]
    kill_switch_events: int
    owner_tickets: int
    what_changed: tuple[str, ...]
    what_to_avoid: tuple[str, ...]
    research_needed: tuple[str, ...]


def _report(cadence: str, ledger: Ledger, start_ms: int, end_ms: int, health: Optional[StrategyHealthTracker], brokers: Optional[BrokerLearner]) -> LearningReport:
    decisions: Counter = Counter(); rejections: Counter = Counter(); outcomes: Counter = Counter()
    cycles = trades = kills = tickets = 0
    pnl = ZERO
    for ev in ledger.iter():
        if not (start_ms <= ev.event_time_ms <= end_ms):
            continue
        if ev.kind is EventKind.OPPORTUNITY_ASSESSMENT:
            cycles += 1; decisions[ev.payload.get("decision", "?")] += 1
        elif ev.kind is EventKind.RISK_DECISION:
            d = ev.payload.get("decision", {})
            if d.get("decision") == "REJECTED":
                rejections[d.get("reason_code", "?")] += 1
        elif ev.kind is EventKind.TRADE_REVIEW:
            trades += 1; outcomes[ev.payload.get("outcome", "?")] += 1
            pnl += Decimal(str(ev.payload.get("pnl", "0")))
        elif ev.kind is EventKind.KILL_SWITCH:
            kills += 1
        elif ev.kind is EventKind.OWNER_TICKET:
            tickets += 1
    no_trade = Decimal(decisions.get("NO_TRADE", 0) + decisions.get("WAIT", 0) + decisions.get("SKIP", 0)) / Decimal(cycles) if cycles else ZERO
    sh, dem = {}, {}
    if health is not None:
        for sid in health._obs:
            v = health.verdict(sid); sh[sid] = str(v.health)
            if v.state_recommendation:
                dem[sid] = v.state_recommendation
    bs = {f"{k[0]}:{k[1]}:{k[2]}": p.state().value for k, p in (brokers.profiles.items() if brokers else [])}
    changed = tuple(f"{s} → {d}" for s, d in dem.items()) + tuple(f"broker {k} {v}" for k, v in bs.items() if v != "CERTIFIED")
    avoid = tuple(f"{code}: {n} rejections" for code, n in rejections.most_common(3))
    research = tuple(f"{o}: {n}" for o, n in outcomes.items() if o in ("BAD_LOSS", "EXECUTION_FAILURE", "DATA_FAILURE", "RISK_FAILURE", "BROKER_FAILURE", "UNKNOWN") and n > 0)
    return LearningReport(cadence, start_ms, end_ms, cycles, dict(decisions), dict(rejections), trades, dict(outcomes), pnl, no_trade.quantize(Decimal("0.001")), sh, dem, bs, kills, tickets, changed, avoid, research)


def daily_report(ledger: Ledger, *, day_end_ms: int, health: StrategyHealthTracker | None = None, brokers: BrokerLearner | None = None) -> LearningReport:
    return _report("DAILY", ledger, day_end_ms - 86_400_000, day_end_ms, health, brokers)


def weekly_report(ledger: Ledger, *, week_end_ms: int, health: StrategyHealthTracker | None = None, brokers: BrokerLearner | None = None) -> LearningReport:
    return _report("WEEKLY", ledger, week_end_ms - 7 * 86_400_000, week_end_ms, health, brokers)


def monthly_report(ledger: Ledger, *, month_end_ms: int, health: StrategyHealthTracker | None = None, brokers: BrokerLearner | None = None) -> LearningReport:
    return _report("MONTHLY", ledger, month_end_ms - 30 * 86_400_000, month_end_ms, health, brokers)
