#!/usr/bin/env bash
#
# Rev 1.5 §13 — decide whether an installed Browser Stream Host is what it claims to be.
#
# This is the gate. `bootstrap.sh` completing proves files were written; it proves nothing
# about whether the debugger is fenced or the control agent refuses a stranger, and those
# are the two facts this host exists to guarantee.
#
# Every check reports GREEN, RED or UNKNOWN. UNKNOWN is not a pass: a check that could not
# run is recorded as one that did not run, because a qualification script that reports
# success for a check it skipped is worse than having no script.
set -uo pipefail

CDP_PORT="${VAN_BROWSER_CDP_PORT:-9222}"
AGENT_PORT="${VAN_BROWSER_CONTROL_PORT:-9443}"
STREAM_PORT="${VAN_BROWSER_STREAM_PORT:-8443}"
PKI_DIR="${VAN_BROWSER_PKI_DIR:-/opt/van-browser-stream/pki}"
PROFILE_MOUNT="${VAN_BROWSER_PROFILE_MOUNT:-/var/lib/van-browser-profiles}"

results=()
overall=0

record() { # name status detail
  results+=("{\"check\":\"$1\",\"status\":\"$2\",\"detail\":$(printf '%s' "$3" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}")
  if [ "$2" != "GREEN" ]; then overall=1; fi
}

# ---------------------------------------------------------------- 1. RB-117
# The check that comes first because it is the one that turns this host into a remote shell.
non_loopback=$(ip -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
if [ -z "$non_loopback" ]; then
  record "cdp_not_public" "UNKNOWN" "no global addresses found; cannot prove the debugger is fenced"
else
  exposed=""
  for addr in $non_loopback; do
    if timeout 2 bash -c "</dev/tcp/$addr/$CDP_PORT" 2>/dev/null; then
      exposed="$exposed $addr"
    fi
  done
  if [ -n "$exposed" ]; then
    record "cdp_not_public" "RED" "the debugger answered on:$exposed"
  else
    record "cdp_not_public" "GREEN" "debugger did not answer on any global address ($non_loopback)"
  fi
fi

# The other half: it must actually be listening on loopback, or the first check passed
# because nothing is running.
if timeout 2 bash -c "</dev/tcp/127.0.0.1/$CDP_PORT" 2>/dev/null; then
  record "cdp_on_loopback" "GREEN" "debugger answers on 127.0.0.1:$CDP_PORT"
else
  record "cdp_on_loopback" "RED" "nothing is listening on 127.0.0.1:$CDP_PORT, so the fencing check above proves nothing"
fi

# ---------------------------------------------------------------- 2. mTLS refusals
if ! command -v openssl >/dev/null 2>&1; then
  record "agent_refuses_anonymous" "UNKNOWN" "openssl is not installed"
  record "agent_refuses_foreign_ca" "UNKNOWN" "openssl is not installed"
else
  if echo | timeout 5 openssl s_client -connect "127.0.0.1:$AGENT_PORT" -CAfile "$PKI_DIR/ca.crt" >/dev/null 2>&1; then
    record "agent_refuses_anonymous" "RED" "the control agent completed a handshake with no client certificate"
  else
    record "agent_refuses_anonymous" "GREEN" "handshake without a client certificate was rejected"
  fi

  if [ -f "$PKI_DIR/foreign-client.crt" ]; then
    if echo | timeout 5 openssl s_client -connect "127.0.0.1:$AGENT_PORT" \
        -cert "$PKI_DIR/foreign-client.crt" -key "$PKI_DIR/foreign-client.key" >/dev/null 2>&1; then
      record "agent_refuses_foreign_ca" "RED" "a certificate from another CA was accepted"
    else
      record "agent_refuses_foreign_ca" "GREEN" "a certificate from another CA was rejected"
    fi
  else
    record "agent_refuses_foreign_ca" "UNKNOWN" "no foreign test certificate at $PKI_DIR/foreign-client.crt; run make-stream-pki.sh --with-foreign-test-cert"
  fi
fi

# ---------------------------------------------------------------- 3. public surface
for addr in $non_loopback; do
  if timeout 2 bash -c "</dev/tcp/$addr/$STREAM_PORT" 2>/dev/null; then
    record "stream_port_public" "GREEN" "stream endpoint answers on $addr:$STREAM_PORT"
    break
  fi
done
if ! printf '%s\n' "${results[@]}" | grep -q stream_port_public; then
  record "stream_port_public" "RED" "nothing answers on :$STREAM_PORT on any global address"
fi

# ---------------------------------------------------------------- 4. profile volume
if mountpoint -q "$PROFILE_MOUNT" 2>/dev/null; then
  source_dev=$(findmnt -no SOURCE "$PROFILE_MOUNT" 2>/dev/null)
  if printf '%s' "$source_dev" | grep -q "^/dev/mapper/"; then
    record "profile_volume_encrypted" "GREEN" "mounted from $source_dev"
  else
    record "profile_volume_encrypted" "RED" "mounted from $source_dev, which is not a dm-crypt device"
  fi
else
  record "profile_volume_encrypted" "RED" "$PROFILE_MOUNT is not a mount point"
fi

# ---------------------------------------------------------------- 5. Chromium privileges
chromium_user=$(ps -o user= -C chrome 2>/dev/null | head -1 | tr -d ' ')
if [ -z "$chromium_user" ]; then
  record "chromium_unprivileged" "UNKNOWN" "no chrome process found"
elif [ "$chromium_user" = "root" ]; then
  record "chromium_unprivileged" "RED" "chromium is running as root"
else
  record "chromium_unprivileged" "GREEN" "chromium runs as $chromium_user"
fi

if [ -S /var/run/docker.sock ] && [ -n "$chromium_user" ] && id -nG "$chromium_user" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
  record "no_docker_socket_reach" "RED" "$chromium_user is in the docker group, which is root one API call away"
else
  record "no_docker_socket_reach" "GREEN" "the browser user cannot reach the docker socket"
fi

printf '{"host":"%s","checked_at":"%s","checks":[%s]}\n' \
  "$(hostname)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(IFS=,; echo "${results[*]}")"

exit "$overall"
