"""TRD-REV51-116 execution style selector, 117 conformal interval engine."""

from __future__ import annotations

from decimal import Decimal

import pytest

from vati.core.events import EventKind
from vati.core.ledger import Ledger
from vati.execution.policy import ExecutionBucket, ExecutionPolicyEngine
from vati.execution.policy_templates import (
    DEFAULT_TEMPLATES,
    DO_NOT_EXECUTE,
    MARKET_WITH_SLIPPAGE_CAP,
    PASSIVE,
    template,
)
from vati.execution.route_registry import RouteRegistry
from vati.execution.style_selector import (
    MAX_SLICES,
    ExecutionStyleSelector,
    LiquidityView,
    StyleRefused,
    Urgency,
)
from vati.risk.conformal import (
    ConformalAdmissionGate,
    ConformalAdmissionPolicy,
    ConformalEngine,
    InsufficientCalibration,
    Residual,
    min_calibration_size,
)
from vati.risk import Decision, RiskAuthority, TradingMandate
from vati.risk.contracts import SymbolContract
from conftest import NOW, intent, mandate_dict, snapshot

D = Decimal


def _contract(**over) -> SymbolContract:
    base = dict(symbol="EURUSD", venue="mt5", base_currency="EUR", quote_currency="USD",
                account_currency="USD", contract_size=D("100000"), tick_size=D("0.00001"),
                tick_value=D("1"), volume_min=D("0.01"), volume_step=D("0.01"),
                volume_max=D("100"), min_stop_distance=D("0.00020"))
    base.update(over)
    return SymbolContract(**base)


def _route(contract=None):
    reg = RouteRegistry()
    reg.refresh(account_alias="a", adapter_id="mt5",
                contracts={"EURUSD": contract or _contract()}, now_ms=0)
    return reg.resolve("a", "EURUSD", now_ms=1)


def _policy(template_id=None):
    b = ExecutionBucket("mt5", "a", "EURUSD", "LONDON", "NORMAL", "NONE", "LONG")
    d = ExecutionPolicyEngine().select(candidate_id="c1", bucket=b)
    if template_id:
        d = type(d)(**{**d.__dict__, "template_id": template_id})
    return d


def _select(**over):
    kw = dict(trade_intent_id="t1", policy_decision=_policy(), route=_route(),
              quantity=D("0.50"), liquidity=LiquidityView(), now_ms=1)
    kw.update(over)
    return ExecutionStyleSelector().select(**kw)


# -------------------------------------------------------------------- 116
def test_a_selected_style_is_sealed_and_inside_its_template():
    s = _select()
    assert s.seal_ok()
    assert s.within(template(s.template_id))


def test_the_selector_does_not_second_guess_the_template_choice():
    d = _policy()
    assert _select(policy_decision=d).template_id == d.template_id


def test_a_do_not_execute_policy_produces_no_style():
    with pytest.raises(StyleRefused) as e:
        _select(policy_decision=_policy(DO_NOT_EXECUTE))
    assert "refused this order" in str(e.value)


@pytest.mark.parametrize("template_id", sorted(t for t in DEFAULT_TEMPLATES if t != DO_NOT_EXECUTE))
def test_no_template_can_be_escaped(template_id):
    """_bounded is the one function that has to be right, so every template
    gets exercised against it."""
    s = _select(policy_decision=_policy(template_id))
    t = template(template_id)
    assert s.entry_type in t.allowed_entry_types
    assert s.max_slippage <= t.max_slippage
    assert s.max_wait_ms <= t.max_wait_ms


def test_size_within_the_participation_cap_is_worked_in_one():
    s = _select(quantity=D("0.10"), liquidity=LiquidityView(displayed_size=D("10")))
    assert s.slices == 1 and s.slice_quantity == D("0.10")


def test_size_beyond_the_cap_is_sliced_and_the_total_is_preserved():
    s = _select(quantity=D("1.00"), liquidity=LiquidityView(displayed_size=D("0.5")))
    assert s.slices > 1
    assert s.total_quantity == D("1.00")


def test_slicing_is_bounded_because_more_slices_start_signalling():
    s = _select(quantity=D("90"), liquidity=LiquidityView(displayed_size=D("0.04")))
    assert s.slices <= MAX_SLICES


def test_the_slice_count_comes_down_until_the_lot_step_can_express_it():
    s = _select(quantity=D("0.03"), liquidity=LiquidityView(displayed_size=D("0.01")),
                route=_route(_contract(volume_step=D("0.01"), volume_min=D("0.01"))))
    assert s.slice_quantity >= D("0.01")
    assert s.total_quantity == D("0.03")


def test_a_size_the_venue_cannot_express_at_all_is_refused():
    with pytest.raises(StyleRefused):
        _select(quantity=D("0.004"))


def test_no_view_of_depth_is_not_a_licence_to_assume_it_is_deep():
    s = _select(quantity=D("5"), liquidity=LiquidityView())
    assert s.slices == 1 and "no displayed depth" in s.reason


def test_an_urgent_exit_is_worked_in_one_and_does_not_wait():
    s = _select(quantity=D("1.00"), liquidity=LiquidityView(displayed_size=D("0.1")),
                urgency=Urgency.IMMEDIATE)
    assert s.slices == 1 and s.max_wait_ms == 0


def test_elevated_urgency_halves_the_wait_and_never_exceeds_it():
    t = template(_policy().template_id)
    s = _select(urgency=Urgency.ELEVATED)
    assert s.max_wait_ms <= t.max_wait_ms // 2


def test_a_wide_spread_narrows_the_cap_rather_than_widening_it():
    """A wide spread is a reason to tolerate less, not more: the measured
    cost of crossing has gone up."""
    normal = _select(policy_decision=_policy(MARKET_WITH_SLIPPAGE_CAP))
    wide = _select(policy_decision=_policy(MARKET_WITH_SLIPPAGE_CAP),
                   liquidity=LiquidityView(spread=D("0.0010"), typical_spread=D("0.0002")))
    assert wide.max_slippage < normal.max_slippage


def test_urgency_never_widens_the_slippage_cap():
    t = template(MARKET_WITH_SLIPPAGE_CAP)
    for urgency in Urgency:
        s = _select(policy_decision=_policy(MARKET_WITH_SLIPPAGE_CAP), urgency=urgency)
        assert s.max_slippage <= t.max_slippage


def test_a_passive_only_template_is_never_given_a_market_order():
    s = _select(policy_decision=_policy(PASSIVE), urgency=Urgency.IMMEDIATE)
    assert s.entry_type == "PASSIVE_LIMIT"


def test_an_out_of_range_participation_cap_is_refused():
    with pytest.raises(StyleRefused):
        ExecutionStyleSelector(participation_cap=D("1.5"))


def test_styles_are_ledgered_against_the_intent():
    led = Ledger(":memory:")
    ExecutionStyleSelector(ledger=led).select(
        trade_intent_id="t9", policy_decision=_policy(), route=_route(),
        quantity=D("0.5"), liquidity=LiquidityView(), now_ms=3)
    assert led.count(EventKind.EXECUTION_STYLE) == 1
    assert [e.correlation_id for e in led.iter(EventKind.EXECUTION_STYLE)] == ["t9"]


def test_the_selector_does_not_send_anything():
    """INV-EXEC-001 as a fact about the module's imports."""
    import ast
    import inspect

    from vati.execution import style_selector
    tree = ast.parse(inspect.getsource(style_selector))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(a.name for a in node.names)
    assert "VenueAdapter" not in names and "ExecutionRouter" not in names
    assert "vati.execution.router" not in names


# -------------------------------------------------------------------- 117
def _calibrated(n=20, alpha=D("0.10"), **kw) -> ConformalEngine:
    e = ConformalEngine(alpha=alpha, **kw)
    for i in range(n):
        e.observe("eurusd-h1", predicted=D("0"), actual=D(str(i % 10)), observed_ms=1_000 + i)
    return e


def test_ninety_percent_coverage_needs_nine_residuals():
    assert min_calibration_size(D("0.10")) == 9
    assert min_calibration_size(D("0.05")) == 19


def test_too_few_residuals_raise_rather_than_returning_a_narrow_interval():
    """A narrower interval from fewer points is exactly how a thin sample
    looks confident."""
    e = _calibrated(n=5)
    with pytest.raises(InsufficientCalibration) as ex:
        e.interval("eurusd-h1", point=D("1"))
    assert "needed for" in str(ex.value)


def test_an_interval_is_symmetric_around_the_point():
    iv = _calibrated().interval("eurusd-h1", point=D("100"))
    assert iv.upper - iv.point == iv.point - iv.lower


def test_a_wider_calibration_spread_gives_a_wider_interval():
    tight = ConformalEngine()
    wide = ConformalEngine()
    for i in range(20):
        tight.observe("b", predicted=D("0"), actual=D("1"), observed_ms=i)
        wide.observe("b", predicted=D("0"), actual=D(str(i)), observed_ms=i)
    assert wide.interval("b", point=D("0")).width > tight.interval("b", point=D("0")).width


def test_a_tighter_alpha_gives_a_wider_interval():
    e = _calibrated(n=100)
    assert (e.interval("eurusd-h1", point=D("0"), alpha=D("0.01")).width
            >= e.interval("eurusd-h1", point=D("0"), alpha=D("0.20")).width)


def test_stale_residuals_do_not_count_toward_calibration():
    e = ConformalEngine(max_calibration_age_ms=1_000)
    for i in range(20):
        e.observe("b", predicted=D("0"), actual=D("1"), observed_ms=i)
    assert e.calibration_size("b", now_ms=1_000_000) == 0
    with pytest.raises(InsufficientCalibration):
        e.interval("b", point=D("1"), now_ms=1_000_000)


def test_admission_is_about_the_bad_end_of_the_interval():
    iv = _calibrated().interval("eurusd-h1", point=D("10"))
    assert iv.admits(worst_tolerable=iv.lower)
    assert not iv.admits(worst_tolerable=iv.lower + D("1"))


def test_a_narrow_interval_does_not_license_more_size():
    """The engine returns evidence. Sizing belongs to the Risk Authority."""
    iv = _calibrated().interval("eurusd-h1", point=D("10"))
    assert set(dir(iv)) & {"approved_size", "size", "lots"} == set()


def test_coverage_is_reported_rather_than_asserted():
    e = _calibrated(n=100)
    iv = e.interval("eurusd-h1", point=D("5"))
    observations = [(D(str(i % 10)), iv) for i in range(100)]
    rep = e.coverage_report("eurusd-h1", observations)
    assert rep.observations == 100
    assert rep.realised is not None


def test_an_undercovering_bucket_is_named_as_such():
    e = ConformalEngine()
    for i in range(20):
        e.observe("b", predicted=D("0"), actual=D("0"), observed_ms=i)
    iv = e.interval("b", point=D("0"))            # zero-width: every residual was zero
    rep = e.coverage_report("b", [(D("50"), iv)] * 10)
    assert rep.realised == D("0") and rep.is_undercovering


def test_empty_observations_report_no_realised_coverage():
    rep = _calibrated().coverage_report("eurusd-h1", [])
    assert rep.realised is None and not rep.is_undercovering


def test_try_interval_is_the_tolerant_caller_s_door():
    assert _calibrated(n=3).try_interval("eurusd-h1", point=D("1")) is None
    assert _calibrated().try_interval("eurusd-h1", point=D("1")) is not None


def test_a_negative_residual_is_refused_because_scores_are_absolute():
    with pytest.raises(ValueError):
        Residual(D("-1"), 0)


def test_intervals_are_ledgered_per_bucket():
    led = Ledger(":memory:")
    e = _calibrated(ledger=led)
    e.interval("eurusd-h1", point=D("1"), now_ms=5_000)
    assert led.count(EventKind.CONFORMAL_INTERVAL) == 1


def test_the_same_calibration_gives_the_same_interval():
    a, b = _calibrated(), _calibrated()
    assert (a.interval("eurusd-h1", point=D("7")).digest
            == b.interval("eurusd-h1", point=D("7")).digest)



# --------------------------------------------------------- 117 authority hook
def _authority_with_conformal(eurusd, *, worst="0.005", calibrated=True):
    engine = ConformalEngine()
    if calibrated:
        now_ms = NOW * 1000
        for i in range(12):
            engine.add_residual(
                "FX-LONDON-BREAKOUT-04:EURUSD",
                Residual(D("0.001"), now_ms - i),
            )
    gate = ConformalAdmissionGate(
        engine,
        {
            "FX-LONDON-BREAKOUT-04": ConformalAdmissionPolicy(
                strategy_id="FX-LONDON-BREAKOUT-04",
                bucket="{strategy_id}:{symbol}",
                worst_tolerable=D(worst),
            )
        },
    )
    return RiskAuthority(
        TradingMandate.from_mapping(mandate_dict()),
        conformal_gate=gate,
    )


def test_risk_authority_rejects_when_required_conformal_evidence_is_missing(eurusd):
    authority = _authority_with_conformal(eurusd, calibrated=False)
    d = authority.evaluate(
        intent(expected_gross_move_pct=D("0.01")),
        snapshot(eurusd),
    )
    assert d.decision is Decision.REJECTED
    assert d.reason_code == "CONFORMAL_EVIDENCE_UNAVAILABLE"


def test_risk_authority_admits_only_when_worst_conformal_bound_survives(eurusd):
    authority = _authority_with_conformal(eurusd, worst="0.005")
    d = authority.evaluate(
        intent(expected_gross_move_pct=D("0.01")),
        snapshot(eurusd),
    )
    assert d.decision in (Decision.APPROVED, Decision.REDUCED)


def test_risk_authority_conformal_gate_can_only_reject_not_increase_size(eurusd):
    baseline = RiskAuthority(TradingMandate.from_mapping(mandate_dict())).evaluate(
        intent(expected_gross_move_pct=D("0.01")),
        snapshot(eurusd),
    )
    gated = _authority_with_conformal(eurusd, worst="0.0095").evaluate(
        intent(expected_gross_move_pct=D("0.01")),
        snapshot(eurusd),
    )
    assert gated.decision is Decision.REJECTED
    assert gated.reason_code == "CONFORMAL_WORST_CASE"
    assert gated.approved_size <= baseline.approved_size
