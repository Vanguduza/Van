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


STRATEGY_LEARNING_OUTCOMES = frozenset({Outcome.GOOD_WIN, Outcome.GOOD_LOSS, Outcome.BAD_WIN, Outcome.BAD_LOSS})


@dataclass(frozen=True)
class InitialRisk:
    amount: Decimal
    evidence_ref: str


def initial_risk_from_ledger(ledger, trade_intent_id: str, *, available_cutoff_ms: int | None = None) -> InitialRisk | None:
    """Frozen approved money risk, never current equity or an amended stop.

    Reconstruct and verify both the original decision seal and its exact input
    snapshot. Missing, conflicting or unbound historical data stays unknown.
    """
    from vati.core.events import EventKind
    from vati.risk.authority import _canonical_hash
    from vati.risk.serde import snapshot_from_dict
    found = {}
    for event in ledger.iter(EventKind.RISK_DECISION, correlation_id=trade_intent_id):
        if event.producer not in {"vati-cycle", "vati-account-coordinator"}:
            continue
        if available_cutoff_ms is not None and event.received_time_ms > available_cutoff_ms:
            continue
        try:
            decision = event.payload["decision"]
            inputs = event.payload["inputs"]
            if (decision["trade_intent_id"] != trade_intent_id or inputs["intent"]["trade_intent_id"] != trade_intent_id
                or decision["decision"] not in {"APPROVED", "REDUCED"}
                or canonical_hash({k: v for k, v in decision.items() if k != "decision_hash"}) != decision["decision_hash"]):
                return None
            version = decision.get("approval_schema_version")
            if version not in (None, 2) or (version == 2 and canonical_hash(inputs["intent"]) != decision.get("intent_hash")):
                return None
            snapshot = snapshot_from_dict(inputs["snapshot"])
            if _canonical_hash(snapshot) != decision["risk_snapshot_hash"]:
                return None
            fraction = Decimal(str(decision["approved_risk_pct"]))
            if not fraction.is_finite() or not snapshot.equity.is_finite() or not ZERO < fraction <= Decimal("1") or snapshot.equity <= ZERO:
                return None
            risk = snapshot.equity*fraction
            found.setdefault(decision["decision_hash"], InitialRisk(risk, "risk-decision://"+event.hash))
        except (ValueError, TypeError, KeyError, ArithmeticError):
            return None
    return next(iter(found.values())) if len(found) == 1 else None


@dataclass(frozen=True)
class PnlMeasurement:
    amount: Decimal | None
    basis: str


def _reported_parent_cash(rows):
    """Aggregate labelled execution deltas, preserving legacy snapshot semantics."""
    if not rows:
        return None
    scopes = {row.get("pnl_scope") for row in rows}
    if "EXECUTION_DELTA" not in scopes:
        if not scopes <= {None, "PARENT_SNAPSHOT"}:
            raise ValueError("unknown reported PnL scope")
        row = rows[-1]
        return Decimal(str(row["pnl"])), row.get("pnl_basis")
    if scopes != {"EXECUTION_DELTA"}:
        raise ValueError("mixed cash delta and parent snapshot")
    seen = {}
    basis = {row.get("pnl_basis") for row in rows}
    if len(basis) != 1 or next(iter(basis)) not in {"GROSS_PRICE_MOVEMENT", "NET_CONFIRMED"}:
        raise ValueError("cash delta basis is ambiguous")
    total = ZERO
    for row in rows:
        identity = row.get("close_id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("cash delta lacks native identity")
        digest = canonical_hash(row)
        if identity in seen:
            if seen[identity] != digest:
                raise ValueError("conflicting native cash delta identity")
            continue
        seen[identity] = digest
        amount = Decimal(str(row["pnl"]))
        if not amount.is_finite():
            raise ValueError("nonfinite cash delta")
        total += amount
    return total, next(iter(basis))


def closed_trade_pnl(entry, exit_price: Decimal, contract, reported_rows=()) -> PnlMeasurement:
    """Share the caller's explicit net/gross convention across both runtimes.

    This price-derived estimate includes only recorded charges. It is not a
    complete venue cash reconciliation or a payoff model for nonlinear products.
    """
    from vati.risk.contracts import Direction, LossModel
    try:
        fees, carry = Decimal(str(entry.get("fees", ZERO))), Decimal(str(entry.get("carry", ZERO)))
        if not fees.is_finite() or not carry.is_finite():
            return PnlMeasurement(None, "UNKNOWN_CHARGES")
        reported = _reported_parent_cash([row for row in reported_rows or ()
                                         if row.get("intent") == entry.get("trade_intent_id")])
        if reported is not None:
            amount, basis = reported
            if not amount.is_finite():
                return PnlMeasurement(None, "UNKNOWN_REPORTED_PNL")
            if basis == "GROSS_PRICE_MOVEMENT":
                return PnlMeasurement(amount-fees+carry, "REPORTED_GROSS_NET_RECORDED_CHARGES")
            return PnlMeasurement(amount, "REPORTED_NET_CONFIRMED" if basis == "NET_CONFIRMED"
                                  else "REPORTED_NET_OR_LEGACY_UNSPECIFIED_CONVENTION")
        quantity, opened = Decimal(str(entry.get("quantity", ZERO))), Decimal(str(entry["entry"]))
        if contract is None or contract.loss_model is LossModel.FULL_STAKE:
            return PnlMeasurement(None, "UNKNOWN_REQUIRES_PRODUCT_SETTLEMENT")
        factor = contract.value_per_price_unit_per_lot
        if any(not isinstance(v, Decimal) or not v.is_finite() for v in (quantity, opened, exit_price, factor)) or quantity <= ZERO or factor <= ZERO:
            return PnlMeasurement(None, "UNKNOWN_LINEAR_INPUTS")
        if not isinstance(entry["direction"], Direction):
            return PnlMeasurement(None, "UNKNOWN_DIRECTION")
        sign = Decimal("1") if entry["direction"] is Direction.LONG else Decimal("-1")
        return PnlMeasurement((exit_price-opened)*sign*quantity*factor-fees+carry, "PRICE_DERIVED_NET_RECORDED_CHARGES")
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return PnlMeasurement(None, "UNKNOWN_INPUTS")


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
    initial_money_risk: Decimal | None = None
    initial_risk_evidence_ref: str | None = None
    r_basis: str = "PRICE_MOVE_OVER_STOP_DISTANCE"
    pnl_basis: str = "CALLER_PROVIDED"
    thesis_evidence_basis: str = "CALLER_ASSERTION"
    account_alias: str = ""
    review_version: str = "trade-review/5.2.0"
    record_revision: int = 0
    supersedes_review_ref: str | None = None
    maturity: dict = field(default_factory=dict)
    broker_ok: bool = True


def review_trade(*, trade_intent_id: str, strategy_id: str, entry: Decimal, exit_price: Decimal, stop: Decimal, direction_long: bool, pnl: Decimal,
                 thesis_correct: bool, process_ok: bool, execution_ok: bool = True, data_ok: bool = True, risk_ok: bool = True, broker_ok: bool = True,
                 exit_reason: str = "", exit_known: bool = True, initial_money_risk: Decimal | None = None,
                 initial_risk_evidence_ref: str | None = None, pnl_basis: str = "CALLER_PROVIDED",
                 thesis_evidence_basis: str = "CALLER_ASSERTION", account_alias: str = "", maturity: dict | None = None) -> TradeReview:
    risk_per_unit = abs(entry - stop)
    move = (exit_price - entry) if direction_long else (entry - exit_price)
    r = move / risk_per_unit if risk_per_unit > ZERO else ZERO
    r_basis = "PRICE_MOVE_OVER_STOP_DISTANCE"
    if initial_money_risk is not None:
        if (not isinstance(initial_money_risk, Decimal) or not initial_money_risk.is_finite()
            or initial_money_risk <= ZERO or not isinstance(pnl, Decimal) or not pnl.is_finite()):
            raise ValueError("net return multiple requires finite positive initial money risk and finite PnL")
        r = pnl/initial_money_risk
        r_basis = "NET_PNL_OVER_APPROVED_MONEY_RISK"
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
    rv = TradeReview(trade_intent_id, strategy_id, r.quantize(Decimal("0.01")), pnl, thesis_correct, process_ok, execution_ok, data_ok, risk_ok, outcome, polarity, tuple(lessons),
        initial_money_risk=initial_money_risk, initial_risk_evidence_ref=initial_risk_evidence_ref,
        r_basis=r_basis, pnl_basis=pnl_basis, thesis_evidence_basis=thesis_evidence_basis, account_alias=account_alias,
        maturity=dict(maturity or {}), broker_ok=broker_ok)
    return TradeReview(**{**rv.__dict__, "artifact_hash": canonical_hash({k: v for k, v in rv.__dict__.items() if k != "artifact_hash"})})

def native_economic_maturity(adapter, trade_intent_id: str, measurement: PnlMeasurement) -> dict:
    """Only an adapter-owned settled model supplies economic finality.

    Deterministic paper has no external fee/settlement stream. Its confirmed
    closed balance, no remaining parent position/order and exact zero-fee
    model may establish DEMO finality. Other providers require their own
    admitted finality/reconciliation producer; a finite PnL alone is not one.
    """
    from vati.execution.paper import PaperAdapter
    unknown = {"parent_final": False, "fees_final": False, "cash_reconciled": False,
               "source_environment": None, "source": "PROVIDER_FINALITY_UNAVAILABLE"}
    if type(adapter) is not PaperAdapter or adapter.inject_disconnect or measurement.amount is None:
        return unknown
    matches = [row for row in adapter.closed if row.get("intent") == trade_intent_id]
    if not matches:
        return unknown
    try:
        exact_cash = _reported_parent_cash(matches)[0] == measurement.amount
        final = (exact_cash and not any(row.trade_intent_id == trade_intent_id for row in adapter.positions())
                 and not any(row["cmd"].trade_intent_id == trade_intent_id for row in adapter.pending.values()))
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return unknown
    return {"parent_final": final, "fees_final": final, "cash_reconciled": final,
            "source_environment": "DEMO", "account_currency": adapter.currency,
            "source": "DETERMINISTIC_PAPER_SETTLEMENT"}
