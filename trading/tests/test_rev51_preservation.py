"""TRD-REV51-106 position families, 107 risk envelope, 111 preservation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.lifecycle.envelope import (
    MAX_PROTECTED_PROFIT_FRACTION,
    EnvelopeCalculator,
    GuaranteedExitCertificate,
    HaircutReason,
)
from vati.lifecycle.family import (
    FamilyError,
    FamilyMember,
    FamilyRegistry,
    FamilyState,
    MemberRole,
)
from vati.lifecycle.preservation import (
    ACCOUNT_HALT_WORST_CASE_PCT,
    PRESERVATION_REASONS,
    ActionKind,
    PreservationEngine,
    Urgency,
)
from vati.lifecycle.trade_health import PositionHealthInputs, TradeHealthEngine
from vati.risk.contracts import Direction

D = Decimal


def _registry(**kw) -> FamilyRegistry:
    return FamilyRegistry(**kw)


def _open(reg, *, direction=Direction.LONG, qty="2", price="1.10", stop="1.09"):
    return reg.open_family(family_id="f1", account_alias="acct", symbol="EURUSD",
                           direction=direction,
                           root=FamilyMember("m1", MemberRole.ROOT, D(qty), D(price), 0,
                                             trade_intent_id="ti-1", stop=D(stop)),
                           now_ms=0)


# ------------------------------------------------------------------ 106 family
def test_a_scale_in_joins_the_family_rather_than_starting_a_trade():
    """Three positions each individually within limits and jointly outside
    them is the specific failure this prevents."""
    reg = _registry()
    fam = _open(reg)
    reg.apply("f1", FamilyMember("m2", MemberRole.SCALE_IN, D("2"), D("1.12"), 10), now_ms=10)
    assert fam.net_quantity == D("4") and fam.scale_ins == 1
    assert len(reg.open_families(account_alias="acct")) == 1


def test_the_average_entry_is_weighted_not_chosen():
    reg = _registry()
    fam = _open(reg, qty="1", price="1.10")
    reg.apply("f1", FamilyMember("m2", MemberRole.SCALE_IN, D("3"), D("1.14"), 10), now_ms=10)
    assert fam.average_entry == D("1.13")


def test_a_partial_exit_realises_against_the_running_average():
    reg = _registry()
    fam = _open(reg, qty="2", price="1.10")
    reg.apply("f1", FamilyMember("m2", MemberRole.PARTIAL_EXIT, D("1"), D("1.13"), 20), now_ms=20)
    assert fam.realised_money == D("0.03")
    assert fam.net_quantity == D("1")


def test_a_short_family_realises_with_the_right_sign():
    reg = _registry()
    fam = _open(reg, direction=Direction.SHORT, qty="1", price="1.10", stop="1.11")
    reg.apply("f1", FamilyMember("m2", MemberRole.PARTIAL_EXIT, D("1"), D("1.08"), 20), now_ms=20)
    assert fam.realised_money == D("0.02")


def test_closing_more_than_is_held_is_refused():
    reg = _registry()
    _open(reg, qty="1")
    with pytest.raises(FamilyError):
        reg.apply("f1", FamilyMember("m2", MemberRole.FULL_EXIT, D("5"), D("1.11"), 20), now_ms=20)


def test_a_family_closes_when_its_net_quantity_reaches_zero():
    reg = _registry()
    fam = _open(reg, qty="1")
    reg.apply("f1", FamilyMember("m2", MemberRole.FULL_EXIT, D("1"), D("1.12"), 20), now_ms=20)
    assert fam.state is FamilyState.CLOSED and not fam.is_open


def test_a_closed_family_does_not_reopen():
    reg = _registry()
    _open(reg, qty="1")
    reg.apply("f1", FamilyMember("m2", MemberRole.FULL_EXIT, D("1"), D("1.12"), 20), now_ms=20)
    with pytest.raises(FamilyError) as e:
        reg.apply("f1", FamilyMember("m3", MemberRole.SCALE_IN, D("1"), D("1.13"), 30), now_ms=30)
    assert "a new position is a new family" in str(e.value)


def test_a_family_stop_moves_toward_the_position_and_never_away():
    reg = _registry()
    fam = _open(reg)
    fam.tighten_stop(D("1.095"))
    assert fam.current_stop == D("1.095")
    with pytest.raises(FamilyError) as e:
        fam.tighten_stop(D("1.08"))
    assert "stop widening is not available" in str(e.value)


def test_a_member_carrying_a_wider_stop_does_not_widen_the_family():
    reg = _registry()
    fam = _open(reg)
    reg.apply("f1", FamilyMember("m2", MemberRole.SCALE_IN, D("1"), D("1.12"), 10,
                                 stop=D("1.05")), now_ms=10)
    assert fam.current_stop == D("1.09")


def test_venue_disagreement_is_a_state_that_blocks_new_risk():
    reg = _registry()
    fam = _open(reg)
    assert reg.reconcile("f1", venue_quantity=D("1"), now_ms=30) is FamilyState.DIVERGED
    assert not fam.admits_new_risk
    assert reg.diverged() == [fam]


def test_agreement_clears_a_divergence():
    reg = _registry()
    fam = _open(reg)
    reg.reconcile("f1", venue_quantity=D("1"), now_ms=30)
    assert reg.reconcile("f1", venue_quantity=D("2"), now_ms=40) is FamilyState.OPEN
    assert fam.admits_new_risk


def test_a_family_is_found_from_any_of_its_intents():
    reg = _registry()
    fam = _open(reg)
    reg.apply("f1", FamilyMember("m2", MemberRole.SCALE_IN, D("1"), D("1.12"), 10,
                                 trade_intent_id="ti-2"), now_ms=10)
    assert reg.for_intent("ti-1") is fam and reg.for_intent("ti-2") is fam


def test_a_family_opens_with_a_root_member():
    reg = _registry()
    with pytest.raises(FamilyError):
        reg.open_family(family_id="fx", account_alias="a", symbol="S", direction=Direction.LONG,
                        root=FamilyMember("m", MemberRole.SCALE_IN, D("1"), D("1"), 0), now_ms=0)


def test_families_are_ledgered_on_every_change():
    led = Ledger(":memory:")
    reg = _registry(ledger=led)
    _open(reg)
    reg.apply("f1", FamilyMember("m2", MemberRole.SCALE_IN, D("1"), D("1.12"), 10), now_ms=10)
    assert led.count(EventKind.POSITION_FAMILY) == 2


# ---------------------------------------------------------------- 107 envelope
def _family_with_profit():
    reg = _registry()
    fam = _open(reg, qty="2", price="1.10", stop="1.09")
    reg.apply("f1", FamilyMember("m2", MemberRole.PARTIAL_EXIT, D("1"), D("1.13"), 20), now_ms=20)
    return fam


def _env(calc, fam, **over):
    kw = dict(mark=D("1.12"), value_per_price_unit=D("100000"), equity=D("10000"), now_ms=100)
    kw.update(over)
    return calc.compute(fam, **kw)


def test_banked_profit_is_worth_nothing_without_a_certificate():
    """INV-PPC-001. Profit is only a buffer if it survives the event that
    would consume it."""
    env = _env(EnvelopeCalculator(), _family_with_profit())
    assert env.realised_money > 0
    assert env.protected_profit_credit == D("0")
    assert env.haircut_reason is HaircutReason.NO_CERTIFICATE
    assert env.worst_case_loss == env.open_risk_money


def test_an_independent_certificate_credits_only_part_of_the_profit():
    """Guaranteed at the venue is not guaranteed against the venue."""
    calc = EnvelopeCalculator()
    fam = _family_with_profit()
    calc.certify(GuaranteedExitCertificate("c1", "f1", "broker", D("1.09"), 0, 10**9))
    env = _env(calc, fam)
    assert env.protected_profit_credit == env.realised_money * MAX_PROTECTED_PROFIT_FRACTION
    assert env.worst_case_loss < env.open_risk_money


def test_a_self_asserted_certificate_is_not_independent_evidence():
    calc = EnvelopeCalculator()
    fam = _family_with_profit()
    calc.certify(GuaranteedExitCertificate("c1", "f1", "vati", D("1.09"), 0, 10**9,
                                           self_asserted=True))
    env = _env(calc, fam)
    assert env.protected_profit_credit == D("0")
    assert env.haircut_reason is HaircutReason.CERTIFICATE_NOT_INDEPENDENT


def test_an_expired_certificate_gives_zero_not_its_last_value():
    calc = EnvelopeCalculator()
    fam = _family_with_profit()
    calc.certify(GuaranteedExitCertificate("c1", "f1", "broker", D("1.09"), 0, 50))
    env = _env(calc, fam, now_ms=10_000)
    assert env.protected_profit_credit == D("0")
    assert env.haircut_reason is HaircutReason.CERTIFICATE_EXPIRED


def test_a_diverged_family_earns_no_credit():
    calc = EnvelopeCalculator()
    fam = _family_with_profit()
    calc.certify(GuaranteedExitCertificate("c1", "f1", "broker", D("1.09"), 0, 10**9))
    fam.reconcile(venue_quantity=D("0"), now_ms=90)
    assert _env(calc, fam).haircut_reason is HaircutReason.FAMILY_DIVERGED


def test_a_loss_making_family_earns_no_credit():
    reg = _registry()
    fam = _open(reg, qty="2", price="1.10", stop="1.09")
    reg.apply("f1", FamilyMember("m2", MemberRole.PARTIAL_EXIT, D("1"), D("1.095"), 20), now_ms=20)
    assert _env(EnvelopeCalculator(), fam).haircut_reason is HaircutReason.NO_REALISED_PROFIT


def test_an_unknown_stop_is_unbounded_risk_not_zero_risk():
    reg = _registry()
    fam = reg.open_family(family_id="f1", account_alias="a", symbol="S",
                          direction=Direction.LONG,
                          root=FamilyMember("m1", MemberRole.ROOT, D("1"), D("1.10"), 0),
                          now_ms=0)
    env = _env(EnvelopeCalculator(), fam)
    assert not env.risk_is_known
    assert env.haircut_reason is HaircutReason.STOP_UNKNOWN


def test_open_risk_is_computed_at_the_family_level():
    env = _env(EnvelopeCalculator(), _family_with_profit())
    # one lot left, mark 1.12, stop 1.09, 100000 per price unit
    assert env.open_risk_money == D("0.03") * D("1") * D("100000")


def test_a_stop_already_through_the_mark_carries_no_further_risk():
    reg = _registry()
    fam = _open(reg, qty="1", price="1.10", stop="1.09")
    env = _env(EnvelopeCalculator(), fam, mark=D("1.085"))
    assert env.open_risk_money == D("0")


def test_the_portfolio_view_names_unknown_risk_rather_than_counting_it_as_zero():
    calc = EnvelopeCalculator()
    reg = _registry()
    known = _open(reg, qty="1")
    blind = reg.open_family(family_id="f2", account_alias="a", symbol="S",
                            direction=Direction.LONG,
                            root=FamilyMember("mx", MemberRole.ROOT, D("1"), D("1.1"), 0),
                            now_ms=0)
    out = calc.portfolio_worst_case([_env(calc, known), _env(calc, blind)])
    assert out["families_with_unknown_risk"] == ["f2"]
    assert out["risk_fully_known"] is False


def test_envelopes_are_ledgered_per_family():
    led = Ledger(":memory:")
    _env(EnvelopeCalculator(ledger=led), _family_with_profit())
    assert led.count(EventKind.POSITION_RISK_ENVELOPE) == 1


# ------------------------------------------------------------ 111 preservation
def _health(**over):
    base = dict(trade_intent_id="ti-1", symbol="EURUSD", direction=Direction.LONG,
                entry_price=D("1.1000"), current_price=D("1.1010"),
                original_stop=D("1.0900"), current_stop=D("1.0900"),
                has_confirmed_stop=True, opened_ms=0, now_ms=60_000,
                expected_horizon_ms=600_000, worst_price=D("1.0990"),
                best_price=D("1.1020"))
    base.update(over)
    return TradeHealthEngine().assess(PositionHealthInputs(**base))


def test_preservation_has_no_action_that_adds_exposure():
    """INV-RISK-001 as a type rather than a policy document."""
    assert {k.value for k in ActionKind} == {
        "NONE", "TIGHTEN_STOP", "PARTIAL_CLOSE", "FULL_CLOSE", "HALT_NEW_RISK"}


def test_a_healthy_family_needs_nothing_and_blocks_nothing():
    reg = _registry()
    fam = _open(reg)
    a = PreservationEngine().evaluate(family=fam, health=_health(),
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert a.kind is ActionKind.NONE and not a.blocks_new_risk


def test_an_unprotected_family_is_closed_immediately():
    """Waiting for a better price is how a bounded loss becomes unbounded."""
    reg = _registry()
    fam = _open(reg)
    a = PreservationEngine().evaluate(family=fam, health=_health(has_confirmed_stop=False),
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert a.kind is ActionKind.FULL_CLOSE and a.urgency is Urgency.IMMEDIATE
    assert "UNPROTECTED" in a.reasons


def test_an_invalidated_thesis_is_closed_immediately():
    reg = _registry()
    fam = _open(reg)
    a = PreservationEngine().evaluate(family=fam, health=_health(thesis_invalidated=True),
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert a.kind is ActionKind.FULL_CLOSE and "THESIS_INVALIDATED" in a.reasons


def test_a_diverged_family_is_closed_immediately():
    reg = _registry()
    fam = _open(reg)
    fam.reconcile(venue_quantity=D("9"), now_ms=1)
    a = PreservationEngine().evaluate(family=fam, health=_health(),
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert a.kind is ActionKind.FULL_CLOSE and "FAMILY_DIVERGED" in a.reasons


def test_reaching_one_r_moves_the_stop_to_the_entry():
    reg = _registry()
    fam = _open(reg, qty="1", price="1.1000", stop="1.0900")
    health = _health(best_price=D("1.1100"), current_price=D("1.1050"))
    a = PreservationEngine().evaluate(family=fam, health=health,
                                      envelope=_env(EnvelopeCalculator(), fam, mark=D("1.1050")),
                                      mark=D("1.1050"), now_ms=1)
    assert a.kind is ActionKind.TIGHTEN_STOP and a.new_stop == D("1.1000")
    assert "BREAKEVEN_REACHED" in a.reasons


def test_a_larger_excursion_trails_the_stop_further():
    reg = _registry()
    fam = _open(reg, qty="1", price="1.1000", stop="1.0900")
    health = _health(best_price=D("1.1300"), current_price=D("1.1250"))
    a = PreservationEngine().evaluate(family=fam, health=health,
                                      envelope=_env(EnvelopeCalculator(), fam, mark=D("1.1250")),
                                      mark=D("1.1250"), now_ms=1)
    assert a.kind is ActionKind.TIGHTEN_STOP and "TRAIL_ADVANCED" in a.reasons
    assert a.new_stop > D("1.1000")


def test_a_proposed_stop_is_never_looser_and_never_through_the_mark():
    reg = _registry()
    fam = _open(reg, qty="1", price="1.1000", stop="1.0900")
    fam.tighten_stop(D("1.1200"))
    health = _health(best_price=D("1.1100"), current_price=D("1.1050"))
    a = PreservationEngine().evaluate(family=fam, health=health,
                                      envelope=_env(EnvelopeCalculator(), fam, mark=D("1.1050")),
                                      mark=D("1.1050"), now_ms=1)
    assert a.new_stop is None


def test_handing_back_a_real_gain_takes_half_off():
    reg = _registry()
    fam = _open(reg, qty="2", price="1.1000", stop="1.0900")
    health = _health(best_price=D("1.1300"), current_price=D("1.1020"))
    a = PreservationEngine().evaluate(family=fam, health=health,
                                      envelope=_env(EnvelopeCalculator(), fam, mark=D("1.1020")),
                                      mark=D("1.1020"), now_ms=1)
    assert a.kind is ActionKind.PARTIAL_CLOSE and a.close_fraction == D("0.5")


def test_an_impaired_family_halts_new_risk_even_with_nothing_to_tighten():
    reg = _registry()
    fam = _open(reg, qty="1", price="1.1000", stop="1.0900")
    health = _health(worst_price=D("1.0920"))
    a = PreservationEngine().evaluate(family=fam, health=health,
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert a.kind is ActionKind.HALT_NEW_RISK and "HEALTH_IMPAIRED" in a.reasons


def test_an_unknown_family_risk_halts_new_risk():
    reg = _registry()
    fam = reg.open_family(family_id="f1", account_alias="a", symbol="S",
                          direction=Direction.LONG,
                          root=FamilyMember("m1", MemberRole.ROOT, D("1"), D("1.10"), 0),
                          now_ms=0)
    a = PreservationEngine().evaluate(family=fam, health=_health(),
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert a.kind is ActionKind.HALT_NEW_RISK and "RISK_UNKNOWN" in a.reasons


def test_a_high_account_worst_case_halts_new_risk_everywhere():
    calc = EnvelopeCalculator()
    reg = _registry()
    fam = _open(reg, qty="3", price="1.1000", stop="1.0900")
    env = _env(calc, fam, mark=D("1.1000"), equity=D("10000"))
    a = PreservationEngine().account_verdict([env], equity=D("10000"), now_ms=1)
    assert env.worst_case_pct >= ACCOUNT_HALT_WORST_CASE_PCT
    assert a.kind is ActionKind.HALT_NEW_RISK


def test_a_modest_account_worst_case_does_not_halt():
    calc = EnvelopeCalculator()
    reg = _registry()
    fam = _open(reg, qty="1", price="1.1000", stop="1.0990")
    a = PreservationEngine().account_verdict([_env(calc, fam, mark=D("1.1000"))],
                                             equity=D("10000"), now_ms=1)
    assert a.kind is ActionKind.NONE


def test_every_reason_emitted_has_a_description():
    reg = _registry()
    fam = _open(reg)
    a = PreservationEngine().evaluate(family=fam, health=_health(has_confirmed_stop=False),
                                      envelope=_env(EnvelopeCalculator(), fam),
                                      mark=D("1.101"), now_ms=1)
    assert all(r in PRESERVATION_REASONS for r in a.reasons)


def test_preservation_reads_no_model_output():
    """It has to work when every provider is down."""
    import ast
    import inspect

    from vati.lifecycle import preservation
    tree = ast.parse(inspect.getsource(preservation))
    modules = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(m.startswith("vati.cognition") for m in modules)


def test_actions_are_ledgered_but_no_action_is_not():
    led = Ledger(":memory:")
    reg = _registry()
    fam = _open(reg)
    eng = PreservationEngine(ledger=led)
    eng.evaluate(family=fam, health=_health(), envelope=_env(EnvelopeCalculator(), fam),
                 mark=D("1.101"), now_ms=1)
    assert led.count(EventKind.PRESERVATION_ACTION) == 0
    eng.evaluate(family=fam, health=_health(has_confirmed_stop=False),
                 envelope=_env(EnvelopeCalculator(), fam), mark=D("1.101"), now_ms=2)
    assert led.count(EventKind.PRESERVATION_ACTION) == 1
