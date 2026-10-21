"""AP-001 omission verifier regression: the current package's five acceptance-free gate units
are detected, the proposed patch closes them additively, and every induced failure is caught."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ap001", ROOT / "tools/rebuild/ap001.py")
ap001 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ap001)


def test_current_package_omission_and_patched_view():
    plan, tests = ap001.registries()
    r = ap001.evaluate(plan, tests, ap001.load(ap001.PATCH))
    assert [f.split(":")[1] for f in r["current_package_findings"]] == ["BQ-003", "BQ-004", "QA-002", "QA-003", "REL-002"]
    assert r["patched_clean"], r
    assert r["counts"] == {"before": 1610, "after": 1624}


def test_every_induced_failure_is_detected(capsys):
    assert ap001.cmd_selftest() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] == report["total"] == 13
