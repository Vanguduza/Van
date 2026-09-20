"""Phase 13: coverage, drift, browser evidence, feed disagreement."""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal as D

import pytest

from vati.learning import coverage as coverage_mod
from vati.learning import drift as drift_mod
from vati.learning.coverage import (
    COVERED_CERTIFIED,
    INTENTIONALLY_ABSTAIN,
    RESEARCH_NEGATIVE,
    SETTLED_STATES,
    UNRESEARCHED,
    CoverageCell,
    OpportunityCostEstimate,
    StrategyCoverageMap,
)
from vati.learning.drift import (
    DEGRADED,
    INSUFFICIENT,
    STABLE,
    WATCH,
    DriftSegment,
    EdgeDriftMonitor,
    FeatureDriftMonitor,
    standardised_shift,
)
from vati.research import trading_evidence as evidence_mod
from vati.research.market_data_disagreement import (
    AGREE,
    BOTH_STALE,
    CONTINUE,
    EXECUTION_FEED_STALE,
    HALT,
    MAJOR_DIVERGENCE,
    NO_REFERENCE,
    REDUCE,
    REFERENCE_FEED_STALE,
    WAIT,
    FeedSample,
    MarketDataDisagreementDetector,
)
from vati.research.trading_evidence import (
    FORBIDDEN_EFFECTS,
    UNTRUSTED_EXTERNAL,
    EvidenceAuthorityError,
    EvidenceEffect,
    TradingEvidenceArtifact,
    TradingEvidenceCollector,
)
from vati.strategies.capsule import CapsuleRegistry

REG = "trading/strategies/registry"


# --- coverage -------------------------------------------------------------

def test_fx_range_is_uncovered_and_the_map_derives_it_from_the_registry():
    """Not asserted by hand: read off what the capsules actually declare."""
    m = StrategyCoverageMap.from_capsules(list(CapsuleRegistry.load_dir(REG).all()))
    fx_gaps = [c for c in m.gaps() if c.market == "FX"]
    assert fx_gaps, "the map should find FX gaps"
    assert "RANGE" in {c.regime for c in fx_gaps}


def test_a_forbidden_regime_is_an_abstention_not_a_gap():
    """Declining a regime deliberately is a decision, not missing coverage."""
    m = StrategyCoverageMap.from_capsules(list(CapsuleRegistry.load_dir(REG).all()))
    abstain = [c for c in m.cells() if c.state == INTENTIONALLY_ABSTAIN]
    assert abstain
    assert all(c.state != UNRESEARCHED for c in abstain)


def test_an_uncovered_cell_is_not_lost_profit():
    """A frequent regime with no edge after costs is idle time, not foregone profit."""
    frequent_but_unprofitable = OpportunityCostEstimate(
        cell_key="FX|EURUSD|SWING|RANGE", share_of_tradable_time=D("0.45"),
        historical_opportunity_count=500, mean_spread_cost_pct=D("0.0002"),
        hypothetical_expectancy_R=D("0.20"), edge_after_cost_R=D("-0.05"))
    assert not frequent_but_unprofitable.worth_researching


def test_a_cell_worth_researching_needs_edge_frequency_and_sample():
    good = OpportunityCostEstimate(
        cell_key="k", share_of_tradable_time=D("0.30"), historical_opportunity_count=200,
        mean_spread_cost_pct=D("0.0002"), edge_after_cost_R=D("0.12"))
    assert good.worth_researching
    assert not OpportunityCostEstimate(
        cell_key="k", share_of_tradable_time=D("0.30"), historical_opportunity_count=5,
        mean_spread_cost_pct=D("0.0002"), edge_after_cost_R=D("0.12")).worth_researching


def test_research_negative_is_a_settled_result_not_a_gap():
    m = StrategyCoverageMap([CoverageCell("FX", "EURUSD", "SWING", "RANGE", RESEARCH_NEGATIVE)])
    assert m.gaps() == ()
    assert RESEARCH_NEGATIVE in SETTLED_STATES


def test_unknown_coverage_state_is_refused():
    with pytest.raises(ValueError, match="unknown coverage state"):
        StrategyCoverageMap().set(CoverageCell("FX", "EURUSD", "SWING", "RANGE", "PROBABLY_FINE"))


def test_coverage_map_is_hashable_for_evidence():
    m = StrategyCoverageMap.from_capsules(list(CapsuleRegistry.load_dir(REG).all()))
    assert m.map_hash()


# --- feature drift --------------------------------------------------------

BASE = [50.0 + (i % 10) for i in range(60)]
MON = FeatureDriftMonitor()
SEG = DriftSegment("rsi", "S", "EURUSD", "H1", "BULL")


def test_a_stable_feature_is_stable():
    o = MON.observe(SEG, baseline_values=BASE, recent_values=BASE,
                    baseline_contribution=D("0.1"), recent_contribution=D("0.1"))
    assert o.state == STABLE


def test_a_shifted_distribution_is_flagged():
    o = MON.observe(SEG, baseline_values=BASE, recent_values=[80.0 + (i % 10) for i in range(60)])
    assert o.state == DEGRADED


def test_a_feature_that_stopped_contributing_is_degraded():
    """The leading indicator: contribution collapses before the capsule does."""
    o = MON.observe(SEG, baseline_values=BASE, recent_values=BASE,
                    baseline_contribution=D("0.20"), recent_contribution=D("0.02"))
    assert o.state == DEGRADED
    assert any("contribution_drop" in r for r in o.reasons)


def test_a_short_window_is_insufficient_not_stable():
    o = MON.observe(SEG, baseline_values=BASE[:5], recent_values=BASE[:5])
    assert o.state == INSUFFICIENT


def test_standardised_shift_is_scale_free():
    a = standardised_shift([1.0, 2.0, 3.0] * 20, [2.0, 3.0, 4.0] * 20)
    b = standardised_shift([100.0, 200.0, 300.0] * 20, [200.0, 300.0, 400.0] * 20)
    assert abs(a - b) < D("0.001")


def test_drift_observation_is_sealed():
    assert MON.observe(SEG, baseline_values=BASE, recent_values=BASE).observation_hash


def test_drift_module_cannot_mutate_a_capsule():
    tree = ast.parse(inspect.getsource(drift_mod))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("capsule" in m or "registry" in m for m in mods)
    for name in ("promote", "demote", "apply", "update"):
        assert not hasattr(FeatureDriftMonitor, name)


# --- edge drift -----------------------------------------------------------

EDGE = EdgeDriftMonitor()


def test_a_large_expectancy_drop_is_degraded():
    o = EDGE.observe(strategy_id="S", segment="all",
                     baseline_expectancy_R=D("0.35"), recent_expectancy_R=D("0.10"))
    assert o.state == DEGRADED


def test_a_lost_edge_floor_is_degraded_even_when_the_mean_looks_fine():
    """The evidence stopped supporting the mean."""
    o = EDGE.observe(strategy_id="S", segment="all",
                     baseline_expectancy_R=D("0.30"), recent_expectancy_R=D("0.28"),
                     recent_edge_floor_R=D("-0.02"))
    assert o.state == DEGRADED
    assert any("edge_floor_not_positive" in r for r in o.reasons)


def test_a_small_drop_is_only_a_watch():
    o = EDGE.observe(strategy_id="S", segment="all",
                     baseline_expectancy_R=D("0.30"), recent_expectancy_R=D("0.24"))
    assert o.state == WATCH


# --- browser evidence -----------------------------------------------------

def _artifact(**kw):
    base = dict(evidence_id="e1", source_uri="https://example.invalid/x",
                source_type="CENTRAL_BANK_STATEMENT", source_hash="h",
                observed_at_ms=1_000, extractor_version="1.0.0")
    base.update(kw)
    return TradingEvidenceArtifact(**base).sealed()


def test_evidence_defaults_to_untrusted():
    assert _artifact().trust_tier == UNTRUSTED_EXTERNAL


@pytest.mark.parametrize("effect", sorted(FORBIDDEN_EFFECTS))
def test_browser_evidence_can_never_have_an_authority_effect(effect):
    with pytest.raises(EvidenceAuthorityError):
        EvidenceEffect(evidence_id="e1", effect=effect, target="X")


def test_evidence_may_only_reduce_confidence():
    EvidenceEffect(evidence_id="e1", effect="REDUCE_CONFIDENCE", target="X",
                   confidence_multiplier=D("0.5"))
    with pytest.raises(EvidenceAuthorityError, match="only reduce"):
        EvidenceEffect(evidence_id="e1", effect="REDUCE_CONFIDENCE", target="X",
                       confidence_multiplier=D("1.5"))


def test_a_page_saying_buy_is_untrusted_content_not_a_signal():
    c = TradingEvidenceCollector()
    c.admit(_artifact(evidence_id="e2", source_type="OTHER",
                      extracted_facts={"text": "buy EURUSD now"}))
    with pytest.raises(EvidenceAuthorityError):
        c.propose(EvidenceEffect(evidence_id="e2", effect="SEND_ORDER", target="EURUSD"))


def test_retrieval_success_is_not_truth():
    """Stagehand fetching a page proves retrieval; the flag says only that."""
    a = _artifact(retrieval_verified=True)
    assert a.retrieval_verified and a.trust_tier == UNTRUSTED_EXTERNAL


def test_an_effect_for_unknown_evidence_is_refused():
    with pytest.raises(EvidenceAuthorityError, match="no such evidence"):
        TradingEvidenceCollector().propose(
            EvidenceEffect(evidence_id="ghost", effect="EXPLAIN", target="X"))


def test_expired_evidence_leaves_the_active_set():
    c = TradingEvidenceCollector()
    c.admit(_artifact(expires_at_ms=2_000))
    assert c.active(1_500) and not c.active(3_000)


def test_evidence_module_cannot_import_execution():
    tree = ast.parse(inspect.getsource(evidence_mod))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("execution" in m or "router" in m for m in mods)


# --- feed disagreement ----------------------------------------------------

DET = MarketDataDisagreementDetector()
REF = FeedSample("ref", D("1.1000"), D("1.1001"), 1_000)


def _cmp(execution, reference=REF, now=1_100):
    return DET.compare(symbol="EURUSD", execution=execution, reference=reference, now_ms=now)


def test_agreeing_feeds_continue():
    assert _cmp(FeedSample("broker", D("1.1000"), D("1.1001"), 1_000)).response == CONTINUE


def test_major_divergence_halts():
    o = _cmp(FeedSample("broker", D("1.1100"), D("1.1101"), 1_000))
    assert o.state == MAJOR_DIVERGENCE and o.response == HALT


def test_minor_divergence_reduces():
    o = _cmp(FeedSample("broker", D("1.10075"), D("1.10085"), 1_000))
    assert o.response == REDUCE


def test_spread_anomaly_reduces():
    o = _cmp(FeedSample("broker", D("1.0995"), D("1.1006"), 1_000))
    assert o.response in (REDUCE, HALT)


def test_stale_execution_feed_halts():
    o = _cmp(FeedSample("broker", D("1.1000"), D("1.1001"), 0), now=99_000)
    assert o.state in (EXECUTION_FEED_STALE, BOTH_STALE) and o.response == HALT


def test_a_stale_reference_only_waits():
    """A stale reference says nothing about the execution feed."""
    o = DET.compare(symbol="EURUSD",
                    execution=FeedSample("broker", D("1.1000"), D("1.1001"), 98_900),
                    reference=FeedSample("ref", D("1.1000"), D("1.1001"), 0), now_ms=99_000)
    assert o.state == REFERENCE_FEED_STALE and o.response == WAIT


def test_absent_reference_is_not_agreement():
    o = DET.compare(symbol="EURUSD",
                    execution=FeedSample("broker", D("1.1000"), D("1.1001"), 1_000),
                    reference=None, now_ms=1_100)
    assert o.state == NO_REFERENCE and o.state != AGREE


def test_there_is_no_switch_feed_response():
    """Disagreement means one is wrong and we do not know which."""
    from vati.research import market_data_disagreement as m
    assert not hasattr(m, "SWITCH_FEED")
    assert set(m.__all__) & {CONTINUE, WAIT, REDUCE, HALT}


def test_slow_research_plane_is_reachable_through_vati_cli(tmp_path, capsys):
    import argparse
    import json
    from vati.__main__ import cmd_research

    spec = tmp_path / "research.json"
    spec.write_text(json.dumps({
        "operation": "coverage",
        "capsule_dir": REG,
    }))
    assert cmd_research(argparse.Namespace(spec=str(spec), ledger=None)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "coverage"
    assert payload["map_hash"]
    assert payload["gap_count"] > 0


def test_research_cli_builds_strategy_certificate_from_raw_validation_data(tmp_path, capsys):
    import argparse
    import json
    from vati.__main__ import cmd_research

    spec = tmp_path / "strategy-cert.json"
    spec.write_text(json.dumps({
        "operation": "strategy_certificate",
        "validation": {
            "strategy_id": "S", "strategy_version": "1.0", "capsule_hash": "cap",
            "data_manifest_hash": "manifest:1", "evidence_refs": ["wf:1", "cpcv:1"],
            "feature_set_version": "features/1", "cost_model_revision": "cost/1",
            "pnls": [10, -4, 12, 8, -3, 9, 7, -2],
            "r_multiples": [1, -0.4, 1.2, 0.8, -0.3, 0.9, 0.7, -0.2],
            "start_equity": 1000,
            "trial_returns_matrix": [
                [0.2,-0.1,0.3,0.1,-0.05,0.2,0.15,-0.02],
                [0.1,-0.2,0.25,0.05,-0.1,0.1,0.12,-0.08],
                [0.05,-0.1,0.1,0.02,-0.03,0.08,0.07,-0.04],
                [0.15,-0.05,0.2,0.08,-0.02,0.14,0.11,-0.01]
            ],
            "walk_forward_windows": 4,
            "cost_stress_2x": "GREEN",
            "latency_slippage_stress": "GREEN",
            "parameter_perturbation_stability": "GREEN",
            "leakage_switch_result": "GREEN"
        }
    }))
    assert cmd_research(argparse.Namespace(spec=str(spec), ledger=None)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "strategy_certificate"
    cert = payload["certificate"]
    assert cert["validation_hash"]
    assert cert["data_manifest_hash"] == "manifest:1"
    assert cert["evidence_refs"] == ["wf:1", "cpcv:1"]
    assert 0 <= cert["stats"]["dsr_probability"] <= 1
    assert 0 <= cert["stats"]["pbo_probability"] <= 1
