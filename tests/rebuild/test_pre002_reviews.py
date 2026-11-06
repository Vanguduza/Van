"""PRE-002 author reviews stay consistent with the admitted package: every cited identity and
master section exists, every family registry claim holds per requirement, every owner-question
override names a real pair, and the committed outputs match their generators."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/rebuild" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("tool", ["pre002_neg_review", "pre002_truth_review", "pre002_decisions"])
def test_review_matches_package_and_committed_output(tool, capsys):
    assert load(tool).main(["x", "check"]) == 0, capsys.readouterr().out


def test_neg_review_covers_exactly_the_flagged_set():
    mod = load("pre002_neg_review")
    out, problems = mod.build()
    assert not problems
    assert out["counts"] == {mod.A: 37, mod.G: 6}
    assert all(r["proposed_refinement"] for r in out["reviews"] if r["disposition"] == mod.G)
