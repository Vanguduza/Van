"""The stack lock is deterministic stitching: one canonical tool per layer,
one order sender, one sizer, one transactional authority, and licence classes
that force an explicit decision where the licence is not permissive."""

from __future__ import annotations

import json
from pathlib import Path

LOCK = json.loads((Path(__file__).resolve().parents[1] / "architecture" / "stack_lock.json").read_text(encoding="utf-8"))
LAYERS = LOCK["layers"]
ALLOWED_LICENCE_CLASSES = {"PERMISSIVE", "COPYLEFT_WEAK", "COPYLEFT_NETWORK", "SOURCE_AVAILABLE", "VENDOR_TERMS", "INTERNAL", "MIXED_REVIEW", "VERIFY_AT_ADOPTION"}
DECISION_REQUIRED = {"COPYLEFT_NETWORK", "SOURCE_AVAILABLE"}


def test_one_canonical_choice_per_layer():
    names = [l["layer"] for l in LAYERS]
    assert len(names) == len(set(names)), "duplicate layer entries"
    for l in LAYERS:
        assert l["canonical"], l["layer"]
        assert l["executes_live_orders"] in (True, False)
        assert l["latency_tier"] in {"T0", "T1", "T2", "T3"}
        assert l["licence_class"] in ALLOWED_LICENCE_CLASSES, l["layer"]
        assert isinstance(l["adoption_phase"], int) and l["adoption_phase"] >= 1


def test_only_kernel_and_venue_adapters_send_live_orders():
    senders = {l["layer"] for l in LAYERS if l["executes_live_orders"]}
    assert senders == {"trading_kernel", "mt5_execution", "deriv_execution", "ctrader_execution"}


def test_t0_path_contains_no_network_brokers_workflows_or_llms():
    t0 = {l["layer"] for l in LAYERS if l["latency_tier"] == "T0"}
    assert t0 == {"trading_kernel", "mt5_execution", "deriv_execution", "ctrader_execution"}
    for l in LAYERS:
        if l["layer"] in ("event_backbone", "durable_workflows", "google_research_mesh", "research_data_facade"):
            assert l["latency_tier"] != "T0"


def test_validation_oracle_never_controls_live_accounts():
    lean = next(l for l in LAYERS if l["layer"] == "independent_validation_oracle")
    assert lean["executes_live_orders"] is False and "validation_only" in lean["constraints"]


def test_non_permissive_licences_require_owner_decision():
    for l in LAYERS:
        if l["licence_class"] in DECISION_REQUIRED:
            assert any("owner-signed adoption decision" in c for c in l.get("constraints", [])), l["layer"]


def test_nothing_is_pinned_before_adoption_gate():
    for l in LAYERS:
        assert l["pin_status"] in {"UNPINNED_VERIFY_AT_ADOPTION", "PIN_TO_DIAL_COMMIT_AT_ADOPTION", "N/A"}, l["layer"]


def test_single_authorities_declared():
    assert LOCK["single_sizer"].startswith("trading/vati/risk")
    assert "RiskGate" in LOCK["single_order_sender"]
    assert LOCK["single_transactional_authority"].startswith("PostgreSQL")
