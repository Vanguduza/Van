"""PRE-002 challenge dossiers: every active requirement has an author-prepared dossier that is
never labelled admission, committed outputs match the generator, and each challenge fires."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pre002_dossiers", ROOT / "tools/rebuild/pre002_dossiers.py")
dossiers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dossiers)


def test_one_dossier_per_requirement_and_no_drift(capsys):
    assert dossiers.main(["x", "check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["drift"] == []
    src = dossiers.load()
    built = dossiers.build(src)
    assert len(built) == src["authority"]["active_requirement_count"] == len({d["id"] for d in built})
    assert {d["challenge_state"] for d in built} == {dossiers.STATE}
    assert all(len(d["challenge_questions"]) >= len(dossiers.COMMON_QUESTIONS) for d in built)


def test_every_challenge_fires_on_an_induced_defect(capsys):
    assert dossiers.selftest() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] == report["total"] == 11
