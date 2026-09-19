"""The maturity gate must fail on the defect shape it exists to prevent.

A gate that only ever passes proves nothing. These tests inject each defect the
whole-system audit actually found and assert the gate rejects it:

  * a capability claiming INTEGRATED while naming no production caller — the exact
    shape of the twenty isolated cognition classes;
  * a component claiming deliberate removal while its file is still present;
  * a finding with no remediation gate;
  * a gate assignment the blueprint does not define.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "tools" / "ci" / "maturity_gate.py"
FINDINGS = ROOT / "evidence" / "van-system-audit" / "findings.json"
COMPONENTS = ROOT / "evidence" / "van-system-audit" / "component_ledger.json"


def run_gate() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE)], capture_output=True, text=True, cwd=str(ROOT)
    )


@pytest.fixture
def ledgers_restored():
    """Mutate the real ledgers in place, then put them back exactly."""
    findings_before = FINDINGS.read_text(encoding="utf-8")
    components_before = COMPONENTS.read_text(encoding="utf-8")
    yield
    FINDINGS.write_text(findings_before, encoding="utf-8")
    COMPONENTS.write_text(components_before, encoding="utf-8")


def test_gate_passes_on_the_committed_ledgers():
    result = run_gate()
    assert result.returncode == 0, f"gate failed on committed state:\n{result.stdout}\n{result.stderr}"
    assert "MATURITY GATE PASSED" in result.stdout


def test_gate_rejects_integrated_claim_without_a_production_caller(ledgers_restored):
    """The defect that produced twenty isolated cognition classes."""
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    target = data["components"][0]
    target["terminal_state"] = "INTEGRATED_AND_EVIDENCED"
    target["producer"] = "something"
    target["consumer"] = "something"
    target["production_caller"] = None  # the whole defect, in one field
    target["tests"] = ["a test"]
    target["runtime_evidence"] = ["some evidence"]
    COMPONENTS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "production_caller" in result.stderr
    assert "INTEGRATED_AND_EVIDENCED" in result.stderr


def test_gate_rejects_removal_claim_while_the_file_still_exists(ledgers_restored):
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    still_present = next(
        c for c in data["components"]
        if c.get("path") and (ROOT / c["path"]).is_file()
    )
    still_present["terminal_state"] = "DELIBERATELY_REMOVED_CANON_CORRECTED"
    # And clear any inherited assertion, so this exercises the `file_absent` default.
    #
    # This test started failing when components began carrying `symbols_absent`: it picks
    # the first component whose file exists, and that component's own assertion sent the
    # gate to check symbols — which were genuinely gone, so the gate passed and the test
    # read it as the gate failing to notice. The gate was right; the fixture had quietly
    # stopped testing the branch it names.
    still_present.pop("removal_assertion", None)
    COMPONENTS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "still exists" in result.stderr


def test_gate_rejects_symbol_removal_claim_while_the_symbol_survives(ledgers_restored):
    """Deleting two methods from a surviving module must assert those symbols are gone."""
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    target = next(c for c in data["components"] if c["n"] == 63)
    # Claim removal of a symbol the file still defines.
    target["removal_assertion"] = {"kind": "symbols_absent", "symbols": ["health"]}
    COMPONENTS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "still defines" in result.stderr


def test_gate_rejects_a_class_removal_claim_while_the_class_survives(ledgers_restored):
    """A deleted *class* is a removal too, and the gate could not see one.

    `symbols_absent` matched `def` and `fun` only. A component asserting a class was gone
    passed because the pattern never matched anything — the most useless way for a gate to
    agree with you, and it went unnoticed because every symbol assertion in the ledger named
    a function. P1-CTX-004 deleted `Claim` and `Provenance`, which is what needed it.
    """
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    target = next(c for c in data["components"] if c["n"] == 2)
    # SemanticClass is still defined in that module, and deliberately so.
    target["removal_assertion"] = {"kind": "symbols_absent", "symbols": ["SemanticClass"]}
    COMPONENTS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "still defines" in result.stderr


def test_gate_rejects_a_kotlin_removal_claim_while_the_function_survives(ledgers_restored):
    """The Kotlin arm of the same check, which no test exercised either.

    Two components assert deleted Kotlin symbols and both are genuinely gone, so the `fun`
    pattern could have been broken for the whole programme without a single test noticing.
    A pattern only ever asked about absent things is never asked anything.
    """
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    target = next(c for c in data["components"] if c["n"] == 90)
    # canAuthenticate is still defined in BiometricGate.kt.
    target["removal_assertion"] = {"kind": "symbols_absent", "symbols": ["canAuthenticate"]}
    COMPONENTS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "still defines" in result.stderr


def test_gate_accepts_symbol_removal_that_actually_happened():
    """The committed state claims message_agent and create_council are gone. They are."""
    bridge = (ROOT / "backend" / "van_gateway" / "hermes" / "bridge.py").read_text(encoding="utf-8")
    assert "async def message_agent" not in bridge
    assert "async def create_council" not in bridge
    assert "async def create_run" in bridge, "the live dispatch path must survive the deletion"


def test_gate_rejects_an_unassigned_finding(ledgers_restored):
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    data["findings"][0].pop("remediation_gate", None)
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "no remediation_gate" in result.stderr


def test_gate_rejects_a_gate_the_blueprint_does_not_define(ledgers_restored):
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    data["findings"][0]["remediation_gate"] = "GATE 99"
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "blueprint does not define" in result.stderr


def test_every_registered_finding_names_a_gate():
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    unassigned = [f["id"] for f in data["findings"] if not f.get("remediation_gate")]
    assert not unassigned, f"unassigned findings: {unassigned}"


def test_every_inventoried_component_carries_one_disposition():
    data = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    valid = {"WIRE", "COMPLETE", "REPLACE", "DELETE"}
    bad = [
        c["component"] for c in data["components"]
        if c.get("disposition") not in valid
    ]
    assert not bad, f"components without a valid disposition: {bad}"
    assert len(data["components"]) == data["component_count"]


def test_gate_rejects_a_closed_finding_with_no_closure_block(ledgers_restored):
    """A status anybody can assert and nobody can check is the defect, restated."""
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    # Built rather than borrowed from the register. This used to take the first finding
    # that was still open, which made the test depend on remediation being unfinished: it
    # stopped being able to run on the day it had the most to prove.
    target = dict(data["findings"][0])
    target["id"] = "P0-GATE-SELFTEST"
    target["current_status"] = "CLOSED"
    target.pop("closure", None)
    data["findings"].append(target)
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert target["id"] in result.stderr
    assert "no closure block" in result.stderr


def test_gate_rejects_a_closure_that_names_no_tests(ledgers_restored):
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if f.get("current_status") == "CLOSED")
    target["closure"]["verified_by"] = []
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "verified_by" in result.stderr


def test_gate_rejects_a_closure_citing_a_file_that_does_not_exist(ledgers_restored):
    """A closure that points at nothing is worse than an open finding."""
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if f.get("current_status") == "CLOSED")
    target["closure"]["changed"] = ["backend/van_gateway/imaginary_module.py"]
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "imaginary_module.py" in result.stderr


def test_gate_rejects_an_unexplained_residual(ledgers_restored):
    """Naming what is left undone is only honest if it says why."""
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if f.get("current_status") == "CLOSED")
    target["closure"]["residual"] = "the edge is not done"
    target["closure"].pop("residual_reason", None)
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "residual" in result.stderr


def test_gate_rejects_a_forbidden_route_registration(tmp_path, monkeypatch):
    """The route itself must fail, and a comment about it must not."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("maturity_gate_probe", GATE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["maturity_gate_probe"] = module
    spec.loader.exec_module(module)

    app_file = tmp_path / "app.py"
    monkeypatch.setattr(
        module, "FORBIDDEN_PRODUCTION_ROUTES", (("/v1/google/test-transport", app_file),)
    )

    app_file.write_text(
        '    # /v1/google/test-transport was deleted under P2-SEC-009 and must not return.\n',
        encoding="utf-8",
    )
    assert module.check_forbidden_routes() == [], (
        "an explanation of why a route is gone must not be mistaken for the route"
    )

    app_file.write_text(
        '    @app.post("/v1/google/test-transport")\n    async def swap(): ...\n',
        encoding="utf-8",
    )
    problems = module.check_forbidden_routes()
    assert problems and "test-transport" in problems[0]


def test_the_real_application_does_not_register_the_deleted_route():
    """Asserted against the production file, not a fixture."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("maturity_gate_real", GATE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["maturity_gate_real"] = module
    spec.loader.exec_module(module)

    assert module.check_forbidden_routes() == []


def test_gate_rejects_a_closure_that_does_not_say_what_kind_of_closed(ledgers_restored):
    """CLOSED alone is the collapse the audit forbids one level down.

    A finding whose remediation shipped, one whose subject was deleted, and one the
    repository has finished but cannot finish alone are three different outcomes.
    """
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if f.get("current_status") == "CLOSED")
    target["closure"].pop("state", None)
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "state" in result.stderr


def test_gate_rejects_an_invented_terminal_state(ledgers_restored):
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if f.get("current_status") == "CLOSED")
    target["closure"]["state"] = "MOSTLY_DONE"
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "MOSTLY_DONE" in result.stderr


def test_gate_rejects_a_residual_with_no_class(ledgers_restored):
    """Unfinished work and a deliberate boundary read identically in prose."""
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if f["closure"].get("residual"))
    target["closure"].pop("residual_class", None)
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert "residual_class" in result.stderr


def test_gate_rejects_a_blocked_residual_reported_as_integrated(ledgers_restored):
    """The claim that matters: can VAN finish this by itself or not."""
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(
        f for f in data["findings"]
        if f["closure"].get("residual_class") in {
            "EXTERNAL_ARTEFACT", "EXTERNAL_RUNTIME",
            "ENVIRONMENT_UNVERIFIED", "OWNER_DEPLOYMENT_DECISION",
        }
    )
    target["closure"]["state"] = "INTEGRATED_AND_EVIDENCED"
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert target["id"] in result.stderr


def test_gate_rejects_claiming_blocked_while_naming_no_blocker(ledgers_restored):
    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    target = next(f for f in data["findings"] if not f["closure"].get("residual"))
    target["closure"]["state"] = "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE"
    FINDINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_gate()
    assert result.returncode == 1
    assert target["id"] in result.stderr

