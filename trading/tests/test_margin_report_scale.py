"""Native report spelling and exact permission boundaries remain separate."""
from decimal import Decimal, localcontext, ROUND_UP
from fractions import Fraction
from dataclasses import replace

import pytest

from conftest import intent, snapshot
from vati.risk.arithmetic import decimal
from vati.risk.authority import RiskAuthority, Decision
from vati.risk.margin import cash_margin_bounds, exact_cash_margin_bounds


@pytest.mark.parametrize('equity,used,free,expected', [
    ('10000.0', '1000.0', '9250.5', '9000.0'),
    ('1E+4', '1E+3', '9250.5', '9E+3'),
    ('10000.0', '1000.0', '9000.000', '9000.000'),
    ('10000.00', '1000.0', '9250.5', '9000.00'),
])
def test_original_subtraction_scale_and_native_free_bound_spelling(equity, used, free, expected):
    with localcontext() as caller:
        caller.prec = 1
        caller.rounding = ROUND_UP
        actual, _ = cash_margin_bounds(Decimal(equity), Decimal(used), Decimal(free), Decimal('1025.05'))
        assert str(actual) == expected
        exact, _ = exact_cash_margin_bounds(Decimal(equity), Decimal(used), Decimal(free), Decimal('1025.05'))
        assert exact == Fraction(Decimal(expected))


@pytest.mark.parametrize('value,exponent', [(Fraction(1, 3), -2), (Fraction(1, 100), 0), (Fraction(1), True)])
def test_declared_report_exponent_cannot_round_or_coerce_original_value(value, exponent):
    with pytest.raises(ValueError):
        decimal(value, exponent=exponent)


@pytest.mark.parametrize('equity,reason', [
    ('200.' + '0' * 100 + '1', 'OK'),
    ('200', 'MARGIN_FLOOR'),
    ('199.' + '9' * 100, 'MARGIN_FLOOR'),
    ('100', 'MARGIN_CALL'),
])
def test_real_authority_uses_original_margin_ratio_not_rounded_report(eurusd, mandate, equity, reason):
    equity = Decimal(equity)
    contract = replace(eurusd, volume_min=Decimal('0.0001'), volume_step=Decimal('0.0001'))
    facts = snapshot(contract, equity=equity, balance=equity, peak_equity=equity,
        day_start_equity=equity, week_start_equity=equity, used_margin=Decimal('100'),
        free_margin=Decimal('1000'), margin_level_pct=Decimal('1000'))
    result = RiskAuthority(mandate).evaluate_safe(intent(), facts)
    assert result.reason_code == reason
    assert result.decision is (Decision.APPROVED if reason == 'OK' else Decision.REJECTED)
