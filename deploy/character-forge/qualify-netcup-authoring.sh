#!/usr/bin/env bash
set -uo pipefail

INSTALL_ROOT="${CHARACTER_FORGE_INSTALL_ROOT:-/opt/dial-character-forge}"
STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
FORGE_USER="${CHARACTER_FORGE_USER:-vanforge}"
WORKSPACE="${CHARACTER_FORGE_WORKSPACE:-$STATE_ROOT/work/Van}"
EXPECTED_SHA="${VAN_COMMIT_SHA:-}"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$INSTALL_ROOT/android-sdk}"
AVD_NAME="${CHARACTER_FORGE_AVD_NAME:-van-character-forge-api31}"
PY_VENV="$INSTALL_ROOT/venv"
RIVE_HOME="$STATE_ROOT/rive-home"
# STRICT=1 (bootstrap): the checkout must be exactly VAN_COMMIT_SHA and clean. Otherwise
# (Commander `qualify` during authoring) a descendant commit is GREEN and local authoring
# changes are a WARN, so the toolchain can be requalified mid-production.
STRICT="${CHARACTER_FORGE_QUALIFY_STRICT:-0}"
REPORT="${CHARACTER_FORGE_QUALIFY_REPORT:-$STATE_ROOT/qualification.json}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

checks=()
fails=0

# Run as the forge user whether invoked by root (bootstrap) or by vanforge itself (Commander's
# `qualify`, where runuser is not permitted).
as_forge() {
  if [[ "$(id -un)" == "$FORGE_USER" ]]; then
    env HOME="$RIVE_HOME" "$@"
  else
    runuser -u "$FORGE_USER" -- env HOME="$RIVE_HOME" "$@"
  fi
}

warn() {
  checks+=("{\"check\":\"$1\",\"status\":\"WARN\",\"detail\":$(printf '%s' "$2" | jq -Rs .)}")
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
  observed="$(git -C "$WORKSPACE" rev-parse HEAD 2>/dev/null || true)"
  dirty="$(git -C "$WORKSPACE" status --porcelain 2>/dev/null || true)"
  if [[ "$observed" == "$EXPECTED_SHA" && -z "$dirty" ]]; then
    add repository GREEN "$observed clean"
  elif [[ "$STRICT" != 1 ]] && git -C "$WORKSPACE" merge-base --is-ancestor "$EXPECTED_SHA" "$observed" 2>/dev/null; then
    add repository GREEN "$observed descends from $EXPECTED_SHA"
    [[ -z "$dirty" ]] || warn repository_worktree "authoring in progress: $(wc -l <<<"$dirty") changed paths"
  else
    add repository RED "observed=$observed dirty_lines=$(wc -l <<<"$dirty") strict=$STRICT"
  fi
else
  add repository RED "workspace missing"
fi

if command -v rive >/dev/null 2>&1 && as_forge rive --help >"$TMP/rive-help.txt" 2>&1; then
  add rive_cli GREEN "$(as_forge rive --version 2>&1 | head -n1 || true)"
else
  add rive_cli RED "$(tail -c 500 "$TMP/rive-help.txt" 2>/dev/null)"
fi

command -v inkscape >/dev/null 2>&1 \
  && add inkscape GREEN "$(inkscape --version | head -n1)" \
  || add inkscape RED missing

command -v potrace >/dev/null 2>&1 \
  && add potrace GREEN "$(potrace --version | head -n1)" \
  || add potrace RED missing

command -v xvfb-run >/dev/null 2>&1 \
  && add xvfb GREEN "xvfb-run present" \
  || add xvfb RED missing

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

command -v ffmpeg >/dev/null 2>&1 && command -v convert >/dev/null 2>&1 && command -v montage >/dev/null 2>&1 \
  && add evidence_media GREEN "ffmpeg + ImageMagick" \
  || add evidence_media RED missing

command -v blender >/dev/null 2>&1 \
  && add blender GREEN "$(blender --version 2>/dev/null | head -n1)" \
  || add blender RED missing

command -v google-chrome >/dev/null 2>&1 \
  && add web_editor_lane GREEN "$(google-chrome --version)" \
  || add web_editor_lane RED missing

java -version >"$TMP/java.txt" 2>&1
if grep -q '"17\.' "$TMP/java.txt"; then
  add java17 GREEN "$(head -n1 "$TMP/java.txt")"
else
  add java17 RED "$(head -n1 "$TMP/java.txt" 2>/dev/null)"
fi

if [[ -x "$ANDROID_SDK_ROOT/platform-tools/adb" && -x "$ANDROID_SDK_ROOT/emulator/emulator" ]]; then
  add android_sdk GREEN "adb + emulator"
else
  add android_sdk RED missing
fi

if "$ANDROID_SDK_ROOT/emulator/emulator" -list-avds 2>/dev/null | grep -Fxq "$AVD_NAME"; then
  add api31_avd GREEN "$AVD_NAME"
else
  add api31_avd RED "AVD missing"
fi

if [[ -e /dev/kvm ]]; then
  add kvm GREEN "/dev/kvm present"
else
  checks+=("{\"check\":\"kvm\",\"status\":\"WARN\",\"detail\":\"/dev/kvm absent; Commander will use software emulator acceleration\"}")
fi

if as_forge CHARACTER_FORGE_STATE_ROOT="$STATE_ROOT" RIVE_HOME="$RIVE_HOME" \
  /usr/local/libexec/van-character-forge-rive-smoke >"$TMP/rive-smoke.json" 2>"$TMP/rive-smoke.err"; then
  add rive_authoring_smoke GREEN "$(jq -c '{rive_version,built_riv_sha256,project_scaffold_state_machine,state_machine_bool_schema,state_machine_trigger_schema,number_input,reproducible_build}' "$TMP/rive-smoke.json")"
else
  add rive_authoring_smoke RED "$(tail -c 800 "$TMP/rive-smoke.err" 2>/dev/null)"
fi

if [[ "$(id -un)" == "$FORGE_USER" ]]; then
  worker=(/usr/local/libexec/van-character-forge-worker doctor)
else
  worker=(sudo -n -u "$FORGE_USER" /usr/local/libexec/van-character-forge-worker doctor)
fi
if "${worker[@]}" >"$TMP/forge-worker.txt" 2>&1; then
  add commander_worker GREEN "$(tail -n1 "$TMP/forge-worker.txt")"
else
  add commander_worker RED "$(tail -c 500 "$TMP/forge-worker.txt" 2>/dev/null)"
fi

if [[ -d /etc/van-character-forge && "$(stat -c %U /etc/van-character-forge)" == root ]]; then
  add authority_dir GREEN "/etc/van-character-forge root-owned; cloud-write=$([[ -e /etc/van-character-forge/allow-rive-cloud-write ]] && echo ENABLED || echo disabled) git-push=$([[ -e /etc/van-character-forge/allow-git-push ]] && echo ENABLED || echo disabled)"
else
  add authority_dir RED "/etc/van-character-forge missing or not root-owned"
fi

if [[ -s "$STATE_ROOT/toolchain.lock.json" ]] && jq -e '.rive_cli.version and .rive_cli.archive_sha256 and .android.avd' "$STATE_ROOT/toolchain.lock.json" >/dev/null 2>&1; then
  locked_rive="$(jq -r '.rive_cli.version' "$STATE_ROOT/toolchain.lock.json")"
  locked_bin="$(jq -r '.rive_cli.binary_sha256 // empty' "$STATE_ROOT/toolchain.lock.json")"
  reported_rive="$(as_forge rive --version 2>&1 | head -n1 || true)"
  observed_bin="$(sha256sum "$(readlink -f "$(command -v rive)")" 2>/dev/null | awk '{print $1}')"
  if [[ "$reported_rive" != *"$locked_rive"* ]]; then
    add toolchain_lock RED "Rive lock/version mismatch: lock=$locked_rive observed=$reported_rive"
  elif [[ -z "$locked_bin" || "$locked_bin" != "$observed_bin" ]]; then
    add toolchain_lock RED "Rive binary drifted from lock: lock=$locked_bin observed=$observed_bin"
  else
    add toolchain_lock GREEN "$STATE_ROOT/toolchain.lock.json"
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
  --arg strict "$STRICT" \
  --argjson failures "$fails" \
  --argjson checks "$checks_json" \
  '{status:$status,host:$host,strict:($strict=="1"),required_failures:$failures,at:$at,checks:$checks}' >"$TMP/report.json"
cat "$TMP/report.json"
# Machine-readable evidence for the go-live checklist; best effort when the state root is not writable.
cp "$TMP/report.json" "$REPORT" 2>/dev/null || true

(( fails == 0 ))
