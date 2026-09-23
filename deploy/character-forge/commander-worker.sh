#!/usr/bin/env bash
set -Eeuo pipefail

STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
INSTALL_ROOT="${CHARACTER_FORGE_INSTALL_ROOT:-/opt/dial-character-forge}"
WORKSPACE="${CHARACTER_FORGE_WORKSPACE:-$STATE_ROOT/work/Van}"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$INSTALL_ROOT/android-sdk}"
AVD_NAME="${CHARACTER_FORGE_AVD_NAME:-van-character-forge-api31}"
PY_VENV="$INSTALL_ROOT/venv"
RIVE_HOME="$STATE_ROOT/rive-home"

export HOME="$RIVE_HOME"
export U2NET_HOME="$STATE_ROOT/rembg"
export ANDROID_SDK_ROOT
export PATH="/usr/local/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"

cd "$WORKSPACE"
cmd="${1:-}"
shift || true

case "$cmd" in
  doctor)
    rive --help >/dev/null
    python3 -m tools.character_forge.cli status --json >/dev/null
    echo CHARACTER_FORGE_COMMANDER_READY
    ;;
  status)
    exec python3 -m tools.character_forge.cli status --json
    ;;
  git-status)
    exec git status --short --branch
    ;;
  source-admit)
    exec python3 -m tools.character_forge.cli --actor commander source admit
    ;;
  gate)
    [[ "${1:-}" =~ ^m[0-5]$ ]] || { echo "usage: gate m0..m5" >&2; exit 2; }
    exec python3 -m tools.character_forge.cli --actor commander gate "$1" --json
    ;;
  remove-bg)
    [[ $# -eq 2 ]] || { echo "usage: remove-bg INPUT OUTPUT" >&2; exit 2; }
    exec "$PY_VENV/bin/rembg" i -m birefnet-general "$1" "$2"
    ;;
  vectorize)
    [[ $# -eq 2 ]] || { echo "usage: vectorize INPUT OUTPUT.svg" >&2; exit 2; }
    exec "$PY_VENV/bin/python" -c 'import sys,vtracer; vtracer.convert_image_to_svg_py(sys.argv[1],sys.argv[2],colormode="color",hierarchical="stacked",mode="spline")' "$1" "$2"
    ;;
  svg-lint)
    [[ $# -eq 1 ]] || { echo "usage: svg-lint FILE.svg" >&2; exit 2; }
    exec python3 -m tools.character_forge.cli vectors lint "$1"
    ;;
  rive)
    exec rive "$@"
    ;;
  rive-help)
    exec rive --help
    ;;
  android-build)
    cd android
    exec ./gradlew :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
    ;;
  emulator-up)
    accel=(-accel off)
    [[ -e /dev/kvm ]] && accel=(-accel on)
    nohup "$ANDROID_SDK_ROOT/emulator/emulator" \
      -avd "$AVD_NAME" -no-window -no-audio -no-boot-anim \
      -gpu swiftshader_indirect "${accel[@]}" >"$STATE_ROOT/emulator.log" 2>&1 &
    "$ANDROID_SDK_ROOT/platform-tools/adb" wait-for-device
    for _ in $(seq 1 180); do
      if [[ "$("$ANDROID_SDK_ROOT/platform-tools/adb" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then
        echo EMULATOR_READY
        exit 0
      fi
      sleep 2
    done
    echo "emulator boot timeout" >&2
    exit 1
    ;;
  emulator-down)
    exec "$ANDROID_SDK_ROOT/platform-tools/adb" emu kill
    ;;
  instrumentation)
    cd android
    exec ./gradlew :app:connectedDebugAndroidTest
    ;;
  qualify)
    exec /usr/local/sbin/qualify-van-character-forge
    ;;
  toolchain-lock)
    exec cat "$STATE_ROOT/toolchain.lock.json"
    ;;
  *)
    cat >&2 <<'EOF'
Allowed commands:
  doctor status git-status source-admit gate
  remove-bg vectorize svg-lint
  rive rive-help
  android-build emulator-up emulator-down instrumentation
  qualify toolchain-lock
EOF
    exit 2
    ;;
esac
