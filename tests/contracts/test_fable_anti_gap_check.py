"""The Fable remediation's anti-gap pass is a command, and it passes.

`tools/audit/fable_anti_gap_check.py` re-reads the tree for every artefact the closure report
(docs/audit/van-fable-whole-project-2026-09-21/VAN_FABLE_IMPLEMENTATION_CLOSURE_REPORT.md §13)
claims for the 28 gaps. Running it here means a later change that deletes one of those
artefacts — a route, an executor, a producer, a CI job — re-opens the gap visibly instead of
leaving the report describing a tree that no longer exists.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "audit" / "fable_anti_gap_check.py"


def test_anti_gap_pass_is_green() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    report = json.loads(proc.stdout)
    failed = [c for c in report["checks"] if not c["ok"]]
    assert proc.returncode == 0 and not failed, failed


def test_every_registered_gap_is_checked() -> None:
    register = json.loads(
        (ROOT / "docs/audit/van-fable-whole-project-2026-09-21/VAN_CANONICAL_GAP_REGISTER.json").read_text()
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"], cwd=ROOT, capture_output=True, text=True, check=False,
    )
    checked = {c["gap"] for c in json.loads(proc.stdout)["checks"]}
    registered = {g["id"] for g in register["gaps"]}
    assert registered <= checked, sorted(registered - checked)
