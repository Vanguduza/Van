from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "hermes" / "mcp" / "owner_runtime_stdio.mjs"
REGISTER = ROOT / "tools" / "hermes" / "register_owner_runtime_mcp.sh"

REQUIRED_TOOLS = {
    "runtime_status",
    "mission_result",
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
    "google_status",
    "google_capabilities",
    "google_gmail_search",
    "google_calendar_agenda",
    "google_drive_search",
    "google_contacts_resolve",
    "google_tasks_list",
    "google_job_plan",
    "google_action_execute",
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
    assert "/v1/runtime/missions/result" in text
    assert "this tool cannot assert verified success" in text.lower()
    mission_tool = re.search(
        r"name: 'mission_result'.*?additionalProperties: false", text, re.S
    )
    assert mission_tool is not None
    assert "VERIFIED_SUCCESS" not in mission_tool.group(0)
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


def test_registration_include_list_matches_the_shim_exactly():
    """The drift this catches silently removed nine tools from the live Hermes.

    The shim declared 20 tools and the installer registered 11, omitting the whole
    knowledge protocol that AGENTS.md instructs Hermes to use. The previous contract
    test only checked that tool NAMES appeared somewhere in the script text, which the
    drifted version still satisfied. Compare the parsed include list instead.
    """
    shim_tools = set(re.findall(r"\{ name: '([a-z_]+)'", SHIM.read_text(encoding="utf-8")))
    register_text = REGISTER.read_text(encoding="utf-8")
    include_block = re.search(r'"include": \[(.*?)\]', register_text, re.S)
    assert include_block is not None, "registration script has no tools.include list"
    registered = set(re.findall(r'"([a-z_]+)"', include_block.group(1)))

    assert shim_tools == REQUIRED_TOOLS, (
        f"shim tool surface changed; update REQUIRED_TOOLS deliberately. "
        f"only in shim: {sorted(shim_tools - REQUIRED_TOOLS)}, "
        f"only in contract: {sorted(REQUIRED_TOOLS - shim_tools)}"
    )
    assert registered == shim_tools, (
        f"registration drifted from the shim. "
        f"declared but not registered: {sorted(shim_tools - registered)}, "
        f"registered but not declared: {sorted(registered - shim_tools)}"
    )


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

def test_google_mcp_surface_is_read_or_plan_only():
    text = SHIM.read_text(encoding="utf-8")
    for path in (
        "/v1/google/status",
        "/v1/google/capabilities",
        "/v1/google/gmail/search",
        "/v1/google/calendar/agenda",
        "/v1/google/drive/search",
        "/v1/google/contacts/resolve",
        "/v1/google/tasks",
        "/v1/google/jobs/plan",
    ):
        assert path in text
    # Mutating Workspace routes must not be raw MCP tools. They have caller-supplied
    # approval parameters today and therefore need the Action Runtime boundary first.
    assert "/v1/google/gmail/send" not in text
    assert "/v1/google/gmail/draft" not in text
    assert "/v1/google/calendar/reschedule" not in text
    assert "/v1/google/actions/execute" in text
    action_tool = re.search(
        r"name: 'google_action_execute'.*?additionalProperties: false", text, re.S
    )
    assert action_tool is not None
    assert "approved" not in action_tool.group(0).lower()

