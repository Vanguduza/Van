#!/usr/bin/env bash
set -uo pipefail

INSTALL_ROOT="${CHARACTER_FORGE_INSTALL_ROOT:-/opt/dial-character-forge}"
STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
FORGE_USER="${CHARACTER_FORGE_USER:-vanforge}"
WORKSPACE="${CHARACTER_FORGE_WORKSPACE:-$STATE_ROOT/work/Van}"
EXPECTED_SHA="${VAN_COMMIT_SHA:-}"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$INSTALL_ROOT/android-sdk}"
AVD_NAME="${CHARACTER_FORGE_AVD_NAME:-van-character-forge-api31}"
ANDROID_USER_HOME="${CHARACTER_FORGE_ANDROID_USER_HOME:-$STATE_ROOT/.android}"
ANDROID_AVD_HOME="${CHARACTER_FORGE_ANDROID_AVD_HOME:-$ANDROID_USER_HOME/avd}"
PY_VENV="$INSTALL_ROOT/venv"
RIVE_HOME="$STATE_ROOT/rive-home"
JAVA_HOME="${CHARACTER_FORGE_JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

checks=()
fails=0

as_forge() {
  if [[ "$(id -u)" -eq "$(id -u "$FORGE_USER")" ]]; then
    "$@"
  else
    runuser -u "$FORGE_USER" -- "$@"
  fi
}

add() {
  local name="$1" status="$2" detail="$3"
  checks+=("{\"check\":\"$name\",\"status\":\"$status\",\"detail\":$(printf '%s' "$detail" | jq -Rs .)}")
  [[ "$status" == "GREEN" ]] || fails=$((fails+1))
}

[[ "$(uname -m)" == "x86_64" ]] && add arch GREEN x86_64 || add arch RED "$(uname -m)"

if [[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  add expected_sha GREEN "$EXPECTED_SHA"
else
  add expected_sha RED "VAN_COMMIT_SHA missing/invalid"
fi

if [[ -d "$WORKSPACE/.git" ]]; then
  observed="$(as_forge git -C "$WORKSPACE" rev-parse HEAD 2>/dev/null || true)"
  dirty="$(as_forge git -C "$WORKSPACE" status --porcelain 2>/dev/null || true)"
  if [[ "$observed" == "$EXPECTED_SHA" && -z "$dirty" ]]; then
    add repository GREEN "$observed clean"
  else
    add repository RED "observed=$observed dirty_lines=$(wc -l <<<"$dirty")"
  fi
else
  add repository RED "workspace missing"
fi

if command -v rive >/dev/null 2>&1 && as_forge env HOME="$RIVE_HOME" rive --help >/tmp/van-rive-help.txt 2>&1; then
  add rive_cli GREEN "$(as_forge env HOME="$RIVE_HOME" rive --version 2>&1 | head -n1 || true)"
else
  add rive_cli RED "$(tail -c 500 /tmp/van-rive-help.txt 2>/dev/null)"
fi

command -v inkscape >/dev/null 2>&1 \
  && add inkscape GREEN "$(inkscape --version | head -n1)" \
  || add inkscape RED missing

if [[ -x "$PY_VENV/bin/python" ]] && "$PY_VENV/bin/python" -c 'import vtracer, rembg, PIL' >/dev/null 2>&1; then
  add image_prep GREEN "vtracer/rembg/Pillow import"
else
  add image_prep RED "Python image lane broken"
fi

if find "$STATE_ROOT/rembg" -type f -iname '*birefnet*' -print -quit 2>/dev/null | grep -q .; then
  add birefnet GREEN "model cached"
else
  add birefnet RED "birefnet-general not cached"
fi

command -v ffmpeg >/dev/null 2>&1 && command -v convert >/dev/null 2>&1 \
  && add evidence_media GREEN "ffmpeg + ImageMagick" \
  || add evidence_media RED missing

command -v blender >/dev/null 2>&1 \
  && add blender GREEN "$(blender --version 2>/dev/null | head -n1)" \
  || add blender RED missing

command -v google-chrome >/dev/null 2>&1 \
  && add web_editor_lane GREEN "$(google-chrome --version)" \
  || add web_editor_lane RED missing

"$JAVA_HOME/bin/java" -version >/tmp/van-java.txt 2>&1
if [[ -x "$JAVA_HOME/bin/java" ]] && grep -q '"17\.' /tmp/van-java.txt; then
  add java17 GREEN "$(head -n1 /tmp/van-java.txt)"
else
  add java17 RED "$(head -n1 /tmp/van-java.txt 2>/dev/null)"
fi

if [[ -x "$ANDROID_SDK_ROOT/platform-tools/adb" && -x "$ANDROID_SDK_ROOT/emulator/emulator" ]]; then
  add android_sdk GREEN "adb + emulator"
else
  add android_sdk RED missing
fi

if as_forge env ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME" "$ANDROID_SDK_ROOT/emulator/emulator" -list-avds 2>/dev/null | grep -Fxq "$AVD_NAME"; then
  add api31_avd GREEN "$AVD_NAME"
else
  add api31_avd RED "AVD missing"
fi

if [[ -e /dev/kvm ]]; then
  add kvm GREEN "/dev/kvm present"
else
  checks+=("{\"check\":\"kvm\",\"status\":\"WARN\",\"detail\":\"/dev/kvm absent; Commander will use software emulator acceleration\"}")
fi

if as_forge env HOME="$RIVE_HOME" rive --help >/tmp/van-rive-authoring.txt 2>&1; then
  add rive_authoring_surface GREEN "Rive CLI help reachable for Commander-driven authoring"
else
  add rive_authoring_surface RED "$(tail -c 500 /tmp/van-rive-authoring.txt 2>/dev/null)"
fi

if as_forge env \
  CHARACTER_FORGE_STATE_ROOT="$STATE_ROOT" \
  RIVE_HOME="$RIVE_HOME" \
  /usr/local/libexec/van-character-forge-rive-smoke >/tmp/van-rive-smoke.json 2>/tmp/van-rive-smoke.err; then
  add rive_authoring_smoke GREEN "$(jq -c '{rive_version,built_riv_sha256,project_scaffold_state_machine,state_machine_bool_schema,state_machine_trigger_schema}' /tmp/van-rive-smoke.json)"
else
  add rive_authoring_smoke RED "$(tail -c 800 /tmp/van-rive-smoke.err 2>/dev/null)"
fi

if as_forge /usr/local/libexec/van-character-forge-worker doctor >/tmp/van-forge-worker.txt 2>&1; then
  add commander_worker GREEN "$(tail -n1 /tmp/van-forge-worker.txt)"
else
  add commander_worker RED "$(tail -c 500 /tmp/van-forge-worker.txt 2>/dev/null)"
fi

if [[ -s "$STATE_ROOT/toolchain.lock.json" ]] && jq -e '.rive_cli.version and .rive_cli.archive_sha256 and .android.avd' "$STATE_ROOT/toolchain.lock.json" >/dev/null 2>&1; then
  locked_rive="$(jq -r '.rive_cli.version' "$STATE_ROOT/toolchain.lock.json")"
  reported_rive="$(as_forge env HOME="$RIVE_HOME" rive --version 2>&1 | head -n1 || true)"
  if [[ "$reported_rive" == *"$locked_rive"* ]]; then
    add toolchain_lock GREEN "$STATE_ROOT/toolchain.lock.json"
  else
    add toolchain_lock RED "Rive lock/version mismatch: lock=$locked_rive observed=$reported_rive"
  fi
else
  add toolchain_lock RED missing
fi

status=GREEN
(( fails )) && status=RED
checks_json="[$(IFS=,; echo "${checks[*]}")]"
jq -n \
  --arg status "$status" \
  --arg host "$(hostname)" \
  --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson failures "$fails" \
  --argjson checks "$checks_json" \
  '{status:$status,host:$host,required_failures:$failures,at:$at,checks:$checks}'

(( fails == 0 ))
