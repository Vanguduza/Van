"""Phase 4: a candidate cannot execute itself (TRD-ENH-030/031)."""

from __future__ import annotations

import dataclasses
import ast
import inspect
import textwrap
from decimal import Decimal

import pytest

from vati.arbiter import candidate as candidate_mod
from vati.arbiter import intent_factory as intent_mod
from vati.arbiter.candidate import (
    FORBIDDEN_CANDIDATE_FIELDS,
    CandidateOpportunity,
    make_candidate_id,
)
from vati.arbiter.intent_factory import IntentFactory, IntentFactoryError, resolve_targets
from vati.risk.contracts import Direction


def _cand(**kw) -> CandidateOpportunity:
    base = dict(
        candidate_id="cand_1", account_alias="fx_primary", venue="deriv", symbol="EURUSD",
        strategy_id="FX-TREND-PULLBACK-01", strategy_version="1.0.0", capsule_hash="cap",
        strategy_state="DEMO", generated_at_ms=1_000, valid_from_ms=1_000, valid_until_ms=61_000,
        mtf_state_hash="mtf", source_state_hashes=("s1",), feature_contract_hash="fc",
        direction=Direction.LONG, entry=Decimal("1.1000"), stop=Decimal("1.0950"),
        targets=(Decimal("1.1150"), Decimal("1.1300")), horizon="SWING",
        expected_gross_move_pct=Decimal("0.01"), cost_multiple=Decimal("3"),
    )
    base.update(kw)
    return CandidateOpportunity(**base).sealed()


# --- the weakness is structural ------------------------------------------

@pytest.mark.parametrize("field", FORBIDDEN_CANDIDATE_FIELDS)
def test_candidate_has_no_sizing_or_execution_field(field):
    assert field not in CandidateOpportunity.__dataclass_fields__


def _imported_modules(mod) -> set[str]:
    """Modules actually imported, from the AST — comments and docstrings ignored."""
    tree = ast.parse(inspect.getsource(mod))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_candidate_module_cannot_import_the_router():
    """A candidate must have no path to the order sender."""
    imported = _imported_modules(candidate_mod)
    assert not any("execution" in m for m in imported), sorted(imported)


def test_candidate_module_imports_nothing_that_can_send_an_order():
    banned = ("vati.execution.router", "vati.execution.base", "vati.execution")
    assert not (_imported_modules(candidate_mod) & set(banned))


def test_candidate_is_sealed_and_tamper_evident():
    c = _cand()
    assert c.candidate_hash
    tampered = dataclasses.replace(c, entry=Decimal("9.9"))
    assert tampered.candidate_hash == c.candidate_hash  # stale hash retained
    assert tampered.sealed().candidate_hash != c.candidate_hash


def test_candidate_id_is_deterministic_across_restart():
    a = make_candidate_id(account_alias="a", symbol="EURUSD", strategy_id="S", state_hash="h", as_of_ms=1)
    b = make_candidate_id(account_alias="a", symbol="EURUSD", strategy_id="S", state_hash="h", as_of_ms=1)
    c = make_candidate_id(account_alias="a", symbol="EURUSD", strategy_id="S", state_hash="h", as_of_ms=2)
    assert a == b and a != c


# --- freshness and supersession ------------------------------------------

def test_freshness_decays_from_one_to_zero():
    c = _cand()
    assert c.freshness(1_000) == Decimal("1.0000")
    assert c.freshness(31_000) == Decimal("0.5000")
    assert c.freshness(61_000) == Decimal("0.0000")
    assert c.freshness(99_000) == Decimal("0.0000")


def test_expired_candidate_is_not_fresh():
    c = _cand()
    assert c.fresh_at(60_999) and not c.fresh_at(61_000)


def test_supersession_key_identifies_the_same_setup():
    a = _cand(candidate_id="x", generated_at_ms=1)
    b = _cand(candidate_id="y", generated_at_ms=2)
    assert a.supersession_key == b.supersession_key
    assert _cand(entry=Decimal("1.2")).supersession_key != a.supersession_key


# --- target precedence (S2 / P1-TRADE-007) --------------------------------

def test_explicit_targets_are_used_verbatim():
    c = _cand()
    assert resolve_targets(c) == (Decimal("1.1150"), Decimal("1.1300"))


def test_expected_gross_move_is_never_consulted_when_targets_exist():
    """P1-TRADE-007: a scaled exit plan must not be replaced by one derived price."""
    rich = _cand(targets=(Decimal("1.1150"), Decimal("1.1300")), expected_gross_move_pct=Decimal("0.99"))
    poor = _cand(targets=(Decimal("1.1150"), Decimal("1.1300")), expected_gross_move_pct=Decimal("0.01"))
    assert resolve_targets(rich) == resolve_targets(poor)


def test_no_targets_falls_back_to_empty_not_a_derived_price():
    assert resolve_targets(_cand(targets=())) == ()


def test_resolve_targets_never_reads_expected_gross_move():
    """Mutation guard for `swap target precedence` (blueprint §48).

    AST-based, so a docstring mentioning the field cannot satisfy or break it.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(intent_mod.resolve_targets)))
    read = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "expected_gross_move_pct" not in read
    assert "targets" in read


# --- intent factory -------------------------------------------------------

def test_factory_produces_an_intent_with_the_allocated_risk():
    intent = IntentFactory().from_selected_candidate(
        _cand(), requested_risk_pct=Decimal("0.0075"), idempotency_seed="seed")
    assert intent.requested_risk_pct == Decimal("0.0075")
    assert intent.symbol == "EURUSD" and intent.decision_hash


def test_intent_is_deterministic_for_the_same_candidate_and_seed():
    f = IntentFactory()
    a = f.from_selected_candidate(_cand(), requested_risk_pct=Decimal("0.005"), idempotency_seed="s")
    b = f.from_selected_candidate(_cand(), requested_risk_pct=Decimal("0.005"), idempotency_seed="s")
    assert a.idempotency_key == b.idempotency_key and a.trade_intent_id == b.trade_intent_id


def test_allocation_decision_changes_the_intent_identity():
    """The intent records which allocation selected it."""
    f = IntentFactory()
    a = f.from_selected_candidate(_cand(), requested_risk_pct=Decimal("0.005"),
                                  idempotency_seed="s", allocation_decision_hash="alloc-1")
    b = f.from_selected_candidate(_cand(), requested_risk_pct=Decimal("0.005"),
                                  idempotency_seed="s", allocation_decision_hash="alloc-2")
    assert a.decision_hash != b.decision_hash


def test_correlation_multiplier_reaches_the_intent():
    intent = IntentFactory().from_selected_candidate(
        _cand(), requested_risk_pct=Decimal("0.005"), idempotency_seed="s",
        correlation_multiplier=Decimal("0.4"))
    assert intent.correlation_multiplier == Decimal("0.4")


def test_unsealed_candidate_is_refused():
    raw = dataclasses.replace(_cand(), candidate_hash="")
    with pytest.raises(IntentFactoryError, match="unsealed"):
        IntentFactory().from_selected_candidate(raw, requested_risk_pct=Decimal("0.005"),
                                                idempotency_seed="s")


def test_targets_without_a_stop_are_refused():
    c = _cand(stop=None)
    with pytest.raises(IntentFactoryError, match="targets without a stop"):
        IntentFactory().from_selected_candidate(c, requested_risk_pct=Decimal("0.005"),
                                                idempotency_seed="s")
