from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_desktop_commander_runtime_is_exactly_pinned():
    lock = json.loads(read("deploy/van-trading-core/desktop-commander-runtime/package-lock.json"))
    pkg = lock["packages"]["node_modules/@wonderwhy-er/desktop-commander"]
    assert pkg["version"] == "0.2.50"
    assert pkg.get("integrity")


def test_trading_full_commander_is_machine_actuator_not_vati_domain_api():
    full = read("deploy/van-trading-core/hermes/register-full-desktop-commander-mcp.sh")
    bounded = read("deploy/van-trading-core/hermes/register-commander-mcp.sh")
    docs = read("hermes/mcp/README.md")

    assert "van_trading_local_commander" in full
    assert "hermes-commander-gateway.mjs" in full
    assert "'tools':" not in full
    assert "van_trading_commander" in bounded
    assert "'tools': {'include':" in bounded
    assert "VATI as the sole trading execution/risk authority" in docs


def test_private_transport_is_forced_command_and_fail_closed():
    transport = read("deploy/van-trading-core/hermes/install-full-commander-transport.sh")
    wrapper = read("deploy/van-trading-core/hermes/van-trading-full-commander-stdio.sh")

    assert "van-install-commander-key" in transport
    assert "ADMIN_USER" in transport and "COMMANDER_USER" in transport
    assert "vancommander" in transport
    assert "BatchMode=yes" in wrapper
    assert "IdentitiesOnly=yes" in wrapper
    assert "StrictHostKeyChecking=yes" in wrapper
    assert "StrictHostKeyChecking=no" not in wrapper


def test_full_commander_has_an_os_identity_and_secret_boundary():
    installer = read("deploy/van-trading-core/install-full-desktop-commander.sh")
    qualifier = read("deploy/van-trading-core/qualify.sh")
    wrapper = read("deploy/van-trading-core/hermes/van-trading-full-commander-stdio.sh")
    recovery = read("deploy/van-trading-core/van-github-recovery.sh")

    assert 'SERVICE_USER="${VAN_DESKTOP_COMMANDER_USER:-vancommander}"' in installer
    assert '/var/lib/van-commander' in installer
    assert 'passwd -l "$SERVICE_USER"' in installer
    assert 'for forbidden in sudo docker vati' in installer
    assert 'test -r /opt/van-trading/secrets/commander.token' in installer
    assert 'USER_NAME="${VAN_TRADING_COMMANDER_USER:-vancommander}"' in wrapper
    assert "full_desktop_commander_secret_boundary" in qualifier
    assert "full_desktop_commander_identity" in qualifier
    assert "/var/lib/van-commander/.local/bin/van-local-commander-mcp" in recovery


def test_full_commander_is_bootstrapped_on_trading_core():
    bootstrap = read("deploy/van-trading-core/bootstrap.sh")
    qualifier = read("deploy/van-trading-core/qualify.sh")
    installer = read("deploy/van-trading-core/install-full-desktop-commander.sh")

    assert "install-full-desktop-commander.sh" in bootstrap
    assert "install-github-recovery.sh" in bootstrap
    assert "full_desktop_commander" in qualifier
    assert "github_recovery_command" in qualifier
    assert "van-local-commander-mcp" in installer
    assert "npm --prefix" in installer and "ci --ignore-scripts" in installer


def test_github_recovery_is_enumerated_and_does_not_touch_order_sessions():
    recovery = read("deploy/van-trading-core/van-github-recovery.sh")

    assert "restart_trading_services" in recovery
    assert "recover_trading_chatgpt_sessions" in recovery
    assert "vati-vekl.service" in recovery
    assert "vati-commander.service" in recovery
    assert "vati-automation.service" in recovery
    assert "vati-session@" not in recovery
    assert "eval " not in recovery
    assert "VATI remains" in recovery


def test_hermes_side_qualification_proves_full_surface_and_authority_gate():
    qualifier = read("deploy/van-trading-core/hermes/qualify-full-desktop-commander-mcp.sh")

    assert "probe-full-local-commander.mjs" in qualifier
    assert "probe-commander-authority-gateway.mjs" in qualifier
    assert "van_trading_local_commander" in qualifier
    assert "capability_surface" in qualifier
    assert "FULL" in qualifier


def test_trading_core_commander_scripts_are_shell_syntax_valid():
    scripts = [
        "deploy/van-trading-core/qualify.sh",
        "deploy/van-trading-core/install-full-desktop-commander.sh",
        "deploy/van-trading-core/install-github-recovery.sh",
        "deploy/van-trading-core/van-github-recovery.sh",
        "deploy/van-trading-core/hermes/install-full-commander-transport.sh",
        "deploy/van-trading-core/hermes/register-commander-mcp.sh",
        "deploy/van-trading-core/hermes/register-full-desktop-commander-mcp.sh",
        "deploy/van-trading-core/hermes/qualify-full-desktop-commander-mcp.sh",
        "deploy/van-trading-core/hermes/van-trading-full-commander-stdio.sh",
        "deploy/van-trading-core/spmrf/install-spmrf-review-worker.sh",
        "deploy/van-trading-core/spmrf/install-shared-memory-client.sh",
    ]
    for rel in scripts:
        subprocess.run(["bash", "-n", str(ROOT / rel)], check=True)


def test_isolated_commander_has_only_enumerated_recovery_elevation():
    installer = read("deploy/van-trading-core/install-github-recovery.sh")
    qualifier = read("deploy/van-trading-core/qualify.sh")

    assert "vancommander-recovery" in installer
    assert "/usr/local/bin/van-github-recovery probe" in installer
    assert "/usr/local/bin/van-github-recovery collect_diagnostics" in installer
    assert "/usr/local/bin/van-github-recovery restart_trading_services" in installer
    assert "/usr/local/bin/van-github-recovery recover_trading_chatgpt_sessions" in installer
    assert "sudo -n true" in installer
    assert "generic sudo authority" in installer
    assert "full_desktop_commander_no_generic_sudo" in qualifier
    assert "full_desktop_commander_recovery_sudo" in qualifier


def test_privileged_recovery_diagnostics_are_redacted_before_commander_sees_them():
    recovery = read("deploy/van-trading-core/van-github-recovery.sh")
    assert "redact_stream()" in recovery
    assert "journalctl -u \"$u\" -n 30 --no-pager 2>/dev/null | redact_stream" in recovery
    for secret_word in ("password", "token", "api[_-]?key", "signing[_-]?key"):
        assert secret_word in recovery
    assert "[REDACTED]" in recovery
