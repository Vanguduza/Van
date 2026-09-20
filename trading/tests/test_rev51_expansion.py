"""TRD-REV51-108 scale policy, 109 expansion laboratory, 110 expansion engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.lifecycle.envelope import EnvelopeCalculator
from vati.lifecycle.expansion import (
    DECLINE_REASONS,
    EXPANSION_MODE,
    Mode,
    ProfitExpansionEngine,
)
from vati.lifecycle.family import FamilyMember, FamilyRegistry, MemberRole
from vati.lifecycle.preservation import ActionKind, PreservationAction
from vati.lifecycle.preservation import Urgency as PreservationUrgency
from vati.lifecycle.scale_policy import (
    CONSERVATIVE,
    NO_SCALING,
    PolicyError,
    ScalePolicy,
    ScalePolicyRegistry,
    policy_from_mapping,
)
from vati.lifecycle.trade_health import (
    HealthState,
    PositionHealthInputs,
    TradeHealthEngine,
)
from vati.research.expansion_lab import (
    MIN_FAMILIES_FOR_EVIDENCE,
    ExpansionLaboratory,
    FamilyReplay,
    PricePoint,
)
from vati.risk.contracts import Direction

D = Decimal


# ------------------------------------------------------------------ 108 policy
def test_an_unregistered_strategy_does_not_scale():
    """A strategy nobody has thought about scaling is one that does not."""
    assert ScalePolicyRegistry().policy_for("anything") is NO_SCALING
    assert not NO_SCALING.enabled


def test_scaling_is_off_unless_explicitly_enabled():
    assert ScalePolicy("p").enabled is False


def test_each_add_must_be_smaller_than_the_one_before():
    """A pyramid standing on its point: most exposure at the worst price."""
    with pytest.raises(PolicyError) as e:
        ScalePolicy("p", enabled=True, max_scale_ins=2,
                    scale_fractions=(D("0.25"), D("0.5")))
    assert "smaller than the one before" in str(e.value)


def test_more_permitted_adds_than_declared_sizes_is_refused():
    with pytest.raises(PolicyError) as e:
        ScalePolicy("p", enabled=True, max_scale_ins=3, scale_fractions=(D("0.5"),))
    assert "would be a default" in str(e.value)


def test_a_fraction_above_the_root_is_refused():
    with pytest.raises(PolicyError):
        ScalePolicy("p", enabled=True, max_scale_ins=1, scale_fractions=(D("1.5"),))


def test_fractions_run_out_rather_than_repeating():
    assert CONSERVATIVE.fraction_for(0) == D("0.5")
    assert CONSERVATIVE.fraction_for(1) == D("0.25")
    assert CONSERVATIVE.fraction_for(2) is None


def test_a_disabled_policy_offers_no_fraction_at_all():
    assert NO_SCALING.fraction_for(0) is None


def test_configuration_with_an_unknown_field_is_refused():
    """A silently ignored key is a policy the operator believes is in force."""
    with pytest.raises(PolicyError) as e:
        policy_from_mapping({"policy_id": "p", "max_pyramids": 4})
    assert "max_pyramids" in str(e.value)


def test_configuration_builds_a_usable_policy():
    p = policy_from_mapping({"policy_id": "custom", "enabled": True, "max_scale_ins": 1,
                             "scale_fractions": ["0.3"], "required_health": "healthy",
                             "min_progress_r": "2"})
    assert p.enabled and p.fraction_for(0) == D("0.3")
    assert p.required_health is HealthState.HEALTHY


def test_the_registry_reports_which_strategies_may_scale():
    reg = ScalePolicyRegistry()
    reg.register("FX-TREND-03", CONSERVATIVE)
    reg.register("FX-SCALP-01", NO_SCALING)
    assert reg.enabled_strategies() == ["FX-TREND-03"]


# ------------------------------------------------------------------ 110 engine
def _family(reg, *, qty="1", entry="1.1000", stop="1.0900"):
    return reg.open_family(family_id="f1", account_alias="acct", symbol="EURUSD",
                           direction=Direction.LONG,
                           root=FamilyMember("m1", MemberRole.ROOT, D(qty), D(entry), 0,
                                             trade_intent_id="ti-1", stop=D(stop)),
                           now_ms=0)


def _health(**over):
    base = dict(trade_intent_id="ti-1", symbol="EURUSD", direction=Direction.LONG,
                entry_price=D("1.1000"), current_price=D("1.1150"),
                original_stop=D("1.0900"), current_stop=D("1.1000"),
                has_confirmed_stop=True, opened_ms=0, now_ms=60_000,
                expected_horizon_ms=600_000, worst_price=D("1.0995"),
                best_price=D("1.1160"))
    base.update(over)
    return TradeHealthEngine().assess(PositionHealthInputs(**base))


def _quiet_preservation():
    return PreservationAction("f1", ActionKind.NONE, PreservationUrgency.ROUTINE, ())


def _evaluate(*, policy=CONSERVATIVE, mode=Mode.SHADOW, preservation=None, health=None,
              family=None, last_scale_ms=None, in_event_window=False, equity="1000000",
              secure_stop=True, ledger=None):
    reg = FamilyRegistry()
    fam = family or _family(reg)
    if secure_stop and (fam.current_stop is None or fam.current_stop < D("1.1000")):
        fam.tighten_stop(D("1.1000"))
    env = EnvelopeCalculator().compute(fam, mark=D("1.1150"),
                                       value_per_price_unit=D("100000"),
                                       equity=D(equity), now_ms=100)
    return ProfitExpansionEngine(mode=mode, ledger=ledger).evaluate(
        family=fam, strategy_id="FX-TREND-03", policy=policy,
        health=health or _health(), envelope=env,
        preservation=preservation or _quiet_preservation(),
        root_quantity=D("1"), last_scale_ms=last_scale_ms,
        in_event_window=in_event_window, now_ms=10_000_000)


def test_expansion_ships_in_shadow_mode():
    assert EXPANSION_MODE is Mode.SHADOW


def test_a_qualifying_family_produces_a_proposal_that_shadow_withholds():
    p = _evaluate()
    assert p.proposed and p.would_propose and not p.is_candidate
    assert p.scale_fraction == D("0.5")


def test_the_engine_states_a_requested_risk_and_stops_there():
    """It proposes; the Risk Authority sizes and remains free to refuse."""
    p = _evaluate()
    assert p.requested_risk_pct is not None
    assert not hasattr(p, "approved_size")


def test_preservation_having_anything_to_say_stands_the_proposal_down():
    """Weighing a threat and an opportunity in the same pass means sometimes
    picking the opportunity."""
    halt = PreservationAction("f1", ActionKind.HALT_NEW_RISK,
                              PreservationUrgency.PROMPT, ("HEALTH_IMPAIRED",))
    p = _evaluate(preservation=halt)
    assert not p.proposed and "PRESERVATION_ACTIVE" in p.decline_reasons


def test_a_disabled_policy_declines():
    p = _evaluate(policy=NO_SCALING)
    assert not p.proposed and "POLICY_DISABLED" in p.decline_reasons


def test_a_position_that_has_not_paid_for_itself_declines():
    p = _evaluate(health=_health(current_price=D("1.1020"), best_price=D("1.1025")))
    assert "PROGRESS_BELOW_MINIMUM" in p.decline_reasons


def test_anything_less_than_the_required_health_declines():
    p = _evaluate(health=_health(worst_price=D("1.0940")))
    assert "HEALTH_BELOW_REQUIREMENT" in p.decline_reasons


def test_an_unsecured_stop_declines():
    """An add before the stop is secured can turn a paid-for position back
    into a losing one on the original risk."""
    p = _evaluate(secure_stop=False, health=_health(current_stop=D("1.0900")))
    assert "STOP_NOT_AT_ENTRY" in p.decline_reasons


def test_the_cooldown_is_respected():
    p = _evaluate(last_scale_ms=10_000_000 - 60_000)
    assert "COOLDOWN_ACTIVE" in p.decline_reasons


def test_an_open_event_window_declines():
    p = _evaluate(in_event_window=True)
    assert "EVENT_WINDOW" in p.decline_reasons


def test_adds_run_out():
    reg = FamilyRegistry()
    fam = _family(reg)
    for i in range(2):
        reg.apply("f1", FamilyMember(f"s{i}", MemberRole.SCALE_IN, D("0.1"), D("1.11"), 10),
                  now_ms=10)
    p = _evaluate(family=fam)
    assert "SCALE_INS_EXHAUSTED" in p.decline_reasons


def test_open_risk_is_measured_from_the_mark_so_unrealised_gain_is_at_stake():
    """A breakeven stop protects the entry, not the gain above it."""
    p = _evaluate(equity="100000")
    assert "FAMILY_RISK_AT_CEILING" in p.decline_reasons


def test_a_family_already_at_the_policy_ceiling_declines():
    tight = ScalePolicy("tight", enabled=True, max_scale_ins=1,
                        scale_fractions=(D("0.5"),), max_family_risk_pct=D("0.0000001"))
    p = _evaluate(policy=tight)
    assert "FAMILY_RISK_AT_CEILING" in p.decline_reasons


def test_a_diverged_family_declines():
    reg = FamilyRegistry()
    fam = _family(reg)
    fam.tighten_stop(D("1.1000"))
    fam.reconcile(venue_quantity=D("5"), now_ms=5)
    p = _evaluate(family=fam)
    assert "FAMILY_NOT_OPEN" in p.decline_reasons


def test_every_decline_reason_is_named_and_described():
    p = _evaluate(policy=NO_SCALING, in_event_window=True)
    assert p.decline_reasons
    assert all(r in DECLINE_REASONS for r in p.decline_reasons)
    assert p.body()["decline_detail"]


def test_live_mode_makes_the_proposal_a_candidate():
    p = _evaluate(mode=Mode.LIVE)
    assert p.is_candidate and not p.would_propose


def test_proposals_are_ledgered_against_the_family():
    led = Ledger(":memory:")
    _evaluate(ledger=led)
    assert led.count(EventKind.EXPANSION_ACTION) == 1
    assert [e.correlation_id for e in led.iter(EventKind.EXPANSION_ACTION)] == ["f1"]


# ------------------------------------------------------------- 109 laboratory
def _replay(fid="f1", *, exit_price="1.1400", open_at_end=False, points=None):
    return FamilyReplay(
        family_id=fid, strategy_id="s", symbol="EURUSD", direction=Direction.LONG,
        root_quantity=D("1"), entry_price=D("1.1000"), original_stop=D("1.0900"),
        exit_price=D(exit_price), opened_ms=0, closed_ms=10 ** 7,
        path=points if points is not None else (
            PricePoint(3_600_001, D("1.1100"), D("1.0")),
            PricePoint(7_300_000, D("1.1200"), D("2.0")),
        ),
        was_open_at_sample_end=open_at_end)


def test_the_do_nothing_baseline_is_always_compared_against():
    out = ExpansionLaboratory([_replay()]).compare([CONSERVATIVE])
    assert [p["policy_id"] for p in out["policies"]] == ["NO_SCALING", "CONSERVATIVE"]


def test_a_policy_that_helped_shows_a_positive_delta():
    c = ExpansionLaboratory([_replay()]).replay_policy(CONSERVATIVE)
    assert c.outcomes[0].adds == 2 and c.outcomes[0].delta_r > 0


def test_a_policy_that_hurt_shows_a_negative_delta():
    losing = _replay(exit_price="1.1000")       # gave it all back
    c = ExpansionLaboratory([losing]).replay_policy(CONSERVATIVE)
    assert c.outcomes[0].delta_r < 0


def test_open_families_are_excluded_and_counted():
    """Winners run, so the open ones skew optimistic."""
    lab = ExpansionLaboratory([_replay("a"), _replay("b", open_at_end=True)])
    c = lab.replay_policy(CONSERVATIVE)
    assert c.families_excluded_open == 1 and len(c.outcomes) == 1


def test_adds_are_only_priced_at_marks_the_family_traded_through():
    c = ExpansionLaboratory([_replay(points=())]).replay_policy(CONSERVATIVE)
    assert c.outcomes[0].adds == 0
    assert c.outcomes[0].delta_r == D("0")


def test_the_cooldown_is_honoured_in_replay():
    close_together = _replay(points=(PricePoint(1_000, D("1.1100"), D("1.0")),
                                     PricePoint(2_000, D("1.1150"), D("1.5"))))
    c = ExpansionLaboratory([close_together]).replay_policy(CONSERVATIVE)
    assert c.outcomes[0].adds == 1


def test_a_small_sample_is_not_evidence():
    """Scaling results are dominated by a handful of large winners."""
    lab = ExpansionLaboratory([_replay(f"f{i}") for i in range(3)])
    assert not lab.replay_policy(CONSERVATIVE).has_evidence


def test_a_sufficient_sample_reports_evidence():
    lab = ExpansionLaboratory([_replay(f"f{i}") for i in range(MIN_FAMILIES_FOR_EVIDENCE)])
    assert lab.replay_policy(CONSERVATIVE).has_evidence


def test_the_worst_family_outcome_is_reported_beside_the_mean():
    """The mean is the number that makes every scaling policy look good."""
    lab = ExpansionLaboratory([_replay("win"), _replay("lose", exit_price="1.1000")])
    c = lab.replay_policy(CONSERVATIVE)
    assert c.worst_delta_r is not None and c.worst_delta_r < c.mean_delta_r


def test_the_comparison_states_its_assumptions_and_is_not_a_recommendation():
    body = ExpansionLaboratory([_replay()]).replay_policy(CONSERVATIVE).body()
    assert body["is_recommendation"] is False
    assert any("does not move the market" in a for a in body["assumptions"])


def test_a_thin_comparison_names_no_best_policy():
    out = ExpansionLaboratory([_replay()]).compare([CONSERVATIVE])
    assert out["best_by_total_delta"] is None


def test_the_comparison_digest_is_stable():
    lab = ExpansionLaboratory([_replay()])
    assert lab.replay_policy(CONSERVATIVE).digest == lab.replay_policy(CONSERVATIVE).digest
