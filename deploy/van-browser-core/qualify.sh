#!/usr/bin/env bash
#
# van-browser-core self-qualification (owner decision 2026-09-29 §1). JSON report; exits 0
# only when every required check is GREEN. A check it could not run is UNKNOWN, never GREEN.
#
# This is the host's view. The gateway's view is separate and stricter:
# van_gateway.automation.placement.stagehand_production_enabled(), which also requires the
# mTLS client identity, the owner-decided model and fresh worker health through the edge.
set -uo pipefail

# VAN_BROWSER_CORE_ETC: only for exercising this script against a scratch configuration.
ETC="${VAN_BROWSER_CORE_ETC:-/etc/van-browser-core}"
DATA=/var/lib/van-browser-core
PKI="$ETC/pki"
checks=()
fails=0
add() {
  local name="$1" status="$2" detail="$3" required="${4:-1}"
  checks+=("{\"check\":\"$name\",\"status\":\"$status\",\"required\":$required,\"detail\":$(printf '%s' "$detail" | jq -Rs .)}")
  if [[ "$status" != "GREEN" && "$required" == "1" ]]; then fails=$((fails+1)); fi
  return 0
}

# 1. The host is this zone and only this zone.
if grep -qx van-browser-core "$ETC/zone" 2>/dev/null; then add zone_marker GREEN "$ETC/zone"; else add zone_marker RED "zone marker missing or wrong"; fi
foreign=""
for marker in /opt/van-trading /var/lib/van-trading /etc/van-private-core /opt/van-private-core /etc/dial-control /opt/dial-control /etc/van-browser-stream; do
  [[ -e "$marker" ]] && foreign="$foreign $marker"
done
[[ -z "$foreign" ]] && add dedicated_host GREEN "no other zone installed" || add dedicated_host RED "foreign zone present:$foreign"
if systemctl list-unit-files 'vati-*' --no-legend 2>/dev/null | grep -q .; then add no_trading_units RED "vati-* units present on the browser zone"; else add no_trading_units GREEN "no vati-* units"; fi

# 2. Workers are loopback-only; the edge is the only non-loopback listener and is not wildcard.
listeners="$(ss -ltnH 2>/dev/null | awk '{print $4}')"
if [[ -z "$listeners" ]]; then add listeners UNKNOWN "ss unavailable"; else
  bad="$(printf '%s\n' "$listeners" | grep -E ':(9140|9141)$' | grep -Ev '^(127\.0\.0\.1|\[::1\]):' || true)"
  [[ -z "$bad" ]] && add workers_loopback_only GREEN "9140/9141 loopback" || add workers_loopback_only RED "$bad"
  wild="$(printf '%s\n' "$listeners" | grep -E '^(0\.0\.0\.0|\*|\[::\]):9443$' || true)"
  [[ -z "$wild" ]] && add edge_not_wildcard GREEN "9443 bound to a specific address" || add edge_not_wildcard RED "$wild"
fi

# 3. Worker identity.
if curl -fsS --max-time 3 http://127.0.0.1:9140/health >/tmp/vbcq-sh.json 2>/dev/null \
   && jq -e '.ok==true and .trust_zone=="van-browser-core" and .runtime_version=="4.1.0" and .runtime_version_source=="installed-package-metadata" and .act_endpoint_enabled==false and .stagehand_release_commit=="cd7b230778cf92269e4cb90e80d97f5113781c51" and .model_name=="anthropic/claude-sonnet-5" and .direct_agent_loop==false and .model_self_selection==false' /tmp/vbcq-sh.json >/dev/null; then
  add stagehand_identity GREEN "$(jq -c '{runtime_version,runtime_version_source,act_endpoint_enabled,trust_zone,model_name,model_key_present,provider_key_in_browser_memory}' /tmp/vbcq-sh.json)"
else add stagehand_identity RED "Stagehand health missing or not the van-browser-core 4.1.0 / anthropic/claude-sonnet-5 worker"; fi
if curl -fsS --max-time 3 http://127.0.0.1:9141/health >/tmp/vbcq-h.json 2>/dev/null \
   && jq -e '.ok==true and .trust_zone=="van-browser-core" and .runtime_version=="0.1.13" and .helper_authoring==false and .raw_cdp_http==false' /tmp/vbcq-h.json >/dev/null; then
  add harness_identity GREEN "$(jq -c '{runtime_version,trust_zone}' /tmp/vbcq-h.json)"
else add harness_identity RED "Harness health missing or not the van-browser-core worker"; fi

# 4. The edge refuses callers without a certificate from this zone's CA, and refuses /act.
EDGE_BIND="$(sed -n 's/^VAN_BROWSER_CORE_EDGE_BIND=//p' "$ETC/runtime.env" 2>/dev/null | tail -1)"
if [[ -n "$EDGE_BIND" ]]; then
  URL="https://$EDGE_BIND:9443/stagehand/health"
  if curl -fsS --max-time 5 --cacert "$PKI/ca.crt" "$URL" >/dev/null 2>&1; then add edge_refuses_no_cert RED "answered without a client certificate"; else add edge_refuses_no_cert GREEN "refused"; fi
  if [[ -f "$PKI/foreign-client.crt" ]]; then
    if curl -fsS --max-time 5 --cacert "$PKI/ca.crt" --cert "$PKI/foreign-client.crt" --key "$PKI/foreign-client.key" "$URL" >/dev/null 2>&1; then add edge_refuses_foreign_ca RED "accepted a foreign-CA certificate"; else add edge_refuses_foreign_ca GREEN "refused"; fi
  else add edge_refuses_foreign_ca UNKNOWN "run pki/make-browser-core-pki.sh --with-foreign-test-cert"; fi
  client="$(ls "$PKI"/client-*.crt 2>/dev/null | head -1)"
  if [[ -n "$client" ]]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --cacert "$PKI/ca.crt" --cert "$client" --key "${client%.crt}.key" -X POST -H 'content-type: application/json' --data '{}' "https://$EDGE_BIND:9443/stagehand/act")"
    [[ "$code" == 404 ]] && add edge_refuses_stagehand_act GREEN "404" || add edge_refuses_stagehand_act RED "HTTP $code"
  else add edge_refuses_stagehand_act UNKNOWN "no client certificate on this host to probe with (expected: moved to van-gateway)"; fi
else add edge_configured RED "VAN_BROWSER_CORE_EDGE_BIND not set"; fi

# 4b. The network-effect guard holds on the INSTALLED Chromium (review I7 minor 5, unit G11).
# CI qualified the guard on Chromium 1194; bootstrap.sh installs Playwright 1.63.0's Chromium
# (build 1243). Fetch interception, related-target auto-attach and the launch flags it relies
# on are Chromium behaviour, so the canary drives the running Harness worker (its real
# browser-harness child and this Chromium) against a fixture server and reads that server's
# log: an immediate and a 2.5 s-delayed handler POST must both be stopped and the lease must
# end frozen. A missing canary is RED, never skipped.
# Unit G14 (owner answer 2026-09-30 after unit G13, "In-zone canary origin (Recommended)"): the
# Chromium reaches nothing but through the egress proxy, which refuses every non-global
# upstream, so the fixture is served over TLS from VAN_BROWSER_CANARY_ORIGIN (a *.internal name)
# at the zone's overlay address VAN_BROWSER_CANARY_ADDRESS — the proxy's only allowed
# non-global upstream, armed here for the canary's own lease through the MAC-checked control
# socket with the dedicated task id van-guard-canary. The canary also checks the proxy: a
# WebSocket upgrade to the canary origin is refused (EGRESS_WEBSOCKET_REFUSED) and never reaches
# the fixture, and an ordinary task naming the canary origin is refused by the Harness
# (TASK_SCOPE_RESERVED_HOST) and by the proxy (POLICY_SCOPE_RESERVED_HOST).
CANARY=/opt/van-browser-core/runtime/guard_canary.py
if [[ ! -f "$CANARY" ]]; then
  add network_guard_canary RED "guard canary missing: $CANARY (re-run bootstrap.sh)"
elif python3.12 "$CANARY" --runtime-env "$ETC/runtime.env" >/tmp/vbcq-guard.json 2>/tmp/vbcq-guard.err \
     && jq -e '.ok==true' /tmp/vbcq-guard.json >/dev/null; then
  add network_guard_canary GREEN "$(jq -c '{chromium_version,origin,cases:(.cases|map_values(.ok)),websocket:.cases.proxy.websocket}' /tmp/vbcq-guard.json)"
else
  add network_guard_canary RED "$(jq -c '{chromium_version,origin,error,cases}' /tmp/vbcq-guard.json 2>/dev/null || head -c 400 /tmp/vbcq-guard.err)"
fi

# 5. No foreign-zone credential names in this zone's runtime environment.
if [[ -f "$ETC/runtime.env" ]] && grep -Eq '^(VAN_COMMANDER_|VAN_ACCOUNTS_REGISTRY|VAN_OWNER_AUTHORITY_KEYS|VAN_DATABASE_PATH|VAN_VATI_|DERIV_|CTRADER_|BRIDGE_|POSTGRES_PASSWORD|SERVICE_ROLE_KEY|VAN_INTERNAL_CONTROL|VAN_DEVICE_|HINDSIGHT|OPENVIKING|GITHUB_TOKEN|GH_TOKEN)' "$ETC/runtime.env"; then
  add runtime_env_clean RED "foreign-zone credential name in $ETC/runtime.env"
else add runtime_env_clean GREEN "no foreign-zone credential names"; fi

# 6. Unit G12 — egress proxy and zone firewall (owner answers 2026-09-30 after review I7:
#    "Egress proxy (Recommended)", "Firewall UDP in zone (Recommended)"). Each result below is
#    measured on this host, never read from a file this zone wrote about itself.
BROWSER_USER="${VAN_QUALIFY_BROWSER_USER:-van-browser}"
STAGEHAND_USER="${VAN_QUALIFY_STAGEHAND_USER:-van-stagehand}"
uid_of() { if [[ "$1" =~ ^[0-9]+$ ]]; then echo "$1"; else id -u "$1" 2>/dev/null || true; fi; }
reject_count() { nft list chain inet van_browser_core browser_out 2>/dev/null \
  | sed -n 's/.*counter packets \([0-9]*\) .*comment "van-tcp-bypass-reject".*/\1/p' | head -1; }
# Review I8 MAJOR-4: only the browser and Stagehand users' packets jump to browser_out; the
# output chain accepts everything else (packets without an owning socket included).
if ! command -v nft >/dev/null 2>&1; then add firewall_loaded RED "nft not installed"
elif ruleset="$(nft list table inet van_browser_core 2>/dev/null)"; then
  missing=""
  for c in van-browser-users van-local-reset van-dns-resolver van-udp-drop van-loopback-tcp van-tcp-bypass-reject van-other-drop; do
    grep -q "comment \"$c\"" <<<"$ruleset" || missing="$missing $c"
  done
  uid="$(uid_of "$BROWSER_USER")"; suid="$(uid_of "$STAGEHAND_USER")"
  jump="$(grep 'comment "van-browser-users"' <<<"$ruleset")"
  if [[ -z "$uid" || -z "$suid" ]]; then add firewall_loaded RED "browser user $BROWSER_USER or Stagehand user $STAGEHAND_USER does not exist"
  elif [[ -n "$missing" ]]; then add firewall_loaded RED "rules missing:$missing"
  elif grep -q "skuid !=" <<<"$ruleset" || grep -q "tcp dport 53" <<<"$ruleset"; then
    add firewall_loaded RED "an old-form rule is loaded (skuid != ... / TCP 53): reload firewall/van-browser-core.nft"
  elif grep -Eq "meta skuid \{ [^}]*\b($uid|\"?$BROWSER_USER\"?)\b" <<<"$jump" \
       && grep -Eq "meta skuid \{ [^}]*\b($suid|\"?$STAGEHAND_USER\"?)\b" <<<"$jump" && grep -q "jump browser_out" <<<"$jump"; then
    add firewall_loaded GREEN "table inet van_browser_core loaded for uids $uid (browser) and $suid (Stagehand)"
  else add firewall_loaded RED "ruleset is not bound to $BROWSER_USER ($uid) and $STAGEHAND_USER ($suid)"; fi
else add firewall_loaded RED "table inet van_browser_core not loaded"; fi
# The browser user's own sockets: UDP (STUN, QUIC) must fail locally; direct TCP must be reset.
rejects_before="$(reject_count)"
probe="$(setpriv --reuid="$BROWSER_USER" --regid="$(id -g "$BROWSER_USER" 2>/dev/null || echo 65534)" --clear-groups \
  python3 - 2>/dev/null <<'PY'
import errno, socket
out = []
for host, port in (("192.0.2.1", 3478), ("192.0.2.1", 443), ("127.0.0.1", 3478)):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(b"van-qualify", (host, port))
        out.append("SENT")
    except OSError as exc:
        out.append("BLOCKED" if exc.errno == errno.EPERM else "ERR%d" % exc.errno)
    finally:
        s.close()
print("udp", ",".join(out))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(("192.0.2.1", 443))
    print("tcp CONNECTED")
except ConnectionRefusedError:
    print("tcp REJECTED")
except socket.timeout:
    print("tcp TIMEOUT")
except OSError as exc:
    print("tcp ERR%d" % exc.errno)
PY
)"
udp="$(sed -n 's/^udp //p' <<<"$probe")"; tcp="$(sed -n 's/^tcp //p' <<<"$probe")"
[[ "$udp" == "BLOCKED,BLOCKED,BLOCKED" ]] && add browser_udp_blocked GREEN "UDP send as $BROWSER_USER: $udp" \
  || add browser_udp_blocked RED "UDP send as $BROWSER_USER: ${udp:-probe did not run}"
# Review I8 MINOR-5: a refused connect alone proves nothing (anything can answer RST); the
# ruleset's own reject counter must have counted it.
rejects_after="$(reject_count)"
if [[ "$tcp" == "REJECTED" && "$rejects_before" =~ ^[0-9]+$ && "$rejects_after" =~ ^[0-9]+$ && "$rejects_after" -gt "$rejects_before" ]]; then
  add browser_tcp_bypass_blocked GREEN "direct TCP as $BROWSER_USER: reset by van-tcp-bypass-reject ($rejects_before -> $rejects_after)"
else add browser_tcp_bypass_blocked RED "direct TCP as $BROWSER_USER: ${tcp:-probe did not run}; reject counter ${rejects_before:-?} -> ${rejects_after:-?}"; fi
# The egress proxy: running, keyed, no test overrides; it refuses without a policy and refuses
# a WebSocket upgrade and a POST under a read-only policy it has verified. The probe policy is
# MACed with the proxy's own key copy (root reads it here) for the alias qualify_probe only;
# nothing is sent upstream (every probe is refused before a connection is opened).
egress="$(python3 - "$ETC/runtime.env" "$BROWSER_USER" 2>/dev/null <<'PY'
import hashlib, hmac, json, pwd, re, socket, subprocess, sys
env = dict(re.findall(r"^([A-Z_][A-Z0-9_]*)=(.*)$", open(sys.argv[1], encoding="utf-8").read(), re.M))
ctl, key_file = env.get("VAN_EGRESS_CONTROL_SOCKET", ""), env.get("VAN_EGRESS_FENCE_KEY_FILE", "")
browser = pwd.getpwnam(sys.argv[2])
def call(msg):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5); s.connect(ctl); s.sendall(json.dumps(msg).encode() + b"\n")
        return json.loads(s.makefile().readline())
SEND = ("import re,socket,sys\n"
        "with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=5) as s:\n"
        "    s.sendall(bytes.fromhex(sys.argv[2])); head = s.recv(4096).decode('latin-1')\n"
        "m = re.search(r'X-Van-Egress-Refused: ([A-Z_]+)', head)\n"
        "print(m.group(1) if m else head.split('\\r\\n')[0][:40])\n")
def raw(port, data, as_browser=True):
    # Review I8 MAJOR-3: the listeners serve the browser user only, so the probe connects as it
    # (and once as root, which must be refused).
    cmd = [sys.executable, "-c", SEND, str(port), data.hex()]
    if as_browser:
        cmd = ["setpriv", f"--reuid={browser.pw_uid}", f"--regid={browser.pw_gid}", "--clear-groups"] + cmd
    return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip() or "NO_ANSWER"
try:
    h = call({"op": "health"})
    print("health", "OK" if h.get("ok") and h.get("trust_zone") == "van-browser-core" and h.get("policy_key") is True
          and h.get("test_overrides") is False and h.get("interception") == "zone-local-ca" else "BAD " + json.dumps(h)[:200])
    # An alias that is never given a policy, and one that is (both fixed: no port leak per run).
    empty = call({"op": "listener", "alias": "qualify_nopolicy"})["port"]
    print("nopolicy", raw(empty, b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"))
    alias = "qualify_probe"
    port = call({"op": "listener", "alias": alias})["port"]
    key = open(key_file, "rb").read().strip()
    scope = {"entries": [{"origin": "http://example.com", "path_prefix": None}]}
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    gen = 1 << 40
    mac = hmac.new(key, f"van-harness-effect/1\n{alias}\n{gen}\nqualify\nqualify\n0\n{digest}".encode(), hashlib.sha256).hexdigest()
    ok = call({"op": "policy", "alias": alias, "lease_generation": gen, "lease_holder_id": "qualify", "task_id": "qualify",
               "mutating": False, "task_scope": scope, "effect_mac": mac})
    forged = call({"op": "policy", "alias": alias, "lease_generation": gen, "lease_holder_id": "qualify", "task_id": "qualify",
                   "mutating": True, "task_scope": scope, "effect_mac": mac})
    print("policy", "OK" if ok.get("ok") is True and forged.get("error") == "POLICY_MAC_INVALID" else "BAD")
    print("websocket", raw(port, b"GET http://example.com/ws-pay HTTP/1.1\r\nHost: example.com\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n"))
    print("post", raw(port, b"POST http://example.com/pay HTTP/1.1\r\nHost: example.com\r\nContent-Length: 1\r\n\r\nx"))
    # Both are POSTs: if the check under test regressed, the write rule still refuses them
    # (a different code, so RED), and nothing reaches example.com either way.
    print("smuggle", raw(port, b"POST http://example.com/ HTTP/1.1\r\nHost: example.com\r\nX-A: 1\n\nPOST /pay HTTP/1.1\r\n\r\n"))
    print("otheruid", raw(port, b"POST http://example.com/pay HTTP/1.1\r\nHost: example.com\r\nContent-Length: 1\r\n\r\nx",
                          as_browser=False))
except Exception as exc:  # noqa: BLE001
    print("error", type(exc).__name__)
PY
)"
field() { sed -n "s/^$1 //p" <<<"$egress"; }
[[ "$(field health)" == OK ]] && add egress_proxy_active GREEN "keyed, zone-local CA, no test overrides" \
  || add egress_proxy_active RED "egress proxy health: $(field health)$(field error)"
[[ "$(field nopolicy)" == EGRESS_POLICY_UNKNOWN ]] && add egress_refuses_without_policy GREEN "EGRESS_POLICY_UNKNOWN" \
  || add egress_refuses_without_policy RED "$(field nopolicy)$(field error)"
[[ "$(field policy)" == OK ]] && add egress_policy_mac_enforced GREEN "valid MAC accepted, flipped flag refused" \
  || add egress_policy_mac_enforced RED "$(field policy)$(field error)"
[[ "$(field websocket)" == EGRESS_WEBSOCKET_REFUSED && "$(field post)" == EGRESS_WRITE_REFUSED ]] \
  && add egress_refuses_websocket_and_write GREEN "Upgrade: websocket and POST refused under a read-only policy" \
  || add egress_refuses_websocket_and_write RED "websocket=$(field websocket) post=$(field post)$(field error)"
[[ "$(field smuggle)" == EGRESS_REQUEST_INVALID ]] && add egress_refuses_smuggling GREEN "a bare-LF header injection is refused" \
  || add egress_refuses_smuggling RED "smuggle=$(field smuggle)$(field error)"
[[ "$(field otheruid)" == EGRESS_CLIENT_REFUSED ]] && add egress_refuses_other_users GREEN "a root client of a browser listener is refused" \
  || add egress_refuses_other_users RED "otheruid=$(field otheruid)$(field error)"
# Review I8 MINOR-5: measured on the browser processes themselves (/proc/<pid>/cmdline), not
# read from the Harness's own report: every Chromium browser process of the browser user runs
# with the proxy flags (the canary above leaves at least one running).
argv="$(python3 - "$BROWSER_USER" "$ETC/runtime.env" 2>/dev/null <<'PY'
import os, pwd, re, sys
uid = pwd.getpwnam(sys.argv[1]).pw_uid if not sys.argv[1].isdigit() else int(sys.argv[1])
env = dict(re.findall(r"^([A-Z_][A-Z0-9_]*)=(.*)$", open(sys.argv[2], encoding="utf-8").read(), re.M))
low, _, high = env.get("VAN_EGRESS_PORT_RANGE", "9150-9199").partition("-")
found, bad = 0, []
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        if os.stat(f"/proc/{pid}").st_uid != uid:
            continue
        args = [a.decode("utf-8", "replace") for a in open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0") if a]
    except OSError:
        continue
    if not any(a.startswith("--user-data-dir=") for a in args) or not any(a.startswith("--remote-debugging-port=") for a in args) \
            or any(a.startswith("--type=") for a in args):
        continue  # the browser process of a Harness-owned Chromium only (not its renderers)
    found += 1
    proxy = [re.fullmatch(r"--proxy-server=http://127\.0\.0\.1:(\d+)", a) for a in args if a.startswith("--proxy-server=")]
    if not (len(proxy) == 1 and proxy[0] and int(low) <= int(proxy[0].group(1)) <= int(high or low)
            and "--proxy-bypass-list=<-loopback>" in args and "--disable-quic" in args
            and any(a.startswith("--ignore-certificate-errors-spki-list=") for a in args)
            and "--ignore-certificate-errors" not in args):
        bad.append(pid)
print(found, len(bad))
PY
)"
if [[ "$argv" =~ ^([0-9]+)\ 0$ && "${BASH_REMATCH[1]}" -ge 1 ]] && jq -e '.egress_proxy==true' /tmp/vbcq-h.json >/dev/null 2>&1; then
  add harness_uses_egress_proxy GREEN "${BASH_REMATCH[1]} Chromium browser process(es) of $BROWSER_USER, each with the proxy flags"
else add harness_uses_egress_proxy RED "Chromium argv (processes, without proxy flags): ${argv:-none}; Harness /health egress_proxy: $(jq -c .egress_proxy /tmp/vbcq-h.json 2>/dev/null)"; fi

# Review I8 MINOR-4: Stagehand runs as its own user, which can read neither the lease-fence key
# nor the egress proxy's control socket (with them it could forge the gateway's MACs).
iso="$(python3 - "$STAGEHAND_USER" "$ETC/runtime.env" "$BROWSER_USER" 2>/dev/null <<'PY'
import os, pwd, re, subprocess, sys
env = dict(re.findall(r"^([A-Z_][A-Z0-9_]*)=(.*)$", open(sys.argv[2], encoding="utf-8").read(), re.M))
user = pwd.getpwnam(sys.argv[1])
running = subprocess.run(["pgrep", "-u", str(user.pw_uid), "-f", "stagehand_service.mjs"], capture_output=True).returncode == 0
as_browser = subprocess.run(["pgrep", "-u", sys.argv[3], "-f", "stagehand_service.mjs"],
                            capture_output=True).returncode == 0
code = ("import errno, socket, sys\n"
        "out = []\n"
        "for path in sys.argv[1:3]:\n"
        "    try:\n"
        "        open(path, 'rb').close(); out.append('READ')\n"
        "    except OSError as e:\n"
        "        out.append('DENIED' if e.errno in (errno.EACCES, errno.EPERM) else 'ERR%d' % e.errno)\n"
        "s = socket.socket(socket.AF_UNIX)\n"
        "try:\n"
        "    s.connect(sys.argv[3]); out.append('CONNECTED')\n"
        "except OSError as e:\n"
        "    out.append('DENIED' if e.errno in (errno.EACCES, errno.EPERM) else 'ERR%d' % e.errno)\n"
        "print(','.join(out))\n")
probe = subprocess.run(["setpriv", f"--reuid={user.pw_uid}", f"--regid={user.pw_gid}", "--init-groups", sys.executable, "-c", code,
                        env.get("VAN_HARNESS_FENCE_KEY_FILE", ""), env.get("VAN_EGRESS_FENCE_KEY_FILE", ""),
                        env.get("VAN_EGRESS_CONTROL_SOCKET", "")], capture_output=True, text=True, timeout=20).stdout.strip()
print("running" if running else "notrunning", "shared" if as_browser else "separate", probe or "noprobe")
PY
)"
[[ "$iso" == "running separate DENIED,DENIED,DENIED" ]] && add stagehand_isolated GREEN "Stagehand runs as $STAGEHAND_USER; fence keys and control socket denied" \
  || add stagehand_isolated RED "Stagehand isolation: ${iso:-probe did not run} (want: running separate DENIED,DENIED,DENIED)"

# 7. Model pin status (§4): informational, required=0. UNVERIFIED is not GREEN.
add model_immutable_snapshot UNKNOWN "immutable provider revision for claude-sonnet-5 not established" 0

printf '{"zone":"van-browser-core","fails":%d,"checks":[%s]}\n' "$fails" "$(IFS=,; echo "${checks[*]}")"
[[ "$fails" == 0 ]]
