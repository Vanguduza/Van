#!/usr/bin/env bash
# Source-backed VM qualification; no claim about OAuth pairing or reachable MCP.
set -Eeuo pipefail
fail() { echo "BRC_QUALIFICATION=RED code=$1" >&2; exit 2; }
[[ "$(hostname)" == 'van-trading-core' ]] || fail WRONG_HOST
[[ "$(uname -m)" == 'aarch64' ]] || fail WRONG_ARCH
id vanbrc >/dev/null 2>&1 || fail SERVICE_ACCOUNT_MISSING
[[ "$(getent passwd vanbrc | cut -d: -f6)" == '/var/lib/van-brc' ]] || fail HOME_MISMATCH
for forbidden in root sudo docker vati; do
  id -nG vanbrc | tr ' ' '\n' | grep -Fxq "$forbidden" && fail "PRIVILEGED_GROUP"
done
readonly SRC='/var/lib/van-brc/releases/cbe511702dd0147650353c29ac6ab1decd8afda1'
[[ "$(runuser -u vanbrc -- git -C "$SRC" rev-parse HEAD 2>/dev/null)" == 'cbe511702dd0147650353c29ac6ab1decd8afda1' ]] || fail SOURCE_SHA
[[ -f "$SRC/packages/agent/dist/cli.js" ]] || fail CLI_MISSING
[[ -d /var/lib/van-brc/work/Van/.git ]] || fail SANDBOX_WORKSPACE_MISSING
[[ -s /etc/systemd/system/van-brc-agent.service ]] || fail UNIT_MISSING
if runuser -u vanbrc -- test -r /opt/van-trading/secrets/commander.token; then fail VATI_SECRET_EXPOSED; fi
if runuser -u vanbrc -- test -r /opt/van-trading/secrets/commander.token.hermes; then fail VATI_HERMES_SECRET_EXPOSED; fi
if runuser -u vanbrc -- sudo -n true >/dev/null 2>&1; then fail ROOT_SUDO_EXPOSED; fi
if [[ ! -e /etc/van-brc/agent.env ]]; then
  echo 'BRC_AGENT_PACKAGE=VERIFIED'
  echo 'BRC_AGENT_SERVICE=INSTALLED_NOT_ENABLED'
  echo 'BRC_OAUTH_PAIRING=NOT_STARTED'
  echo 'BRC_MCP_REMOTE_ACCESS=NOT_VERIFIED'
else
  printf 'BRC_AGENT_SERVICE='; systemctl is-active van-brc-agent.service || :
  echo 'BRC_OAUTH_PAIRING=REQUIRES_LIVE_REMOTE_EVIDENCE'
  echo 'BRC_MCP_REMOTE_ACCESS=NOT_VERIFIED_BY_LOCAL_PROBE'
fi
echo BRC_QUALIFICATION=SOURCE_AND_HOST_ISOLATION_PASS
