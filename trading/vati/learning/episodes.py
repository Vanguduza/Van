"""Knowledge objects (integration doc §5, §7, §19, §20) with environment
weights (Rev 4 improvement: quantified) and hashes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.core.ledger import Ledger

ZERO = Decimal("0")


class Environment(str, Enum):
    BACKTEST = "BACKTEST"
    REPLAY = "REPLAY"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    DEMO = "DEMO"
    SHADOW = "SHADOW"
    LIMITED_LIVE = "LIMITED_LIVE"
    LIVE = "LIVE"


# Evidence weight by environment. Execution facts (spread, slippage, fills)
# from COUNTERFACTUAL/BACKTEST carry zero weight: only real venues teach execution.
ENVIRONMENT_WEIGHT = {
    Environment.LIVE: Decimal("1.0"), Environment.LIMITED_LIVE: Decimal("1.0"), Environment.SHADOW: Decimal("0.7"),
    Environment.DEMO: Decimal("0.5"), Environment.REPLAY: Decimal("0.3"), Environment.BACKTEST: Decimal("0.3"), Environment.COUNTERFACTUAL: Decimal("0.2"),
}
EXECUTION_FACT_WEIGHT = {**ENVIRONMENT_WEIGHT, Environment.BACKTEST: ZERO, Environment.REPLAY: ZERO, Environment.COUNTERFACTUAL: ZERO}


def _seal(obj) -> str:
    return canonical_hash({k: v for k, v in obj.__dict__.items() if k != "artifact_hash"})


@dataclass(frozen=True)
class ExperienceEpisode:
    episode_id: str                 # = trade_intent_id
    environment: Environment
    instrument: str
    venue: str
    account_alias: str
    strategy_id: str
    strategy_version: str
    horizon: str
    direction: str
    market_state_hash: str
    activation_id: str
    decision: dict                  # label, multipliers, reasons
    risk: dict                      # requested/approved pct, size, heat before/after, decision_hash
    execution: dict                 # fill, slippage, spread, channel, receipt_hash
    outcome: dict                   # pnl, r_multiple, exit_reason, duration_ms
    review: dict                    # outcome class, polarity, thesis/process flags, lessons
    opened_ms: int
    closed_ms: Optional[int]
    evidence_refs: tuple[str, ...]
    admission_state: str = "PROPOSED"
    artifact_hash: str = ""

    def weight(self) -> Decimal:
        return ENVIRONMENT_WEIGHT[self.environment]

    def sealed(self) -> "ExperienceEpisode":
        return ExperienceEpisode(**{**self.__dict__, "artifact_hash": _seal(self)})


@dataclass(frozen=True)
class MissedOpportunityEpisode:
    """A considered-and-rejected setup. `ex_ante_snapshot_hash` freezes what was
    known at decision time; validity is judged only from that (hindsight guard)."""
    episode_id: str
    environment: Environment
    instrument: str
    strategy_id: str
    ex_ante_snapshot_hash: str
    rejection_reason: str
    rejection_layer: str            # ARBITER | META_LABELER | RISK_AUTHORITY | ROUTER
    horizon: str
    hypothetical_entry: Decimal
    hypothetical_stop: Decimal
    evaluation_window_ms: int
    later_path_summary: dict        # mfe, mae, close at window end (simulated, weight 0.2)
    hypothetical_r: Decimal
    ex_ante_valid: bool             # would the setup have passed with information available then?
    verdict: str                    # GOOD_NO_TRADE | COSTLY_NO_TRADE | INCONCLUSIVE
    artifact_hash: str = ""

    def sealed(self) -> "MissedOpportunityEpisode":
        return MissedOpportunityEpisode(**{**self.__dict__, "artifact_hash": _seal(self)})


@dataclass(frozen=True)
class CounterfactualResult:
    episode_id: str
    variant: str
    description: str
    simulated_pnl: Decimal
    simulated_r: Decimal
    base_pnl: Decimal
    delta_pnl: Decimal
    environment: Environment = Environment.COUNTERFACTUAL
    weight: Decimal = ENVIRONMENT_WEIGHT[Environment.COUNTERFACTUAL]
    label: str = "SIMULATED_EVIDENCE_NOT_CAUSAL"
    artifact_hash: str = ""

    def sealed(self) -> "CounterfactualResult":
        return CounterfactualResult(**{**self.__dict__, "artifact_hash": _seal(self)})


@dataclass(frozen=True)
class MacroEventEpisode:
    event_id: str
    event_type: str
    release_ms: int
    source_id: str
    vintage_id: str
    consensus: Optional[Decimal]
    prior: Optional[Decimal]
    revised_prior: Optional[Decimal]
    actual: Optional[Decimal]
    surprise_vector: dict
    reaction_vector: dict           # keyed by horizon label: t_1m, t_5m, t_30m, t_2h ...
    pre_event_regime: dict
    strategies_triggered: tuple[str, ...]
    strategies_rejected: tuple[str, ...]
    result_summary: str
    lessons: tuple[str, ...]
    artifact_hash: str = ""

    def sealed(self) -> "MacroEventEpisode":
        return MacroEventEpisode(**{**self.__dict__, "artifact_hash": _seal(self)})


def episode_from_ledger(ledger: Ledger, trade_intent_id: str, *, environment: Environment) -> Optional[ExperienceEpisode]:
    """Assemble an ExperienceEpisode from the chained events of one intent."""
    dec = rec = tca = rev = None
    receipts = []
    for ev in ledger.iter(correlation_id=trade_intent_id):
        if ev.kind is EventKind.RISK_DECISION:
            dec = ev
        elif ev.kind is EventKind.EXECUTION_RECEIPT:
            receipts.append(ev)
        elif ev.kind is EventKind.TCA_RECORD:
            tca = ev
        elif ev.kind is EventKind.TRADE_REVIEW:
            rev = ev
    if dec is None:
        return None
    intent = dec.payload["inputs"]["intent"]
    d = dec.payload["decision"]
    entry_rec = next((r for r in receipts if r.payload.get("status") in ("FILLED", "PARTIAL", "OWNER_EXECUTED", "ACCEPTED")), None)
    exit_rec = next((r for r in reversed(receipts) if r.payload.get("exit_action") == "CLOSE" or r.payload.get("reject_reason") in ("VENUE_STOP", "TARGET", "END_OF_TEST")), None)
    ep = ExperienceEpisode(
        episode_id=trade_intent_id, environment=environment, instrument=intent["symbol"], venue=intent["venue"], account_alias=intent["account_alias"],
        strategy_id=intent["strategy_id"], strategy_version=intent["strategy_version"], horizon=intent.get("horizon", ""), direction=intent["direction"],
        market_state_hash=intent["market_snapshot_hash"], activation_id=intent.get("activation_id", ""),
        decision={"multipliers": {k: intent[k] for k in intent if k.endswith("_multiplier")}, "expected_gross_move_pct": intent.get("expected_gross_move_pct")},
        risk={"requested_risk_pct": d["requested_risk_pct"], "approved_risk_pct": d["approved_risk_pct"], "approved_size": d["approved_size"], "heat_before": d["portfolio_heat_before"], "heat_after": d["portfolio_heat_after"], "decision": d["decision"], "decision_hash": d["decision_hash"]},
        execution={"fill": entry_rec.payload.get("average_fill") if entry_rec else None, "channel": entry_rec.payload.get("execution_channel") if entry_rec else None,
                   "receipt_hash": entry_rec.payload.get("receipt_hash") if entry_rec else None, "tca": tca.payload if tca else None},
        outcome={"pnl": rev.payload.get("pnl") if rev else None, "r_multiple": rev.payload.get("r_multiple") if rev else None, "exit_reason": exit_rec.payload.get("reject_reason") if exit_rec else None},
        review={"outcome": rev.payload.get("outcome"), "polarity": rev.payload.get("polarity"), "thesis_correct": rev.payload.get("thesis_correct"), "process_ok": rev.payload.get("process_ok"), "lessons": rev.payload.get("lessons")} if rev else {},
        opened_ms=dec.event_time_ms, closed_ms=rev.event_time_ms if rev else None,
        evidence_refs=tuple(x for x in (dec.hash, entry_rec.hash if entry_rec else None, tca.hash if tca else None, rev.hash if rev else None) if x),
    )
    return ep.sealed()
