"""Phase 9/10: execution templates, policy selection, exit research."""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal

import pytest

from vati.execution import policy as policy_mod
from vati.execution.policy import (
    EVIDENCE_ABSENT,
    EVIDENCE_SUFFICIENT,
    MIN_EVIDENCE_SAMPLE,
    ExecutionBucket,
    ExecutionPolicyEngine,
)
from vati.execution.policy_templates import (
    CERTIFIED_DEFAULT,
    DEFAULT_TEMPLATES,
    DO_NOT_EXECUTE,
    LIMIT_AT_TOUCH,
    MARKET_WITH_SLIPPAGE_CAP,
    PASSIVE,
    TEMPLATE_IDS,
    ExecutionTemplate,
    ExecutionTemplateError,
    template,
)
from vati.learning import exit_research as exit_mod
from vati.learning.exit_research import (
    CURRENT_POLICY,
    EXIT_POLICY_FAMILY,
    EXPANSIVE_POLICIES,
    FIXED_4R,
    LET_RUN_UNTIL_INVALIDATION,
    ExitPolicyResearchEngine,
    PostEntryPath,
)
from vati.market_data.bars import Bar
from vati.risk.contracts import Direction

BUCKET = ExecutionBucket("deriv", "fx", "EURUSD", "LONDON", "NORMAL", "NONE", "LONG")


# --- templates ------------------------------------------------------------

def test_every_template_is_bounded():
    for t in DEFAULT_TEMPLATES.values():
        assert t.max_slippage >= 0 and t.max_chase_ticks >= 0 and t.max_replace_count >= 0


def test_unknown_template_is_refused():
    with pytest.raises(ExecutionTemplateError, match="unknown template"):
        ExecutionTemplate("FREESTYLE", "1.0.0", ("MARKET",), 0, 0, 0, Decimal("0"))


def test_negative_bound_is_refused():
    with pytest.raises(ExecutionTemplateError, match="negative bound"):
        ExecutionTemplate(PASSIVE, "1.0.0", ("LIMIT",), -1, 0, 0, Decimal("0"))


def test_fallback_cannot_loop_to_itself():
    with pytest.raises(ExecutionTemplateError, match="loops to itself"):
        ExecutionTemplate(PASSIVE, "1.0.0", ("LIMIT",), 0, 0, 0, Decimal("0"),
                          fallback_template_id=PASSIVE)


def test_do_not_execute_allows_no_entry_type():
    assert template(DO_NOT_EXECUTE).allowed_entry_types == ()


def test_certified_default_is_what_the_router_does_today():
    assert CERTIFIED_DEFAULT == LIMIT_AT_TOUCH
    assert template(CERTIFIED_DEFAULT).allowed_entry_types == ("LIMIT",)


# --- selection ------------------------------------------------------------

def test_no_evidence_falls_back_to_the_certified_default():
    d = ExecutionPolicyEngine().select(candidate_id="c", bucket=BUCKET)
    assert d.template_id == CERTIFIED_DEFAULT and d.evidence_state == EVIDENCE_ABSENT


def test_thin_evidence_still_falls_back():
    e = ExecutionPolicyEngine()
    for _ in range(MIN_EVIDENCE_SAMPLE - 1):
        e.observe(BUCKET, PASSIVE, filled=True, shortfall=Decimal("0"))
    assert e.select(candidate_id="c", bucket=BUCKET).template_id == CERTIFIED_DEFAULT


def test_non_fill_cost_can_beat_the_half_a_spread_heuristic():
    """A passive order that never fills is not free."""
    e = ExecutionPolicyEngine()
    for i in range(MIN_EVIDENCE_SAMPLE + 10):
        # Passive: cheap when it fills, but fills half the time.
        e.observe(BUCKET, PASSIVE, filled=(i % 2 == 0), shortfall=Decimal("0.00001"),
                  non_fill_cost=Decimal("0.00030"))
        # Limit at touch: always fills, slightly worse price.
        e.observe(BUCKET, LIMIT_AT_TOUCH, filled=True, shortfall=Decimal("0.00008"))
    d = e.select(candidate_id="c", bucket=BUCKET)
    assert d.template_id == LIMIT_AT_TOUCH
    assert d.evidence_state == EVIDENCE_SUFFICIENT


def test_passive_wins_when_it_actually_fills():
    e = ExecutionPolicyEngine()
    for _ in range(MIN_EVIDENCE_SAMPLE + 10):
        e.observe(BUCKET, PASSIVE, filled=True, shortfall=Decimal("0.00001"))
        e.observe(BUCKET, LIMIT_AT_TOUCH, filled=True, shortfall=Decimal("0.00008"))
    assert e.select(candidate_id="c", bucket=BUCKET).template_id == PASSIVE


def test_blackout_cancels_regardless_of_evidence():
    e = ExecutionPolicyEngine()
    for _ in range(100):
        e.observe(BUCKET, PASSIVE, filled=True, shortfall=Decimal("0"))
    d = e.select(candidate_id="c", bucket=BUCKET, event_state="PRE_BLACKOUT")
    assert d.template_id == DO_NOT_EXECUTE


def test_selection_only_ever_returns_a_registered_template():
    e = ExecutionPolicyEngine()
    for _ in range(MIN_EVIDENCE_SAMPLE + 1):
        e.observe(BUCKET, PASSIVE, filled=True, shortfall=Decimal("0"))
    assert e.select(candidate_id="c", bucket=BUCKET).template_id in TEMPLATE_IDS


def test_decision_maps_to_a_concrete_entry_type_for_the_router():
    d = ExecutionPolicyEngine().select(candidate_id="c", bucket=BUCKET)
    assert d.entry_type in ("LIMIT", "MARKET", "PASSIVE_LIMIT")


def test_decision_is_sealed_and_deterministic():
    e = ExecutionPolicyEngine()
    a = e.select(candidate_id="c", bucket=BUCKET)
    b = e.select(candidate_id="c", bucket=BUCKET)
    assert a.decision_hash == b.decision_hash and a.decision_hash


def test_engine_cannot_create_a_trade():
    """It decides how, never whether."""
    for name in ("approve", "size", "create_intent", "submit", "execute"):
        assert not hasattr(ExecutionPolicyEngine, name)


def test_engine_does_not_import_the_router():
    tree = ast.parse(inspect.getsource(policy_mod))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "vati.execution.router" not in mods


# --- exit research --------------------------------------------------------

def _path(pid, moves, *, direction=Direction.LONG):
    bars, px = [], Decimal("1.1000")
    for i, m in enumerate(moves):
        nxt = px + Decimal(str(m))
        bars.append(Bar("EURUSD", i * 60_000, (i + 1) * 60_000, px, max(px, nxt),
                        min(px, nxt), nxt, Decimal("10"), 5, Decimal("0.0001")))
        px = nxt
    return PostEntryPath(pid, "S", "EURUSD", "BULL", "LONDON", direction,
                         Decimal("1.1000"), Decimal("1.0950"), tuple(bars), Decimal("0.0050"))


RUNNERS = [_path(f"w{i}", [0.002] * 12) for i in range(8)]
LOSERS = [_path(f"l{i}", [-0.002, -0.004]) for i in range(4)]
MIXED = RUNNERS + LOSERS


def test_family_contains_expansive_members():
    """Without these the search can only ever recommend trading less."""
    assert EXPANSIVE_POLICIES <= set(EXIT_POLICY_FAMILY)
    assert LET_RUN_UNTIL_INVALIDATION in EXIT_POLICY_FAMILY
    assert FIXED_4R in EXIT_POLICY_FAMILY


def test_unregistered_policy_is_refused():
    with pytest.raises(ValueError, match="unregistered"):
        ExitPolicyResearchEngine().evaluate(MIXED, "MY_SPECIAL_EXIT")


def test_every_path_is_replayed_not_only_winners():
    e = ExitPolicyResearchEngine()
    assert e.evaluate(MIXED, CURRENT_POLICY).episodes == len(MIXED)
    assert e.evaluate(MIXED, CURRENT_POLICY).win_rate < Decimal("1")


def test_search_can_find_that_the_incumbent_exits_too_early():
    """The direction of improvement that a conservative-only family cannot find."""
    best = ExitPolicyResearchEngine().search(MIXED, strategy_id="S")[0]
    assert best.delta_mean_r > 0


def test_mfe_distribution_uses_all_paths_including_losers():
    d = ExitPolicyResearchEngine().mfe_mae_distribution(MIXED)
    assert d["mae_r_p10"] < 0, "losers are in the sample"
    assert d["mfe_r_p50"] > 0


def test_stop_is_applied_before_target_within_a_bar():
    """Within one bar the order is unknown; assuming the good one inflates everything."""
    whipsaw = [_path("x", [-0.010, 0.030])]
    r = ExitPolicyResearchEngine().evaluate(whipsaw, CURRENT_POLICY)
    assert r.mean_r < 0


def test_candidate_is_research_state_and_sealed():
    c = ExitPolicyResearchEngine().search(MIXED, strategy_id="S")[0]
    assert c.state == "RESEARCH" and c.candidate_hash


def test_research_engine_cannot_touch_live_protection():
    tree = ast.parse(inspect.getsource(exit_mod))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("protection" in m for m in mods)
    for name in ("register", "tighten", "apply", "on_mark"):
        assert not hasattr(ExitPolicyResearchEngine, name)


def test_give_back_from_mfe_is_measured():
    r = ExitPolicyResearchEngine().evaluate(RUNNERS, CURRENT_POLICY)
    assert r.give_back_from_mfe_r >= 0
