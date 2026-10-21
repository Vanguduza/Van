from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location(
    "omv_cert", ROOT/"tools"/"certification"/"openmuse_van_convergence.py"
)
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_convergence_repository_certificate_is_green():
    report=MOD.evaluate(ROOT)
    assert report["repository_complete"] is True, report["issues"]
    assert report["issues"]==[]
    assert "QUAL-OMV-002" in report["external_live_gates"]
    assert "QUAL-OMV-007" in report["external_live_gates"]


def test_convergence_certificate_rejects_truth_written_ahead_of_work():
    matrix=__import__("json").loads((ROOT/MOD.MATRIX).read_text())
    broken=copy.deepcopy(matrix)
    broken["packages"][0]["repository_state"]="PLANNED"
    report=MOD.evaluate(ROOT,broken)
    assert "OMV-001:not_repository_complete" in report["issues"]


def test_convergence_certificate_rejects_self_promoted_live_claim():
    matrix=__import__("json").loads((ROOT/MOD.MATRIX).read_text())
    broken=copy.deepcopy(matrix)
    broken["packages"][1]["live_state"]="LIVE_CERTIFIED"
    report=MOD.evaluate(ROOT,broken)
    assert "OMV-002:matrix_may_not_self_promote_live" in report["issues"]
