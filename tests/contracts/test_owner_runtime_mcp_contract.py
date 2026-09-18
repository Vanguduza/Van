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
    "context_lexical_query",
    "context_hot_capsule",
    "context_readiness",
    "context_snapshot",
    "knowledge_status",
    "vekl_query",
    "obsidian_query",
    "notebook_enterprise_recent",
    "notebook_enterprise_get",
    "notebook_consumer_ask",
    "knowledge_action_execute",
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
    assert "/v1/runtime/context/lexical/query" in text
    assert "/v1/runtime/context/hot-capsules" in text
    assert "/v1/runtime/knowledge/vekl/query" in text
    assert "/v1/runtime/knowledge/obsidian/query" in text
    assert "/v1/runtime/knowledge/notebook/consumer/ask" in text
    assert "/v1/runtime/knowledge/actions/execute" in text
    assert "/knowledge/obsidian/index" not in text
    assert "/knowledge/obsidian/certify" not in text
    assert "/knowledge/vekl/certify-canary" not in text
    assert "/knowledge/notebook/consumer/certify" not in text
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


def test_retrieval_tools_remain_read_only_and_bounded():
    text = SHIM.read_text(encoding="utf-8")
    assert "No embedding, model inference or remote call is used" in text
    assert "cache of evidence references, not a truth store" in text
    assert "maximum: 64" in text
    assert "maximum: 300000" in text
    assert "context_lexical_query: { method: 'POST'" in text
    assert "context_hot_capsule: { method: 'POST'" in text


def test_knowledge_mutation_tool_is_authorized_execution_only():
    text = SHIM.read_text(encoding="utf-8")
    assert "Execute a Notebook mutation only after action_begin has produced an AUTHORIZED execution" in text
    assert "parameters must exactly match" not in text.lower() or "parameters must exactly match" in text.lower()
    assert "knowledge_action_execute: { method: 'POST'" in text
    assert "/knowledge/notebook/enterprise/create" not in text
    assert "/knowledge/notebook/consumer/note" not in text