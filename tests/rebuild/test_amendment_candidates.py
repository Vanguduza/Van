import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("amendment_candidates", ROOT / "tools/rebuild/amendment_candidates.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture(scope="module", params=[(["AP-002"], 1618), (["AP-001", "AP-002"], 1632)])
def candidate(request, tmp_path_factory):
    names, count = request.param
    target = tmp_path_factory.mktemp("amendments") / "package"
    report = module.prepare(target, names)
    assert report["acceptance_count"] == count
    assert report["preservation_findings"] == []
    assert report["removed_files"] == []
    assert all(r["exit"] == 0 for r in report["verifiers"]), report["verifiers"]
    receipt = "CUMULATIVE" if len(names) > 1 else "STANDALONE"
    committed = module.PROPOSALS / "AP-002" / (receipt + "_CANDIDATE_VERIFICATION.json")
    assert json.loads(committed.read_text()) == report
    return target, names


def test_individual_and_cumulative_candidates_preserve_the_original(candidate):
    target, names = candidate
    assert module.audit_candidate(target, names) == []


@pytest.mark.parametrize("mutation,prefix", [
    ("original_test", "ORIGINAL_TEST_CHANGED:"),
    ("new_oracle", "PROPOSED_ORACLE_CHANGED:"),
    ("unit_exit", "UNIT_CONTRACT_CHANGED:"),
    ("lineage", "HISTORICAL_OR_TRACE_SOURCE_CHANGED:"),
    ("fake_signature", "FALSE_SIGNATURE_OR_ADMISSION"),
])
def test_induced_preservation_failures_are_rejected(candidate, mutation, prefix):
    target, names = candidate
    paths = {"original_test": "verification/TEST_CONTRACTS.json",
             "new_oracle": "verification/TEST_CONTRACTS.json", "unit_exit": "plan/DEVELOPMENT_PLAN.json",
             "lineage": "lineage/forecast_rev1_1/plan/REQUIREMENTS.json",
             "fake_signature": "plan/PROPOSED_SCOPE_LOCK.json"}
    path = target / paths[mutation]
    original = path.read_bytes()
    data = json.loads(original)
    if mutation == "original_test": data["tests"][0]["expectation"] = "always pass"
    elif mutation == "new_oracle": data["tests"][-1]["observable"] = "unverified acknowledgment"
    elif mutation == "unit_exit": data["units"][0]["exit_contract"] = "skip review"
    elif mutation == "lineage": data["requirements"][0]["obligation"] = "drop preservation"
    elif mutation == "fake_signature": data["signature"] = "self-issued"
    try:
        path.write_text(json.dumps(data))
        assert any(x.startswith(prefix) for x in module.audit_candidate(target, names))
    finally:
        path.write_bytes(original)


def test_original_package_is_never_a_candidate_output():
    with pytest.raises(ValueError, match="overlap"):
        module.prepare(module.BASE, ["AP-002"])
