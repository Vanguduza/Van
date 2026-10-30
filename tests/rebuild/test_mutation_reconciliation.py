import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mutation_reconciliation", ROOT / "tools/rebuild/mutation_reconciliation.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("kind,exit,output,kotlin,expected", [
    ("baseline", 0, "3 passed", False, "PASS"),
    ("baseline", 2, "collection error", False, "INVALID_CONTROL"),
    ("mutation", 0, "3 passed", False, "SURVIVED"),
    ("mutation", 1, "FAILED test_guard.py::test_refusal - AssertionError", False, "ASSERTION_DETECTED"),
    ("mutation", 2, "ERROR test_guard.py", False, "INVALID_EXECUTION"),
    ("mutation", 1, "some unrelated process failure", False, "INVALID_EXECUTION"),
    ("mutation", 1, "SessionTest > refuses unsafe replay FAILED\n123 tests completed, 1 failed", True, "ASSERTION_DETECTED"),
    ("mutation", 1, "compileKotlin FAILED\ne: Unresolved reference", True, "INVALID_EXECUTION"),
    ("mutation", 1, "Gradle could not resolve dependency", True, "INVALID_EXECUTION"),
])
def test_only_executed_assertion_failures_qualify_as_detected_mutations(kind, exit, output, kotlin, expected):
    result = SimpleNamespace(returncode=exit, stdout=output, stderr="")
    assert module.classify(kind, result, kotlin) == expected


def test_all_reference_identities_are_preserved():
    assert module.preservation() == 374
    assert len(module.reference_cases()) == 32


def test_retargeted_python_edits_cannot_claim_syntax_errors_as_invariant_proof(tmp_path):
    (tmp_path / "guard.py").write_text("if True:\n    guard = 1\n")
    with pytest.raises(SyntaxError):
        module.valid_python_edits([("guard.py", "if True:", "if :", "unsafe")], tmp_path)
    assert (tmp_path / "guard.py").read_text() == "if True:\n    guard = 1\n"
