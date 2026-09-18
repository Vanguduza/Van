"""Rev 1 §§27, 75 — calibration adapts style and never truth standards.

§27's rule is the entire test surface: *"Do NOT tune truth standards. Truth and
evidence rules are invariant. Interaction style may adapt."* So the tests check
both halves — that style genuinely responds to the owner, and that nothing
reachable from here can lower a bar.
"""

from __future__ import annotations

import pytest

from conftest_automation import make_store
from van_gateway.reasoning.calibration import (
    CALIBRATION_INPUTS,
    Calibration,
    EvidencePresentation,
    RelationshipCalibrationEngine,
    Verbosity,
)
from van_gateway.reasoning.kernel import ChallengeMode
from van_gateway.understanding.owner_model import OwnerCognitiveModel, OwnerModelField


async def _engine_with(tmp_path, field=None, value=None):
    store = await make_store(tmp_path)
    if field is not None:
        model = OwnerCognitiveModel(store)
        assertion = await model.observe(
            owner_principal_id="owner", field=field, value=value, episode_ref="m1"
        )
        await model.confirm(assertion.assertion_id)
    return RelationshipCalibrationEngine(store)


def test_there_is_nothing_here_that_could_tune_a_truth_standard():
    """§27 — enforced by there being no such field, not by discipline."""
    fields = set(Calibration.__dataclass_fields__)
    assert fields == {
        "challenge_mode", "verbosity", "evidence_presentation",
        "interrupt_threshold", "reasons",
    }
    for forbidden in ("evidence_required", "verification_threshold", "confidence_floor",
                      "may_skip_verification", "factual_standard"):
        assert forbidden not in fields


def test_risk_tolerance_is_not_a_calibration_input():
    """What risk the owner accepts is an authority question for DomainTrust,
    not a presentation question for this engine."""
    assert OwnerModelField.ACCEPTED_RISK_PATTERN not in CALIBRATION_INPUTS
    assert OwnerModelField.DELEGATION_PREFERENCE not in CALIBRATION_INPUTS


async def test_the_work_sets_a_floor_the_relationship_cannot_lower(tmp_path):
    """§28 — an owner who likes brisk agreement still gets RED_TEAM on
    something irreversible."""
    engine = await _engine_with(
        tmp_path, OwnerModelField.COMMUNICATION_PREFERENCE, "terse and brief please"
    )
    calibration = await engine.calibrate(
        owner_principal_id="owner", consequential=True, irreversible=True
    )
    assert calibration.challenge_mode is ChallengeMode.RED_TEAM
    # Style still adapted underneath the floor.
    assert calibration.verbosity is Verbosity.TERSE


async def test_being_corrected_makes_van_push_harder_not_softer(tmp_path):
    """§71's failure mode is fluent agreement, so corrections raise the mode."""
    engine = await _engine_with(tmp_path)
    calm = await engine.calibrate(owner_principal_id="owner")
    assert calm.challenge_mode is ChallengeMode.BALANCED
    corrected = await engine.calibrate(owner_principal_id="owner", prior_corrections=3)
    assert corrected.challenge_mode is ChallengeMode.CRITICAL
    assert any("correction" in r for r in corrected.reasons)


async def test_low_confidence_widens_the_search_rather_than_hedging_the_wording(tmp_path):
    engine = await _engine_with(tmp_path)
    calibration = await engine.calibrate(owner_principal_id="owner", van_confidence=0.2)
    assert calibration.challenge_mode is ChallengeMode.CRITICAL


async def test_only_confirmed_preferences_change_behaviour(tmp_path):
    """§64 — a CANDIDATE is something VAN noticed, not something it may act on."""
    store = await make_store(tmp_path)
    model = OwnerCognitiveModel(store)
    # Two episodes reaches CANDIDATE, which must not calibrate anything.
    for episode in ("m1", "m2"):
        await model.observe(
            owner_principal_id="owner", field=OwnerModelField.COMMUNICATION_PREFERENCE,
            value="terse", episode_ref=episode,
        )
    engine = RelationshipCalibrationEngine(store)
    calibration = await engine.calibrate(owner_principal_id="owner")
    assert calibration.verbosity is Verbosity.BALANCED


async def test_a_confirmed_evidence_preference_leads_with_evidence(tmp_path):
    engine = await _engine_with(
        tmp_path, OwnerModelField.EVIDENCE_PREFERENCE, "always show me the evidence"
    )
    calibration = await engine.calibrate(owner_principal_id="owner")
    assert calibration.evidence_presentation is EvidencePresentation.EVIDENCE_FIRST


async def test_urgency_overrides_a_standing_verbosity_preference(tmp_path):
    """A thorough answer to an urgent thing is a worse answer."""
    engine = await _engine_with(
        tmp_path, OwnerModelField.REASONING_PREFERENCE, "thorough and full detail"
    )
    relaxed = await engine.calibrate(owner_principal_id="owner", urgency=0.2)
    assert relaxed.verbosity is Verbosity.THOROUGH
    urgent = await engine.calibrate(owner_principal_id="owner", urgency=0.9)
    assert urgent.verbosity is Verbosity.BALANCED


async def test_the_interrupt_threshold_stays_inside_a_band(tmp_path):
    """Never zero (VAN goes silent), never one (VAN never stops)."""
    engine = await _engine_with(
        tmp_path, OwnerModelField.INTERRUPTION_PREFERENCE, "minimal interruptions"
    )
    for urgency in (0.0, 0.5, 1.0):
        calibration = await engine.calibrate(owner_principal_id="owner", urgency=urgency)
        assert 0.25 <= calibration.interrupt_threshold <= 0.85


async def test_the_payload_states_the_invariant(tmp_path):
    engine = await _engine_with(tmp_path)
    payload = (await engine.calibrate(owner_principal_id="owner")).as_dict()
    assert payload["truth_standards_tuned"] is False
