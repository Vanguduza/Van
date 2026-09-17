#!/usr/bin/env bash
# Registers the Van trading commander as a Hermes subordinate MCP on dial-hermes-control.
# Splices exactly one block (mcp_servers.van_trading_commander) into the live ~/.hermes/config.yaml,
# preserving every other byte (comments, anchors), verifying the result before writing and
# taking a 0600 backup. Ported from DIAL's install-hermes-local-mcp-plane.sh. Idempotent; --dry-run.
set -euo pipefail
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_CONFIG="${HERMES_CONFIG:-$HERMES_HOME/config.yaml}"
VAN_REPO="${VAN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
COMMANDER_URL="${COMMANDER_URL:-https://10.0.1.233:9133}"
TOKEN_FILE="${TOKEN_FILE:-$HOME/.van/commander.token}"
CA_FILE="${CA_FILE:-$HOME/.van/van-trading-bridge-ca.crt}"
DRY_RUN=0; [[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1
fail() { echo "ERROR: $*" >&2; exit 1; }
command -v node >/dev/null || fail "node is required on the Hermes host"
python3 -c 'import yaml' 2>/dev/null || fail "python3 PyYAML is required (apt-get install -y python3-yaml)"
[[ -f "$HERMES_CONFIG" ]] || fail "Hermes config not found: $HERMES_CONFIG"
[[ -f "$VAN_REPO/trading/commander/mcp_stdio.mjs" ]] || fail "shim not found under $VAN_REPO"
if [[ ! -f "$TOKEN_FILE" ]]; then echo "NOTE: token file $TOKEN_FILE missing; copy /opt/van-trading/secrets/commander.token from van-trading-core (mode 0600) before Hermes can call the commander." >&2; fi
VAN_DRY_RUN="$DRY_RUN" python3 - "$HERMES_CONFIG" "$VAN_REPO" "$COMMANDER_URL" "$TOKEN_FILE" "$CA_FILE" <<'PY'
import os, re, sys, shutil, tempfile, datetime, yaml
path, repo, url, token_file, ca_file = sys.argv[1:6]
dry = os.environ.get('VAN_DRY_RUN') == '1'
KEY, PARENT = 'van_trading_commander', 'mcp_servers'
spec = {
    'command': 'node', 'args': [os.path.join(repo, 'trading/commander/mcp_stdio.mjs')], 'cwd': repo,
    'env': {'VAN_COMMANDER_URL': url, 'VAN_COMMANDER_TOKEN_FILE': token_file, 'NODE_EXTRA_CA_CERTS': ca_file},
    'enabled': True, 'connect_timeout': 20, 'timeout': 120, 'supports_parallel_tool_calls': False,
    'tools': {'include': ['status', 'ledger_status', 'services', 'restart_service', 'tail_log', 'run_backtest', 'vekl_resolve', 'halt', 'doctor', 'accounts'], 'resources': False, 'prompts': False},
}
def indent_of(line): return len(line) - len(line.lstrip(' '))
def is_blank(line): return line.strip() == '' or line.lstrip().startswith('#')
def render(indent):
    body = yaml.safe_dump({KEY: spec}, sort_keys=False, default_flow_style=False, width=10**6)
    pad = ' ' * indent
    return ''.join(pad + l if l.strip() else l for l in body.splitlines(keepends=True))
def splice(text):
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'): lines[-1] += '\n'
    pi = next((i for i, l in enumerate(lines) if re.match(r'^%s\s*:' % PARENT, l)), None)
    if pi is None:
        sep = '' if (not lines or lines[-1].strip() == '') else '\n'
        return ''.join(lines) + sep + '%s:\n' % PARENT + render(2)
    m = re.match(r'^(%s\s*:)([^\n]*)\n$' % PARENT, lines[pi]); tail = m.group(2).strip() if m else ''
    if tail in ('{}', '~', 'null', ''): lines[pi] = '%s:\n' % PARENT
    elif not tail.startswith('#'): sys.exit('ERROR: %s has an unsupported inline value: %r' % (PARENT, tail))
    end = pi + 1
    while end < len(lines) and (is_blank(lines[end]) or indent_of(lines[end]) > 0): end += 1
    while end > pi + 1 and is_blank(lines[end - 1]): end -= 1
    child = next((indent_of(l) for l in lines[pi + 1:end] if not is_blank(l)), 2)
    ki = next((i for i in range(pi + 1, end) if indent_of(lines[i]) == child and re.match(r'^\s*%s\s*:' % KEY, lines[i])), None)
    block = render(child)
    if ki is None: return ''.join(lines[:end]) + block + ''.join(lines[end:])
    ke = ki + 1
    while ke < end and (is_blank(lines[ke]) or indent_of(lines[ke]) > child): ke += 1
    return ''.join(lines[:ki]) + block + ''.join(lines[ke:])
original = open(path, encoding='utf-8').read()
try: before = yaml.safe_load(original) or {}
except Exception as exc: sys.exit('ERROR: refusing to touch unparseable Hermes config: %s' % exc)
if not isinstance(before, dict): sys.exit('ERROR: Hermes config root is not a mapping')
updated = splice(original)
after = yaml.safe_load(updated) or {}
if (after.get(PARENT) or {}).get(KEY) != spec: sys.exit('ERROR: post-splice verification failed; config left untouched')
if {k: v for k, v in before.items() if k != PARENT} != {k: v for k, v in after.items() if k != PARENT}: sys.exit('ERROR: splice altered unrelated configuration; config left untouched')
if {k: v for k, v in (before.get(PARENT) or {}).items() if k != KEY} != {k: v for k, v in (after.get(PARENT) or {}).items() if k != KEY}: sys.exit('ERROR: splice altered sibling MCP servers; config left untouched')
if updated == original: print('Hermes config already carries van_trading_commander; no change.'); sys.exit(0)
if dry: print('DRY RUN: would add/refresh %s.%s in %s (no write performed).' % (PARENT, KEY, path)); sys.exit(0)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'); backup = '%s.van-bak-%s' % (path, stamp)
shutil.copy2(path, backup); os.chmod(backup, 0o600)
st = os.stat(path); fd, tmp = tempfile.mkstemp(prefix='.config.yaml.', dir=os.path.dirname(path) or '.', text=True)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f: f.write(updated); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp, st.st_mode & 0o7777)
    try: os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError: pass
    os.replace(tmp, path)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
print('Hermes config updated. Rollback: cp %s %s' % (backup, path))
PY
