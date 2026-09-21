"""TRD-REV51-094 — CognitiveAssessment contract and reason vocabulary.

The contract is a control surface, so most of these tests are about what a
model is not allowed to say.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.cognition.contracts import (
    CONTRACT_VERSION,
    REASON_VOCABULARY,
    AssessmentRejected,
    ModelRole,
    Verdict,
    abstention,
    normalise,
)

CTX = "c" * 64


def _norm(**over):
    raw = {"verdict": "CONCUR", "reason_codes": [], "risk_multiplier": "1", "confidence": "0.5"}
    raw.update(over)
    return normalise(raw, model_id="fable-5.1", role=ModelRole.PRIMARY, context_hash=CTX, now_ms=1_000)


def test_a_valid_assessment_is_sealed_and_joins_to_its_context():
    a = _norm()
    assert a.seal_ok()
    assert a.context_hash == CTX
    assert a.contract_version == CONTRACT_VERSION


def test_editing_a_sealed_assessment_breaks_its_seal():
    a = _norm()
    tampered = type(a)(**{**a.__dict__, "narrative": "something else"})
    assert not tampered.seal_ok()


def test_a_multiplier_above_one_is_refused_not_clamped():
    """A model reaching for more size is the event worth seeing. Clamping to 1
    would make the breach indistinguishable from agreement."""
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="REDUCE", reason_codes=["EVIDENCE_THIN"], risk_multiplier="1.25")
    assert e.value.code == "MULTIPLIER_ABOVE_ONE"


def test_a_negative_multiplier_is_refused():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="REDUCE", reason_codes=["EVIDENCE_THIN"], risk_multiplier="-0.1")
    assert e.value.code == "MULTIPLIER_NEGATIVE"


def test_an_unknown_verdict_is_refused_rather_than_defaulted():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="INCREASE")
    assert e.value.code == "VERDICT_UNKNOWN"


def test_there_is_no_verdict_that_raises_risk():
    assert not any("INCREASE" in v.value or "OVERRIDE" in v.value or "LIVE" in v.value
                   for v in Verdict)


def test_an_unclassified_reason_is_forbidden():
    """INV-LEARN-001 applied at the parser: unclassified means forbidden."""
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="FLAG", reason_codes=["VIBES"])
    assert e.value.code == "REASON_UNKNOWN"


def test_a_behaviour_changing_verdict_must_cite_a_reason():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="ABSTAIN", reason_codes=[], risk_multiplier="0")
    assert e.value.code == "REASON_REQUIRED"


def test_concur_may_stand_without_a_reason():
    assert _norm(verdict="CONCUR").verdict is Verdict.CONCUR


def test_abstain_carrying_size_is_incoherent_and_refused():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="ABSTAIN", reason_codes=["LIQUIDITY_THIN"], risk_multiplier="0.4")
    assert e.value.code == "ABSTAIN_WITH_SIZE"


def test_reduce_that_does_not_reduce_is_refused():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="REDUCE", reason_codes=["EVIDENCE_THIN"], risk_multiplier="1")
    assert e.value.code == "REDUCE_WITHOUT_REDUCTION"


def test_a_non_sizing_verdict_may_not_carry_a_multiplier():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="FLAG", reason_codes=["DRIFT_DETECTED"], risk_multiplier="0.5")
    assert e.value.code == "NON_SIZING_VERDICT_WITH_MULTIPLIER"


@pytest.mark.parametrize("field", ["approved_size", "lots", "stake", "order", "stop", "entry", "venue"])
def test_an_assessment_carrying_order_fields_is_refused(field):
    """INV-AUTH-001 / INV-EXEC-001 as a parsing rule: an assessment that
    carries order fields is trying to be an order."""
    with pytest.raises(AssessmentRejected) as e:
        _norm(**{field: "1"})
    assert e.value.code == "ORDER_FIELDS_PRESENT"


def test_confidence_outside_the_unit_interval_is_refused():
    with pytest.raises(AssessmentRejected) as e:
        _norm(confidence="1.5")
    assert e.value.code == "CONFIDENCE_OUT_OF_RANGE"


def test_a_non_object_result_is_refused_rather_than_crashing():
    with pytest.raises(AssessmentRejected) as e:
        normalise("CONCUR", model_id="m", role=ModelRole.PRIMARY, context_hash=CTX, now_ms=1)
    assert e.value.code == "NOT_AN_OBJECT"


def test_malformed_numbers_are_refused_with_a_named_code():
    with pytest.raises(AssessmentRejected) as e:
        _norm(verdict="REDUCE", reason_codes=["EVIDENCE_THIN"], risk_multiplier="half")
    assert e.value.code == "FIELD_MALFORMED"


def test_duplicate_reasons_are_collapsed_in_order():
    a = _norm(verdict="REDUCE", reason_codes=["EVIDENCE_THIN", "EVIDENCE_THIN", "DRIFT_DETECTED"],
              risk_multiplier="0.5")
    assert a.reason_codes == ("EVIDENCE_THIN", "DRIFT_DETECTED")


def test_abstention_is_a_real_sealed_record_not_a_gap():
    """Silence is an outcome the performance ledger has to be able to score."""
    a = abstention(context_hash=CTX, model_id="none", role=ModelRole.FINAL_FALLBACK,
                   reason="MODEL_UNAVAILABLE", now_ms=7)
    assert a.seal_ok()
    assert a.verdict is Verdict.INSUFFICIENT_CONTEXT
    assert a.risk_multiplier == Decimal("1")   # changes nothing
    assert not a.is_actionable


def test_abstention_with_an_unclassified_reason_is_refused():
    with pytest.raises(AssessmentRejected):
        abstention(context_hash=CTX, model_id="m", role=ModelRole.PRIMARY,
                   reason="TIRED", now_ms=1)


def test_only_reduce_and_abstain_are_actionable():
    actionable = {v for v in Verdict
                  if _actionable(v)}
    assert actionable == {Verdict.REDUCE, Verdict.ABSTAIN}


def _actionable(v: Verdict) -> bool:
    if v is Verdict.REDUCE:
        a = _norm(verdict="REDUCE", reason_codes=["EVIDENCE_THIN"], risk_multiplier="0.5")
    elif v is Verdict.ABSTAIN:
        a = _norm(verdict="ABSTAIN", reason_codes=["LIQUIDITY_THIN"], risk_multiplier="0")
    else:
        a = _norm(verdict=v.value, reason_codes=["EVIDENCE_THIN"] if v in
                  (Verdict.FLAG, Verdict.PROPOSE_RESEARCH, Verdict.INSUFFICIENT_CONTEXT) else [])
    return a.is_actionable


def test_every_reason_in_the_vocabulary_has_a_description():
    assert all(isinstance(v, str) and v.strip() for v in REASON_VOCABULARY.values())


def test_fallback_roles_carry_no_reduced_authority():
    """INV-MODEL-001: the hierarchy is availability routing. A result from the
    final fallback passes exactly the same checks as one from the primary."""
    for role in (ModelRole.PRIMARY, ModelRole.FIRST_FALLBACK,
                 ModelRole.SECOND_FALLBACK, ModelRole.FINAL_FALLBACK):
        with pytest.raises(AssessmentRejected):
            normalise({"verdict": "REDUCE", "reason_codes": ["EVIDENCE_THIN"],
                       "risk_multiplier": "1.5"},
                      model_id="m", role=role, context_hash=CTX, now_ms=1)
