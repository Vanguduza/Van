"""Trade review and TradeExperienceArtifact proposal (Rev 2 §33, §6.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.core.canonical import canonical_hash

ZERO = Decimal("0")


class Outcome(str, Enum):
    GOOD_WIN = "GOOD_WIN"
    GOOD_LOSS = "GOOD_LOSS"
    BAD_WIN = "BAD_WIN"
    BAD_LOSS = "BAD_LOSS"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    DATA_FAILURE = "DATA_FAILURE"
    RISK_FAILURE = "RISK_FAILURE"
    BROKER_FAILURE = "BROKER_FAILURE"     # venue rejected/lost the protective stop or the position (reconciliation class), not a strategy lesson
    UNKNOWN = "UNKNOWN"                   # exit could not be established; never reinforced either way


@dataclass(frozen=True)
class TradeReview:
    trade_intent_id: str
    strategy_id: str
    r_multiple: Decimal
    pnl: Decimal
    thesis_correct: bool
    process_ok: bool
    execution_ok: bool
    data_ok: bool
    risk_ok: bool
    outcome: Outcome
    polarity: str            # POSITIVE | ANTI_PATTERN
    lessons: tuple[str, ...]
    admission_state: str = "PROPOSED"
    proposed_by: str = "vati-trade-review"
    artifact_hash: str = ""


def review_trade(*, trade_intent_id: str, strategy_id: str, entry: Decimal, exit_price: Decimal, stop: Decimal, direction_long: bool, pnl: Decimal,
                 thesis_correct: bool, process_ok: bool, execution_ok: bool = True, data_ok: bool = True, risk_ok: bool = True, broker_ok: bool = True,
                 exit_reason: str = "", exit_known: bool = True) -> TradeReview:
    risk_per_unit = abs(entry - stop)
    move = (exit_price - entry) if direction_long else (entry - exit_price)
    r = move / risk_per_unit if risk_per_unit > ZERO else ZERO
    lessons: list[str] = []
    if not exit_known:
        outcome = Outcome.UNKNOWN; lessons.append("exit not established; reconcile before this trade teaches anything")
    elif not data_ok:
        outcome = Outcome.DATA_FAILURE; lessons.append("stale or divergent data at decision; verify freshness gate")
    elif not risk_ok:
        outcome = Outcome.RISK_FAILURE; lessons.append("risk process breached; inspect authority and mandate")
    elif not broker_ok:
        outcome = Outcome.BROKER_FAILURE; lessons.append("venue lost or rejected protection/position; broker profile evidence, not strategy evidence")
    elif not execution_ok:
        outcome = Outcome.EXECUTION_FAILURE; lessons.append("execution shortfall exceeded model; review venue/session")
    elif pnl >= ZERO:
        outcome = Outcome.GOOD_WIN if (thesis_correct and process_ok) else Outcome.BAD_WIN
        if outcome is Outcome.BAD_WIN:
            lessons.append("profit without valid thesis/process: anti-pattern, do not reinforce")
    else:
        outcome = Outcome.GOOD_LOSS if process_ok else Outcome.BAD_LOSS
        if outcome is Outcome.GOOD_LOSS:
            lessons.append("loss with correct process: positive process evidence")
        else:
            lessons.append("loss with process breach: anti-pattern")
    if exit_reason:
        lessons.append(f"exit: {exit_reason}")
    polarity = "POSITIVE" if outcome in (Outcome.GOOD_WIN, Outcome.GOOD_LOSS) else "ANTI_PATTERN"
    rv = TradeReview(trade_intent_id, strategy_id, r.quantize(Decimal("0.01")), pnl, thesis_correct, process_ok, execution_ok, data_ok, risk_ok, outcome, polarity, tuple(lessons))
    return TradeReview(**{**rv.__dict__, "artifact_hash": canonical_hash({k: v for k, v in rv.__dict__.items() if k != "artifact_hash"})})
