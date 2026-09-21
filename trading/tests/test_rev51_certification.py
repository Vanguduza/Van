"""Rev 5.1 certification harness tests (TRD-REV51-133)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools" / "certification" / "rev51_harness.py"


def _module():
    spec = importlib.util.spec_from_file_location("rev51_harness", HARNESS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_harness_certifies_repository_implementation_but_not_live_eligibility():
    report = _module().evaluate_repository()
    assert report["states"]["SPEC_CLOSED"] is True
    assert report["states"]["IMPLEMENTATION_CLOSED"] is True
    assert report["states"]["RUNTIME_QUALIFIED"] is False
    assert report["states"]["SHADOW_QUALIFIED"] is False
    assert report["states"]["LIVE_ELIGIBLE"] is False
    assert report["live_status"] == "NOT_CLAIMED"


def test_harness_covers_every_rev51_packet_and_declared_file():
    report = _module().evaluate_repository()
    assert report["gates"]["registry_complete"]["ok"]
    assert report["gates"]["declared_files_exist"]["ok"]


def test_harness_proves_single_authority_and_order_sender_boundaries():
    report = _module().evaluate_repository()
    gate = report["gates"]["authority_singletons"]
    assert gate["ok"]
    assert gate["detail"]["risk_authority_classes"] == [
        "trading/vati/risk/authority.py"
    ]
    assert gate["detail"]["adapter_submit_paths"] == [
        "trading/vati/execution/router.py"
    ]


def test_harness_proves_rev51_execution_and_conformal_hooks_are_present():
    report = _module().evaluate_repository()
    assert report["gates"]["non_bypassable_execution"]["ok"]
    assert report["gates"]["conformal_authority_hook"]["ok"]


def test_harness_refuses_to_convert_repo_green_into_live_green():
    report = _module().evaluate_repository()
    assert report["gates"]["first_pass_live_safety"]["ok"]
    assert report["states"]["IMPLEMENTATION_CLOSED"]
    assert not report["states"]["LIVE_ELIGIBLE"]
