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
    """P0-TRADE-001 — "signed" used to mean "the field is not empty"."""
    for refused, why in [
        ("", "an empty field"),
        ("sig:owner-device:abc123", "the exact string every suite used to pass"),
        ("van-oa1.not-real.not-real", "something shaped like a token"),
    ]:
        with pytest.raises(MandateError, match="not owner-signed"):
            TradingMandate.from_mapping(mandate_dict(owner_signature_ref=refused)), why


def test_a_mandate_signature_does_not_admit_a_later_version():
    """The version is in the subject, so widening the limits needs a new signature."""
    from conftest import owner_authority

    base = mandate_dict()
    tampered = {**base, "version": "1.0.1", "max_risk_per_trade": "0.5000"}
    with pytest.raises(MandateError, match="not owner-signed"):
        TradingMandate.from_mapping(tampered)

    # ...and the owner can of course sign the new version.
    tampered["owner_signature_ref"] = owner_authority().token(
        act="mandate-admit",
        subject=f"{tampered['mandate_id']}:{tampered['version']}",
        issued_at_unix=int(tampered["signed_at_unix"]),
        lifetime_seconds=int(tampered["expires_at_unix"]) - int(tampered["signed_at_unix"]),
    )
    # It is still refused, but now by the risk ceiling rather than by the signature,
    # which is the point: the two checks are independent.
    with pytest.raises(MandateError):
        TradingMandate.from_mapping(tampered)


def test_a_mandate_signed_for_another_mandate_is_refused():
    from conftest import owner_authority

    base = mandate_dict()
    stolen = {**base, "owner_signature_ref": owner_authority().token(
        act="mandate-admit", subject="some-other-mandate:1.0.0",
        issued_at_unix=int(base["signed_at_unix"]),
        lifetime_seconds=int(base["expires_at_unix"]) - int(base["signed_at_unix"]),
    )}
    with pytest.raises(MandateError, match="not owner-signed"):
        TradingMandate.from_mapping(stolen)


def test_a_halt_token_does_not_admit_a_mandate():
    """Acts are not interchangeable. The old refs were, because they meant nothing."""
    from conftest import owner_authority

    base = mandate_dict()
    wrong_act = {**base, "owner_signature_ref": owner_authority().token(
        act="owner-halt", subject=f"{base['mandate_id']}:{base['version']}",
        issued_at_unix=int(base["signed_at_unix"]),
    )}
    with pytest.raises(MandateError, match="not owner-signed"):
        TradingMandate.from_mapping(wrong_act)


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
