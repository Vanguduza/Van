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
