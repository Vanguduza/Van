"""TRD-REV51-098 action translator, 099 TradeHealth engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.cognition import translator as translator_mod
from vati.cognition.contracts import ModelRole, Verdict, normalise
from vati.cognition.translator import (
    LIVE_ADVISORY_ENABLED,
    VERDICT_ACTIONS,
    ActionKind,
    ActionTranslator,
    Mode,
    TranslationRefused,
)
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.lifecycle.trade_health import (
    ADVERSE_IMPAIRED,
    HEALTH_REASONS,
    HealthInputError,
    HealthState,
    PositionHealthInputs,
    TradeHealthEngine,
)
from vati.risk.contracts import Direction, StrategyState, TradeIntent

D = Decimal


def _intent(risk="0.01") -> TradeIntent:
    return TradeIntent("t1", "key", "acct", "MT5", "EURUSD", Direction.LONG, "s1", "1",
                       StrategyState.CERTIFIED_LIVE, D("1.10"), D("1.09"), D(risk), "dh", "mh")


def _assess(verdict="REDUCE", mult="0.5"):
    raw = {"verdict": verdict, "confidence": "0.8"}
    if verdict == "REDUCE":
        raw |= {"reason_codes": ["EVIDENCE_THIN"], "risk_multiplier": mult}
    elif verdict == "ABSTAIN":
        raw |= {"reason_codes": ["EVENT_PROXIMITY"], "risk_multiplier": "0"}
    elif verdict in ("FLAG", "PROPOSE_RESEARCH", "INSUFFICIENT_CONTEXT"):
        raw |= {"reason_codes": ["DRIFT_DETECTED"]}
    return normalise(raw, model_id="fable-5.1", role=ModelRole.PRIMARY,
                     context_hash="ctx", now_ms=1)


# ------------------------------------------------------------- 098 translator
def test_live_advisory_is_disabled_in_the_first_pass():
    assert LIVE_ADVISORY_ENABLED is False


def test_asking_for_live_advisory_raises_rather_than_downgrading():
    """Running in a weaker mode than the operator believes is worse than not
    running."""
    with pytest.raises(TranslationRefused) as e:
        ActionTranslator(mode=Mode.LIVE_ADVISORY)
    assert "INV-LIVE-001" in str(e.value)


def test_shadow_mode_records_the_reduction_and_hands_the_intent_back_untouched():
    r = ActionTranslator().translate(_assess("REDUCE", "0.5"), _intent(), now_ms=1)
    assert r.action.kind is ActionKind.REDUCE_REQUESTED_RISK
    assert r.action.proposed_risk_pct == D("0.005")
    assert r.action.applied is False
    assert r.intent.requested_risk_pct == D("0.01")
    assert r.intent_unchanged


def test_every_verdict_has_an_explicit_action_mapping():
    assert set(VERDICT_ACTIONS) == set(Verdict)


@pytest.mark.parametrize("verdict,kind", [
    ("CONCUR", ActionKind.NO_CHANGE),
    ("REDUCE", ActionKind.REDUCE_REQUESTED_RISK),
    ("ABSTAIN", ActionKind.WITHHOLD_CANDIDATE),
    ("FLAG", ActionKind.RAISE_FLAG),
    ("PROPOSE_RESEARCH", ActionKind.OPEN_RESEARCH_MISSION),
    ("INSUFFICIENT_CONTEXT", ActionKind.NO_CHANGE),
])
def test_verdicts_translate_to_their_declared_action(verdict, kind):
    r = ActionTranslator().translate(_assess(verdict), _intent(), now_ms=1)
    assert r.action.kind is kind


def test_a_flag_never_changes_the_request():
    r = ActionTranslator().translate(_assess("FLAG"), _intent(), now_ms=1)
    assert r.action.proposed_risk_pct == r.action.original_risk_pct
    assert not r.action.reduces


def test_a_broken_seal_is_refused():
    a = _assess()
    tampered = type(a)(**{**a.__dict__, "risk_multiplier": D("0.1")})
    with pytest.raises(TranslationRefused):
        ActionTranslator().translate(tampered, _intent(), now_ms=1)


def _imported_names(module) -> set[str]:
    """Every name the module actually pulls in, by reading its imports."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(a.name for a in node.names)
    return names


def test_the_translator_never_constructs_an_order_or_a_decision():
    """INV-AUTH-001 / INV-EXEC-001 as a fact about what the module imports,
    not as a promise in its docstring."""
    names = _imported_names(translator_mod)
    for forbidden in ("RiskDecision", "RiskAuthority", "OrderCommand",
                      "ExecutionRouter", "VenueAdapter"):
        assert forbidden not in names
    assert not any(n.startswith("vati.execution") or n.startswith("vati.risk.authority")
                   for n in names)


def test_actions_are_ledgered_against_the_intent():
    led = Ledger(":memory:")
    ActionTranslator(ledger=led).translate(_assess(), _intent(), now_ms=4)
    assert led.count(EventKind.COGNITIVE_ASSESSMENT) == 1
    assert [e.correlation_id for e in led.iter(EventKind.COGNITIVE_ASSESSMENT)] == ["t1"]


# --- the advisory path, exercised with the gate deliberately lifted ----------
@pytest.fixture()
def advisory(monkeypatch):
    monkeypatch.setattr(translator_mod, "LIVE_ADVISORY_ENABLED", True)
    return ActionTranslator(mode=Mode.LIVE_ADVISORY)


def test_advisory_mode_returns_a_smaller_request(advisory):
    r = advisory.translate(_assess("REDUCE", "0.25"), _intent(), now_ms=1)
    assert r.action.applied and r.intent.requested_risk_pct == D("0.0025")


def test_advisory_mode_withholds_on_abstain(advisory):
    r = advisory.translate(_assess("ABSTAIN"), _intent(), now_ms=1)
    assert r.withheld and r.intent is None


def test_the_reduced_intent_is_otherwise_identical(advisory):
    original = _intent()
    r = advisory.translate(_assess("REDUCE", "0.5"), original, now_ms=1)
    changed = {f for f in original.__dataclass_fields__
               if getattr(original, f) != getattr(r.intent, f)}
    assert changed == {"requested_risk_pct"}


def test_a_multiplier_that_somehow_exceeds_one_still_cannot_raise(advisory):
    """The contract already refuses this. Two locks on the one door that
    opens onto live sizing."""
    a = _assess("REDUCE", "0.5")
    forged = type(a)(**{**a.__dict__, "risk_multiplier": D("4")})
    forged = type(a)(**{**forged.__dict__, "seal": ""}).sealed()
    r = advisory.translate(forged, _intent(), now_ms=1)
    assert r.intent.requested_risk_pct == D("0.01")
    assert not r.action.reduces


def test_concur_in_advisory_mode_changes_nothing(advisory):
    r = advisory.translate(_assess("CONCUR"), _intent(), now_ms=1)
    assert not r.action.applied and r.intent.requested_risk_pct == D("0.01")


# ------------------------------------------------------------ 099 trade health
def _inputs(**over) -> PositionHealthInputs:
    base = dict(trade_intent_id="t1", symbol="EURUSD", direction=Direction.LONG,
                entry_price=D("1.1000"), current_price=D("1.1010"),
                original_stop=D("1.0900"), current_stop=D("1.0900"),
                has_confirmed_stop=True, opened_ms=0, now_ms=60_000,
                expected_horizon_ms=600_000,
                worst_price=D("1.0990"), best_price=D("1.1020"))
    base.update(over)
    return PositionHealthInputs(**base)


def test_a_normal_position_is_healthy_and_does_not_block_scaling():
    h = TradeHealthEngine().assess(_inputs())
    assert h.state is HealthState.HEALTHY and not h.blocks_scaling


def test_no_state_licenses_more_risk():
    """A position doing well is not evidence the account can afford more."""
    for state in HealthState:
        assert state.value in ("HEALTHY", "WATCH", "IMPAIRED", "FAILING")
    assert all(not n.startswith("ALLOW") and not n.startswith("SCALE")
               for n in HealthState.__members__)


def test_an_unprotected_position_is_failing_whatever_the_price_is_doing():
    h = TradeHealthEngine().assess(_inputs(has_confirmed_stop=False, current_price=D("1.1090")))
    assert h.state is HealthState.FAILING and "NO_CONFIRMED_STOP" in h.reasons
    assert h.is_urgent


def test_a_stop_wider_than_the_approved_one_is_a_defect_not_a_state():
    h = TradeHealthEngine().assess(_inputs(current_stop=D("1.0800")))
    assert h.state is HealthState.FAILING and "STOP_WIDER_THAN_ORIGINAL" in h.reasons


def test_an_invalidated_thesis_is_failing():
    h = TradeHealthEngine().assess(_inputs(thesis_invalidated=True))
    assert h.state is HealthState.FAILING and "THESIS_INVALIDATED" in h.reasons


def test_deep_adverse_excursion_impairs_the_position():
    h = TradeHealthEngine().assess(_inputs(worst_price=D("1.0920")))
    assert h.mae_r >= ADVERSE_IMPAIRED
    assert h.state is HealthState.IMPAIRED and h.requires_preservation


def test_half_the_risk_distance_given_up_is_a_watch():
    h = TradeHealthEngine().assess(_inputs(worst_price=D("1.0945")))
    assert h.state is HealthState.WATCH and "ADVERSE_EXCURSION_ELEVATED" in h.reasons


def test_a_position_well_past_its_horizon_with_no_progress_is_stagnant():
    h = TradeHealthEngine().assess(_inputs(now_ms=1_000_000, current_price=D("1.1001")))
    assert "STAGNANT" in h.reasons and h.blocks_scaling


def test_handing_back_most_of_a_real_gain_is_a_watch():
    h = TradeHealthEngine().assess(_inputs(best_price=D("1.1200"), current_price=D("1.1020")))
    assert "GIVE_BACK" in h.reasons


def test_a_small_wobble_on_a_small_gain_is_not_a_give_back():
    h = TradeHealthEngine().assess(_inputs(best_price=D("1.1015"), current_price=D("1.1005")))
    assert "GIVE_BACK" not in h.reasons


def test_an_abnormal_spread_is_recorded_because_exiting_would_cross_it():
    h = TradeHealthEngine().assess(_inputs(spread=D("0.0009"), typical_spread=D("0.0001")))
    assert "SPREAD_ABNORMAL" in h.reasons


def test_a_stale_mark_is_stated_rather_than_silently_trusted():
    h = TradeHealthEngine().assess(_inputs(mark_age_ms=300_000))
    assert "MARK_STALE" in h.reasons and h.state is HealthState.WATCH


def test_a_short_position_is_measured_with_the_right_sign():
    h = TradeHealthEngine().assess(_inputs(direction=Direction.SHORT,
                                           original_stop=D("1.1100"),
                                           current_price=D("1.0950"),
                                           current_stop=D("1.1100"),
                                           worst_price=D("1.1010"),
                                           best_price=D("1.0950")))
    assert h.current_r > 0 and h.mfe_r > 0


def test_a_position_with_no_risk_distance_is_refused_rather_than_scored():
    with pytest.raises(HealthInputError):
        _inputs(original_stop=D("1.1000"))


def test_the_worst_state_wins_and_every_reason_is_kept():
    h = TradeHealthEngine().assess(_inputs(has_confirmed_stop=False,
                                           worst_price=D("1.0920"),
                                           spread=D("0.0009"), typical_spread=D("0.0001")))
    assert h.state is HealthState.FAILING
    assert {"NO_CONFIRMED_STOP", "ADVERSE_EXCURSION_DEEP", "SPREAD_ABNORMAL"} <= set(h.reasons)


def test_every_reason_emitted_has_a_description():
    h = TradeHealthEngine().assess(_inputs(has_confirmed_stop=False))
    assert all(r in HEALTH_REASONS for r in h.reasons)
    assert h.body()["reason_detail"]


def test_health_reads_no_model_output():
    """INV-FAIL-001: the protective path must not be reachable from a model,
    which is guaranteed by it importing nothing from the cognition package."""
    from vati.lifecycle import trade_health
    assert not any(n.startswith("vati.cognition") for n in _imported_names(trade_health))


def test_health_is_ledgered_against_the_position():
    led = Ledger(":memory:")
    TradeHealthEngine(ledger=led).assess(_inputs())
    assert led.count(EventKind.TRADE_HEALTH) == 1
    assert [e.correlation_id for e in led.iter(EventKind.TRADE_HEALTH)] == ["t1"]
