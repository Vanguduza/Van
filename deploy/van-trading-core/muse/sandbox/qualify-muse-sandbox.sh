#!/usr/bin/env bash
set -uo pipefail
fails=0; checks=()
add(){ local n="$1" s="$2" d="$3"; checks+=("{\"check\":\"$n\",\"status\":\"$s\",\"detail\":$(printf '%s' "$d"|jq -Rs .)}"); [[ "$s" == GREEN ]] || fails=$((fails+1)); }
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 2; }
[[ -f /etc/van-muse-sandbox.env ]] || { echo 'missing /etc/van-muse-sandbox.env' >&2; exit 2; }
# shellcheck disable=SC1091
set -a; . /etc/van-muse-sandbox.env; set +a
CORE_IP="${VAN_CORE_IP:-10.0.1.233}"

for u in van-muse-sandbox-mounts.service van-muse-sandbox-firewall.service van-muse-sandbox-proxy.service van-muse-sandbox.service van-muse-cdp-bridge.service; do
  systemctl is-active --quiet "$u" && add "$u" GREEN active || add "$u" RED "$(systemctl is-active "$u" 2>&1)"
done

runtime="$(docker inspect -f '{{.HostConfig.Runtime}}' van-muse-browser 2>/dev/null || true)"
[[ "$runtime" == runsc-muse ]] && add gvisor_runtime GREEN "$runtime" || add gvisor_runtime RED "${runtime:-missing}"

priv="$(docker inspect -f '{{.HostConfig.Privileged}}' van-muse-browser 2>/dev/null || true)"
ro="$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' van-muse-browser 2>/dev/null || true)"
[[ "$priv" == false && "$ro" == true ]] && add container_privilege GREEN "privileged=$priv readonly_rootfs=$ro" || add container_privilege RED "privileged=$priv readonly_rootfs=$ro"

caps="$(docker inspect -f '{{json .HostConfig.CapAdd}}' van-muse-browser 2>/dev/null || true)"
python3 - "$caps" <<'PY' >/dev/null 2>&1
import json,sys
v=set(json.loads(sys.argv[1] or "[]") or [])
assert v == {"SETUID","SETGID","KILL"}, v
PY
[[ $? -eq 0 ]] && add capability_set GREEN "$caps" || add capability_set RED "$caps"

nnp="$(docker inspect -f '{{json .HostConfig.SecurityOpt}}' van-muse-browser 2>/dev/null || true)"
grep -q 'no-new-privileges' <<<"$nnp" && add no_new_privileges GREEN "$nnp" || add no_new_privileges RED "$nnp"

network_internal="$(docker network inspect -f '{{.Internal}}' "$MUSE_SANDBOX_NETWORK" 2>/dev/null || true)"
bridge="$(docker network inspect -f '{{index .Options "com.docker.network.bridge.name"}}' "$MUSE_SANDBOX_NETWORK" 2>/dev/null || true)"
[[ "$network_internal" == true && "$bridge" == "$MUSE_SANDBOX_BRIDGE" ]] && add internal_network GREEN "internal=$network_internal bridge=$bridge" || add internal_network RED "internal=$network_internal bridge=$bridge"
members="$(docker network inspect -f '{{json .Containers}}' "$MUSE_SANDBOX_NETWORK" 2>/dev/null || true)"
python3 - "$members" <<'PY' >/dev/null 2>&1
import json,sys
v=json.loads(sys.argv[1] or "{}")
assert len(v) == 1, v
assert next(iter(v.values())).get("Name") == "van-muse-browser", v
PY
[[ $? -eq 0 ]] && add isolated_network_membership GREEN "van-muse-browser only" || add isolated_network_membership RED "$members"

ip="$(docker inspect -f "{{with index .NetworkSettings.Networks \"$MUSE_SANDBOX_NETWORK\"}}{{.IPAddress}}{{end}}" van-muse-browser 2>/dev/null || true)"
[[ "$ip" == "$MUSE_SANDBOX_IP" ]] && add sandbox_ip GREEN "$ip" || add sandbox_ip RED "${ip:-missing}"

mounts="$(docker inspect -f '{{json .Mounts}}' van-muse-browser 2>/dev/null || true)"
python3 - "$mounts" <<'PY' >/dev/null 2>&1
import json,sys
mounts=json.loads(sys.argv[1] or "[]")
allowed={"/home/muse/profile","/home/muse/downloads","/run/secrets/control-token"}
dst={m.get("Destination") for m in mounts if m.get("Type")=="bind"}
assert dst == allowed, (dst,allowed)
assert all("docker.sock" not in str(m.get("Source","")) for m in mounts)
PY
[[ $? -eq 0 ]] && add bind_mount_allowlist GREEN "profile,downloads,control-token only" || add bind_mount_allowlist RED "$mounts"

published="$(docker inspect -f '{{json .HostConfig.PortBindings}}' van-muse-browser 2>/dev/null || true)"
[[ "$published" == "null" || "$published" == "{}" ]] && add no_docker_published_ports GREEN "$published" || add no_docker_published_ports RED "$published"

ctl="$(sudo -u vanmusectl /usr/local/bin/van-muse-sandboxctl health 2>/dev/null || true)"
python3 - "$ctl" <<'PY' >/dev/null 2>&1
import json,sys
d=json.loads(sys.argv[1])
assert d["ok"] is True
assert d["sandbox_supervisor_uid"] == 0
assert d["browser_uid"] == 10001
assert d["shell_endpoint"] is False
assert d["arbitrary_exec"] is False
PY
[[ $? -eq 0 ]] && add supervisor_boundary GREEN "$ctl" || add supervisor_boundary RED "${ctl:-unavailable}"

listener="$(ss -ltnH | awk '{print $4}' | grep ":$MUSE_SANDBOX_CDP_PORT$" || true)"
[[ "$listener" == "127.0.0.1:$MUSE_SANDBOX_CDP_PORT" ]] && add cdp_loopback GREEN "$listener" || add cdp_loopback RED "${listener:-missing}"

cdp_file=/run/van-browser/muse_owner/cdp-endpoint.json
if [[ -f "$cdp_file" ]] && jq -e --arg u "http://127.0.0.1:$MUSE_SANDBOX_CDP_PORT" '.profile_alias=="muse_owner" and .external_managed==true and .cdp_url==$u' "$cdp_file" >/dev/null; then
  add cdp_handoff GREEN "$(cat "$cdp_file")"
else
  add cdp_handoff RED "missing or invalid $cdp_file"
fi

# A direct TCP route to the public Internet, cloud metadata, or VATI control port is forbidden.
probe_py='import socket,sys; host=sys.argv[1]; port=int(sys.argv[2]); s=socket.socket(); s.settimeout(2); s.connect((host,port)); s.close()'
if docker exec van-muse-browser python3 -c "$probe_py" 1.1.1.1 443 >/dev/null 2>&1; then add direct_internet RED reachable; else add direct_internet GREEN blocked; fi
if docker exec van-muse-browser python3 -c "$probe_py" 169.254.169.254 80 >/dev/null 2>&1; then add metadata RED reachable; else add metadata GREEN blocked; fi
if docker exec van-muse-browser python3 -c "$probe_py" "$CORE_IP" 9133 >/dev/null 2>&1; then add vati_control RED reachable; else add vati_control GREEN blocked; fi

# The sandbox-facing proxy is not a host capability. Even root on the host must use
# the namespace qualifier rather than silently borrowing the sandbox's regional identity.
if curl --proxy "socks5h://$MUSE_SANDBOX_GATEWAY:$MUSE_SANDBOX_PROXY_PORT" -fsS --max-time 3 https://www.cloudflare.com/cdn-cgi/trace >/dev/null 2>&1; then
  add host_sandbox_proxy_borrow RED reachable
else
  add host_sandbox_proxy_borrow GREEN blocked
fi

# Prove the one admitted network path: SOCKS5 handshake originating inside the sandbox.
if docker exec van-muse-browser python3 - <<'PY' >/dev/null 2>&1
import socket
s=socket.create_connection(("172.31.77.1",17892),3)
s.sendall(b"\x05\x01\x00")
assert s.recv(2)==b"\x05\x00"
host=b"www.cloudflare.com"
s.sendall(b"\x05\x01\x00\x03"+bytes([len(host)])+host+(443).to_bytes(2,"big"))
r=s.recv(10)
assert len(r)>=2 and r[0]==5 and r[1]==0, r
s.close()
PY
then add socks_only_path GREEN admitted; else add socks_only_path RED failed; fi

for d in "$MUSE_SANDBOX_PROFILE_DIR" "$MUSE_SANDBOX_DOWNLOAD_DIR"; do
  opts="$(findmnt -no OPTIONS --target "$d" 2>/dev/null || true)"
  good=1
  for required in rw nosuid nodev noexec; do
    grep -qw "$required" <<<"${opts//,/ }" || good=0
  done
  [[ $good -eq 1 ]] && add "persistent_mount:$(basename "$d")" GREEN "$opts" || add "persistent_mount:$(basename "$d")" RED "${opts:-not-a-mount}"
done

profile_mib="$(du -sm "$MUSE_SANDBOX_PROFILE_DIR" 2>/dev/null | awk '{print $1}' || echo 0)"
download_mib="$(du -sm "$MUSE_SANDBOX_DOWNLOAD_DIR" 2>/dev/null | awk '{print $1}' || echo 0)"
(( profile_mib <= MUSE_SANDBOX_PROFILE_MAX_MIB )) && add profile_quota GREEN "${profile_mib}MiB" || add profile_quota RED "${profile_mib}MiB > ${MUSE_SANDBOX_PROFILE_MAX_MIB}MiB"
(( download_mib <= MUSE_SANDBOX_DOWNLOAD_MAX_MIB )) && add download_quota GREEN "${download_mib}MiB" || add download_quota RED "${download_mib}MiB > ${MUSE_SANDBOX_DOWNLOAD_MAX_MIB}MiB"

if /usr/local/bin/van-muse-egress-check >/tmp/muse-egress-id 2>/dev/null; then
  add egress_identity GREEN "$(cat /tmp/muse-egress-id)"
else
  add egress_identity RED "fixed US/CA egress qualification failed"
fi

status=GREEN; ((fails)) && status=RED
jq -n --arg status "$status" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"   --argjson failures "$fails" --argjson checks "[$(IFS=,; echo "${checks[*]}")]"   '{status:$status,required_failures:$failures,at:$at,checks:$checks}'
((fails==0))
