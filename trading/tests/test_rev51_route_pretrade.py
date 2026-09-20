"""TRD-REV51-104 route/quantisation registry, 105 pre-trade control layer.

Both are live-affecting, so the tests lean on real RiskDecisions from the real
RiskAuthority rather than on stand-ins: a control layer that only works
against a mock is not a control layer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import NOW, intent, snapshot
from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.execution.pretrade import (
    FAT_FINGER_MULTIPLE,
    MIN_ORDERS_FOR_FAT_FINGER,
    PRETRADE_REASONS,
    MarketReference,
    PreTradeConfigError,
    PreTradeControls,
    Verdict,
)
from vati.execution.route_registry import (
    QuantisationRefused,
    RouteRegistry,
    RouteState,
    RouteUnresolved,
    quantise_stop,
    quantise_volume,
)
from vati.risk import Decision, Direction, RiskAuthority, SymbolContract

D = Decimal
NOW_MS = NOW * 1000


def _contract(**over) -> SymbolContract:
    base = dict(symbol="EURUSD", venue="mt5", base_currency="EUR", quote_currency="USD",
                account_currency="USD", contract_size=D("100000"), tick_size=D("0.00001"),
                tick_value=D("1"), volume_min=D("0.01"), volume_step=D("0.01"),
                volume_max=D("100"), min_stop_distance=D("0.00020"))
    base.update(over)
    return SymbolContract(**base)


def _registry(contract=None, **kw) -> RouteRegistry:
    r = RouteRegistry(**kw)
    r.refresh(account_alias="fx_primary", adapter_id="mt5",
              contracts={"EURUSD": contract or _contract()}, now_ms=NOW_MS)
    return r


# ---------------------------------------------------------------- 104 routing
def test_a_refreshed_symbol_resolves():
    route = _registry().resolve("fx_primary", "EURUSD", now_ms=NOW_MS + 10)
    assert route.state is RouteState.RESOLVED and route.venue == "mt5"


def test_an_unknown_symbol_is_unresolved_not_assumed():
    with pytest.raises(RouteUnresolved):
        _registry().resolve("fx_primary", "GBPUSD", now_ms=NOW_MS)


def test_a_contract_older_than_the_refresh_window_is_stale():
    """A lot step from last week is a guess."""
    reg = _registry(max_age_ms=1_000)
    assert reg.state_of("fx_primary", "EURUSD", now_ms=NOW_MS + 5_000) is RouteState.STALE
    with pytest.raises(RouteUnresolved):
        reg.resolve("fx_primary", "EURUSD", now_ms=NOW_MS + 5_000)


def test_close_only_and_disabled_venues_do_not_resolve():
    for mode, state in (("CLOSE_ONLY", RouteState.CLOSE_ONLY), ("DISABLED", RouteState.DISABLED)):
        reg = _registry(_contract(trade_mode=mode))
        assert reg.state_of("fx_primary", "EURUSD", now_ms=NOW_MS) is state
        with pytest.raises(RouteUnresolved):
            reg.resolve("fx_primary", "EURUSD", now_ms=NOW_MS)


def test_a_one_sided_trade_mode_refuses_the_wrong_direction():
    reg = _registry(_contract(trade_mode="LONG_ONLY"))
    reg.resolve("fx_primary", "EURUSD", now_ms=NOW_MS, direction=Direction.LONG)
    with pytest.raises(RouteUnresolved) as e:
        reg.resolve("fx_primary", "EURUSD", now_ms=NOW_MS, direction=Direction.SHORT)
    assert "does not permit" in str(e.value)


def test_an_operator_disable_takes_effect_immediately():
    reg = _registry()
    reg.disable("fx_primary", "EURUSD")
    assert reg.state_of("fx_primary", "EURUSD", now_ms=NOW_MS) is RouteState.DISABLED


def test_volume_rounds_down_never_up():
    """Rounding up places more risk than was approved, which is what a second
    sizer looks like in practice."""
    qty, shortfall = quantise_volume(_contract(), D("0.137"))
    assert qty == D("0.13") and shortfall == D("0.007")


def test_a_size_below_the_venue_minimum_is_refused_not_rounded_up():
    with pytest.raises(QuantisationRefused) as e:
        quantise_volume(_contract(), D("0.004"))
    assert "cannot express the approved size" in str(e.value)


def test_volume_is_capped_at_the_venue_maximum():
    qty, _ = quantise_volume(_contract(volume_max=D("1")), D("5"))
    assert qty == D("1")


def test_a_long_stop_rounds_up_toward_entry():
    """Rounding a stop away from entry is stop widening by arithmetic."""
    c = _contract()
    got = quantise_stop(c, entry=D("1.10000"), stop=D("1.090003"), direction=Direction.LONG)
    assert got >= D("1.090003")


def test_a_short_stop_rounds_down_toward_entry():
    c = _contract()
    got = quantise_stop(c, entry=D("1.10000"), stop=D("1.110007"), direction=Direction.SHORT)
    assert got <= D("1.110007")


def test_quantising_never_widens_the_stop_distance():
    c = _contract()
    for raw in ("1.090001", "1.090004", "1.090009", "1.089999"):
        got = quantise_stop(c, entry=D("1.10000"), stop=D(raw), direction=Direction.LONG)
        assert abs(D("1.10000") - got) <= abs(D("1.10000") - D(raw)) + c.tick_size


def test_a_stop_inside_the_venue_minimum_is_refused_rather_than_widened():
    reg = _registry()
    route = reg.resolve("fx_primary", "EURUSD", now_ms=NOW_MS)
    with pytest.raises(QuantisationRefused) as e:
        reg.quantise(route, quantity=D("0.1"), entry=D("1.10000"),
                     stop=D("1.09995"), direction=Direction.LONG)
    assert "widening it is not available" in str(e.value)


def test_routes_are_ledgered_on_refresh():
    led = Ledger(":memory:")
    RouteRegistry(ledger=led).refresh(account_alias="a", adapter_id="mt5",
                                      contracts={"EURUSD": _contract()}, now_ms=NOW_MS)
    assert led.count(EventKind.ROUTE_REGISTRY) == 1


def test_the_report_names_what_is_unusable():
    reg = _registry(max_age_ms=1)
    r = reg.report(now_ms=NOW_MS + 10_000)
    assert r["unusable"] == ["fx_primary/EURUSD"]


# --------------------------------------------------------------- 105 controls
def _approved(mandate, contract, **intent_over):
    auth = RiskAuthority(mandate)
    i = intent(**intent_over)
    d = auth.evaluate(i, snapshot(contract))
    assert d.decision in (Decision.APPROVED, Decision.REDUCED), d
    return i, d


@pytest.fixture()
def controls():
    return PreTradeControls(routes=_registry())


def test_a_sound_approved_intent_passes(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    r = controls.check(intent=i, decision=d, mark=MarketReference(D("1.10010"), 100),
                       now_ms=NOW_MS)
    assert r.passed and r.quantised.quantity > 0


def test_a_rejected_decision_never_reaches_a_route(controls, mandate, eurusd):
    auth = RiskAuthority(mandate)
    i = intent(stop=None)
    d = auth.evaluate(i, snapshot(eurusd))
    assert d.decision is Decision.REJECTED
    r = controls.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "DECISION_NOT_APPROVED"
    assert "ROUTE_UNRESOLVED" not in r.checks_run


def test_a_decision_for_another_intent_is_refused(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    other = intent(trade_intent_id="ti-other", idempotency_key="idem-other")
    r = controls.check(intent=other, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "DECISION_INTENT_MISMATCH"


def test_a_tampered_decision_is_caught_before_any_heuristic(controls, mandate, eurusd):
    """A fat-finger check that fired on a tampered decision would hide the
    tampering."""
    i, d = _approved(mandate, eurusd)
    forged = type(d)(**{**d.__dict__, "approved_size": D("99")})
    r = controls.check(intent=i, decision=forged, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "DECISION_SEAL_INVALID"
    assert r.checks_run[-1] == "DECISION_SEAL_INVALID"


def test_a_replayed_idempotency_key_is_refused(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    controls.note_sent(account_alias=i.account_alias, idempotency_key=i.idempotency_key,
                       quantity=D("0.1"), now_ms=NOW_MS)
    r = controls.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "IDEMPOTENCY_REPLAY"


def test_an_unresolved_route_is_a_rejection_not_a_warning(mandate, eurusd):
    c = PreTradeControls(routes=RouteRegistry())
    i, d = _approved(mandate, eurusd)
    r = c.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "ROUTE_UNRESOLVED"


def test_a_venue_that_cannot_express_the_size_rejects(mandate, eurusd):
    c = PreTradeControls(routes=_registry(_contract(volume_min=D("50"), volume_step=D("50"))))
    i, d = _approved(mandate, eurusd)
    r = c.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "SIZE_NOT_EXPRESSIBLE"


def test_a_stale_mark_stops_the_order(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    r = controls.check(intent=i, decision=d,
                       mark=MarketReference(D("1.10010"), 600_000), now_ms=NOW_MS)
    assert r.reason_code == "MARK_STALE"


def test_an_entry_far_from_the_mark_is_refused(controls, mandate, eurusd):
    """The usual cause is a stale decision, and a stale decision filling at
    market is the most expensive ordinary bug in this kind of system."""
    i, d = _approved(mandate, eurusd)
    r = controls.check(intent=i, decision=d, mark=MarketReference(D("1.20000"), 100),
                       now_ms=NOW_MS)
    assert r.reason_code == "PRICE_OFF_MARKET"


def test_a_notional_cap_is_enforced(mandate, eurusd):
    c = PreTradeControls(routes=_registry(), max_notional=D("1"))
    i, d = _approved(mandate, eurusd)
    r = c.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "NOTIONAL_CAP"


def test_the_fat_finger_check_abstains_until_there_is_a_typical(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    for n in range(MIN_ORDERS_FOR_FAT_FINGER - 1):
        controls.note_sent(account_alias=i.account_alias, idempotency_key=f"k{n}",
                           quantity=D("0.01"), now_ms=NOW_MS)
    r = controls.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert "FAT_FINGER" not in r.checks_run and r.passed


def test_an_order_far_outside_the_recent_range_is_refused(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    for n in range(MIN_ORDERS_FOR_FAT_FINGER + 5):
        controls.note_sent(account_alias=i.account_alias, idempotency_key=f"k{n}",
                           quantity=D("0.001"), now_ms=NOW_MS)
    r = controls.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "FAT_FINGER"


def test_an_order_storm_is_rate_limited(mandate, eurusd):
    c = PreTradeControls(routes=_registry(), max_orders_per_window=2)
    i, d = _approved(mandate, eurusd)
    for n in range(2):
        c.note_sent(account_alias=i.account_alias, idempotency_key=f"k{n}",
                    quantity=D("0.1"), now_ms=NOW_MS)
    r = c.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.reason_code == "ORDER_RATE_LIMIT"


def test_the_rate_limit_window_rolls(mandate, eurusd):
    c = PreTradeControls(routes=_registry(), max_orders_per_window=1, order_window_ms=1_000)
    i, d = _approved(mandate, eurusd)
    c.note_sent(account_alias=i.account_alias, idempotency_key="k", quantity=D("0.1"),
                now_ms=NOW_MS)
    assert c.check(intent=i, decision=d, mark=None, now_ms=NOW_MS + 5_000).passed


def test_an_order_limit_of_zero_is_a_halt_and_must_be_said_so():
    with pytest.raises(PreTradeConfigError):
        PreTradeControls(routes=RouteRegistry(), max_orders_per_window=0)


def test_the_quantised_size_never_exceeds_the_approved_size(controls, mandate, eurusd):
    i, d = _approved(mandate, eurusd)
    r = controls.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.quantised.quantity <= d.approved_size


def test_the_layer_only_ever_refuses_or_rounds_down(controls, mandate, eurusd):
    """It validates; it never sizes."""
    i, d = _approved(mandate, eurusd)
    r = controls.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert r.verdict in (Verdict.PASS, Verdict.REJECT)
    assert r.quantised.quantity_shortfall >= 0


def test_every_reason_code_it_can_emit_is_documented():
    assert "OK" not in PRETRADE_REASONS
    assert all(isinstance(v, str) and v for v in PRETRADE_REASONS.values())


def test_results_are_ledgered_against_the_intent(mandate, eurusd):
    led = Ledger(":memory:")
    c = PreTradeControls(routes=_registry(), ledger=led)
    i, d = _approved(mandate, eurusd)
    c.check(intent=i, decision=d, mark=None, now_ms=NOW_MS)
    assert led.count(EventKind.PRETRADE_CONTROL) == 1
    assert [e.correlation_id for e in led.iter(EventKind.PRETRADE_CONTROL)] == ["ti-1"]
