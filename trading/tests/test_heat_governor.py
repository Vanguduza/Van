from __future__ import annotations

from decimal import Decimal

import pytest

from vati.risk import (
    Direction,
    DrawdownTier,
    KillSwitch,
    KillSwitchTrigger,
    OpenPosition,
    currency_leg_exposure,
    drawdown_verdict,
    open_stop_risk,
)

VPPU = Decimal("100000")


def pos(symbol, base, quote, direction, lots="0.10", stop="0.00100", protected=True):
    return OpenPosition(symbol, direction, Decimal(lots), Decimal(stop), VPPU, base, quote, has_broker_side_stop=protected)


def test_usd_leg_stacks_across_pairs():
    # EURUSD long (short USD) + USDJPY short (short USD): each 10 USD risk → USD leg 20 USD = 0.2% of 10k
    positions = (pos("EURUSD", "EUR", "USD", Direction.LONG), pos("USDJPY", "USD", "JPY", Direction.SHORT))
    legs = currency_leg_exposure(positions, Decimal("10000"))
    assert legs["USD"] == Decimal("0.002")
    assert legs["EUR"] == Decimal("0.001") and legs["JPY"] == Decimal("0.001")
    assert open_stop_risk(positions, Decimal("10000")) == Decimal("0.002")


def test_offsetting_legs_net():
    positions = (pos("EURUSD", "EUR", "USD", Direction.LONG), pos("GBPUSD", "GBP", "USD", Direction.SHORT))
    legs = currency_leg_exposure(positions, Decimal("10000"))
    assert legs["USD"] == Decimal("0")


def test_unprotected_position_is_infinite_risk():
    positions = (pos("EURUSD", "EUR", "USD", Direction.LONG, protected=False),)
    assert not open_stop_risk(positions, Decimal("10000")).is_finite()
    assert not currency_leg_exposure(positions, Decimal("10000"))["*"].is_finite()


def test_drawdown_tiers():
    tiers = (DrawdownTier(Decimal("0.02"), Decimal("0.75")), DrawdownTier(Decimal("0.04"), Decimal("0.40"), True), DrawdownTier(Decimal("0.06"), Decimal("0")))
    assert drawdown_verdict(Decimal("100"), Decimal("99"), tiers).multiplier == Decimal("1")
    v = drawdown_verdict(Decimal("100"), Decimal("97"), tiers)
    assert v.multiplier == Decimal("0.75") and not v.top_tier_only
    v = drawdown_verdict(Decimal("100"), Decimal("95"), tiers)
    assert v.multiplier == Decimal("0.40") and v.top_tier_only and not v.suspended
    v = drawdown_verdict(Decimal("100"), Decimal("93"), tiers)
    assert v.suspended and v.top_tier_only
    assert drawdown_verdict(Decimal("0"), Decimal("1"), tiers).suspended


def test_kill_switch_latches_and_requires_owner_to_clear():
    """P0-TRADE-001 — this used to pass with owner_signature_ref="sig:owner"."""
    from conftest_owner_authority import OwnerAuthorityHarness

    owner = OwnerAuthorityHarness()
    ks = KillSwitch()
    assert not ks.halted
    ks.trip(KillSwitchTrigger.STALE_DATA, 1)
    assert ks.halted

    for rejected, why in [
        ("", "nothing at all"),
        ("sig:owner", "a string that looks like a reference"),
        (owner.token(act="owner-halt", subject="s-1", issued_at_unix=1), "authority for a different act"),
        (owner.token(act="kill-switch-clear", subject="s-2", issued_at_unix=1), "authority for another session"),
        (owner.stranger_token(act="kill-switch-clear", subject="s-1", issued_at_unix=1), "a key this host does not trust"),
    ]:
        with pytest.raises(PermissionError):
            ks.clear(KillSwitchTrigger.STALE_DATA, 2, owner_signature_ref=rejected,
                     authority=owner.verifier, subject="s-1")
        assert ks.halted, f"the kill switch cleared on {why}"

    good = owner.token(act="kill-switch-clear", subject="s-1", issued_at_unix=1)
    ks.clear(KillSwitchTrigger.STALE_DATA, 2, owner_signature_ref=good,
             authority=owner.verifier, subject="s-1")
    assert not ks.halted and len(ks.history) == 2
    assert "owner-authority:" in ks.history[-1][1]

    # Single use: the token is in the history now, in the clear.
    ks.trip(KillSwitchTrigger.STALE_DATA, 3)
    with pytest.raises(PermissionError):
        ks.clear(KillSwitchTrigger.STALE_DATA, 4, owner_signature_ref=good,
                 authority=owner.verifier, subject="s-1")
    assert ks.halted
