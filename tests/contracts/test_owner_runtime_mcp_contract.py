from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "hermes" / "mcp" / "owner_runtime_stdio.mjs"
REGISTER = ROOT / "tools" / "hermes" / "register_owner_runtime_mcp.sh"

REQUIRED_TOOLS = {
    "runtime_status",
    "resolve_command",
    "context_graph_query",
    "context_readiness",
    "context_snapshot",
    "research_status",
    "research_search",
    "action_begin",
    "action_submitted",
    "action_verify",
    "action_get",
}


def test_owner_runtime_mcp_has_fixed_narrow_surface():
    text = SHIM.read_text(encoding="utf-8")
    for tool in REQUIRED_TOOLS:
        assert f"name: '{tool}'" in text
    assert "/v1/runtime/context/facts" not in text
    assert "/v1/runtime/context/edges" not in text
    assert "generic HTTP" in text
    assert "Object.hasOwn(ROUTES, name)" in text


def test_owner_runtime_registration_is_secret_safe_and_scoped():
    text = REGISTER.read_text(encoding="utf-8")
    assert 'KEY = "van_owner_runtime"' in text
    assert "SUBORDINATE_CAPABILITY_NOT_TRUTH_AUTHORITY" in text
    assert "VAN_GATEWAY_ENV_FILE" in text
    assert "VAN_INTERNAL_CONTROL_TOKEN missing" in text
    assert "splice altered sibling MCP servers" in text
    assert "--dry-run" in text


def test_owner_runtime_mcp_tools_list_is_parseable_without_network():
    node = shutil.which("node")
    if node is None:
        return
    env = os.environ.copy()
    env["VAN_INTERNAL_CONTROL_TOKEN"] = "contract-test-only"
    requests = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
        "",
    ])
    completed = subprocess.run(
        [node, str(SHIM)],
        input=requests,
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    listed = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert listed == REQUIRED_TOOLS
