"""VTIL borrows DIAL's VEKL resolver unchanged (Rev 2.1 §E.4).

Runs trading/vtil/tools/resolve_probe.mjs, which mirrors the two directory
names DIAL hard-codes and executes DIAL's own resolver against the Van trading
registry. Skipped when Node or a dial-new checkout is unavailable; a skip is
reported, never counted as a pass.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIAL = Path(os.environ.get("DIAL_REPO", ROOT.parent / "dial-new"))
PROBE = ROOT / "trading" / "vtil" / "tools" / "resolve_probe.mjs"
REGISTRY = ROOT / "trading" / "vtil" / "registry"


def test_registry_files_present_in_dial_vekl_layout():
    for name in ("ENGINEERING_RESOURCE_REGISTRY.json", "ENGINEERING_RESOURCE_SOURCE_REGISTRY.json", "ENGINEERING_SKILL_REGISTRY.json", "TASK_CLASS_SIGNAL_POLICY.json"):
        assert (REGISTRY / name).is_file(), name
    sources = json.loads((REGISTRY / "ENGINEERING_RESOURCE_SOURCE_REGISTRY.json").read_text())
    assert all(s["sensitive_data_allowed"] is False for s in sources)
    assert all(s["executable_content_allowed"] is False for s in sources)
    resources = json.loads((REGISTRY / "ENGINEERING_RESOURCE_REGISTRY.json").read_text())
    assert all("PLACE_ORDER" in r["forbidden_effects"] for r in resources if r["resource_class"] != "RULESET")
    assert all(r["activation_mode"] != "EXECUTABLE_CAPABILITY" for r in resources)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(not (DIAL / "agent-system/orchestration/engineering-resource-resolver.mjs").is_file(), reason="dial-new checkout not available (set DIAL_REPO)")
def test_dial_resolver_selects_trading_knowledge_from_van_registry():
    proc = subprocess.run(["node", str(PROBE)], capture_output=True, text=True, env={**os.environ, "DIAL_REPO": str(DIAL)}, timeout=120)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    report = json.loads(proc.stdout)
    assert report["status"] == "GREEN"
    assert report["registry_validation"]["ok"]
    for case in report["cases"]:
        assert case["ok"], case
        assert case["policy_version"] == "vekl-2.1"
        assert "van.trading.rules.rev2-canon" in case["selected"], "T0 trading policy must always bind"
        for cid in case["community_corroboration_only"]:
            assert cid.startswith("community."), cid
