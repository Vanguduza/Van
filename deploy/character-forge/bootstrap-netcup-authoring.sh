#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_ROOT="${CHARACTER_FORGE_INSTALL_ROOT:-/opt/dial-character-forge}"
STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
FORGE_USER="${CHARACTER_FORGE_USER:-vanforge}"
COMMANDER_USER="${CHARACTER_FORGE_COMMANDER_USER:-}"
WORKSPACE="${CHARACTER_FORGE_WORKSPACE:-$STATE_ROOT/work/Van}"
VAN_REPO_URL="${VAN_REPO_URL:-https://github.com/Vanguduza/Van.git}"
VAN_COMMIT_SHA="${VAN_COMMIT_SHA:-}"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$INSTALL_ROOT/android-sdk}"
ANDROID_CLI_ZIP="commandlinetools-linux-15859902_latest.zip"
ANDROID_CLI_SHA256="4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583"
ANDROID_CLI_URL="https://dl.google.com/android/repository/$ANDROID_CLI_ZIP"
AVD_NAME="${CHARACTER_FORGE_AVD_NAME:-van-character-forge-api31}"
ANDROID_USER_HOME="${CHARACTER_FORGE_ANDROID_USER_HOME:-$STATE_ROOT/.android}"
ANDROID_AVD_HOME="${CHARACTER_FORGE_ANDROID_AVD_HOME:-$ANDROID_USER_HOME/avd}"
RIVE_CLI_VERSION="1.1.1"
RIVE_CLI_ARCHIVE="rive-linux-x64.tar.gz"
RIVE_CLI_SHA256="41684e9d99fea98e01c2c155e07ec985130b95b640410dc0fbe4ca30c271a7d5"
RIVE_CLI_URL="https://releases.rive.app/cli/v$RIVE_CLI_VERSION/$RIVE_CLI_ARCHIVE"
TOOLCHAIN_LOCK="$STATE_ROOT/toolchain.lock.json"
PY_VENV="$INSTALL_ROOT/venv"
RIVE_HOME="$STATE_ROOT/rive-home"
REMBG_HOME="$STATE_ROOT/rembg"
JAVA17_HOME="${CHARACTER_FORGE_JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"

log(){ printf '[character-forge bootstrap] %s\n' "$*"; }
die(){ printf '[character-forge bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "run as root"
[[ "$(uname -m)" == "x86_64" ]] || die "Netcup Rive workstation requires x86_64"

HOST="$(hostname -s 2>/dev/null || hostname)"
case "$HOST" in
  oracle-admin|vekl-worker|van-trading-core)
    die "refusing protected/non-control host $HOST"
    ;;
esac

if [[ -z "$COMMANDER_USER" ]]; then
  if id vancommander >/dev/null 2>&1; then
    COMMANDER_USER=vancommander
  else
    COMMANDER_USER=ubuntu
  fi
fi

id "$COMMANDER_USER" >/dev/null 2>&1 \
  || die "Commander user '$COMMANDER_USER' missing; finish Netcup DIAL-control bootstrap first"
[[ "$VAN_COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || die "VAN_COMMIT_SHA must be the exact 40-hex revision"

export DEBIAN_FRONTEND=noninteractive
log "installing production workstation packages"
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git jq unzip zip gnupg xz-utils file rsync sudo \
  python3 python3-venv python3-pip python3-yaml \
  openjdk-17-jdk-headless \
  inkscape potrace imagemagick librsvg2-bin ffmpeg blender \
  xvfb dbus-x11 fonts-dejavu-core \
  qemu-kvm libgl1 libegl1 libgles2 libpulse0 libnss3 libx11-6 libxcomposite1 libxcursor1 libxi6 \
  libxrandr2 libxdamage1 libxfixes3 libxtst6

[[ -x "$JAVA17_HOME/bin/java" ]] || die "Java 17 runtime missing at $JAVA17_HOME"
export JAVA_HOME="$JAVA17_HOME"
export PATH="$JAVA_HOME/bin:$PATH"

if ! command -v google-chrome >/dev/null 2>&1; then
  log "installing Chrome for optional Rive web-editor review"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor --yes -o /etc/apt/keyrings/google-chrome.gpg
  chmod 0644 /etc/apt/keyrings/google-chrome.gpg
  printf '%s\n' \
    'deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main' \
    >/etc/apt/sources.list.d/google-chrome.list
  apt-get update
  apt-get install -y --no-install-recommends google-chrome-stable
fi

if ! id "$FORGE_USER" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$STATE_ROOT" --shell /bin/bash "$FORGE_USER"
fi
getent group kvm >/dev/null 2>&1 && usermod -aG kvm "$FORGE_USER" || true

install -d -o "$FORGE_USER" -g "$FORGE_USER" -m 0755 \
  "$INSTALL_ROOT" "$STATE_ROOT" "$RIVE_HOME" "$REMBG_HOME" "$ANDROID_USER_HOME" "$ANDROID_AVD_HOME" "$(dirname "$WORKSPACE")"

log "installing pinned image-preparation lane"
if [[ ! -x "$PY_VENV/bin/python" ]]; then
  python3 -m venv "$PY_VENV"
  chown -R "$FORGE_USER:$FORGE_USER" "$PY_VENV"
fi
runuser -u "$FORGE_USER" -- "$PY_VENV/bin/python" -m pip install --upgrade pip wheel
runuser -u "$FORGE_USER" -- "$PY_VENV/bin/python" -m pip install \
  'rembg[cpu,cli]==2.0.85' \
  'vtracer==0.6.15' \
  'Pillow==12.3.0'
runuser -u "$FORGE_USER" -- env U2NET_HOME="$REMBG_HOME" \
  "$PY_VENV/bin/rembg" d birefnet-general

log "installing checksum-pinned official Rive CLI $RIVE_CLI_VERSION"
TMP_RIVE_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_RIVE_DIR"' EXIT
curl -fsSL "$RIVE_CLI_URL" -o "$TMP_RIVE_DIR/$RIVE_CLI_ARCHIVE"
echo "$RIVE_CLI_SHA256  $TMP_RIVE_DIR/$RIVE_CLI_ARCHIVE" | sha256sum -c -
mkdir -p "$TMP_RIVE_DIR/unpacked"
tar -xzf "$TMP_RIVE_DIR/$RIVE_CLI_ARCHIVE" -C "$TMP_RIVE_DIR/unpacked"
RIVE_ARCHIVE_BIN="$(find "$TMP_RIVE_DIR/unpacked" -type f -name rive -perm -u+x -print -quit 2>/dev/null || true)"
[[ -n "$RIVE_ARCHIVE_BIN" && -x "$RIVE_ARCHIVE_BIN" ]] || die "pinned Rive archive contains no executable rive binary"
RIVE_INSTALL_DIR="$INSTALL_ROOT/rive/$RIVE_CLI_VERSION"
install -d -o root -g root -m 0755 "$RIVE_INSTALL_DIR"
install -o root -g root -m 0755 "$RIVE_ARCHIVE_BIN" "$RIVE_INSTALL_DIR/rive"
ln -sfn "$RIVE_INSTALL_DIR/rive" /usr/local/bin/rive
RIVE_VERSION_OUTPUT="$(runuser -u "$FORGE_USER" -- env HOME="$RIVE_HOME" rive --version 2>&1 | head -n1 || true)"
[[ "$RIVE_VERSION_OUTPUT" == *"$RIVE_CLI_VERSION"* ]] \
  || die "Rive CLI version mismatch: expected $RIVE_CLI_VERSION, observed '$RIVE_VERSION_OUTPUT'"
runuser -u "$FORGE_USER" -- env HOME="$RIVE_HOME" rive --help >/dev/null

log "installing checksum-pinned Android command-line tools"
install -d -o "$FORGE_USER" -g "$FORGE_USER" -m 0755 "$ANDROID_SDK_ROOT"
if [[ ! -x "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" ]]; then
  TMP_ANDROID="$(mktemp -d)"
  curl -fsSL "$ANDROID_CLI_URL" -o "$TMP_ANDROID/$ANDROID_CLI_ZIP"
  echo "$ANDROID_CLI_SHA256  $TMP_ANDROID/$ANDROID_CLI_ZIP" | sha256sum -c -
  unzip -q "$TMP_ANDROID/$ANDROID_CLI_ZIP" -d "$TMP_ANDROID/unpacked"
  install -d "$ANDROID_SDK_ROOT/cmdline-tools/latest"
  cp -a "$TMP_ANDROID/unpacked/cmdline-tools/." "$ANDROID_SDK_ROOT/cmdline-tools/latest/"
  rm -rf "$TMP_ANDROID"
  chown -R "$FORGE_USER:$FORGE_USER" "$ANDROID_SDK_ROOT"
fi

SDKMANAGER="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
yes | runuser -u "$FORGE_USER" -- env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:/usr/local/bin:/usr/bin:/bin" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME" \
  "$SDKMANAGER" --licenses >/dev/null || true
runuser -u "$FORGE_USER" -- env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:/usr/local/bin:/usr/bin:/bin" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME" "$SDKMANAGER" \
  "platform-tools" \
  "platforms;android-36" \
  "build-tools;36.0.0" \
  "emulator" \
  "system-images;android-31;google_apis;x86_64"

AVDMANAGER="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/avdmanager"
if ! runuser -u "$FORGE_USER" -- env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:/usr/local/bin:/usr/bin:/bin" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME" \
  "$ANDROID_SDK_ROOT/emulator/emulator" -list-avds | grep -Fxq "$AVD_NAME"; then
  printf 'no\n' | runuser -u "$FORGE_USER" -- env JAVA_HOME="$JAVA_HOME" PATH="$JAVA_HOME/bin:/usr/local/bin:/usr/bin:/bin" ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME" \
    "$AVDMANAGER" create avd --force --name "$AVD_NAME" \
    --package "system-images;android-31;google_apis;x86_64"
fi
runuser -u "$FORGE_USER" -- env ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME" \
  "$ANDROID_SDK_ROOT/emulator/emulator" -list-avds | grep -Fxq "$AVD_NAME" \
  || die "Android AVD $AVD_NAME was not created"

log "checking out exact VAN revision"
if [[ ! -d "$WORKSPACE/.git" ]]; then
  runuser -u "$FORGE_USER" -- git clone "$VAN_REPO_URL" "$WORKSPACE"
fi
runuser -u "$FORGE_USER" -- git -C "$WORKSPACE" fetch --prune origin
runuser -u "$FORGE_USER" -- git -C "$WORKSPACE" checkout --detach "$VAN_COMMIT_SHA"
[[ "$(runuser -u "$FORGE_USER" -- git -C "$WORKSPACE" rev-parse HEAD)" == "$VAN_COMMIT_SHA" ]] \
  || die "workspace SHA mismatch"
[[ -z "$(runuser -u "$FORGE_USER" -- git -C "$WORKSPACE" status --porcelain)" ]] \
  || die "workspace not clean"

log "installing bounded Commander surface"
# Root-owned authority switches (Rive cloud write, git push). Created empty: enabling either
# is an explicit owner action (`touch` as root), never something this bootstrap does.
install -d -o root -g root -m 0755 /etc/van-character-forge
install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0755 \
  "$WORKSPACE/deploy/character-forge/commander-worker.sh" \
  /usr/local/libexec/van-character-forge-worker
install -o root -g root -m 0755 \
  "$WORKSPACE/deploy/character-forge/qualify-netcup-authoring.sh" \
  /usr/local/sbin/qualify-van-character-forge
install -o root -g root -m 0755 \
  "$WORKSPACE/deploy/character-forge/rive-cli-smoke.sh" \
  /usr/local/libexec/van-character-forge-rive-smoke

cat >/etc/sudoers.d/van-character-forge <<EOF
$COMMANDER_USER ALL=($FORGE_USER) NOPASSWD: /usr/local/libexec/van-character-forge-worker *
EOF
chmod 0440 /etc/sudoers.d/van-character-forge
visudo -cf /etc/sudoers.d/van-character-forge >/dev/null

log "recording installed toolchain"
RIVE_VERSION="$RIVE_CLI_VERSION"
RIVE_REPORTED_VERSION="$(runuser -u "$FORGE_USER" -- env HOME="$RIVE_HOME" rive --version 2>&1 | head -n1 || true)"
[[ "$RIVE_REPORTED_VERSION" == *"$RIVE_VERSION"* ]] || die "Rive CLI version drift: expected $RIVE_VERSION, observed '$RIVE_REPORTED_VERSION'"
INKSCAPE_REPORTED="$(inkscape --version 2>/dev/null | head -n1)"
INKSCAPE_VERSION="$(grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)*' <<<"$INKSCAPE_REPORTED" | head -n1)"
[[ -n "$INKSCAPE_VERSION" ]] || die "cannot parse Inkscape version from '$INKSCAPE_REPORTED'"
RIVE_BINARY_SHA256="$(sha256sum "$RIVE_INSTALL_DIR/rive" | awk '{print $1}')"
BIREFNET_MODEL="$(find "$REMBG_HOME" -type f -iname '*birefnet*' -print -quit)"
[[ -n "$BIREFNET_MODEL" ]] || die "birefnet-general model missing after download"
BIREFNET_SHA256="$(sha256sum "$BIREFNET_MODEL" | awk '{print $1}')"
CHROME_VERSION="$(google-chrome --version | head -n1)"
JAVA_VERSION="$("$JAVA_HOME/bin/java" -version 2>&1 | head -n1)"
EMULATOR_VERSION="$("$ANDROID_SDK_ROOT/emulator/emulator" -version 2>&1 | head -n1)"
VTRACER_VERSION="$(runuser -u "$FORGE_USER" -- "$PY_VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("vtracer"))')"
REMBG_VERSION="$(runuser -u "$FORGE_USER" -- "$PY_VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("rembg"))')"

jq -n \
  --arg host "$HOST" \
  --arg arch "$(uname -m)" \
  --arg repo_sha "$VAN_COMMIT_SHA" \
  --arg rive "$RIVE_VERSION" \
  --arg rive_reported "$RIVE_REPORTED_VERSION" \
  --arg rive_archive_sha "$RIVE_CLI_SHA256" \
  --arg rive_source "$RIVE_CLI_URL" \
  --arg inkscape "$INKSCAPE_VERSION" \
  --arg inkscape_reported "$INKSCAPE_REPORTED" \
  --arg rive_binary_sha "$RIVE_BINARY_SHA256" \
  --arg birefnet_sha "$BIREFNET_SHA256" \
  --arg vtracer "$VTRACER_VERSION" \
  --arg rembg "$REMBG_VERSION" \
  --arg chrome "$CHROME_VERSION" \
  --arg java "$JAVA_VERSION" \
  --arg emulator "$EMULATOR_VERSION" \
  --arg android_cli_sha "$ANDROID_CLI_SHA256" \
  --arg avd "$AVD_NAME" \
  '{
    schema_version:1,
    host:$host,
    arch:$arch,
    repository_sha:$repo_sha,
    rive_cli:{version:$rive,reported_version:$rive_reported,archive_sha256:$rive_archive_sha,binary_sha256:$rive_binary_sha,source:$rive_source},
    inkscape:{version:$inkscape,reported_version:$inkscape_reported},
    vtracer:{version:$vtracer},
    rembg:{version:$rembg,model:"birefnet-general",model_sha256:$birefnet_sha},
    chrome:{version:$chrome},
    java:{version:$java},
    android:{
      command_line_tools_sha256:$android_cli_sha,
      emulator:$emulator,
      avd:$avd
    }
  }' >"$TOOLCHAIN_LOCK"
chown "$FORGE_USER:$FORGE_USER" "$TOOLCHAIN_LOCK"
chmod 0644 "$TOOLCHAIN_LOCK"

log "running fail-closed qualification"
CHARACTER_FORGE_QUALIFY_STRICT=1 \
CHARACTER_FORGE_INSTALL_ROOT="$INSTALL_ROOT" \
CHARACTER_FORGE_STATE_ROOT="$STATE_ROOT" \
CHARACTER_FORGE_USER="$FORGE_USER" \
CHARACTER_FORGE_WORKSPACE="$WORKSPACE" \
VAN_COMMIT_SHA="$VAN_COMMIT_SHA" \
ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
CHARACTER_FORGE_AVD_NAME="$AVD_NAME" \
CHARACTER_FORGE_JAVA_HOME="$JAVA_HOME" \
CHARACTER_FORGE_ANDROID_USER_HOME="$ANDROID_USER_HOME" \
CHARACTER_FORGE_ANDROID_AVD_HOME="$ANDROID_AVD_HOME" \
  /usr/local/sbin/qualify-van-character-forge

cat <<EOF
[character-forge bootstrap] AUTHORING_WORKSTATION_READY
Desktop Commander:
  sudo -n -u $FORGE_USER /usr/local/libexec/van-character-forge-worker status
No owner/art/device milestone was promoted by this bootstrap.
EOF
