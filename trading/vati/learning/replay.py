"""Durable reconstruction of reduce-only live learning state.

Learning may reduce authority but never expand it beyond the owner-approved
mandate.  Runtime process state therefore cannot be the only place a reduction
lives: a restart must reconstruct the same capsule-health and broker-profile
inputs before the next decision.

Strategy health is rebuilt from TRADE_EXPERIENCE_ARTIFACT because that artifact
carries the original Environment. Broker profiles are rebuilt only from
TCA_RECORD rows that explicitly carry their original learning context; older or
crash-recovered TCA without that context is not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from vati.arbiter.strategy_arbiter import ACTIVE_STATES
from vati.core.events import EventKind
from vati.learning.episodes import Environment
from vati.learning.health import HealthObservation
from vati.risk.contracts import StrategyState
from vati.strategies.capsule import Capsule

ONE = Decimal("1")


@dataclass(frozen=True)
class LearningReplayReport:
    tca_observations: int
    health_observations: int
    capsule_multipliers: int
    broker_multipliers: int
    demotions_restored: int


def _engines_for_strategy(engines_by_symbol: Mapping[str, object], strategy_id: str):
    for engine in engines_by_symbol.values():
        try:
            engine.registry.get(strategy_id)
        except KeyError:
            continue
        yield engine


def _restore_exact_capsule_events(ledger, engines_by_symbol: Mapping[str, object]) -> int:
    """Replay durable learning demotions; full capsule payload wins when present."""
    restored = 0
    for event in ledger.iter(EventKind.CAPSULE_STATE):
        p = event.payload
        if p.get("authority") != "AUTOMATIC_DEMOTION_ONLY":
            continue
        if p.get("by") != "vati-learning":
            continue
        strategy_id = str(p.get("strategy_id") or "")
        if not strategy_id:
            continue
        target_raw = str(p.get("to") or "")
        try:
            target = StrategyState(target_raw)
        except ValueError:
            continue
        if target not in (
            StrategyState.DEGRADED, StrategyState.SHADOW, StrategyState.SUSPENDED
        ):
            continue
        exact = p.get("capsule")
        for engine in _engines_for_strategy(engines_by_symbol, strategy_id):
            current = engine.registry.get(strategy_id)
            if isinstance(exact, dict):
                try:
                    candidate = Capsule(dict(exact))
                    if candidate.capsule_hash != str(p.get("capsule_hash") or candidate.capsule_hash):
                        continue
                    engine.registry.add(candidate)
                    restored += 1
                    continue
                except Exception:
                    # Never promote malformed durable state into runtime truth.
                    pass
            if current.state in ACTIVE_STATES and current.state is not target:
                engine.registry.demote(
                    strategy_id,
                    target,
                    reason=f"replayed durable automatic demotion {event.hash}",
                )
                restored += 1
    return restored


def restore_learning_runtime(ledger, learning, engines_by_symbol: Mapping[str, object]) -> LearningReplayReport:
    """Rebuild reduce-only learning inputs before a restarted runtime can decide."""
    tca_n = 0
    health_n = 0

    # Broker execution learning is only replayed where the original context was
    # persisted. Absence is not filled from current session state.
    for event in ledger.iter(EventKind.TCA_RECORD):
        p = event.payload
        required = (
            "learning_environment", "broker", "symbol", "session", "event_window",
        )
        if not all(p.get(k) is not None for k in required):
            continue
        try:
            environment = Environment(str(p["learning_environment"]))
            cost_ratio = Decimal(str(p["cost_ratio"]))
            slippage = Decimal(str(p["slippage"]))
        except (ValueError, ArithmeticError, KeyError):
            continue
        if cost_ratio.is_infinite():
            cost_ratio = Decimal("10")
        learning.brokers.observe(
            broker=str(p["broker"]),
            symbol=str(p["symbol"]),
            session=str(p["session"]),
            environment=environment,
            cost_ratio=cost_ratio,
            slippage_pips=slippage,
            rejected=bool(p.get("rejected", False)),
            in_event_window=str(p["event_window"]) in {
                "QUIET", "DRIFT", "PRE_BLACKOUT", "POST_BLACKOUT",
            },
        )
        tca_n += 1

    # Experience artifacts are the durable source of the environment weighting
    # used by strategy health. Do not infer it from the current mandate.
    for event in ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT):
        p = event.payload
        try:
            strategy_id = str(p["strategy_id"])
            environment = Environment(str(p["environment"]))
            r_multiple = Decimal(str(p["outcome"]["r_multiple"]))
            process_ok = bool(p["review"]["process_ok"])
            tca = p.get("execution", {}).get("tca") or {}
            cost_ratio = Decimal(str(tca.get("cost_ratio", "1")))
            if cost_ratio.is_infinite():
                cost_ratio = Decimal("10")
            evidence_ref = str(p.get("artifact_hash") or event.hash)
        except (ValueError, ArithmeticError, KeyError, TypeError):
            continue
        learning.health.observe(HealthObservation(
            strategy_id=strategy_id,
            environment=environment,
            r_multiple=r_multiple,
            process_ok=process_ok,
            cost_ratio=min(cost_ratio, Decimal("10")),
            regime_fit=True,
            evidence_ref=evidence_ref,
        ))
        health_n += 1

    capsule_multipliers = 0
    for strategy_id in list(learning.health._obs):
        adj = learning.health.live_adjustment(strategy_id)
        if adj is None:
            continue
        for engine in _engines_for_strategy(engines_by_symbol, strategy_id):
            engine.m.capsule_health[strategy_id] = adj.multiplier
            capsule_multipliers += 1
            if adj.demote_to:
                capsule = engine.registry.get(strategy_id)
                target = (
                    StrategyState.SHADOW
                    if capsule.state in (
                        StrategyState.LIMITED_LIVE,
                        StrategyState.CERTIFIED_LIVE,
                    )
                    else StrategyState.DEGRADED
                )
                if capsule.state in ACTIVE_STATES and capsule.state is not target:
                    verdict = learning.health.verdict(strategy_id)
                    engine.registry.demote(
                        strategy_id,
                        target,
                        reason=(
                            f"replayed learning health {adj.multiplier}: "
                            + "; ".join(verdict.reasons)
                        ),
                    )

    broker_multipliers = 0
    symbols = {
        symbol
        for (_broker, symbol, _session) in learning.brokers.profiles
    }
    for symbol in sorted(symbols):
        effective = learning.broker_liquidity(symbol)
        if effective >= ONE:
            continue
        for engine in engines_by_symbol.values():
            engine.m.broker_liquidity[symbol] = effective
            broker_multipliers += 1

    exact_demotions = _restore_exact_capsule_events(ledger, engines_by_symbol)
    return LearningReplayReport(
        tca_observations=tca_n,
        health_observations=health_n,
        capsule_multipliers=capsule_multipliers,
        broker_multipliers=broker_multipliers,
        demotions_restored=exact_demotions,
    )


__all__ = ["LearningReplayReport", "restore_learning_runtime"]
