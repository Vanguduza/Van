from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import mandate_dict
from vati.risk import HARD_FORBIDDEN_BEHAVIOURS, MandateError, PlatformCeilings, TradingMandate


def test_valid_mandate_loads(mandate):
    assert mandate.mode.value == "LIMITED_LIVE"
    assert "EURUSD" in mandate.instruments
    assert mandate.drawdown_tiers[-1].multiplier == Decimal("0")


def test_unsigned_mandate_rejected():
    with pytest.raises(MandateError, match="unsigned"):
        TradingMandate.from_mapping(mandate_dict(owner_signature_ref=""))


@pytest.mark.parametrize("behaviour", sorted(HARD_FORBIDDEN_BEHAVIOURS))
def test_mandate_cannot_omit_any_hard_forbidden_behaviour(behaviour):
    forbidden = sorted(HARD_FORBIDDEN_BEHAVIOURS - {behaviour})
    with pytest.raises(MandateError, match=behaviour):
        TradingMandate.from_mapping(mandate_dict(forbidden=forbidden))


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_risk_per_trade": "0.03", "max_open_stop_risk": "0.03"},
        {"max_open_stop_risk": "0.07"},
        {"max_daily_loss": "0.06"},
        {"max_weekly_drawdown": "0.11"},
        {"max_currency_leg_exposure": "0.05"},
    ],
)
def test_mandate_exceeding_platform_ceiling_rejected(overrides):
    with pytest.raises(MandateError, match="exceeds platform ceiling"):
        TradingMandate.from_mapping(mandate_dict(**overrides))


def test_ceiling_is_owner_policy_not_hardcode():
    wider = PlatformCeilings(max_risk_per_trade=Decimal("0.03"), max_open_stop_risk=Decimal("0.03"), policy_version="risk-policy/test")
    m = TradingMandate.from_mapping(mandate_dict(max_risk_per_trade="0.03", max_open_stop_risk="0.03"), ceilings=wider)
    assert m.max_risk_per_trade == Decimal("0.03")


def test_per_trade_cannot_exceed_open_heat():
    with pytest.raises(MandateError, match="cannot exceed max_open_stop_risk"):
        TradingMandate.from_mapping(mandate_dict(max_risk_per_trade="0.0150", max_open_stop_risk="0.0100"))


def test_tiers_must_end_in_suspension():
    tiers = [{"threshold": "0.02", "multiplier": "0.5"}]
    with pytest.raises(MandateError, match="suspending tier"):
        TradingMandate.from_mapping(mandate_dict(drawdown_tiers=tiers))


def test_invalid_mode_and_expiry():
    with pytest.raises(MandateError, match="invalid mode"):
        TradingMandate.from_mapping(mandate_dict(mode="YOLO"))
    with pytest.raises(MandateError, match="expires before"):
        TradingMandate.from_mapping(mandate_dict(expires_at_unix=1))


def test_fraction_bounds():
    with pytest.raises(MandateError, match="fraction"):
        TradingMandate.from_mapping(mandate_dict(max_daily_loss="0"))
    with pytest.raises(MandateError, match="not a decimal"):
        TradingMandate.from_mapping(mandate_dict(max_daily_loss="abc"))
