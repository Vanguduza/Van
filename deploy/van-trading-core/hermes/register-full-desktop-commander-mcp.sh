#!/usr/bin/env bash
# Registers the full Trading Core Desktop Commander as a Hermes subordinate.
# The existing van_trading_commander remains the bounded VATI/domain commander.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_CONFIG="${HERMES_CONFIG:-$HERMES_HOME/config.yaml}"
VAN_REPO="${VAN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
DIAL_REPO="${DIAL_REPO:-$HOME/dial-new}"
[[ -f "$DIAL_REPO/agent-system/orchestration/hermes-commander-gateway.mjs" ]] || DIAL_REPO="/opt/dial/dial-new"
GATEWAY="$DIAL_REPO/agent-system/orchestration/hermes-commander-gateway.mjs"
WRAPPER="$VAN_REPO/deploy/van-trading-core/hermes/van-trading-full-commander-stdio.sh"
DRY_RUN=0; [[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ "$(hostname)" == "${DIAL_HERMES_HOST_ID:-dial-hermes-control}" ]] || fail "must run on dial-hermes-control"
command -v node >/dev/null 2>&1 || fail "node is required"
python3 -c 'import yaml' 2>/dev/null || fail "python3 PyYAML is required"
[[ -f "$HERMES_CONFIG" ]] || fail "Hermes config not found"
[[ -f "$GATEWAY" ]] || fail "DIAL Commander authority gateway missing: $GATEWAY"
[[ -x "$WRAPPER" ]] || fail "Trading Commander SSH stdio wrapper missing/executable: $WRAPPER"

VAN_DRY_RUN="$DRY_RUN" python3 - "$HERMES_CONFIG" "$GATEWAY" "$WRAPPER" <<'PY'
import os,re,sys,shutil,tempfile,datetime,yaml
path,gateway,wrapper=sys.argv[1:4]
dry=os.environ.get('VAN_DRY_RUN')=='1'
KEY,PARENT='van_trading_local_commander','mcp_servers'
spec={
  'command':'node',
  'args':[gateway,'--commander-id','van_trading_local_commander'],
  'env':{'DIAL_LOCAL_COMMANDER_WRAPPER':wrapper},
  'enabled':True,
  'connect_timeout':20,
  'timeout':600,
  'supports_parallel_tool_calls':False,
}
def indent_of(line): return len(line)-len(line.lstrip(' '))
def is_blank(line): return line.strip()=='' or line.lstrip().startswith('#')
def render(indent):
  body=yaml.safe_dump({KEY:spec},sort_keys=False,default_flow_style=False,width=10**6)
  pad=' '*indent
  return ''.join(pad+l if l.strip() else l for l in body.splitlines(keepends=True))
def splice(text):
  lines=text.splitlines(keepends=True)
  if lines and not lines[-1].endswith('\n'): lines[-1]+='\n'
  pi=next((i for i,l in enumerate(lines) if re.match(r'^%s\s*:'%PARENT,l)),None)
  if pi is None:
    sep='' if (not lines or lines[-1].strip()=='') else '\n'
    return ''.join(lines)+sep+'%s:\n'%PARENT+render(2)
  m=re.match(r'^(%s\s*:)([^\n]*)\n$'%PARENT,lines[pi]); tail=m.group(2).strip() if m else ''
  if tail in ('{}','~','null',''): lines[pi]='%s:\n'%PARENT
  elif not tail.startswith('#'): sys.exit('ERROR: unsupported inline mcp_servers value')
  end=pi+1
  while end<len(lines) and (is_blank(lines[end]) or indent_of(lines[end])>0): end+=1
  while end>pi+1 and is_blank(lines[end-1]): end-=1
  child=next((indent_of(l) for l in lines[pi+1:end] if not is_blank(l)),2)
  ki=next((i for i in range(pi+1,end) if indent_of(lines[i])==child and re.match(r'^\s*%s\s*:'%KEY,lines[i])),None)
  block=render(child)
  if ki is None: return ''.join(lines[:end])+block+''.join(lines[end:])
  ke=ki+1
  while ke<end and (is_blank(lines[ke]) or indent_of(lines[ke])>child): ke+=1
  return ''.join(lines[:ki])+block+''.join(lines[ke:])
original=open(path,encoding='utf-8').read()
before=yaml.safe_load(original) or {}
if not isinstance(before,dict): sys.exit('ERROR: config root is not a mapping')
updated=splice(original)
after=yaml.safe_load(updated) or {}
if (after.get(PARENT) or {}).get(KEY)!=spec: sys.exit('ERROR: post-splice verification failed')
if {k:v for k,v in before.items() if k!=PARENT}!={k:v for k,v in after.items() if k!=PARENT}: sys.exit('ERROR: unrelated config changed')
if {k:v for k,v in (before.get(PARENT) or {}).items() if k!=KEY}!={k:v for k,v in (after.get(PARENT) or {}).items() if k!=KEY}: sys.exit('ERROR: sibling MCP changed')
if updated==original: print('van_trading_local_commander already configured'); sys.exit(0)
if dry: print('DRY RUN: would register full Trading Commander'); sys.exit(0)
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup='%s.van-full-commander-bak-%s'%(path,stamp)
shutil.copy2(path,backup); os.chmod(backup,0o600)
st=os.stat(path); fd,tmp=tempfile.mkstemp(prefix='.config.yaml.',dir=os.path.dirname(path) or '.',text=True)
try:
  with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(updated); f.flush(); os.fsync(f.fileno())
  os.chmod(tmp,st.st_mode & 0o7777)
  try: os.chown(tmp,st.st_uid,st.st_gid)
  except PermissionError: pass
  os.replace(tmp,path)
finally:
  if os.path.exists(tmp): os.unlink(tmp)
print('Registered van_trading_local_commander. Rollback: cp %s %s'%(backup,path))
PY
