"""PRE-001 (VAN-PKT-001) oracle regression: the judge and trace check must reject each induced
failure class, and the committed artefacts must still describe the registries they came from.

Full regeneration (`tools/rebuild/pre001.py check`) needs the unshallowed Git history and takes
about a minute, so it is run as a separate step; this suite covers the oracles themselves.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pre001", ROOT / "tools/rebuild/pre001.py")
pre001 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre001)


def test_every_induced_failure_is_rejected(capsys):
    assert pre001.cmd_selftest() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] == report["total"] == 10


def test_committed_trace_check_matches_current_registries():
    committed = json.loads((pre001.OUT / "TRACE_CHECK.json").read_text())
    assert committed == pre001.trace_check(pre001.PKG)
    assert committed["counts"]["acceptance_identities"] == 1610
    assert committed["counts"]["requirements"] == 324


def test_status_stays_open_while_rows_are_undisposed():
    status = json.loads((pre001.OUT / "STATUS.json").read_text())
    if status["source_unclassified"]["count"] or status["refs_open"]["count"] or status["overlap_open"]["count"]:
        assert status["status"] == "OPEN"
