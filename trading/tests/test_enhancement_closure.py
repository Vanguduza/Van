"""Phase 14/15: guardrails, observability, degraded truth, closure.

These are the tests that protect the corrections themselves. If any of them
can be deleted without another test failing, the correction was decorative.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal as D

import pytest

from vati.observability.enhancement_metrics import (
    ALL_METRICS,
    ALLOWED_LABELS,
    BLOCKS_NEW_RISK,
    DEGRADED_STATES,
    EXECUTION_INTELLIGENCE_INSUFFICIENT,
    FEATURE_DEGRADED,
    FORBIDDEN_LABELS,
    OWNER_LANGUAGE,
    ACCOUNT_LEASE_HELD_ELSEWHERE,
    ACCOUNT_LEASE_UNAVAILABLE,
    MetricCardinalityError,
    check_labels,
)

GUARD = "trading/tools/check_enhancement_architecture.py"
MIGRATE = "trading/tools/migrate_capsule_timeframes.py"


# --- architecture guardrails ---------------------------------------------

def test_architecture_guardrails_pass_on_the_current_tree():
    r = subprocess.run([sys.executable, GUARD], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_guardrail_script_actually_fails_when_violated(tmp_path, monkeypatch):
    """A check that cannot fail is not a check.

    Applies the §48 mutation `rank Allocator V0 on confidence_score` to a copy
    of the tree and asserts the guardrail kills it.
    """
    import pathlib
    import shutil

    src = pathlib.Path("trading")
    dst = tmp_path / "trading"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    alloc = dst / "vati" / "arbiter" / "portfolio_allocator.py"
    text = alloc.read_text()
    mutated = text.replace(
        'utility = (cost * freshness * regime * dependency_penalty).quantize(Decimal("0.000001"))',
        'utility = (cost * freshness * regime * dependency_penalty * c.confidence_score).quantize(Decimal("0.000001"))')
    assert mutated != text, "the mutation target moved; update this test"
    alloc.write_text(mutated)

    r = subprocess.run([sys.executable, str(dst / "tools" / "check_enhancement_architecture.py")],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "confidence" in r.stderr


def test_capsule_migration_is_settled():
    r = subprocess.run([sys.executable, MIGRATE, "--check"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "migration provenance reconciled" in r.stdout


def test_every_capsule_has_a_timeframe_contract():
    import glob
    import json
    from vati.intelligence.mtf import TimeframeContract
    for path in glob.glob("trading/strategies/registry/*.json"):
        doc = json.loads(open(path).read())
        c = TimeframeContract.from_capsule(doc)
        assert c is not None, path
        assert c.required_timeframes, path


def test_migration_check_rejects_post_migration_capsule_drift(tmp_path):
    import json
    import pathlib
    import shutil
    from vati.core.canonical import canonical_hash

    src = pathlib.Path("trading")
    dst = tmp_path / "trading"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    cap = dst / "strategies" / "registry" / "FX-TREND-PULLBACK-01.json"
    doc = json.loads(cap.read_text())
    doc["timeframe_contract"]["execution"] = "M15"
    body = {k: v for k, v in doc.items() if k != "capsule_hash"}
    doc["capsule_hash"] = canonical_hash(body)
    cap.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

    r = subprocess.run(
        [sys.executable, str(dst / "tools" / "migrate_capsule_timeframes.py"), "--check"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "migration provenance" in r.stderr or "timeframe_contract drifted" in r.stderr


def test_every_migration_record_asserts_unchanged_logic():
    import json
    import pathlib
    p = pathlib.Path("trading/strategies/migrations/capsule_migrations.json")
    records = json.loads(p.read_text())
    assert records
    for r in records:
        assert r["strategy_logic_changed"] is False
        assert r["migration_reason"] == "MTF_SCHEMA_ADOPTION"
        assert r["old_capsule_hash"] and r["new_capsule_hash"]
        assert r["old_capsule_hash"] != r["new_capsule_hash"]
        assert r["record_hash"]


# --- observability --------------------------------------------------------

def test_metric_names_are_unique_and_prefixed():
    assert len(set(ALL_METRICS)) == len(ALL_METRICS)
    assert all(m.startswith("vati_") for m in ALL_METRICS)


def test_bounded_labels_are_accepted():
    check_labels({"symbol": "EURUSD", "strategy_id": "S", "outcome": "SELECTED"})


@pytest.mark.parametrize("label", sorted(FORBIDDEN_LABELS))
def test_every_unbounded_label_is_refused(label):
    """A metric with unbounded cardinality is a memory leak with a dashboard."""
    with pytest.raises(MetricCardinalityError, match="unbounded"):
        check_labels({label: "x"})


def test_an_unknown_label_must_be_added_deliberately():
    with pytest.raises(MetricCardinalityError, match="unknown label"):
        check_labels({"vibes": "good"})


def test_allowed_and_forbidden_labels_do_not_overlap():
    assert not (ALLOWED_LABELS & FORBIDDEN_LABELS)


# --- degraded truth -------------------------------------------------------

def test_every_degraded_state_has_owner_language_and_a_risk_verdict():
    assert set(DEGRADED_STATES) == set(OWNER_LANGUAGE)
    assert set(DEGRADED_STATES) == set(BLOCKS_NEW_RISK)


def test_degraded_states_are_not_one_red_icon():
    """Different facts with different responses."""
    assert BLOCKS_NEW_RISK[FEATURE_DEGRADED] is True
    assert BLOCKS_NEW_RISK[EXECUTION_INTELLIGENCE_INSUFFICIENT] is False


def test_the_two_lease_failures_stay_distinct_in_the_owner_surface():
    """B2 all the way through: fail-closed is not the same as fenced."""
    assert ACCOUNT_LEASE_UNAVAILABLE != ACCOUNT_LEASE_HELD_ELSEWHERE
    assert BLOCKS_NEW_RISK[ACCOUNT_LEASE_UNAVAILABLE] is True
    assert BLOCKS_NEW_RISK[ACCOUNT_LEASE_HELD_ELSEWHERE] is True
    assert "fail-closed" in OWNER_LANGUAGE[ACCOUNT_LEASE_UNAVAILABLE]
    assert OWNER_LANGUAGE[ACCOUNT_LEASE_UNAVAILABLE] != OWNER_LANGUAGE[ACCOUNT_LEASE_HELD_ELSEWHERE]


def test_owner_language_says_what_still_works():
    """"What broke, what still works, what VAN will not do"."""
    assert "others continue" in OWNER_LANGUAGE[FEATURE_DEGRADED]
    assert "certified default" in OWNER_LANGUAGE[EXECUTION_INTELLIGENCE_INSUFFICIENT]


# --- the invariants, restated as tests ------------------------------------

def test_no_runtime_multiplier_can_exceed_one():
    from vati.risk.sizing import clamp_multiplier
    for value in ("2", "1.0001", "99", float("inf")):
        assert clamp_multiplier(value) <= D("1")


def test_the_risk_authority_is_still_the_only_sizer():
    from vati.app.account_coordinator import AccountDecisionCoordinator
    from vati.arbiter.portfolio_allocator import AllocatorV1, OpportunityPortfolioAllocator
    for cls in (OpportunityPortfolioAllocator, AllocatorV1, AccountDecisionCoordinator):
        for name in ("size", "allocate_size", "reserve_heat", "preapprove"):
            assert not hasattr(cls, name), f"{cls.__name__}.{name}"


def test_confidence_remains_uncalibrated_and_excluded():
    from vati.arbiter.confidence import BASIS
    assert "UNCALIBRATED" in BASIS
    assert "never sizes" in BASIS or "never a size" in BASIS


def test_vati_serve_reaches_account_coordinator_for_multi_instrument_config(monkeypatch, capsys):
    import argparse
    import types
    import vati.__main__ as cli
    import vati.app.account_service as account_service_mod
    import vati.app.process_lock as process_lock_mod
    import vati.app.service as service_mod

    cfg = types.SimpleNamespace(
        account_alias="acct",
        instruments=[{"symbol": "GBPUSD"}],
    )
    monkeypatch.setattr(service_mod.ServiceConfig, "load", lambda _path: cfg)

    class _Lock:
        def release(self):
            pass

    class _SessionLock:
        def __init__(self, alias):
            assert alias == "acct"
        def acquire(self):
            return _Lock()

    monkeypatch.setattr(process_lock_mod, "SessionLock", _SessionLock)

    calls = []
    class _AccountService:
        def __init__(self, received):
            assert received is cfg
            self.cycles = 0
            calls.append("constructed")
        def build(self):
            calls.append("built")
            return self
        def start(self):
            calls.append("started")
        def step_once(self):
            self.cycles = 1
            calls.append("stepped")
            return types.SimpleNamespace(outcomes=("ok",))

    monkeypatch.setattr(account_service_mod, "AccountCoordinatorService", _AccountService)
    rc = cli.cmd_serve(argparse.Namespace(config="ignored.json", once=True))
    assert rc == 0
    assert calls == ["constructed", "built", "started", "stepped"]
    assert '"cycles": 1' in capsys.readouterr().out
