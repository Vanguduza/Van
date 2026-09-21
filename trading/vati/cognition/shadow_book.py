"""Deterministic shadow book (TRD-REV51-100, G3b).

Before cognition may influence anything it has to be measured, and measuring
it means recording, at every eligible decision point, what the deterministic
path did *and* what cognition would have done — as a pair, sealed, at the time,
before either outcome is known.

The discipline that makes this worth anything is that the shadow entry is
written at T0. A shadow decision reconstructed after the fact is not a
measurement, it is a story. So `record` takes the deterministic decision and
the assessment together, seals them, and from then on the only permitted
mutation is attaching an outcome (INV-REPLAY-001).

INV-LIVE-001 is structural here rather than promised: this module imports
nothing from the execution path and returns nothing a live caller consumes.
Its only outputs are records and statistics. The one guard worth stating in
code is the assertion in `record` that the assessment cannot raise size — the
contract already refuses that, and this is the second lock on the same door.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Iterator, Optional

from vati.cognition.contracts import CognitiveAssessment, Verdict
from vati.core.canonical import canonical_hash, dec
from vati.core.events import EventKind, make_event

PRODUCER = "vati-shadow-book"
SHADOW_BOOK_VERSION = "shadow-book/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: This module must never be able to affect a live order. Kept as a readable
#: fact so the certification harness can assert it rather than infer it.
IS_LIVE_AFFECTING = False


class ShadowError(RuntimeError):
    pass


class EntryStatus(str, Enum):
    OPEN = "OPEN"            # written at T0, outcome not yet known
    RESOLVED = "RESOLVED"    # an outcome was attached
    EXPIRED = "EXPIRED"      # the horizon passed with no outcome
    NO_TRADE = "NO_TRADE"    # the deterministic path declined; nothing to compare


@dataclass(frozen=True)
class DeterministicOutcome:
    """What the existing path actually decided, as it decided it."""

    decision: str                    # APPROVED | REDUCED | REJECTED
    reason_code: str
    approved_size: Decimal
    approved_risk_pct: Decimal
    risk_decision_hash: str = ""

    @property
    def traded(self) -> bool:
        return self.decision in ("APPROVED", "REDUCED") and self.approved_size > ZERO

    def body(self) -> dict[str, Any]:
        return {
            "decision": self.decision, "reason_code": self.reason_code,
            "approved_size": str(self.approved_size),
            "approved_risk_pct": str(self.approved_risk_pct),
            "risk_decision_hash": self.risk_decision_hash,
        }


@dataclass(frozen=True)
class ShadowEntry:
    """One decision point, both answers, sealed at T0."""

    entry_id: str
    decision_point_id: str
    context_hash: str
    symbol: str
    strategy_id: str
    account_alias: str
    actual: DeterministicOutcome
    assessment: CognitiveAssessment
    opened_ms: int
    horizon_ms: int
    status: EntryStatus = EntryStatus.OPEN
    #: Attached later. Realised result of the trade that actually happened,
    #: in R multiples of its own initial risk.
    actual_r: Optional[Decimal] = None
    resolved_ms: Optional[int] = None
    shadow_book_version: str = SHADOW_BOOK_VERSION
    seal: str = ""

    # The seal covers only what was true at T0. Outcome fields are deliberately
    # outside it: attaching a result must not require re-sealing the decision.
    def body(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "decision_point_id": self.decision_point_id,
            "context_hash": self.context_hash,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "account_alias": self.account_alias,
            "actual": self.actual.body(),
            "assessment_seal": self.assessment.seal,
            "assessment_verdict": self.assessment.verdict.value,
            "assessment_multiplier": str(self.assessment.risk_multiplier),
            "model_id": self.assessment.model_id,
            "opened_ms": self.opened_ms,
            "horizon_ms": self.horizon_ms,
            "shadow_book_version": self.shadow_book_version,
        }

    def sealed(self) -> "ShadowEntry":
        return ShadowEntry(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    @property
    def shadow_multiplier(self) -> Decimal:
        """What fraction of the actual size cognition would have taken."""
        if self.assessment.verdict is Verdict.ABSTAIN:
            return ZERO
        if self.assessment.verdict is Verdict.REDUCE:
            return self.assessment.risk_multiplier
        return ONE

    @property
    def diverged(self) -> bool:
        return self.shadow_multiplier != ONE

    @property
    def shadow_r(self) -> Optional[Decimal]:
        """The counterfactual result, under size scaling only.

        This is exact for a pure size change on the same entry and exit, and
        it is not a model of anything else: cognition declining to size is the
        only counterfactual the shadow book claims to evaluate. Timing and
        selection differences are explicitly out of scope, which is why the
        attribution engine labels the basis SIZE_ONLY rather than implying the
        trade would have gone differently.
        """
        if self.actual_r is None:
            return None
        return self.actual_r * self.shadow_multiplier

    @property
    def delta_r(self) -> Optional[Decimal]:
        """Shadow minus actual. Positive means cognition would have helped."""
        if self.actual_r is None:
            return None
        return self.shadow_r - self.actual_r

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.body(), "seal": self.seal, "status": self.status.value,
            "actual_r": None if self.actual_r is None else str(self.actual_r),
            "shadow_r": None if self.shadow_r is None else str(self.shadow_r),
            "delta_r": None if self.delta_r is None else str(self.delta_r),
            "resolved_ms": self.resolved_ms,
            "diverged": self.diverged,
        }


class ShadowBook:
    """Paired records of what happened and what cognition would have done."""

    def __init__(self, *, ledger=None, producer: str = PRODUCER) -> None:
        self._ledger = ledger
        self._producer = producer
        self._entries: dict[str, ShadowEntry] = {}
        self._by_point: dict[str, str] = {}

    # ------------------------------------------------------------------ write
    def record(self, *, decision_point_id: str, context_hash: str, symbol: str,
               strategy_id: str, account_alias: str, actual: DeterministicOutcome,
               assessment: CognitiveAssessment, now_ms: int,
               horizon_ms: int) -> ShadowEntry:
        if decision_point_id in self._by_point:
            raise ShadowError(
                f"{decision_point_id} already has a shadow entry; a decision point is "
                "measured once, at T0")
        if not assessment.seal_ok():
            raise ShadowError("assessment seal does not verify; refusing to measure it")
        if assessment.context_hash != context_hash:
            raise ShadowError(
                f"assessment answered context {assessment.context_hash[:12]} but the entry "
                f"claims {context_hash[:12]}")
        # Second lock on the door the contract already holds shut.
        if assessment.risk_multiplier > ONE:
            raise ShadowError("assessment would raise risk; cognition is reduce-only")

        entry = ShadowEntry(
            entry_id=canonical_hash({"p": decision_point_id, "c": context_hash, "t": now_ms})[:32],
            decision_point_id=decision_point_id,
            context_hash=context_hash,
            symbol=symbol,
            strategy_id=strategy_id,
            account_alias=account_alias,
            actual=actual,
            assessment=assessment,
            opened_ms=now_ms,
            horizon_ms=horizon_ms,
            status=EntryStatus.OPEN if actual.traded else EntryStatus.NO_TRADE,
        ).sealed()
        self._entries[entry.entry_id] = entry
        self._by_point[decision_point_id] = entry.entry_id
        self._emit(entry, now_ms)
        return entry

    def resolve(self, entry_id: str, *, actual_r: Decimal, now_ms: int) -> ShadowEntry:
        entry = self._entries.get(entry_id)
        if entry is None:
            raise KeyError(entry_id)
        if entry.status is EntryStatus.NO_TRADE:
            raise ShadowError(f"{entry_id} recorded no trade; there is nothing to resolve")
        if entry.status is not EntryStatus.OPEN:
            raise ShadowError(f"{entry_id} is already {entry.status.value}")
        resolved = ShadowEntry(**{**entry.__dict__, "actual_r": dec(actual_r),
                                  "resolved_ms": now_ms, "status": EntryStatus.RESOLVED})
        if not resolved.seal_ok():
            raise ShadowError("attaching an outcome changed the sealed decision")
        self._entries[entry_id] = resolved
        self._emit(resolved, now_ms)
        return resolved

    def expire_due(self, *, now_ms: int) -> list[ShadowEntry]:
        """Close out entries whose horizon passed without an outcome.

        An expired entry is a measurement too: it says the comparison could
        not be made, which the performance ledger scores separately from a
        comparison that was made and lost."""
        out = []
        for eid, e in list(self._entries.items()):
            if e.status is EntryStatus.OPEN and now_ms >= e.opened_ms + e.horizon_ms:
                expired = ShadowEntry(**{**e.__dict__, "status": EntryStatus.EXPIRED,
                                         "resolved_ms": now_ms})
                self._entries[eid] = expired
                self._emit(expired, now_ms)
                out.append(expired)
        return out

    # ------------------------------------------------------------------- read
    def get(self, entry_id: str) -> Optional[ShadowEntry]:
        return self._entries.get(entry_id)

    def for_decision_point(self, decision_point_id: str) -> Optional[ShadowEntry]:
        eid = self._by_point.get(decision_point_id)
        return None if eid is None else self._entries[eid]

    def entries(self, *, status: Optional[EntryStatus] = None,
                model_id: Optional[str] = None) -> list[ShadowEntry]:
        out = [e for e in self._entries.values()
               if (status is None or e.status is status)
               and (model_id is None or e.assessment.model_id == model_id)]
        return sorted(out, key=lambda e: (e.opened_ms, e.entry_id))

    def __len__(self) -> int:
        return len(self._entries)

    def statistics(self, *, model_id: Optional[str] = None) -> dict[str, Any]:
        resolved = self.entries(status=EntryStatus.RESOLVED, model_id=model_id)
        diverged = [e for e in resolved if e.diverged]
        deltas = [e.delta_r for e in diverged if e.delta_r is not None]
        return {
            "shadow_book_version": SHADOW_BOOK_VERSION,
            "is_live_affecting": IS_LIVE_AFFECTING,
            "entries": len(self.entries(model_id=model_id)),
            "resolved": len(resolved),
            "expired": len(self.entries(status=EntryStatus.EXPIRED, model_id=model_id)),
            "no_trade": len(self.entries(status=EntryStatus.NO_TRADE, model_id=model_id)),
            "diverged": len(diverged),
            "total_delta_r": str(sum(deltas, ZERO)),
            "mean_delta_r": str(sum(deltas, ZERO) / Decimal(len(deltas))) if deltas else None,
        }

    # -------------------------------------------------------------- internals
    def _emit(self, entry: ShadowEntry, now_ms: int) -> None:
        if self._ledger is None:
            return
        self._ledger.append(make_event(
            EventKind.SHADOW_DECISION, self._producer, entry.to_dict(),
            event_time_ms=now_ms, received_time_ms=now_ms,
            correlation_id=entry.decision_point_id))
