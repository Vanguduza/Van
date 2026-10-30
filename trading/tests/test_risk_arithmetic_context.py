"""Caller arithmetic settings cannot change the signed risk ceiling."""
from decimal import Decimal, DefaultContext, localcontext, ROUND_DOWN, ROUND_UP
from contextlib import contextmanager
from fractions import Fraction
from dataclasses import replace

import pytest

from conftest import intent, snapshot
from vati.core.decimal_context import native_decimal_context
from vati.risk.authority import RiskAuthority, Decision
from vati.risk.contracts import OpenPosition, Direction
from vati.risk.heat import position_risk, open_stop_risk, currency_leg_exposure
from vati.risk.sizing import Multipliers, size_stop_contract


@contextmanager
def hostile_profile(target):
    """Exercise every ambient Decimal field and restore the shared default."""
    def fingerprint(context):
        return (context.prec, context.rounding, context.Emin, context.Emax,
                context.capitals, context.clamp, dict(context.traps), dict(context.flags))

    with localcontext() as caller:
        context = caller if target == 'current' else DefaultContext
        saved = context.copy()
        try:
            context.prec = 1
            context.rounding = ROUND_UP
            context.Emin = -2
            context.Emax = 2
            context.capitals = 0
            context.clamp = 1
            context.clear_flags()
            for signal in context.traps:
                context.traps[signal] = True
            before = fingerprint(context)
            yield
            assert fingerprint(context) == before, 'native calculation mutated ambient arithmetic'
        finally:
            for name in ('prec', 'rounding', 'Emin', 'Emax', 'capitals', 'clamp'):
                setattr(context, name, getattr(saved, name))
            context.traps = saved.traps
            context.flags = saved.flags


@pytest.mark.parametrize('rounding', [ROUND_DOWN, ROUND_UP])
def test_portfolio_loss_and_leg_reports_do_not_inherit_caller_rounding(rounding):
    position = OpenPosition('GBPUSD', Direction.LONG, Decimal('1'), Decimal('1'),
                            Decimal('9999'), 'GBP', 'USD', has_broker_side_stop=True)
    with localcontext() as context:
        context.prec = 1; context.rounding = rounding
        assert position_risk(position) == Decimal('9999')
        assert open_stop_risk([position], Decimal('100000')) == Decimal('0.09999')
        assert currency_leg_exposure([position], Decimal('100000')) == {
            'GBP': Decimal('0.09999'), 'USD': Decimal('0.09999')}
        assert context.prec == 1 and context.rounding == rounding


@pytest.mark.parametrize('rounding', [ROUND_DOWN, ROUND_UP])
def test_native_sizing_keeps_exact_budget_and_venue_round_down(eurusd, rounding):
    with localcontext() as context:
        context.prec = 1; context.rounding = rounding
        sized = size_stop_contract(equity=Decimal('10000'), allowed_risk_pct=Decimal('0.004'),
            entry=Decimal('1.10010'), stop=Decimal('1.09790'), direction=Direction.LONG,
            contract=eurusd, multipliers=Multipliers())
        actual_loss = Fraction(sized.size) * (Fraction(Decimal('1.10010')) - Fraction(Decimal('1.09790'))) * Fraction(eurusd.tick_value) / Fraction(eurusd.tick_size)
        assert actual_loss <= Fraction(40), 'approved native quantity exceeds its original exact risk budget'
        assert sized.size == Decimal('0.18')
        assert sized.risk_amount == Decimal('39.6')
        assert context.prec == 1 and context.rounding == rounding


@pytest.mark.parametrize('rounding', [ROUND_DOWN, ROUND_UP])
def test_bounded_multiplier_product_preserves_original_joint_parameters(rounding):
    with localcontext() as context:
        context.prec = 1; context.rounding = rounding
        assert Multipliers(regime=Decimal('0.9'), confidence=Decimal('0.9')).product() == Decimal('0.81')


def test_real_authority_cannot_admit_over_heat_by_lowering_callers_precision(eurusd, mandate):
    existing = OpenPosition('GBPUSD', Direction.LONG, Decimal('1'), Decimal('0.001499'),
                            Decimal('100000'), 'GBP', 'USD', has_broker_side_stop=True)
    facts = snapshot(eurusd, open_positions=(existing,))
    request = intent()
    with localcontext(native_decimal_context()):
        reference = RiskAuthority(mandate).evaluate_safe(request, facts)
    assert reference.decision is Decision.REJECTED and reference.reason_code == 'PORTFOLIO_HEAT'
    with localcontext() as context:
        context.prec = 1; context.rounding = ROUND_DOWN
        actual = RiskAuthority(mandate).evaluate_safe(request, facts)
        assert actual.decision is Decision.REJECTED
        assert actual.reason_code == reference.reason_code


def test_normal_context_positive_control_still_produces_bound_native_approval(eurusd, mandate):
    from vati.risk.serde import intent_binding_hash, mandate_binding_hash
    request = intent(); facts = snapshot(eurusd)
    with localcontext(native_decimal_context()):
        decision = RiskAuthority(mandate).evaluate_safe(request, facts)
    assert decision.decision is Decision.APPROVED
    assert decision.approved_size == Decimal('0.18')
    assert decision.approved_risk_pct == Decimal('0.00396')
    assert decision.intent_hash == intent_binding_hash(request)
    assert decision.mandate_hash == mandate_binding_hash(mandate)


def test_nonterminating_tick_conversion_preserves_exact_original_loss(eurusd):
    contract = replace(eurusd, tick_size=Decimal('3'), tick_value=Decimal('1'),
                       volume_min=Decimal('1'), volume_step=Decimal('1'))
    sized = size_stop_contract(equity=Decimal('100'), allowed_risk_pct=Decimal('0.01'),
        entry=Decimal('6'), stop=Decimal('3'), direction=Direction.LONG,
        contract=contract, multipliers=Multipliers())
    assert sized.size == Decimal('1')
    assert sized.risk_amount == Decimal('1')
    assert sized.risk_pct == Decimal('0.01')


def test_rounding_a_reporting_ratio_cannot_hide_any_excess_over_signed_heat(eurusd, mandate):
    contract = replace(eurusd, tick_value=Decimal('5e-102'))
    positions = tuple(OpenPosition('GBPUSD', side, Decimal('1'), Decimal('0.000750075'),
        Decimal('100000'), 'GBP', 'USD', has_broker_side_stop=True)
        for side in (Direction.LONG, Direction.SHORT))
    facts = snapshot(contract, equity=Decimal('10001'), balance=Decimal('10001'),
        peak_equity=Decimal('10001'), day_start_equity=Decimal('10001'),
        week_start_equity=Decimal('10001'), open_positions=positions)
    # Existing gross heat equals the signed ceiling exactly. Opposing currency
    # legs cancel, but gross loss does not. Any positive new loss must refuse.
    original_loss = sum((Fraction(p.lots) * Fraction(p.stop_distance)
                         * Fraction(p.value_per_price_unit_per_lot) for p in positions), Fraction())
    assert original_loss / Fraction(facts.equity) == Fraction(mandate.max_open_stop_risk)
    with localcontext(native_decimal_context()):
        result = RiskAuthority(mandate).evaluate_safe(intent(), facts)
    assert result.decision is Decision.REJECTED
    assert result.reason_code == 'PORTFOLIO_HEAT'


def test_new_position_heat_uses_original_tick_terms_not_rounded_value_per_price(eurusd, mandate):
    contract = replace(eurusd, tick_size=Decimal('3'), tick_value=Decimal('1'))
    positions = tuple(OpenPosition('GBPUSD', side, Decimal('1'), Decimal('0.000550075'),
        Decimal('100000'), 'GBP', 'USD', has_broker_side_stop=True)
        for side in (Direction.LONG, Direction.SHORT))
    positions += (OpenPosition('AUDNZD', Direction.LONG, Decimal('1'), Decimal('1e-100'),
                             Decimal('1'), 'AUD', 'NZD', has_broker_side_stop=True),)
    facts = snapshot(contract, equity=Decimal('10001'), balance=Decimal('10001'),
        peak_equity=Decimal('10001'), day_start_equity=Decimal('10001'),
        week_start_equity=Decimal('10001'), open_positions=positions)
    request = intent(entry=Decimal('6'), stop=Decimal('3'))
    with localcontext(native_decimal_context()):
        sized = size_stop_contract(equity=facts.equity, allowed_risk_pct=request.requested_risk_pct,
            entry=request.entry, stop=request.stop, direction=request.direction,
            contract=contract, multipliers=Multipliers())
        result = RiskAuthority(mandate).evaluate_safe(request, facts)
    assert sized.size == Decimal('40')
    existing = sum((Fraction(p.lots) * Fraction(p.stop_distance)
                    * Fraction(p.value_per_price_unit_per_lot) for p in positions), Fraction())
    actual_new_loss = Fraction(sized.size) * 3 * Fraction(contract.tick_value) / Fraction(contract.tick_size)
    assert (existing + actual_new_loss) / Fraction(facts.equity) > Fraction(mandate.max_open_stop_risk)
    assert result.decision is Decision.REJECTED
    assert result.reason_code == 'PORTFOLIO_HEAT'


@pytest.mark.parametrize('target', ['current', 'default'])
@pytest.mark.parametrize('over_limit', [False, True])
def test_signed_decision_and_hash_ignore_traps_exponents_clamp_and_defaults(eurusd, mandate, target, over_limit):
    position = OpenPosition('GBPUSD', Direction.LONG, Decimal('1'), Decimal('0.001499'),
                            Decimal('100000'), 'GBP', 'USD', has_broker_side_stop=True)
    request = intent()
    facts = snapshot(eurusd, open_positions=(position,) if over_limit else ())
    with localcontext(native_decimal_context()):
        reference = RiskAuthority(mandate).evaluate_safe(request, facts)
    assert reference.reason_code == ('PORTFOLIO_HEAT' if over_limit else 'OK')
    with hostile_profile(target):
        actual = RiskAuthority(mandate).evaluate_safe(request, facts)
        assert actual == reference


@pytest.mark.parametrize('target', ['current', 'default'])
@pytest.mark.parametrize('model', ['stop', 'stake', 'illiquid'])
def test_each_native_loss_model_preserves_exact_budget_under_hostile_profile(eurusd, target, model):
    from vati.risk.contracts import LossModel
    from vati.risk.sizing import size_stake_contract, size_illiquid_equity
    common = dict(equity=Decimal('10000'), allowed_risk_pct=Decimal('0.004'),
                  multipliers=Multipliers(regime=Decimal('0.9'), confidence=Decimal('0.9')))
    if model == 'stop':
        size = size_stop_contract
        args = dict(common, contract=eurusd, direction=Direction.LONG,
                    entry=Decimal('1.10010'), stop=Decimal('1.09790'))
        loss_per_unit = Fraction(220)
    elif model == 'stake':
        size = size_stake_contract
        args = dict(common, contract=replace(eurusd, loss_model=LossModel.FULL_STAKE), requested_stake=None)
        loss_per_unit = Fraction(1)
    else:
        size = size_illiquid_equity
        args = dict(common, contract=replace(eurusd, loss_model=LossModel.ILLIQUID_EQUITY,
                    board_lot=Decimal('1'), adv_20d=Decimal('100000'), liquidity_haircut=Decimal('0.1')),
                    entry=Decimal('10'), stop=Decimal('9'))
        loss_per_unit = Fraction(2)
    with localcontext(native_decimal_context()):
        reference = size(**args)
    with hostile_profile(target):
        actual = size(**args)
        assert actual == reference
        assert Fraction(actual.size) * loss_per_unit <= Fraction(40) * Fraction(81, 100)
        assert Fraction(actual.risk_amount) == Fraction(actual.size) * loss_per_unit


@pytest.mark.parametrize('target', ['current', 'default'])
def test_drawdown_tier_and_cash_margin_bounds_ignore_hostile_profile(mandate, target):
    from vati.risk.governor import drawdown_verdict
    from vati.risk.margin import cash_margin_bounds
    args = (Decimal('10000'), Decimal('9800'), mandate.drawdown_tiers)
    with localcontext(native_decimal_context()):
        expected_tier = drawdown_verdict(*args)
    with hostile_profile(target):
        assert drawdown_verdict(*args) == expected_tier
        assert cash_margin_bounds(Decimal('10000'), Decimal('4000'), Decimal('99999'), Decimal('99999')) == (
            Decimal('6000'), Decimal('250'))


def test_cost_permission_compares_original_cost_beyond_reporting_precision(eurusd, mandate):
    cost = Decimal('0.001' + '0' * 100 + '1')
    request = intent(expected_gross_move_pct=Decimal('0.002'))
    assert Fraction(request.expected_gross_move_pct) < Fraction(cost) * 2
    result = RiskAuthority(mandate).evaluate_safe(request, snapshot(replace(eurusd, round_trip_cost_pct=cost)))
    assert result.decision is Decision.REJECTED
    assert result.reason_code == 'EDGE_BELOW_COST'
