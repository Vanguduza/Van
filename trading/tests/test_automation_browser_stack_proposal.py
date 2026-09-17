"""Rev 1.3 §413 stack-lock assertions for the proposed Automation & Browser Fabric layers.

The three layers are not admitted: Rev 1.3 §366 blocks stack-lock mutation until the repository
records an owner-approved adoption decision. They therefore live in
``trading/architecture/proposed/automation_browser_fabric_layers.json`` and are validated here
against the *same* schema rules ``test_stack_lock.py`` applies to admitted layers, plus the §413
assertions. On owner approval the objects move verbatim into ``stack_lock.json`` and these
assertions keep holding — promotion changes where the layers live, not whether they are valid.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_stack_lock import ALLOWED_LICENCE_CLASSES, DECISION_REQUIRED, LAYERS as ADMITTED_LAYERS

ARCH = Path(__file__).resolve().parents[1] / "architecture"
PROPOSAL = json.loads((ARCH / "proposed" / "automation_browser_fabric_layers.json").read_text(encoding="utf-8"))
PROPOSED = PROPOSAL["layers"]
BY_NAME = {layer["layer"]: layer for layer in PROPOSED}


def test_proposal_is_not_owner_signed():
    """Rev 1.3 §365: an implementation agent creates the proposal, never signs it."""
    assert PROPOSAL["proposal_status"] == "PENDING_OWNER"
    for ref in PROPOSAL["adoption_decision_refs"].values():
        decision = (Path(__file__).resolve().parents[2] / ref).read_text(encoding="utf-8")
        assert "owner_signature_status: PENDING" in decision, ref


def test_proposed_layers_are_not_yet_admitted():
    """Rev 1.3 §366: stack-lock mutation is blocked until the decision is recorded."""
    admitted = {layer["layer"] for layer in ADMITTED_LAYERS}
    assert admitted.isdisjoint(BY_NAME), "proposed layers must not be merged into stack_lock.json yet"


def test_proposed_layers_satisfy_admitted_layer_schema():
    """Every rule test_stack_lock.py enforces on admitted layers must already hold here.

    This is what makes promotion mechanical: the Rev 1.2 review found the Rev 1.2 draft entry
    failed three of these (compound "T2/T3" tier, and missing licence_class/adoption_phase/
    pin_status). Rev 1.3 fixed all three; this test keeps them fixed.
    """
    names = [layer["layer"] for layer in PROPOSED]
    assert len(names) == len(set(names)), "duplicate proposed layer entries"
    for layer in PROPOSED:
        assert layer["canonical"], layer["layer"]
        assert layer["executes_live_orders"] in (True, False), layer["layer"]
        assert layer["latency_tier"] in {"T0", "T1", "T2", "T3"}, layer["layer"]
        assert layer["licence_class"] in ALLOWED_LICENCE_CLASSES, layer["layer"]
        assert isinstance(layer["adoption_phase"], int) and layer["adoption_phase"] >= 1, layer["layer"]
        assert layer["pin_status"] in {
            "UNPINNED_VERIFY_AT_ADOPTION",
            "PIN_TO_DIAL_COMMIT_AT_ADOPTION",
            "N/A",
        }, layer["layer"]


def test_proposed_non_permissive_licences_require_owner_decision():
    for layer in PROPOSED:
        if layer["licence_class"] in DECISION_REQUIRED:
            assert any(
                "owner-signed adoption decision" in constraint for constraint in layer.get("constraints", [])
            ), layer["layer"]


def test_automation_fabric_not_t0():
    """Rev 1.3 §413."""
    n8n = BY_NAME["integration_automation"]
    assert n8n["latency_tier"] != "T0"
    assert n8n["executes_live_orders"] is False


def test_n8n_source_available_requires_owner_decision():
    """Rev 1.3 §413."""
    n8n = BY_NAME["integration_automation"]
    assert n8n["licence_class"] == "SOURCE_AVAILABLE"
    assert any("owner-signed adoption decision" in c for c in n8n["constraints"])


def test_browser_layers_never_send_orders():
    """Rev 1.3 §413."""
    for name in ("semantic_browser", "deterministic_browser"):
        layer = BY_NAME[name]
        assert layer["executes_live_orders"] is False
        assert layer["latency_tier"] != "T0"


def test_no_proposed_layer_becomes_an_order_sender():
    """Admitted senders stay exactly the four certified ones (test_stack_lock.py invariant)."""
    for layer in PROPOSED:
        assert layer["executes_live_orders"] is False, layer["layer"]


def test_proposed_layers_declare_no_authority_over_trading():
    forbidden = ("risk", "mandate", "order", "Project Truth", "authority")
    for layer in PROPOSED:
        text = " ".join(layer["constraints"]).lower()
        assert any(word.lower() in text for word in forbidden), layer["layer"]
