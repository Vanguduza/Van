#!/usr/bin/env bash
set -Eeuo pipefail

STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
RIVE_HOME="${RIVE_HOME:-$STATE_ROOT/rive-home}"
OUT_DIR="${CHARACTER_FORGE_SMOKE_ROOT:-$STATE_ROOT/rive-smoke}"
PROJECT="$OUT_DIR/project"
REPORT="$OUT_DIR/report.json"

export HOME="$RIVE_HOME"
export RIVE_HOME
export RIVE_NO_TUI=1
export TERM=dumb

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

if ! rive create "$PROJECT" >/tmp/van-rive-smoke-create.txt 2>&1; then
  cat /tmp/van-rive-smoke-create.txt >&2 || true
  echo "Rive smoke: project scaffold failed" >&2
  exit 1
fi
[[ -f "$PROJECT/scene.rml" ]] || { echo "Rive smoke: scene.rml missing" >&2; exit 1; }
grep -q '<StateMachine' "$PROJECT/scene.rml" || {
  echo "Rive smoke: scaffold has no state machine" >&2
  exit 1
}

python3 - "$PROJECT/scene.rml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "<StateMachine "
start = text.find(needle)
if start < 0:
    raise SystemExit("Rive smoke: StateMachine opening tag missing")
close = text.find(">", start)
if close < 0:
    raise SystemExit("Rive smoke: malformed StateMachine opening tag")
inputs = """
            <StateMachineBool name="smoke_bool" value="false"/>
            <StateMachineTrigger name="smoke_trigger"/>
"""
text = text[: close + 1] + inputs + text[close + 1 :]
path.write_text(text, encoding="utf-8")
PY

verify_json="$(rive "$PROJECT" --verify --format=json)"
printf '%s
' "$verify_json" | jq -e '.success == true and .command == "verify"' >/dev/null

build_json="$(rive "$PROJECT" --once --format=json)"
riv_path="$(printf '%s
' "$build_json" | jq -r '.data.riv // empty')"
[[ -n "$riv_path" ]] || { echo "Rive smoke: build produced no .riv path" >&2; exit 1; }
if [[ "$riv_path" != /* ]]; then
  riv_path="$PROJECT/$riv_path"
fi
[[ -s "$riv_path" ]] || { echo "Rive smoke: built .riv missing/empty: $riv_path" >&2; exit 1; }

inspect_json="$(rive inspect "$PROJECT" --json)"
printf '%s
' "$inspect_json" | grep -q 'StateMachine' || {
  echo "Rive smoke: inspect output contains no StateMachine" >&2
  exit 1
}
printf '%s
' "$inspect_json" | grep -q 'smoke_bool' || {
  echo "Rive smoke: compiled StateMachineBool input missing from inspect output" >&2
  exit 1
}
printf '%s
' "$inspect_json" | grep -q 'smoke_trigger' || {
  echo "Rive smoke: compiled StateMachineTrigger input missing from inspect output" >&2
  exit 1
}

bool_schema="$(rive schema --search StateMachineBool --json)"
trigger_schema="$(rive schema --search StateMachineTrigger --json)"
printf '%s
' "$bool_schema" | grep -q 'StateMachineBool' || {
  echo "Rive smoke: StateMachineBool schema unavailable" >&2
  exit 1
}
printf '%s
' "$trigger_schema" | grep -q 'StateMachineTrigger' || {
  echo "Rive smoke: StateMachineTrigger schema unavailable" >&2
  exit 1
}

riv_sha="$(sha256sum "$riv_path" | awk '{print $1}')"
jq -n   --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"   --arg version "$(rive --version 2>&1 | head -n1)"   --arg riv "$riv_path"   --arg riv_sha "$riv_sha"   '{
    status:"PASS",
    at:$at,
    rive_version:$version,
    project_scaffold_state_machine:true,
    compiled_boolean_input:"smoke_bool",
    compiled_trigger_input:"smoke_trigger",
    state_machine_bool_schema:true,
    state_machine_trigger_schema:true,
    built_riv:$riv,
    built_riv_sha256:$riv_sha
  }' > "$REPORT"

cat "$REPORT"
