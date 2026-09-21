#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
[[ "$(hostname)" == "${VAN_TRADING_HOST_ID:-van-trading-core}" ]] || { echo "REFUSE: wrong host $(hostname)" >&2; exit 3; }

probe() {
  echo "RECOVERY_HOST=$(hostname)"
  echo "RECOVERY_ACTION=probe"
  date -u '+OBSERVED_AT=%Y-%m-%dT%H:%M:%SZ'
  uptime
  free -m
  df -h /
  systemctl is-active ssh.service 2>/dev/null || systemctl is-active sshd.service 2>/dev/null || true
  systemctl is-active oracle-cloud-agent.service 2>/dev/null || systemctl is-active snap.oracle-cloud-agent.oracle-cloud-agent.service 2>/dev/null || true
  for u in vati-commander.service vati-vekl.service vati-automation.service vati-supabase.service; do
    printf '%s=' "$u"; systemctl is-active "$u" 2>/dev/null || true
  done
  if [[ -x /home/ubuntu/.local/bin/van-local-commander-mcp ]]; then echo "FULL_DESKTOP_COMMANDER=INSTALLED"; else echo "FULL_DESKTOP_COMMANDER=MISSING"; fi
}

case "$ACTION" in
  probe) probe ;;
  collect_diagnostics)
    probe
    systemctl --failed --no-pager || true
    for u in vati-commander.service vati-vekl.service vati-automation.service; do
      journalctl -u "$u" -n 30 --no-pager 2>/dev/null || true
    done
    ;;
  restart_trading_services)
    # Trading sessions/order workers are intentionally not restarted here. VATI remains
    # the trading authority; this repairs only control/knowledge/automation services.
    for u in vati-vekl.service vati-commander.service vati-automation.service; do
      if systemctl cat "$u" >/dev/null 2>&1; then
        systemctl reset-failed "$u" || true
        systemctl restart "$u"
        systemctl is-active --quiet "$u"
        echo "$u=ACTIVE"
      fi
    done
    ;;
  recover_trading_chatgpt_sessions)
    # Full Desktop Commander is stdio/on-demand, not a daemon. Verify its installation
    # and leave session reconstruction to Hermes' durable session registry.
    [[ -x /home/ubuntu/.local/bin/van-local-commander-mcp ]] || { echo "FULL_DESKTOP_COMMANDER=MISSING" >&2; exit 6; }
    echo "CHATGPT_SESSION_RECOVERY=DELEGATED_TO_HERMES"
    echo "FULL_DESKTOP_COMMANDER=READY"
    ;;
  *)
    echo "REFUSE: allowed actions are probe collect_diagnostics restart_trading_services recover_trading_chatgpt_sessions" >&2
    exit 2 ;;
esac
