"""Drawdown evidence keeps independent currency/percentage peaks and cents.

Pure synthetic source fixtures; no trading, promotion or economic admission.
"""
from decimal import Decimal as D, localcontext, Inexact, ROUND_DOWN
from fractions import Fraction
from itertools import accumulate

import pytest

from vati.backtest.metrics import compute_metrics
from vati.validation.builder import build_strategy_validation_certificate
from vati.validation.certificates import GREEN


@pytest.mark.parametrize('start,pnls,amount,ratio', [
    ('100', ('-50', '950', '-100'), '100', '1/2'),
    ('100', ('-150', '1050', '-200'), '200', '3/2'),
    ('1e30', ('-.01',), '1/100', '1/100000000000000000000000000000000'),
    ('10', ('-1.001', '100', '-2.002'), '1001/500', '1001/10000'),
    ('100', ('100', '-20'), '20', '1/10'),
    ('100', ('10', '0', '-5', '0', '-5'), '10', '1/11'),
])
def test_known_paths_keep_the_worst_percentage_independent_of_currency(start, pnls, amount, ratio):
    values = tuple(D(x) for x in pnls)
    result = compute_metrics(values, (D(0),) * len(values), D(start))
    assert result.max_drawdown == float(Fraction(amount))
    assert result.max_drawdown_pct == float(Fraction(ratio))


@pytest.mark.parametrize('precision', [3, 28, 80])
def test_exact_equity_path_is_independent_of_caller_decimal_context(precision):
    start, values = D('1e30'), (D('-.01'), D('1.111'), D('-2.222'))
    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        result = compute_metrics(values, (D(-1), D(1), D(-2)), start)
    assert result.max_drawdown == 2.222
    assert result.max_drawdown_pct == float(Fraction(2222, 1000) / (Fraction(start) + Fraction(1101, 1000)))


def test_prefix_curve_oracle_and_scale_invariance():
    # Recompute every prefix independently, rather than sharing the streaming
    # peak implementation. All arithmetic stays exact until the legacy float.
    values = (D('-3.25'), D('10.1'), D('-8.03'), D('100.003'), D('-20.02'), D('-5.3'))
    start = D('10')
    curve = [Fraction(start), *accumulate((Fraction(x) for x in values), initial=Fraction(start))][1:]
    peaks = [max(curve[:index + 1]) for index in range(len(curve))]
    amount = max(peak - value for peak, value in zip(peaks, curve))
    ratio = max((peak - value) / peak for peak, value in zip(peaks, curve))
    for scale in (Fraction(1, 100), Fraction(1), Fraction(1000000000000000000000000000000)):
        scaled = [Fraction(x) * scale for x in values]
        result = compute_metrics(scaled, (D(0),) * len(values), Fraction(start) * scale)
        assert result.max_drawdown == float(amount * scale)
        assert result.max_drawdown_pct == float(ratio)


def test_actual_validation_producer_preserves_the_original_worst_drawdown():
    pnls = tuple(D(x) for x in ('-50', '950', '-100', '0', '0', '0', '0', '0'))
    certificate = build_strategy_validation_certificate(
        strategy_id='SOURCE_FIXTURE_ONLY', strategy_version='1', capsule_hash='fixture-capsule',
        data_manifest_hash='fixture-data', evidence_refs=('fixture-evidence',),
        feature_set_version='fixture-features', cost_model_revision='fixture-cost',
        pnls=pnls, r_multiples=tuple(D(x) for x in ('-.5', '9.5', '-1', '0', '0', '0', '0', '0')),
        start_equity=D(100), trial_returns_matrix=((.1, -.2, .3, .1, -.1, .2, .1, -.1),),
        walk_forward_windows=4, cost_stress_2x=GREEN, latency_slippage_stress=GREEN,
        parameter_perturbation_stability=GREEN, leakage_switch_result=GREEN)
    assert certificate.verify_seal()
    assert certificate.max_drawdown == .5
    assert certificate.certificate_id.startswith('svc_')
