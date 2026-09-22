"""Knowledge objects (integration doc §5, §7, §19, §20) with environment
weights (Rev 4 improvement: quantified) and hashes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
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


# ===========================================================================
# Lessons: what a closed trade is supposed to change (GAP-F-003)
# ===========================================================================
"""An episode is evidence. A lesson is what the evidence is *for*.

`ExperienceEpisode` records everything about a trade and is consumed by the
health tracker as a number. Nothing in the system ever wrote down, in a form
another decision could retrieve, what the trade actually taught — so the same
mistake could be made in the same regime on the same session forever and every
artefact of it would be present in the ledger and unreadable by the thing that
needed it.

A `Lesson` is deliberately small: what to keep doing, what to avoid, how much
confidence to put on that, and the evidence it rests on. It is keyed by the
three things that make a lesson transferable — strategy, regime and session —
because "this setup fails in the Asian session" is a lesson and "that trade
lost" is not.

The retrieval rule is the one that matters. `lessons_for(...)` returns evidence
to attach to a candidate. It **never** returns a multiplier and nothing reads
it as one. A lesson can make VAN look harder at a setup and can be shown to the
owner; it cannot make a position bigger. Confidence is derived from weighted
sample count and is capped at 1, so even a retrieval path that somebody later
misuses as a multiplier cannot raise risk (INV-RISK-001).

Lessons come from the decision-quality axis, not from R. A lesson learned from
a lucky win is an anti-lesson, and `cognition/attribution.py` is where that
distinction is drawn.
"""

LESSON_VERSION = "trade-lesson/5.1.0"

#: Weighted samples before a lesson is allowed to claim real confidence.
LESSON_MIN_WEIGHTED_SAMPLES = Decimal("2")

#: Confidence ceiling. A lesson is never certain; capping it at 1 also means a
#: caller who mistakes it for a multiplier still cannot raise risk.
LESSON_MAX_CONFIDENCE = Decimal("1")


@dataclass(frozen=True)
class Lesson:
    """One retrievable conclusion drawn from one closed trade.

    `keep` and `avoid` are owner-readable statements. They are never parsed for
    behaviour — the behavioural effects of learning remain the three
    LearningBoundary targets, and this is not one of them.
    """

    lesson_id: str
    strategy_id: str
    symbol: str
    regime: str
    session: str
    quadrant: str
    #: What the trade did that is worth repeating.
    keep: tuple[str, ...]
    #: What it did that is not.
    avoid: tuple[str, ...]
    confidence: Decimal
    environment: Environment
    evidence_refs: tuple[str, ...]
    r_multiple: Decimal
    created_ms: int
    lesson_version: str = LESSON_VERSION
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if not (ZERO <= self.confidence <= LESSON_MAX_CONFIDENCE):
            raise ValueError(f"lesson confidence {self.confidence} is outside [0, 1]")

    def weight(self) -> Decimal:
        return ENVIRONMENT_WEIGHT[self.environment]

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.strategy_id, self.regime.upper(), self.session.upper())

    def as_dict(self) -> dict:
        return {
            "lesson_id": self.lesson_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "regime": self.regime,
            "session": self.session,
            "quadrant": self.quadrant,
            "keep": list(self.keep),
            "avoid": list(self.avoid),
            "confidence": str(self.confidence),
            "environment": self.environment.value,
            "evidence_weight": str(self.weight()),
            "evidence_refs": list(self.evidence_refs),
            "r_multiple": str(self.r_multiple),
            "created_ms": self.created_ms,
            "lesson_version": self.lesson_version,
            "authority": "EVIDENCE_ONLY_NEVER_A_SIZE_MULTIPLIER",
        }

    def sealed(self) -> "Lesson":
        return Lesson(**{**self.__dict__, "artifact_hash": canonical_hash(self.as_dict())})


def lesson_from_verdict(verdict, *, symbol: str, regime: str, session: str,
                        environment: Environment, now_ms: int,
                        evidence_refs: tuple[str, ...] = ()) -> Lesson:
    """Turn a quadrant verdict into a statement another decision can retrieve.

    The four quadrants produce four genuinely different lessons, which is the
    reason for having the axis at all:

    * good/good — keep the process; the result confirms nothing on its own
    * good/bad  — keep the process; the loss is variance, not a defect
    * bad/good  — **avoid** the process; the win is the warning
    * bad/bad   — avoid the process; the loss merely agrees with it
    """
    from vati.cognition.attribution import PROCESS_FAULTS, DecisionQuality

    quadrant = verdict.quadrant
    faults = tuple(verdict.faults)
    keep: list[str] = []
    avoid: list[str] = []

    if quadrant.decision is DecisionQuality.GOOD:
        keep.append(
            f"{verdict.strategy_id} on {symbol} in {regime}/{session}: thesis, risk "
            "discipline, execution policy and event compliance were all sound")
        if quadrant.is_unlucky:
            keep.append(
                "the loss came from the market, not from the process; do not degrade "
                "this capsule for it")
    else:
        for fault in faults:
            avoid.append(f"{fault}: {PROCESS_FAULTS[fault]}")
        if quadrant.is_lucky:
            avoid.append(
                "this trade made money despite the process defect above; the result is "
                "the warning, not the endorsement")

    weight = ENVIRONMENT_WEIGHT[environment]
    confidence = min(
        LESSON_MAX_CONFIDENCE,
        (weight * (Decimal("1") if faults or quadrant.is_unlucky else Decimal("0.6"))),
    )
    return Lesson(
        lesson_id=canonical_hash({
            "trade": verdict.trade_intent_id, "quadrant": quadrant.value,
        })[:24],
        strategy_id=verdict.strategy_id,
        symbol=symbol.upper(),
        regime=regime.upper(),
        session=session.upper(),
        quadrant=quadrant.value,
        keep=tuple(keep),
        avoid=tuple(avoid),
        confidence=confidence,
        environment=environment,
        evidence_refs=tuple(dict.fromkeys(
            evidence_refs + tuple(verdict.evidence_refs) + (verdict.digest,))),
        r_multiple=verdict.r_multiple,
        created_ms=now_ms,
    ).sealed()


class LessonStore:
    """Write-and-retrieve store for lessons, backed by the ledger.

    `lessons_for` is what the opportunity engine calls. It returns evidence
    strings and refs; it returns no number that could size anything.
    """

    def __init__(self, *, ledger=None, producer: str = "vati-lessons",
                 per_key: int = 20) -> None:
        self._ledger = ledger
        self._producer = producer
        self.per_key = per_key
        self._by_key: dict[tuple[str, str, str], list[Lesson]] = {}
        self._by_strategy: dict[str, list[Lesson]] = {}

    def record(self, lesson: Lesson, *, now_ms: Optional[int] = None) -> Lesson:
        sealed = lesson if lesson.artifact_hash else lesson.sealed()
        rows = self._by_key.setdefault(sealed.key, [])
        if any(r.lesson_id == sealed.lesson_id for r in rows):
            return sealed
        rows.append(sealed)
        del rows[:-self.per_key]
        srows = self._by_strategy.setdefault(sealed.strategy_id, [])
        srows.append(sealed)
        del srows[:-self.per_key * 4]
        if self._ledger is not None:
            t = now_ms if now_ms is not None else sealed.created_ms
            self._ledger.append(make_event(
                EventKind.TRADE_LESSON, self._producer,
                sealed.as_dict() | {"artifact_hash": sealed.artifact_hash},
                event_time_ms=t, received_time_ms=t,
                correlation_id=sealed.strategy_id))
        return sealed

    def lessons_for(self, strategy_id: str, regime: str = "", session: str = "",
                    *, limit: int = 5) -> tuple[Lesson, ...]:
        """Lessons for this strategy, narrowed by regime and session when given.

        An exact regime/session match is preferred; a strategy-wide lesson is
        still returned when no narrow one exists, because "this capsule has a
        recurring discipline problem" is relevant in every regime. Newest
        first, because a lesson from the current market beats one from the last
        one.
        """
        exact = self._by_key.get((strategy_id, regime.upper(), session.upper()), [])
        rows = list(exact)
        if len(rows) < limit:
            for lesson in reversed(self._by_strategy.get(strategy_id, [])):
                if lesson.lesson_id not in {r.lesson_id for r in rows}:
                    rows.append(lesson)
                if len(rows) >= limit:
                    break
        rows.sort(key=lambda l: l.created_ms, reverse=True)
        return tuple(rows[:limit])

    def evidence_for(self, strategy_id: str, regime: str = "", session: str = "",
                     *, limit: int = 5) -> tuple[str, ...]:
        """The candidate-attachable form: short strings, never a number.

        This is what `CandidateOpportunity.evidence_refs` receives. It cannot be
        read as a multiplier because it is not one.
        """
        out: list[str] = []
        for lesson in self.lessons_for(strategy_id, regime, session, limit=limit):
            for statement in lesson.avoid:
                out.append(f"lesson[{lesson.quadrant}] avoid: {statement}"[:300])
            for statement in lesson.keep:
                out.append(f"lesson[{lesson.quadrant}] keep: {statement}"[:300])
        return tuple(dict.fromkeys(out))[:limit * 2]

    def restore_from_ledger(self, ledger) -> int:
        """Rebuild the store from TRADE_LESSON events after a restart."""
        n = 0
        for event in ledger.iter(EventKind.TRADE_LESSON):
            p = event.payload
            try:
                lesson = Lesson(
                    lesson_id=str(p["lesson_id"]),
                    strategy_id=str(p["strategy_id"]),
                    symbol=str(p.get("symbol", "")),
                    regime=str(p.get("regime", "")),
                    session=str(p.get("session", "")),
                    quadrant=str(p.get("quadrant", "")),
                    keep=tuple(p.get("keep") or ()),
                    avoid=tuple(p.get("avoid") or ()),
                    confidence=Decimal(str(p.get("confidence", "0"))),
                    environment=Environment(str(p.get("environment", "SHADOW"))),
                    evidence_refs=tuple(p.get("evidence_refs") or ()),
                    r_multiple=Decimal(str(p.get("r_multiple", "0"))),
                    created_ms=int(p.get("created_ms", event.event_time_ms)),
                    artifact_hash=str(p.get("artifact_hash", "")),
                )
            except Exception:  # noqa: BLE001 — a malformed row is skipped, never guessed
                continue
            rows = self._by_key.setdefault(lesson.key, [])
            if any(r.lesson_id == lesson.lesson_id for r in rows):
                continue
            rows.append(lesson)
            self._by_strategy.setdefault(lesson.strategy_id, []).append(lesson)
            n += 1
        return n
