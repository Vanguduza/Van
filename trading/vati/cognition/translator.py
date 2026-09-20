"""Cognitive action translator (TRD-REV51-098, G5).

This is the only place in Rev 5.1 where a model result is allowed to touch
anything the live path will read, so it is the module most worth being
suspicious of.

What it may produce is one bounded thing: a *lower* `requested_risk_pct` on a
TradeIntent that has not yet reached the Risk Authority. That is the entire
surface. It does not build a RiskDecision, does not construct an OrderCommand,
does not call an adapter, and does not import anything that can. The intent it
returns still goes through IntentFactory → RiskSnapshot → RiskAuthority →
ExecutionPolicyEngine → ExecutionRouter exactly as before, and the authority
remains free to reject it outright (INV-AUTH-001, INV-EXEC-001).

Reduce-only is enforced twice over. The contract already refuses a multiplier
above 1, and `_apply` takes `min(original, original × m)` so even a multiplier
that somehow arrived larger cannot raise anything. Two locks on the same door
is the right number for the one door that opens onto live sizing.

Mode is the third control. `LIVE_ADVISORY` is disabled at module scope and
asking for it raises rather than silently downgrading, because a system that
quietly runs in a weaker mode than the operator believes is worse than one
that stops. The first pass runs `SHADOW`, where the translation is recorded
and the intent is handed back untouched (INV-LIVE-001).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from vati.cognition.contracts import CognitiveAssessment, Verdict
from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.risk.contracts import TradeIntent

PRODUCER = "vati-action-translator"
TRANSLATOR_VERSION = "action-translator/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")

#: INV-LIVE-001. Turning this on is a promotion decision with owner evidence
#: behind it, not a configuration change, so it lives in code where it shows
#: up in a diff.
LIVE_ADVISORY_ENABLED = False


class TranslationRefused(RuntimeError):
    pass


class Mode(str, Enum):
    SHADOW = "SHADOW"            # record only; the intent is returned unchanged
    LIVE_ADVISORY = "LIVE_ADVISORY"  # the reduced intent is returned


class ActionKind(str, Enum):
    """Everything a translated assessment may become."""

    NO_CHANGE = "NO_CHANGE"
    REDUCE_REQUESTED_RISK = "REDUCE_REQUESTED_RISK"
    WITHHOLD_CANDIDATE = "WITHHOLD_CANDIDATE"
    RAISE_FLAG = "RAISE_FLAG"
    OPEN_RESEARCH_MISSION = "OPEN_RESEARCH_MISSION"


#: Which verdict becomes which action. Exhaustive by construction: a verdict
#: with no mapping is a programming error, not a default.
VERDICT_ACTIONS: dict[Verdict, ActionKind] = {
    Verdict.CONCUR: ActionKind.NO_CHANGE,
    Verdict.REDUCE: ActionKind.REDUCE_REQUESTED_RISK,
    Verdict.ABSTAIN: ActionKind.WITHHOLD_CANDIDATE,
    Verdict.FLAG: ActionKind.RAISE_FLAG,
    Verdict.PROPOSE_RESEARCH: ActionKind.OPEN_RESEARCH_MISSION,
    Verdict.INSUFFICIENT_CONTEXT: ActionKind.NO_CHANGE,
}


@dataclass(frozen=True)
class TranslatedAction:
    """What an assessment came to, and whether it was allowed to matter."""

    action_id: str
    kind: ActionKind
    mode: Mode
    trade_intent_id: str
    assessment_seal: str
    model_id: str
    original_risk_pct: Decimal
    proposed_risk_pct: Decimal
    applied: bool                 # False in SHADOW, always
    reason_codes: tuple[str, ...]
    justification: str
    translated_ms: int
    translator_version: str = TRANSLATOR_VERSION

    @property
    def reduces(self) -> bool:
        return self.proposed_risk_pct < self.original_risk_pct

    def body(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind.value,
            "mode": self.mode.value,
            "trade_intent_id": self.trade_intent_id,
            "assessment_seal": self.assessment_seal,
            "model_id": self.model_id,
            "original_risk_pct": str(self.original_risk_pct),
            "proposed_risk_pct": str(self.proposed_risk_pct),
            "applied": self.applied,
            "reduces": self.reduces,
            "reason_codes": list(self.reason_codes),
            "justification": self.justification,
            "translated_ms": self.translated_ms,
            "translator_version": self.translator_version,
        }

    @property
    def digest(self) -> str:
        return canonical_hash(self.body())


@dataclass(frozen=True)
class TranslationResult:
    """The action, and the intent as the caller should now treat it."""

    action: TranslatedAction
    intent: Optional[TradeIntent]     # None when the candidate is withheld
    withheld: bool

    @property
    def intent_unchanged(self) -> bool:
        return self.intent is not None and not self.action.applied


class ActionTranslator:
    """Turns an assessment into at most a smaller request."""

    def __init__(self, *, mode: Mode = Mode.SHADOW, ledger=None,
                 producer: str = PRODUCER) -> None:
        if mode is Mode.LIVE_ADVISORY and not LIVE_ADVISORY_ENABLED:
            # Refuse rather than downgrade: running in a weaker mode than the
            # operator believes is worse than not running.
            raise TranslationRefused(
                "LIVE_ADVISORY is disabled (INV-LIVE-001); the first pass is "
                "OFFLINE_EVOLUTION + SHADOW_LIVE")
        self.mode = mode
        self._ledger = ledger
        self._producer = producer
        self._seq = 0

    @staticmethod
    def _apply(original: Decimal, multiplier: Decimal) -> Decimal:
        """Reduce-only, belt and braces.

        The contract has already refused a multiplier above 1. Taking the min
        anyway means a future bug in that check cannot become a size increase
        here — the worst it can do is leave the request alone.
        """
        scaled = original * multiplier
        return scaled if scaled < original else original

    def translate(self, assessment: CognitiveAssessment, intent: TradeIntent, *,
                  now_ms: int) -> TranslationResult:
        if not assessment.seal_ok():
            raise TranslationRefused("assessment seal does not verify")
        kind = VERDICT_ACTIONS.get(assessment.verdict)
        if kind is None:
            raise TranslationRefused(
                f"verdict {assessment.verdict.value} has no mapping; an unmapped verdict "
                "is a programming error, not a default")

        original = intent.requested_risk_pct
        proposed = original
        withheld = False

        if kind is ActionKind.REDUCE_REQUESTED_RISK:
            proposed = self._apply(original, assessment.risk_multiplier)
        elif kind is ActionKind.WITHHOLD_CANDIDATE:
            proposed = ZERO
            withheld = True

        applied = self.mode is Mode.LIVE_ADVISORY and (proposed != original or withheld)

        self._seq += 1
        action = TranslatedAction(
            action_id=f"action-{now_ms}-{self._seq}",
            kind=kind,
            mode=self.mode,
            trade_intent_id=intent.trade_intent_id,
            assessment_seal=assessment.seal,
            model_id=assessment.model_id,
            original_risk_pct=original,
            proposed_risk_pct=proposed,
            applied=applied,
            reason_codes=tuple(assessment.reason_codes),
            justification=assessment.narrative[:500],
            translated_ms=now_ms,
        )

        if self._ledger is not None:
            self._ledger.append(make_event(
                EventKind.COGNITIVE_ASSESSMENT, self._producer,
                {**action.body(), "assessment": assessment.to_dict()},
                event_time_ms=now_ms, received_time_ms=now_ms,
                correlation_id=intent.trade_intent_id))

        if not applied:
            # SHADOW: the intent is handed back exactly as it arrived.
            return TranslationResult(action, intent, withheld=False)
        if withheld:
            return TranslationResult(action, None, withheld=True)
        return TranslationResult(action, replace(intent, requested_risk_pct=proposed),
                                 withheld=False)
