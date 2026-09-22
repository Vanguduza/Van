#!/usr/bin/env bash
# Register VAN owner-runtime typed MCP into live Hermes config.
# Idempotent, fail-closed, secret-safe, and preserves sibling configuration.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_CONFIG="${HERMES_CONFIG:-$HERMES_HOME/config.yaml}"
PROFILE_ROOT="${HERMES_HOME}/profiles/van"
SHIM="${PROFILE_ROOT}/mcp/owner_runtime_stdio.mjs"
OWNER_RUNTIME_URL="${VAN_OWNER_RUNTIME_URL:-http://127.0.0.1:8787}"
GATEWAY_ENV_FILE="${VAN_GATEWAY_ENV_FILE:-$HOME/.config/van/gateway.env}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

fail() { echo "ERROR: $*" >&2; exit 1; }
command -v node >/dev/null || fail "node is required on the Hermes host"
python3 -c 'import yaml' 2>/dev/null || fail "python3 PyYAML is required"
[[ -f "$HERMES_CONFIG" ]] || fail "Hermes config not found: $HERMES_CONFIG"
[[ -f "$SHIM" ]] || fail "owner-runtime MCP shim not installed: $SHIM"
[[ -f "$GATEWAY_ENV_FILE" ]] || fail "gateway env file not found: $GATEWAY_ENV_FILE"
grep -q '^VAN_INTERNAL_CONTROL_TOKEN=' "$GATEWAY_ENV_FILE" || fail "VAN_INTERNAL_CONTROL_TOKEN missing from gateway env file"

VAN_DRY_RUN="$DRY_RUN" python3 - "$HERMES_CONFIG" "$PROFILE_ROOT" "$SHIM" "$OWNER_RUNTIME_URL" "$GATEWAY_ENV_FILE" <<'PY'
import datetime
import os
import re
import shutil
import sys
import tempfile
import yaml

path, profile_root, shim, url, gateway_env = sys.argv[1:6]
dry = os.environ.get("VAN_DRY_RUN") == "1"
PARENT = "mcp_servers"
KEY = "van_owner_runtime"
spec = {
    "command": "node",
    "args": [shim],
    "cwd": profile_root,
    "env": {
        "VAN_OWNER_RUNTIME_URL": url,
        "VAN_GATEWAY_ENV_FILE": gateway_env,
    },
    "enabled": True,
    "connect_timeout": 10,
    "timeout": 120,
    "supports_parallel_tool_calls": False,
    "tools": {
        # Must stay identical to TOOLS in hermes/mcp/owner_runtime_stdio.mjs.
        # tests/contracts/test_owner_runtime_mcp_contract.py asserts the two agree;
        # drift here silently removes capabilities AGENTS.md instructs Hermes to use.
        "include": [
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
            "context_fact_candidate",
            "context_edge_candidate",
            "trading_portfolio",
            "trading_positions",
            "trading_risk",
            "trading_market_state",
            "trading_trade_detail",
            "trading_status",
            "reminder_create",
            "attention_list",
            "briefing_read",
            "browser_task_create",
            "browser_assignment_run",
            "browser_task_status",
            "browser_task_evidence",
            "automation_route",
            "automation_execute",
            "automation_run_status",
        ],
        "resources": False,
        "prompts": False,
    },
    "authority": "SUBORDINATE_CAPABILITY_NOT_TRUTH_AUTHORITY",
}

def indent_of(line):
    return len(line) - len(line.lstrip(" "))

def is_blank(line):
    return line.strip() == "" or line.lstrip().startswith("#")

def render(indent):
    body = yaml.safe_dump({KEY: spec}, sort_keys=False, default_flow_style=False, width=10**6)
    pad = " " * indent
    return "".join(pad + line if line.strip() else line for line in body.splitlines(keepends=True))

def splice(text):
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    parent_index = next((i for i, line in enumerate(lines) if re.match(rf"^{PARENT}\s*:", line)), None)
    if parent_index is None:
        sep = "" if not lines or lines[-1].strip() == "" else "\n"
        return "".join(lines) + sep + f"{PARENT}:\n" + render(2)
    match = re.match(rf"^({PARENT}\s*:)([^\n]*)\n$", lines[parent_index])
    tail = match.group(2).strip() if match else ""
    if tail in ("{}", "~", "null", ""):
        lines[parent_index] = f"{PARENT}:\n"
    elif not tail.startswith("#"):
        sys.exit(f"ERROR: {PARENT} has unsupported inline value: {tail!r}")
    end = parent_index + 1
    while end < len(lines) and (is_blank(lines[end]) or indent_of(lines[end]) > 0):
        end += 1
    while end > parent_index + 1 and is_blank(lines[end - 1]):
        end -= 1
    child_indent = next((indent_of(line) for line in lines[parent_index + 1:end] if not is_blank(line)), 2)
    key_index = next((i for i in range(parent_index + 1, end) if indent_of(lines[i]) == child_indent and re.match(rf"^\s*{KEY}\s*:", lines[i])), None)
    block = render(child_indent)
    if key_index is None:
        return "".join(lines[:end]) + block + "".join(lines[end:])
    key_end = key_index + 1
    while key_end < end and (is_blank(lines[key_end]) or indent_of(lines[key_end]) > child_indent):
        key_end += 1
    return "".join(lines[:key_index]) + block + "".join(lines[key_end:])

original = open(path, encoding="utf-8").read()
try:
    before = yaml.safe_load(original) or {}
except Exception as exc:
    sys.exit(f"ERROR: refusing to touch unparseable Hermes config: {exc}")
if not isinstance(before, dict):
    sys.exit("ERROR: Hermes config root is not a mapping")
updated = splice(original)
after = yaml.safe_load(updated) or {}
if (after.get(PARENT) or {}).get(KEY) != spec:
    sys.exit("ERROR: post-splice verification failed; config left untouched")
if {k: v for k, v in before.items() if k != PARENT} != {k: v for k, v in after.items() if k != PARENT}:
    sys.exit("ERROR: splice altered unrelated configuration; config left untouched")
if {k: v for k, v in (before.get(PARENT) or {}).items() if k != KEY} != {k: v for k, v in (after.get(PARENT) or {}).items() if k != KEY}:
    sys.exit("ERROR: splice altered sibling MCP servers; config left untouched")
if updated == original:
    print("Hermes config already carries van_owner_runtime; no change.")
    sys.exit(0)
if dry:
    print(f"DRY RUN: would add/refresh {PARENT}.{KEY} in {path} (no write performed).")
    sys.exit(0)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = f"{path}.van-owner-runtime-bak-{stamp}"
shutil.copy2(path, backup)
os.chmod(backup, 0o600)
st = os.stat(path)
fd, tmp = tempfile.mkstemp(prefix=".config.yaml.", dir=os.path.dirname(path) or ".", text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(updated)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, st.st_mode & 0o7777)
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print(f"Hermes config updated. Rollback: cp {backup} {path}")
PY
