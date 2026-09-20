"""CognitiveAssessment contract and reason vocabulary (TRD-REV51-094, G1).

This is the narrow gate every model result passes through before any other
Rev 5.1 component may read it. It exists because a model's output is prose
until something gives it a type, and prose cannot be checked against an
invariant.

Three things are enforced here and nowhere else, so there is one place to
argue with:

* **A closed vocabulary.** A verdict or reason the registry does not know is
  rejected, not coerced to a default. INV-LEARN-001 — unclassified means
  forbidden — is a parsing rule here, not a policy document.
* **Reduce-only effect.** The only numeric a model may propose is a risk
  multiplier in [0, 1]. A value above 1 is not clamped, it is refused: a model
  asking to raise a ceiling is a contract breach worth seeing, and silently
  rounding it to 1 would hide exactly the event worth knowing about.
* **No live shortcut.** An assessment carries no size, no order, no stop and
  no venue. It cannot be turned into an order by reading it harder; the
  translator (094 → 098) must go through IntentFactory, RiskAuthority and
  ExecutionRouter like everything else (INV-AUTH-001, INV-EXEC-001).

A rejected assessment is not an outage. The caller falls back to the
deterministic path, which is what it would have done with no model at all
(INV-FAIL-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Optional

from vati.core.canonical import canonical_hash, dec

CONTRACT_VERSION = "cognitive-assessment/5.1.0"

ZERO, ONE = Decimal("0"), Decimal("1")


class AssessmentRejected(ValueError):
    """The model result is not a valid assessment. The caller falls back."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ModelRole(str, Enum):
    """Where a model sits in the availability hierarchy (INV-MODEL-001).

    The order is availability routing only. A fallback role has exactly the
    same authority as the primary — less capability never means fewer controls.
    """

    PRIMARY = "PRIMARY"            # Fable 5.1
    FIRST_FALLBACK = "FIRST_FALLBACK"    # GPT-6 Astra
    SECOND_FALLBACK = "SECOND_FALLBACK"  # Claude Opus 5
    FINAL_FALLBACK = "FINAL_FALLBACK"    # GPT-5.6 Sol
    REVIEWER = "REVIEWER"          # blind reviewer (095), never the author


class Verdict(str, Enum):
    """Everything cognition is permitted to conclude.

    Note what is absent: there is no INCREASE, no OVERRIDE, no GO_LIVE and no
    WIDEN_STOP. The vocabulary is the control surface.
    """

    CONCUR = "CONCUR"                  # deterministic path is sound as-is
    REDUCE = "REDUCE"                  # same trade, less of it
    ABSTAIN = "ABSTAIN"                # take no position this cycle
    FLAG = "FLAG"                      # record a concern, change nothing
    PROPOSE_RESEARCH = "PROPOSE_RESEARCH"  # open an offline mission (118)
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"  # the honest refusal


#: Reasons a verdict may cite. Closed by construction: adding one is a code
#: change that shows up in review, which is the point.
REASON_VOCABULARY: dict[str, str] = {
    # evidence quality
    "EVIDENCE_THIN": "too few comparable observations to support the decision",
    "EVIDENCE_STALE": "the supporting evidence is older than its useful life",
    "ANALOGUE_ABSENT": "no sufficiently similar historical episode was retrieved",
    "CONTEXT_INCOMPLETE": "a required context section was missing or unsealed",
    # market condition
    "REGIME_UNSTABLE": "the regime classification changed within the lookback",
    "VOLATILITY_ELEVATED": "realised volatility is above its calibrated band",
    "LIQUIDITY_THIN": "quoted depth will not absorb the intended size",
    "SPREAD_ABNORMAL": "spread is outside the venue's normal distribution",
    "EVENT_PROXIMITY": "a tier-1 release falls inside the holding horizon",
    "CORRELATION_CROWDED": "the book already carries this exposure under another name",
    # strategy condition
    "EDGE_DECAYING": "measured edge is trending toward its retirement threshold",
    "DRIFT_DETECTED": "feature or edge drift exceeded its alarm level",
    "SAMPLE_CONTAMINATED": "the supporting sample overlaps the evaluation window",
    "OVERFIT_SUSPECTED": "the result does not survive the deflated-Sharpe test",
    # execution condition
    "FILL_QUALITY_POOR": "measured slippage for this bucket is above tolerance",
    "ROUTE_UNCERTAIN": "the venue route or quantisation could not be resolved",
    # system condition
    "BUDGET_EXHAUSTED": "the cognition budget for this window is spent",
    "MODEL_UNAVAILABLE": "no model in the hierarchy answered",
    "REVIEWER_DISSENT": "the blind reviewer disagreed with the author",
    "PROTECTED_PATH_TOUCHED": "the proposal would alter a protected control path",
}

#: Verdicts that must cite at least one reason. CONCUR may stand alone;
#: everything that changes or withholds behaviour must say why.
REASON_REQUIRED = frozenset({
    Verdict.REDUCE, Verdict.ABSTAIN, Verdict.FLAG,
    Verdict.PROPOSE_RESEARCH, Verdict.INSUFFICIENT_CONTEXT,
})


@dataclass(frozen=True)
class CognitiveAssessment:
    """One model's normalised answer about one decision point.

    `seal` is the content hash of everything above it. It is what the shadow
    book, the performance ledger and the replay check all join on, so an
    assessment cannot be quietly edited after its outcome is known
    (INV-REPLAY-001).
    """

    assessment_id: str
    context_hash: str          # the sealed context this answered (093)
    model_id: str
    role: ModelRole
    verdict: Verdict
    reason_codes: tuple[str, ...]
    #: Reduce-only. 1 leaves the deterministic size alone; 0 stands the trade down.
    risk_multiplier: Decimal
    confidence: Decimal        # [0, 1], the model's own, never a control input
    narrative: str             # owner-readable, never parsed for behaviour
    horizon_ms: int            # how long this assessment claims to be valid
    produced_ms: int
    contract_version: str = CONTRACT_VERSION
    seal: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "context_hash": self.context_hash,
            "model_id": self.model_id,
            "role": self.role.value,
            "verdict": self.verdict.value,
            "reason_codes": list(self.reason_codes),
            "risk_multiplier": str(self.risk_multiplier),
            "confidence": str(self.confidence),
            "narrative": self.narrative,
            "horizon_ms": self.horizon_ms,
            "produced_ms": self.produced_ms,
            "contract_version": self.contract_version,
        }

    def sealed(self) -> "CognitiveAssessment":
        return CognitiveAssessment(**{**self.__dict__, "seal": canonical_hash(self.body())})

    def seal_ok(self) -> bool:
        return bool(self.seal) and self.seal == canonical_hash(self.body())

    @property
    def is_actionable(self) -> bool:
        """Whether this assessment changes anything downstream at all."""
        return self.verdict in (Verdict.REDUCE, Verdict.ABSTAIN)

    def to_dict(self) -> dict[str, Any]:
        return {**self.body(), "seal": self.seal}


def _decimal(raw: Mapping[str, Any], key: str, *, default: Optional[str] = None) -> Decimal:
    if key not in raw or raw[key] is None:
        if default is None:
            raise AssessmentRejected("FIELD_MISSING", f"{key} is required")
        return Decimal(default)
    try:
        return dec(raw[key])
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AssessmentRejected("FIELD_MALFORMED", f"{key} is not a number: {raw[key]!r}") from exc


def normalise(raw: Mapping[str, Any], *, model_id: str, role: ModelRole,
              context_hash: str, now_ms: int) -> CognitiveAssessment:
    """Turn one model's raw result into a sealed assessment, or refuse it.

    This is the ModelRouter result normaliser named by the packet's hook. It
    is total: it either returns a sealed, checked assessment or raises
    AssessmentRejected with a code the caller can log and move past.
    """
    if not isinstance(raw, Mapping):
        raise AssessmentRejected("NOT_AN_OBJECT", f"model returned {type(raw).__name__}")

    verdict_raw = str(raw.get("verdict", "")).strip().upper()
    try:
        verdict = Verdict(verdict_raw)
    except ValueError as exc:
        raise AssessmentRejected("VERDICT_UNKNOWN", f"{verdict_raw!r} is not in the vocabulary") from exc

    reasons_raw = raw.get("reason_codes") or ()
    if isinstance(reasons_raw, str):
        reasons_raw = [reasons_raw]
    reasons: list[str] = []
    for r in reasons_raw:
        code = str(r).strip().upper()
        if code not in REASON_VOCABULARY:
            # INV-LEARN-001: unclassified means forbidden, including here.
            raise AssessmentRejected("REASON_UNKNOWN", f"{code!r} is not a classified reason")
        if code not in reasons:
            reasons.append(code)
    if verdict in REASON_REQUIRED and not reasons:
        raise AssessmentRejected("REASON_REQUIRED", f"{verdict.value} must cite at least one reason")

    multiplier = _decimal(raw, "risk_multiplier", default="1")
    if multiplier > ONE:
        # Not clamped. A model reaching for more size is the event worth seeing.
        raise AssessmentRejected(
            "MULTIPLIER_ABOVE_ONE",
            f"risk_multiplier {multiplier} would raise risk; cognition is reduce-only")
    if multiplier < ZERO:
        raise AssessmentRejected("MULTIPLIER_NEGATIVE", f"risk_multiplier {multiplier} is below zero")

    confidence = _decimal(raw, "confidence", default="0")
    if not (ZERO <= confidence <= ONE):
        raise AssessmentRejected("CONFIDENCE_OUT_OF_RANGE", f"confidence {confidence} is outside [0, 1]")

    # An ABSTAIN that still carries size is incoherent; say so rather than
    # picking one of the two meanings.
    if verdict is Verdict.ABSTAIN and multiplier != ZERO:
        raise AssessmentRejected("ABSTAIN_WITH_SIZE", f"ABSTAIN carries risk_multiplier {multiplier}")
    if verdict is Verdict.REDUCE and multiplier >= ONE:
        raise AssessmentRejected("REDUCE_WITHOUT_REDUCTION", "REDUCE must lower the multiplier below 1")
    if verdict in (Verdict.CONCUR, Verdict.FLAG, Verdict.PROPOSE_RESEARCH) and multiplier != ONE:
        raise AssessmentRejected(
            "NON_SIZING_VERDICT_WITH_MULTIPLIER",
            f"{verdict.value} may not change size (got {multiplier})")

    horizon_ms = int(raw.get("horizon_ms", 0) or 0)
    if horizon_ms < 0:
        raise AssessmentRejected("HORIZON_NEGATIVE", f"horizon_ms {horizon_ms} is negative")

    forbidden = sorted(set(raw) & {"approved_size", "lots", "stake", "order", "stop",
                                   "entry", "venue", "account_alias", "mandate"})
    if forbidden:
        # INV-AUTH-001 / INV-EXEC-001 as a parsing rule: an assessment that
        # carries order fields is trying to be an order.
        raise AssessmentRejected("ORDER_FIELDS_PRESENT", f"assessment carries {', '.join(forbidden)}")

    narrative = str(raw.get("narrative", "")).strip()[:2000]
    assessment_id = str(raw.get("assessment_id") or "").strip() or canonical_hash(
        {"c": context_hash, "m": model_id, "t": now_ms, "v": verdict.value})[:32]

    return CognitiveAssessment(
        assessment_id=assessment_id,
        context_hash=context_hash,
        model_id=model_id,
        role=role,
        verdict=verdict,
        reason_codes=tuple(reasons),
        risk_multiplier=multiplier,
        confidence=confidence,
        narrative=narrative,
        horizon_ms=horizon_ms,
        produced_ms=now_ms,
    ).sealed()


def abstention(*, context_hash: str, model_id: str, role: ModelRole, reason: str,
               now_ms: int, narrative: str = "") -> CognitiveAssessment:
    """The assessment to use when no model answered, or every answer was refused.

    It is a real, sealed assessment rather than None so the shadow book and the
    performance ledger record the silence as an outcome (INV-EVID-001) instead
    of having a gap where a measurement should be.
    """
    if reason not in REASON_VOCABULARY:
        raise AssessmentRejected("REASON_UNKNOWN", f"{reason!r} is not a classified reason")
    return CognitiveAssessment(
        assessment_id=canonical_hash({"abstain": context_hash, "m": model_id, "t": now_ms})[:32],
        context_hash=context_hash,
        model_id=model_id,
        role=role,
        verdict=Verdict.INSUFFICIENT_CONTEXT,
        reason_codes=(reason,),
        risk_multiplier=ONE,   # changes nothing; the deterministic path stands
        confidence=ZERO,
        narrative=narrative,
        horizon_ms=0,
        produced_ms=now_ms,
    ).sealed()
