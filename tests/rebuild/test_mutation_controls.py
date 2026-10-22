import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_failing_unmutated_control_cannot_count_as_a_caught_mutation(tmp_path, monkeypatch):
    harness = load("mutation_control_test", ROOT / "tools/audit/mutation.py")
    monkeypatch.setattr(harness, "JOURNAL", tmp_path / "journal.json")
    victim = tmp_path / "guard.py"
    victim.write_text("guarded")
    with pytest.raises(RuntimeError, match="BASELINE_TESTS_FAILED"):
        harness.run([("guard.py", "guarded", "unsafe", "removed guard")], [], root=tmp_path,
                    command=[sys.executable, "-c", "raise SystemExit(2)"])
    assert victim.read_text() == "guarded"
    assert not harness.JOURNAL.exists()


@pytest.mark.parametrize("detects_mutation", [True, False])
def test_valid_control_distinguishes_a_killed_mutation_from_a_survivor(tmp_path, monkeypatch, detects_mutation):
    harness = load("mutation_verdict_test", ROOT / "tools/audit/mutation.py")
    monkeypatch.setattr(harness, "JOURNAL", tmp_path / "journal.json")
    victim = tmp_path / "guard.py"
    victim.write_text("guarded")
    code = (f"from pathlib import Path; raise SystemExit(Path({str(victim)!r}).read_text() != 'guarded')"
            if detects_mutation else "raise SystemExit(0)")
    survivors = harness.run([("guard.py", "guarded", "unsafe", "removed guard")], [], root=tmp_path,
                            command=[sys.executable, "-c", code])
    assert survivors == ([] if detects_mutation else ["removed guard"])
    assert victim.read_text() == "guarded"
    assert not harness.JOURNAL.exists()


@pytest.mark.parametrize("defect", [None, "anchor", "source", "test", "noop"])
def test_registry_preflight_is_read_only_and_rejects_invalid_cases(tmp_path, defect):
    checker = load("mutation_registry_test", ROOT / "tools/rebuild/mutation_registry.py")
    victim = tmp_path / "guard.py"
    victim.write_text("guarded")
    test = tmp_path / "test_guard.py"
    test.write_text("def test_guard(): pass")
    old, new = "guarded", "unsafe"
    if defect == "anchor": old = "missing"
    if defect == "source": victim.unlink()
    if defect == "test": test.unlink()
    if defect == "noop": new = old
    report = checker.inspect([(["test_guard.py"], [("guard.py", old, new, "removed guard")], tmp_path, tmp_path)])
    assert report["mutation_count"] == 1
    assert bool(report["findings"]) == (defect is not None)
    assert report["execution_state"] == "NOT_RUN"
    if victim.exists(): assert victim.read_text() == "guarded"
