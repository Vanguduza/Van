#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVF=/etc/van-muse-sandbox.env
GVISOR_RELEASE=release-20260928.0
GVISOR_ARCHIVE=gvisor-aarch64.tar.zstd
GVISOR_SHA256=fc23acbf56a98f9e95267eec431870cff9354dca7e0620da48749f881eed85b6
GVISOR_URL="https://github.com/google/gvisor/releases/download/$GVISOR_RELEASE/$GVISOR_ARCHIVE"
die(){ echo "[muse-sandbox] ERROR: $*" >&2; exit 1; }
log(){ echo "[muse-sandbox] $*"; }

[[ "$(uname -m)" == aarch64 ]] || die "this profile is for VAN Trading Core ARM64"
command -v docker >/dev/null || die "Docker is required from the existing Trading Core bootstrap"
id van-browser >/dev/null 2>&1 || die "existing VAN browser runtime must be installed first"

export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get -o Acquire::Retries=3 update -qq
apt-get -o Acquire::Retries=3 install -y -qq --no-install-recommends curl jq zstd nftables socat ca-certificates openssl e2fsprogs util-linux >/dev/null

if ! id vanmusectl >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/van-muse-control --create-home --shell /usr/sbin/nologin vanmusectl
fi
if getent passwd 10001 >/dev/null; then
  die "host uid 10001 is already allocated; refusing profile bind that could expose Muse state"
fi

install -d -m 0755 /opt/van-muse-sandbox /var/lib/van-muse-sandbox
install -d -m 0700 /opt/van-muse-sandbox/secrets
install -d -m 0700 -o 10001 -g 100 /var/lib/van-muse-sandbox/profile /var/lib/van-muse-sandbox/downloads
if [[ ! -s /opt/van-muse-sandbox/secrets/control.token ]]; then
  umask 077
  openssl rand -hex 32 >/opt/van-muse-sandbox/secrets/control.token
fi
chown root:vanmusectl /opt/van-muse-sandbox/secrets/control.token
chmod 0640 /opt/van-muse-sandbox/secrets/control.token

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$GVISOR_URL" -o "$tmp/$GVISOR_ARCHIVE"
printf '%s  %s\n' "$GVISOR_SHA256" "$tmp/$GVISOR_ARCHIVE" | sha256sum -c - >/dev/null
tar --use-compress-program=unzstd -xf "$tmp/$GVISOR_ARCHIVE" -C "$tmp"
runsc_path="$(find "$tmp" -type f -name runsc -perm /111 | head -1)"
[[ -n "$runsc_path" ]] || die "runsc missing from pinned gVisor archive"
install -m 0755 "$runsc_path" /usr/local/bin/runsc
/usr/local/bin/runsc --version | grep -q "$GVISOR_RELEASE" || die "gVisor version mismatch"

install -d -m 0755 /etc/docker
old="$tmp/daemon.old.json"
new="$tmp/daemon.new.json"
if [[ -s /etc/docker/daemon.json ]]; then cp /etc/docker/daemon.json "$old"; else printf '{}\n' >"$old"; fi
jq '.runtimes = ((.runtimes // {}) + {"runsc-muse":{"path":"/usr/local/bin/runsc","runtimeArgs":["--platform=systrap"]}})' "$old" >"$new"
dockerd --validate --config-file="$new" >/dev/null || die "merged Docker daemon config is invalid"
cp "$new" /etc/docker/daemon.json
if ! systemctl reload docker; then
  cp "$old" /etc/docker/daemon.json
  systemctl reload docker || true
  die "Docker runtime reload failed; original config restored"
fi
if ! docker info --format '{{json .Runtimes}}' | jq -e 'has("runsc-muse")' >/dev/null; then
  cp "$old" /etc/docker/daemon.json
  systemctl reload docker || true
  die "runsc-muse did not register; original Docker config restored"
fi

if [[ ! -f "$ENVF" ]]; then
  install -m 0600 "$HERE/runtime.env.example" "$ENVF"
fi
chown root:root "$ENVF"; chmod 0600 "$ENVF"
# shellcheck disable=SC1090
set -a; . "$ENVF"; set +a

if docker network inspect "$MUSE_SANDBOX_NETWORK" >/dev/null 2>&1; then
  internal="$(docker network inspect -f '{{.Internal}}' "$MUSE_SANDBOX_NETWORK")"
  bridge="$(docker network inspect -f '{{index .Options "com.docker.network.bridge.name"}}' "$MUSE_SANDBOX_NETWORK")"
  [[ "$internal" == true && "$bridge" == "$MUSE_SANDBOX_BRIDGE" ]] || die "existing Muse network does not match hardened contract"
else
  docker network create --driver bridge --internal     --subnet "$MUSE_SANDBOX_SUBNET" --gateway "$MUSE_SANDBOX_GATEWAY"     -o "com.docker.network.bridge.name=$MUSE_SANDBOX_BRIDGE"     "$MUSE_SANDBOX_NETWORK" >/dev/null
fi

docker build --pull=false -t van-muse-browser:rev1 "$HERE" >/dev/null
image_id="$(docker image inspect -f '{{.Id}}' van-muse-browser:rev1)"
[[ "$image_id" == sha256:* ]] || die "failed to resolve immutable sandbox image id"
image_arch="$(docker image inspect -f '{{.Architecture}}' "$image_id")"
[[ "$image_arch" == "arm64" ]] || die "sandbox image architecture mismatch: $image_arch"
docker run --rm --runtime=runsc-muse --network=none --read-only   --tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m   --entrypoint=/usr/bin/python3 "$image_id"   -c 'import os,platform; assert platform.machine() in ("aarch64","arm64"); assert os.geteuid()==0'   >/dev/null || die "gVisor Systrap smoke container failed"
docker run --rm --runtime=runsc-muse --network=none --read-only \
  --user=10001:100 \
  --tmpfs=/tmp:rw,nosuid,nodev,size=256m \
  --tmpfs=/dev/shm:rw,nosuid,nodev,size=256m \
  --entrypoint=/usr/bin/chromium "$image_id" \
  --headless=new \
  --user-data-dir=/tmp/chromium-smoke-profile \
  --disable-background-networking \
  --disable-component-update \
  --no-first-run \
  --no-default-browser-check \
  --dump-dom about:blank >/tmp/van-muse-chromium-smoke.html 2>/tmp/van-muse-chromium-smoke.err \
  || { tail -c 2000 /tmp/van-muse-chromium-smoke.err >&2 || true; die "Chromium failed inside gVisor without --no-sandbox"; }
grep -qi '<html' /tmp/van-muse-chromium-smoke.html || die "Chromium gVisor smoke returned no DOM"
rm -f /tmp/van-muse-chromium-smoke.html /tmp/van-muse-chromium-smoke.err
python3 - "$ENVF" "$image_id" <<'PY'
import re,sys
p,image=sys.argv[1:]
s=open(p,encoding="utf-8").read()
line=f"MUSE_SANDBOX_IMAGE_ID={image}"
if re.search(r"^MUSE_SANDBOX_IMAGE_ID=",s,re.M):
    s=re.sub(r"^MUSE_SANDBOX_IMAGE_ID=.*$",line,s,flags=re.M)
else:
    s += "\n"+line+"\n"
open(p,"w",encoding="utf-8").write(s)
PY

install -m 0755 "$HERE/runtime/van-muse-sandbox-mounts.sh" /usr/local/sbin/van-muse-sandbox-mounts
install -m 0755 "$HERE/runtime/van-muse-sandbox-firewall.sh" /usr/local/sbin/van-muse-sandbox-firewall
install -m 0755 "$HERE/runtime/van-muse-publish-cdp.sh" /usr/local/sbin/van-muse-publish-cdp
install -m 0755 "$HERE/runtime/van-muse-sandbox-health.sh" /usr/local/sbin/van-muse-sandbox-health
install -m 0755 "$HERE/van-muse-sandboxctl" /usr/local/bin/van-muse-sandboxctl
install -m 0755 "$HERE/qualify-muse-sandbox.sh" /usr/local/bin/qualify-muse-sandbox
for u in van-muse-sandbox-mounts.service van-muse-sandbox-firewall.service van-muse-sandbox-proxy.service van-muse-sandbox.service van-muse-cdp-bridge.service van-muse-sandbox-health.service van-muse-sandbox-health.timer; do
  install -m 0644 "$HERE/systemd/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload

BROWSER_ENV=/opt/van-trading/config/browser-runtime.env
[[ -f "$BROWSER_ENV" ]] || die "existing VAN browser runtime config missing: $BROWSER_ENV"
python3 - "$BROWSER_ENV" "$MUSE_SANDBOX_CDP_PORT" <<'PY'
import re,sys
p,port=sys.argv[1:]
s=open(p,encoding="utf-8").read()
line=f"VAN_BROWSER_EXTERNAL_CDP_MAP=muse_owner=http://127.0.0.1:{port}"
if re.search(r"^VAN_BROWSER_EXTERNAL_CDP_MAP=",s,re.M):
    s=re.sub(r"^VAN_BROWSER_EXTERNAL_CDP_MAP=.*$",line,s,flags=re.M)
else:
    s += "\n"+line+"\n"
open(p,"w",encoding="utf-8").write(s)
PY
chmod 0644 "$BROWSER_ENV"

# Do not enable boot persistence until the already-hardened egress proves its fixed
# regional identity. A staged sandbox must remain inert across reboot.
if ! /usr/local/bin/van-muse-egress-check >/dev/null 2>&1; then
  systemctl disable van-muse-sandbox-mounts.service van-muse-sandbox-firewall.service van-muse-sandbox-proxy.service van-muse-sandbox.service van-muse-cdp-bridge.service van-muse-sandbox-health.timer >/dev/null 2>&1 || true
  systemctl stop van-muse-cdp-bridge.service van-muse-sandbox.service van-muse-sandbox-proxy.service van-muse-sandbox-firewall.service >/dev/null 2>&1 || true
  log "sandbox staged but disabled: hardened US/CA egress is not GREEN"
  exit 20
fi

systemctl enable van-muse-sandbox-mounts.service van-muse-sandbox-firewall.service van-muse-sandbox-proxy.service van-muse-sandbox.service van-muse-cdp-bridge.service van-muse-sandbox-health.timer >/dev/null
systemctl restart van-muse-sandbox-firewall.service
systemctl restart van-muse-sandbox-proxy.service
systemctl restart van-muse-sandbox.service
systemctl restart van-muse-cdp-bridge.service

# Reuse the already-built VAN workers. They now see muse_owner as an externally managed
# loopback CDP profile while every other browser profile keeps its native runtime.
systemctl restart vati-browser-harness.service
systemctl restart vati-stagehand.service
curl -fsS --max-time 5 http://127.0.0.1:9141/health >/dev/null || die "Browser Harness failed after Muse CDP handoff"
curl -fsS --max-time 5 http://127.0.0.1:9140/health >/dev/null || die "Stagehand failed after Muse CDP handoff"

systemctl enable --now van-muse-sandbox-health.timer >/dev/null
/usr/local/bin/qualify-muse-sandbox | tee /var/lib/van-muse-sandbox/qualification-latest.json
jq -e '.status=="GREEN" and .required_failures==0' /var/lib/van-muse-sandbox/qualification-latest.json >/dev/null
log "MUSE_SANDBOX_GREEN image=$image_id gvisor=$GVISOR_RELEASE"
