"""Source-only invariants for the additive OCI BRC agent installer.

These tests make no VM, network, root or device-pairing claims.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy/van-trading-core/better-remote-commander/install-agent.sh"
QUALIFY = ROOT / "deploy/van-trading-core/better-remote-commander/qualify-agent.sh"


def test_brc_installer_refuses_wrong_target_and_does_not_mutate_in_dry_run():
    src = INSTALLER.read_text(encoding="utf-8")
    assert "EXPECTED_HOST='van-trading-core'" in src
    assert "expected OCI A1 aarch64" in src
    assert "BRC requires Node.js >=22.13" in src
    assert "less than 2 GiB of root-disk headroom" in src
    assert "less than 1 GiB of available RAM" in src
    assert '[[ "$MODE" == \'--apply\' ]] || exit 0' in src
    assert src.index('[[ "$MODE" == \'--apply\' ]] || exit 0') < src.index("useradd --system")
    assert "BRC_INSTALL_PLAN=READY" in src


def test_brc_installation_is_pinned_separate_and_never_auto_activates():
    src = INSTALLER.read_text(encoding="utf-8")
    assert "PIN='cbe511702dd0147650353c29ac6ab1decd8afda1'" in src
    assert "EXPECTED_VERSION='2.0.2'" in src
    assert "--frozen-lockfile" in src
    assert "SERVICE_USER='vanbrc'" in src
    assert "NoNewPrivileges=true" in src
    assert "ProtectSystem=strict" in src
    assert "ProtectHome=true" in src
    assert "ReadWritePaths=$SERVICE_HOME" in src
    assert "MemoryMax=768M" in src
    assert "CPUQuota=50%" in src
    assert "ConditionPathExists=$ENV_PATH" in src
    assert "systemctl enable" not in src
    assert "systemctl start" not in src
    for forbidden in ("root sudo docker vati", "BRC_TRADING_SERVICES=UNTOUCHED"):
        assert forbidden in src


def test_preflight_refuses_collisions_and_untrusted_relay_config():
    src = INSTALLER.read_text(encoding="utf-8")
    assert "BRC workdir already exists and is not a Git workspace" in src
    assert "existing unit name is not managed by this installer" in src
    assert "existing BRC relay config must be root-owned mode 600" in src
    assert "existing BRC relay config must use an HTTPS relay" in src
    assert "BRC relay config must be a regular file" in src


def test_qualifier_does_not_claim_unobserved_remote_success():
    src = QUALIFY.read_text(encoding="utf-8")
    assert "BRC_MCP_REMOTE_ACCESS=NOT_VERIFIED" in src
    assert "BRC_OAUTH_PAIRING=NOT_STARTED" in src
    assert "BRC_MCP_REMOTE_ACCESS=NOT_VERIFIED_BY_LOCAL_PROBE" in src
    assert "if runuser -u vanbrc -- sudo -n true" in src
    assert "BRC_QUALIFICATION=SOURCE_AND_HOST_ISOLATION_PASS" in src
