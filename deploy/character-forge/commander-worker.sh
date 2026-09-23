#!/usr/bin/env bash
set -Eeuo pipefail

STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
INSTALL_ROOT="${CHARACTER_FORGE_INSTALL_ROOT:-/opt/dial-character-forge}"
WORKSPACE="${CHARACTER_FORGE_WORKSPACE:-$STATE_ROOT/work/Van}"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$INSTALL_ROOT/android-sdk}"
AVD_NAME="${CHARACTER_FORGE_AVD_NAME:-van-character-forge-api31}"
PY_VENV="$INSTALL_ROOT/venv"
RIVE_HOME="$STATE_ROOT/rive-home"
FORGE_ROOT="$WORKSPACE/visual-authority/character-forge"
RIVE_WORKING="$FORGE_ROOT/09-rive-working"
RIVE_PROJECT_ROOT="$RIVE_WORKING/rml"
VECTOR_CLEAN="$FORGE_ROOT/06-vectors-clean"
VALIDATION_DIR="$FORGE_ROOT/10-validation"
# Authority switches live in a root-owned directory the vanforge user cannot write. A sentinel
# under STATE_ROOT (vanforge-owned) could be created by any worker command that writes a file.
AUTHORITY_DIR="${CHARACTER_FORGE_AUTHORITY_DIR:-/etc/van-character-forge}"
RIVE_CLOUD_WRITE_SENTINEL="$AUTHORITY_DIR/allow-rive-cloud-write"
GIT_PUSH_SENTINEL="$AUTHORITY_DIR/allow-git-push"
MAX_PUT_BYTES=$((8 * 1024 * 1024))

export HOME="$RIVE_HOME"
export U2NET_HOME="$STATE_ROOT/rembg"
export ANDROID_SDK_ROOT
export PATH="/usr/local/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"

cd "$WORKSPACE"

refuse() { echo "refused: $*" >&2; exit 2; }

# Resolve a path and require it to sit inside one of the given roots. Every path Commander
# supplies goes through here; nothing reads or writes outside the Character Forge tree.
jailed() {
  local raw="${1:-}"; shift
  [[ -n "$raw" ]] || refuse "path required"
  local resolved root
  resolved="$(realpath -m -- "$raw")"
  for root in "$@"; do
    case "$resolved" in
      "$root"|"$root"/*) printf '%s\n' "$resolved"; return 0 ;;
    esac
  done
  refuse "$raw is outside the permitted Character Forge roots"
}

project_path() {
  local resolved
  resolved="$(jailed "${1:-}" "$RIVE_PROJECT_ROOT")"
  [[ "$resolved" != "$RIVE_PROJECT_ROOT" ]] || refuse "name a project directory under $RIVE_PROJECT_ROOT"
  printf '%s\n' "$resolved"
}

prep_input() { jailed "${1:-}" "$WORKSPACE/visual-authority/assets" "$FORGE_ROOT"; }
# Lanes produce candidates only (Rev 2 §7): never into 06-vectors-clean or 09+ directly.
prep_output() { jailed "${1:-}" "$FORGE_ROOT/02-ai-working" "$FORGE_ROOT/03-masks" "$FORGE_ROOT/04-raster-layers" "$FORGE_ROOT/05-vectors-candidate"; }

# Accept a file on stdin, bounded in size, written atomically to an already-jailed target.
put_stdin() {
  local target="$1" tmp
  mkdir -p "$(dirname "$target")"
  tmp="$(mktemp "$(dirname "$target")/.put.XXXXXX")"
  head -c "$((MAX_PUT_BYTES + 1))" >"$tmp"
  if (( $(stat -c %s "$tmp") > MAX_PUT_BYTES )); then rm -f "$tmp"; refuse "input exceeds $MAX_PUT_BYTES bytes"; fi
  mv -f "$tmp" "$target"
  sha256sum "$target" | awk '{print $1}'
}

require_root_sentinel() {
  local sentinel="$1" label="$2"
  [[ -f "$sentinel" && ! -L "$sentinel" && "$(stat -c %U "$sentinel")" == root && "$(stat -c %U "$(dirname "$sentinel")")" == root ]] || {
    echo "refused: $label authority is not enabled (root-owned $sentinel absent)" >&2
    exit 3
  }
}

require_cloud_write() { require_root_sentinel "$RIVE_CLOUD_WRITE_SENTINEL" "Rive cloud-write"; }

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
    in="$(prep_input "$1")"; out="$(prep_output "$2")"; mkdir -p "$(dirname "$out")"
    exec "$PY_VENV/bin/rembg" i -m birefnet-general "$in" "$out"
    ;;
  vectorize)
    [[ $# -eq 2 ]] || { echo "usage: vectorize INPUT OUTPUT.svg" >&2; exit 2; }
    in="$(prep_input "$1")"; out="$(prep_output "$2")"; mkdir -p "$(dirname "$out")"
    exec "$PY_VENV/bin/python" -c 'import sys,vtracer; vtracer.convert_image_to_svg_py(sys.argv[1],sys.argv[2],colormode="color",hierarchical="stacked",mode="spline")' "$in" "$out"
    ;;
  vector-put)
    [[ $# -eq 1 && "$1" =~ ^[A-Za-z0-9._-]+\.svg$ ]] || { echo "usage: vector-put NAME.svg < file.svg" >&2; exit 2; }
    put_stdin "$VECTOR_CLEAN/$1"
    ;;
  svg-lint)
    [[ $# -eq 1 ]] || { echo "usage: svg-lint FILE.svg" >&2; exit 2; }
    svg="$(jailed "$1" "$FORGE_ROOT")"
    exec python3 -m tools.character_forge.cli vectors lint "$svg"
    ;;
  vectors-admit)
    [[ $# -eq 2 && "$2" =~ ^[A-Za-z0-9._:-]+$ ]] || { echo "usage: vectors-admit FILE.svg AUTHOR_ID" >&2; exit 2; }
    svg="$(jailed "$1" "$VECTOR_CLEAN")"
    exec python3 -m tools.character_forge.cli --actor commander vectors admit "$svg" --artist "$2"
    ;;
  rive-help)
    exec rive --help
    ;;
  rive-docs)
    exec rive docs "$@"
    ;;
  rive-schema)
    exec rive schema "$@"
    ;;
  rive-create)
    [[ $# -eq 1 ]] || { echo "usage: rive-create PROJECT_DIR" >&2; exit 2; }
    target="$(project_path "$1")"
    mkdir -p "$RIVE_PROJECT_ROOT"
    exec rive create "$target"
    ;;
  rml-put)
    # Commander authors RML by writing source files into a jailed project. Source only: a
    # compiled .riv enters the pipeline solely through rive-candidate.
    [[ $# -eq 2 && "$2" =~ ^[A-Za-z0-9._/-]+\.(rml|json|svg|png|txt|md)$ && "$2" != *..* ]] \
      || { echo "usage: rml-put PROJECT_DIR RELPATH.(rml|json|svg|png|txt|md) < file" >&2; exit 2; }
    project="$(project_path "$1")"
    target="$(jailed "$project/$2" "$project")"
    put_stdin "$target"
    ;;
  rml-cat)
    [[ $# -eq 1 ]] || { echo "usage: rml-cat PROJECT_DIR/RELPATH" >&2; exit 2; }
    file="$(jailed "$1" "$RIVE_PROJECT_ROOT")"
    exec cat -- "$file"
    ;;
  rive-inspect)
    [[ $# -eq 1 ]] || { echo "usage: rive-inspect PROJECT_DIR" >&2; exit 2; }
    project="$(project_path "$1")"
    exec rive inspect "$project" --json
    ;;
  rive-verify)
    [[ $# -eq 1 ]] || { echo "usage: rive-verify PROJECT_DIR" >&2; exit 2; }
    project="$(project_path "$1")"
    exec rive "$project" --verify --format=json
    ;;
  rive-build)
    [[ $# -eq 1 ]] || { echo "usage: rive-build PROJECT_DIR" >&2; exit 2; }
    project="$(project_path "$1")"
    exec rive "$project" --once --format=json
    ;;
  rive-candidate)
    # Build with the pinned CLI and place the output as the next numbered candidate. The .riv
    # a receipt names is therefore always one the pinned toolchain produced from jailed RML.
    [[ $# -eq 3 && "$2" =~ ^(core|full)$ && "$3" =~ ^[0-9]{1,4}$ ]] || { echo "usage: rive-candidate PROJECT_DIR core|full N" >&2; exit 2; }
    project="$(project_path "$1")"
    build_json="$(rive "$project" --once --format=json)"
    riv="$(printf '%s\n' "$build_json" | jq -r '.data.riv // empty')"
    [[ -n "$riv" ]] || refuse "build reported no .riv"
    [[ "$riv" == /* ]] || riv="$project/$riv"
    riv="$(jailed "$riv" "$project")"
    target="$RIVE_WORKING/van_runtime_$2_$3.riv"
    [[ ! -e "$target" ]] || refuse "$target exists; candidates are immutable, use a new N"
    install -m 0644 "$riv" "$target"
    source_hash="$(python3 -m tools.character_forge.cli rive source-hash "$project")"
    jq -n --arg path "${target#"$WORKSPACE"/}" --arg sha "$(sha256sum "$target" | awk '{print $1}')" \
      --arg source "$source_hash" \
      '{candidate:$path,candidate_sha256:$sha,source:($source|fromjson)}'
    ;;
  rive-source-hash)
    [[ $# -eq 1 ]] || { echo "usage: rive-source-hash PROJECT_DIR" >&2; exit 2; }
    project="$(project_path "$1")"
    exec python3 -m tools.character_forge.cli rive source-hash "$project"
    ;;
  rive-receipt)
    [[ $# -eq 5 && "$3" =~ ^[0-9a-f]{64}$ && "$4" =~ ^[A-Za-z0-9._:-]+$ && "$5" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
      || { echo "usage: rive-receipt CANDIDATE.riv PROJECT_DIR SVG_SHA256 AUTHOR_ID RIVE_CLI_VERSION" >&2; exit 2; }
    candidate="$(jailed "$1" "$RIVE_WORKING")"; project="$(project_path "$2")"
    exec python3 -m tools.character_forge.cli --actor commander rive receipt \
      --candidate "$candidate" --source-project "$project" \
      --svg-sha "$3" --artist "$4" --authoring-version "$5" --rive-file-id LOCAL --rive-revision LOCAL
    ;;
  rive-stage)
    [[ $# -eq 2 && "$2" =~ ^(core_rig|full_rig)$ ]] || { echo "usage: rive-stage CANDIDATE.riv core_rig|full_rig" >&2; exit 2; }
    candidate="$(jailed "$1" "$RIVE_WORKING")"
    exec python3 -m tools.character_forge.cli --actor commander rive stage-candidate "$candidate" --stage "$2"
    ;;
  rive-test)
    [[ $# -eq 1 ]] || { echo "usage: rive-test PROJECT_DIR" >&2; exit 2; }
    project="$(project_path "$1")"
    exec rive "$project" --test --format=json
    ;;
  rive-screenshot)
    [[ $# -eq 1 ]] || { echo "usage: rive-screenshot PROJECT_DIR" >&2; exit 2; }
    project="$(project_path "$1")"
    exec rive "$project" --screenshot
    ;;
  rive-smoke)
    exec /usr/local/libexec/van-character-forge-rive-smoke
    ;;
  rive-auth-status)
    # Read-only. Logging in is an explicit owner action performed interactively as vanforge;
    # Commander may observe the session but never create one.
    exec rive whoami
    ;;
  rive-push)
    [[ $# -eq 1 ]] || { echo "usage: rive-push PROJECT_DIR" >&2; exit 2; }
    require_cloud_write
    project="$(project_path "$1")"
    exec rive push "$project" --name "VAN Character Forge"
    ;;
  rive-publish)
    [[ $# -eq 1 ]] || { echo "usage: rive-publish PROJECT_DIR" >&2; exit 2; }
    require_cloud_write
    project="$(project_path "$1")"
    exec rive "$project" --publish --format=json
    ;;
  contact-sheet)
    # Deterministic review sheet (no timestamps) from frames already inside the forge tree.
    [[ $# -eq 2 && "$2" =~ ^[A-Za-z0-9._-]+\.png$ ]] || { echo "usage: contact-sheet FRAMES_DIR NAME.png" >&2; exit 2; }
    frames="$(jailed "$1" "$FORGE_ROOT" "$WORKSPACE/android/app/build/outputs/connected_android_test_additional_output")"
    mapfile -t pngs < <(find "$frames" -type f -name '*.png' | LC_ALL=C sort)
    (( ${#pngs[@]} )) || refuse "no PNG frames under $frames"
    mkdir -p "$VALIDATION_DIR"
    montage -label '%t' "${pngs[@]}" -geometry 240x240+6+6 -tile 6x -background '#0B0F14' -fill '#E8EBF0' \
      -define png:exclude-chunks=date,time "$VALIDATION_DIR/$2"
    sha256sum "$VALIDATION_DIR/$2"
    ;;
  frames-to-webm)
    [[ $# -eq 2 && "$2" =~ ^[A-Za-z0-9._-]+\.webm$ ]] || { echo "usage: frames-to-webm FRAMES_DIR NAME.webm" >&2; exit 2; }
    frames="$(jailed "$1" "$FORGE_ROOT")"
    mkdir -p "$VALIDATION_DIR"
    exec ffmpeg -nostdin -y -loglevel error -framerate 30 -pattern_type glob -i "$frames/*.png" \
      -c:v libvpx-vp9 -b:v 0 -crf 30 -row-mt 0 -threads 1 -fflags +bitexact -flags:v +bitexact "$VALIDATION_DIR/$2"
    ;;
  forge-push)
    # Pushes candidate work to a forge/* branch so van-ci validates it. Needs an owner-provided
    # credential and a root-owned switch; it commits only Character Forge authoring paths.
    [[ $# -eq 2 && "$1" =~ ^forge/[a-z0-9._-]+$ ]] || { echo "usage: forge-push forge/BRANCH 'message'" >&2; exit 2; }
    require_root_sentinel "$GIT_PUSH_SENTINEL" "git push"
    # ACCEPTANCE.yaml and DEVICE_CHECKLIST.yaml are owner records and deliberately absent.
    allowed='^(visual-authority/character-forge/|docs/character_forge/(MANIFEST\.yaml|STATUS\.json|TOOLS\.yaml)$|android/app/src/(androidTest|debug)/assets/)'
    outside="$(git status --porcelain --untracked-files=all | cut -c4- | sed 's/.* -> //' | grep -vE "$allowed" || true)"
    [[ -z "$outside" ]] || { echo "refused: changes outside Character Forge authoring paths:" >&2; echo "$outside" >&2; exit 2; }
    git checkout -B "$1"
    git add -A -- visual-authority/character-forge docs/character_forge/MANIFEST.yaml docs/character_forge/STATUS.json \
      docs/character_forge/TOOLS.yaml android/app/src/androidTest/assets android/app/src/debug/assets
    git -c user.name="VAN Character Forge" -c user.email="vanforge@dial-control" commit -m "character-forge: $2"
    exec git push origin "HEAD:refs/heads/$1"
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
    # Local iteration only. The summary is written beside the build, never into repository
    # evidence: only a GitHub run bound by van_validation.json can be recorded as validation.
    status=0
    (cd android && ./gradlew :app:connectedDebugAndroidTest) || status=$?
    python3 -m tools.character_forge.ci_binding summarise \
      --results android/app/build/outputs/androidTest-results \
      --out "$STATE_ROOT/local-validation.json" || true
    cat "$STATE_ROOT/local-validation.json" 2>/dev/null || true
    exit "$status"
    ;;
  qualify)
    exec /usr/local/sbin/qualify-van-character-forge
    ;;
  toolchain-lock)
    exec cat "$STATE_ROOT/toolchain.lock.json"
    ;;
  import-toolchain-lock)
    exec python3 -m tools.character_forge.cli --actor commander tools import-lock --path "$STATE_ROOT/toolchain.lock.json"
    ;;
  *)
    cat >&2 <<'EOF'
Allowed commands:
  doctor status git-status source-admit gate
  remove-bg vectorize vector-put svg-lint vectors-admit
  rive-help rive-docs rive-schema rive-create rml-put rml-cat rive-inspect
  rive-verify rive-build rive-candidate rive-source-hash rive-receipt rive-stage
  rive-test rive-screenshot rive-smoke rive-auth-status rive-push rive-publish
  contact-sheet frames-to-webm forge-push
  android-build emulator-up emulator-down instrumentation
  qualify toolchain-lock import-toolchain-lock
EOF
    exit 2
    ;;
esac
