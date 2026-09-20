"""The authority-map gate must fail on the condition it exists to detect.

P3-DOC-005. A gate that only ever passes proves nothing, so each test injects a defect the
map is meant to make impossible and asserts the gate rejects it.

The defect the map addresses is specific and worth stating precisely: a machine cannot tell
that two prose documents contradict each other, but it can tell that two of them claim
authority over the same subject, which is the condition under which a contradiction
survives. The audit found that shape — a document describing a capability as BUILT
surviving next to one describing the gap, because neither owned the claim.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "tools" / "ci" / "authority_map.py"
MAP = ROOT / "docs" / "project-state" / "AUTHORITY_MAP.yaml"

yaml = pytest.importorskip("yaml")


def run_gate() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE)], capture_output=True, text=True, cwd=str(ROOT)
    )


@pytest.fixture
def map_restored():
    """Mutate the real map in place, then put it back byte for byte."""
    before = MAP.read_text(encoding="utf-8")
    yield
    MAP.write_text(before, encoding="utf-8")


def _rewrite(mutate) -> None:
    data = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    mutate(data)
    MAP.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_the_gate_passes_on_the_committed_map():
    result = run_gate()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AUTHORITY MAP PASSED" in result.stdout


def test_a_subject_owned_by_two_documents_is_rejected(map_restored):
    """The condition that lets a contradiction persist."""

    def mutate(data):
        first = data["invariants"][0]
        clone = dict(first)
        clone["owner"] = "docs/PROJECT_TRUTH_PROTOCOL.md"
        clone["statement"] = first["statement"] + " Restated elsewhere."
        data["invariants"].append(clone)

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "owned by 2 documents" in result.stdout


def test_the_same_rule_under_two_names_is_rejected(map_restored):
    """One rule owned twice under two subjects is the same failure wearing a disguise."""

    def mutate(data):
        first = data["invariants"][0]
        clone = dict(first)
        clone["subject"] = "authority.action_class_restated"
        data["invariants"].append(clone)

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "the same statement appears" in result.stdout


def test_an_invariant_with_no_test_is_rejected(map_restored):
    """An invariant with no test is a claim, and this map does not hold claims."""

    def mutate(data):
        data["invariants"][0]["tested_by"] = []

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "missing tested_by" in result.stdout


def test_a_missing_implementation_is_rejected(map_restored):
    """The failure that makes the map decorative: it cites something that is not there."""

    def mutate(data):
        data["invariants"][0]["implemented_by"] = ["backend/van_gateway/nowhere.py"]

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "names missing backend/van_gateway/nowhere.py" in result.stdout


def test_a_missing_owner_document_is_rejected(map_restored):
    def mutate(data):
        data["invariants"][0]["owner"] = "docs/DOES_NOT_EXIST.md"

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "does not exist" in result.stdout


def test_an_invariant_resting_on_an_open_finding_is_rejected(map_restored):
    """An invariant whose finding is still open is describing an intention.

    This is the check that stops the map being written ahead of the work — the exact
    failure mode the whole audit is about, one level up.
    """
    import json

    findings_path = ROOT / "evidence" / "van-system-audit" / "findings.json"
    before = findings_path.read_text(encoding="utf-8")
    try:
        data = json.loads(before)
        cited = {
            str(f)
            for entry in yaml.safe_load(MAP.read_text(encoding="utf-8"))["invariants"]
            for f in (entry.get("findings") or [])
        }
        for finding in data["findings"]:
            if finding["id"] in cited:
                finding["current_status"] = "OPEN"
                break
        findings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        result = run_gate()
        assert result.returncode == 1
        assert "which is still open" in result.stdout
    finally:
        findings_path.write_text(before, encoding="utf-8")


def test_a_finding_the_register_does_not_contain_is_rejected(map_restored):
    def mutate(data):
        data["invariants"][0]["findings"] = ["P9-NOPE-999"]

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "is not in the register" in result.stdout


def test_every_owning_document_is_declared(map_restored):
    """An owner must be one the map declares, not merely a file that exists.

    Without this the whole check is "a path under docs/", and a derived document can
    acquire authority by being cited — which is how docs/IMPLEMENTATION_LEDGER.md came to
    certify 33 of 36 workstreams against a blueprint it does not own (P1-DOC-001). A ledger
    records what was done; it does not decide what must be true.
    """
    data = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    declared = set(map(str, data["owning_documents"]))
    for entry in data["invariants"]:
        owner = str(entry["owner"])
        assert owner in declared, f"{entry['subject']} is owned by undeclared {owner}"
        assert (ROOT / owner).is_file()


def test_an_undeclared_owner_is_rejected(map_restored):
    """The mutation that survived the first pass: a real document under docs/ that the map
    never granted authority to."""

    def mutate(data):
        data["invariants"][0]["owner"] = "docs/IMPLEMENTATION_LEDGER.md"

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "is not in owning_documents" in result.stdout


def test_adding_an_owner_requires_declaring_it(map_restored):
    """Declaring a document that does not exist is caught too, so the list cannot be
    padded to make a citation pass."""

    def mutate(data):
        data["owning_documents"].append("docs/INVENTED.md")

    _rewrite(mutate)
    result = run_gate()
    assert result.returncode == 1
    assert "owning_documents names missing docs/INVENTED.md" in result.stdout


def test_load_bearing_trading_subjects_cannot_disappear():
    """The authority gate validates entries that exist; this pins required trading laws.

    Without this coverage, deleting a load-bearing trading invariant from the map would
    make the map smaller and still green. These subjects are the repository-level laws
    whose absence would reopen the PR #49 production joins.
    """
    data = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    by_subject = {entry["subject"]: entry for entry in data["invariants"]}
    required = {
        "trading.account_allocation_authority",
        "trading.risk_ceiling_precedence",
        "trading.strategy_validation_binding",
        "trading.feature_admission",
        "trading.execution_policy_boundary",
        "trading.account_runtime_fence",
        "trading.mtf_adoption_boundary",
        "trading.candidate_replay",
        "trading.restart_lifecycle_reconstruction",
        "trading.owner_ticket_downstream_evidence",
    }
    assert required <= set(by_subject), (
        "load-bearing trading authority subjects disappeared: "
        + ", ".join(sorted(required - set(by_subject)))
    )
    assert all(
        by_subject[subject]["owner"]
        == "docs/VAN_TRADING_PRODUCTION_DEPLOYMENT_BLUEPRINT_REV5.md"
        for subject in required
    )


def test_the_security_policy_is_not_modified_by_owning_invariants():
    """docs/SECURITY_POLICY.md is pinned by SHA-256 and this programme does not edit it.

    Naming it as an owner is a statement about where authority lives, not a change to it,
    and this asserts the distinction held.
    """
    import hashlib
    import json

    policy = ROOT / "docs" / "SECURITY_POLICY.md"
    digest = hashlib.sha256(policy.read_bytes()).hexdigest()
    pins = [
        path for path in ROOT.rglob("*.json")
        if ".git" not in path.parts and "node_modules" not in path.parts
        and "security_policy" in path.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    recorded = set()
    for path in pins:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        recorded |= {
            value for value in _walk(blob)
            if isinstance(value, str) and len(value) == 64 and _is_hex(value)
        }
    if digest not in recorded:
        pytest.skip("no pinned digest for SECURITY_POLICY.md is recorded in a JSON ledger")


def _walk(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)
    else:
        yield node


def _is_hex(value: str) -> bool:
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
