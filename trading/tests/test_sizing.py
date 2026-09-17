from __future__ import annotations

from decimal import Decimal

import pytest

from vati.risk import Direction, Multipliers, SizingRejected, clamp_multiplier, size_stake_contract, size_stop_contract


def test_reference_sizing_eurusd(eurusd):
    # equity 10,000 × 0.40% = 40 USD risk; stop 22 pips = 0.00220 × 100,000/lot = 220 USD per lot → 0.1818 → 0.18 lots
    r = size_stop_contract(
        equity=Decimal("10000"), allowed_risk_pct=Decimal("0.0040"), entry=Decimal("1.10010"), stop=Decimal("1.09790"),
        direction=Direction.LONG, contract=eurusd, multipliers=Multipliers(),
    )
    assert r.size == Decimal("0.18")
    assert r.risk_amount == Decimal("39.6")
    assert r.risk_pct <= Decimal("0.0040")


def test_rounding_is_down_never_up(eurusd):
    r = size_stop_contract(
        equity=Decimal("10000"), allowed_risk_pct=Decimal("0.0040"), entry=Decimal("1.10010"), stop=Decimal("1.09790"),
        direction=Direction.LONG, contract=eurusd, multipliers=Multipliers(confidence=Decimal("0.999")),
    )
    assert r.size == Decimal("0.18") and r.risk_amount <= Decimal("40")


def test_below_venue_minimum_is_no_trade(eurusd):
    with pytest.raises(SizingRejected) as exc:
        size_stop_contract(
            equity=Decimal("100"), allowed_risk_pct=Decimal("0.0040"), entry=Decimal("1.10010"), stop=Decimal("1.09790"),
            direction=Direction.LONG, contract=eurusd, multipliers=Multipliers(),
        )
    assert exc.value.code == "SIZE_BELOW_VENUE_MIN"


def test_stop_on_wrong_side_and_too_tight(eurusd):
    with pytest.raises(SizingRejected) as exc:
        size_stop_contract(equity=Decimal("10000"), allowed_risk_pct=Decimal("0.004"), entry=Decimal("1.1"), stop=Decimal("1.2"),
                           direction=Direction.LONG, contract=eurusd, multipliers=Multipliers())
    assert exc.value.code == "STOP_WRONG_SIDE"
    with pytest.raises(SizingRejected) as exc:
        size_stop_contract(equity=Decimal("10000"), allowed_risk_pct=Decimal("0.004"), entry=Decimal("1.10010"), stop=Decimal("1.10000"),
                           direction=Direction.LONG, contract=eurusd, multipliers=Multipliers())
    assert exc.value.code == "STOP_TOO_TIGHT"


@pytest.mark.parametrize("raw,expected", [("1.5", "1"), ("-0.2", "0"), ("nan", "0"), ("inf", "0"), ("abc", "0"), ("0.37", "0.37")])
def test_multipliers_only_reduce(raw, expected):
    assert clamp_multiplier(raw) == Decimal(expected)


def test_multiplier_product_cannot_amplify(eurusd):
    amplified = Multipliers(regime=Decimal("3"), confidence=Decimal("2"), volatility=Decimal("5"))
    assert amplified.product() == Decimal("1")
    base = size_stop_contract(equity=Decimal("10000"), allowed_risk_pct=Decimal("0.004"), entry=Decimal("1.10010"), stop=Decimal("1.09790"),
                              direction=Direction.LONG, contract=eurusd, multipliers=Multipliers())
    amp = size_stop_contract(equity=Decimal("10000"), allowed_risk_pct=Decimal("0.004"), entry=Decimal("1.10010"), stop=Decimal("1.09790"),
                             direction=Direction.LONG, contract=eurusd, multipliers=amplified)
    assert amp.size == base.size


def test_volume_max_cap(eurusd):
    r = size_stop_contract(equity=Decimal("100000000"), allowed_risk_pct=Decimal("0.004"), entry=Decimal("1.10010"), stop=Decimal("1.09790"),
                           direction=Direction.LONG, contract=eurusd, multipliers=Multipliers())
    assert r.size == eurusd.volume_max


def test_stake_sizing_deriv(deriv_synthetic):
    r = size_stake_contract(equity=Decimal("10000"), allowed_risk_pct=Decimal("0.0040"), requested_stake=None,
                            contract=deriv_synthetic, multipliers=Multipliers(confidence=Decimal("0.5")))
    assert r.size == Decimal("20.00") and r.risk_amount == Decimal("20.00")
    with pytest.raises(SizingRejected) as exc:
        size_stake_contract(equity=Decimal("50"), allowed_risk_pct=Decimal("0.0040"), requested_stake=None,
                            contract=deriv_synthetic, multipliers=Multipliers())
    assert exc.value.code == "STAKE_BELOW_VENUE_MIN"


def test_loss_model_mismatch(eurusd, deriv_synthetic):
    with pytest.raises(SizingRejected):
        size_stake_contract(equity=Decimal("1"), allowed_risk_pct=Decimal("0.01"), requested_stake=None, contract=eurusd, multipliers=Multipliers())
    with pytest.raises(SizingRejected):
        size_stop_contract(equity=Decimal("1"), allowed_risk_pct=Decimal("0.01"), entry=Decimal("2"), stop=Decimal("1"),
                           direction=Direction.LONG, contract=deriv_synthetic, multipliers=Multipliers())
