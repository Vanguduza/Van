"""Hardening contracts for the Meta Muse egress enclave.

These tests protect the boundary that keeps Meta/browser state outside VATI while
allowing Hermes to consume a deterministic US/Canada egress path.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUSE = ROOT / "deploy" / "van-trading-core" / "muse"


def _read(relative: str) -> str:
    return (MUSE / relative).read_text(encoding="utf-8")


def test_trading_core_exposes_muse_proxy_on_loopback_only():
    bridge = _read("systemd/van-muse-bridge.service")
    assert "TCP4-LISTEN:17890,bind=127.0.0.1" in bridge
    assert "0.0.0.0:17890" not in bridge


def test_namespace_default_route_is_wireguard_only():
    up = _read("runtime/van-muse-netns-up.sh")
    assert "ip -n van-muse route replace default dev wg-muse" in up
    assert "ip route replace default" not in up
    assert "ip link set wg-muse netns van-muse" in up


def test_namespace_blocks_private_metadata_and_ipv6_escape():
    up = _read("runtime/van-muse-netns-up.sh")
    for cidr in ("10.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16"):
        assert cidr in up
    assert "net.ipv6.conf.all.disable_ipv6=1" in up
    assert 'oifname "wg-muse" ip daddr @blocked4 drop' in up


def test_egress_identity_is_pinned_to_ip_and_supported_country():
    env = _read("muse-egress.env.example")
    check = _read("runtime/van-muse-egress-check.sh")
    assert "MUSE_EXPECTED_EGRESS_IP=" in env
    assert "MUSE_EXPECTED_COUNTRY=US" in env
    assert "MUSE_EXPECTED_EGRESS_IP" in check
    assert "MUSE_EXPECTED_COUNTRY" in check
    assert "systemctl --no-block stop van-muse-bridge.service" in check


def test_install_proves_kill_switch_and_preserves_host_route():
    installer = _read("install-muse-egress.sh")
    assert "HOST_DEFAULT_BEFORE" in installer
    assert "HOST_DEFAULT_AFTER" in installer
    assert "ip -n van-muse link set wg-muse down" in installer
    assert "kill-switch failure" in installer


def test_exit_rejects_client_access_to_exit_vps_and_private_networks():
    exit_installer = _read("install-us-ca-exit.sh")
    assert 'iifname "wg-muse" drop' in exit_installer
    assert 'iifname "wg-muse" ip daddr @blocked4 drop' in exit_installer
    assert "MUSE_EXIT_EXPECTED_COUNTRY" in exit_installer


def test_meta_session_is_kept_on_hermes_side():
    launcher = _read("hermes/launch-muse-browser.sh")
    installer = _read("install-muse-egress.sh")
    assert "https://muse.ai/" in launcher
    assert "muse.ai" not in installer
    assert "--proxy-server=" in launcher
    assert "--disable-quic" in launcher
    assert "disable_non_proxied_udp" in launcher


def test_no_real_wireguard_or_meta_secret_is_committed():
    for path in MUSE.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "BEGIN PRIVATE KEY" not in text, path
        assert "MUSE_WG_PRIVATE_KEY=" not in text, path
        assert "facebook.com;c_user=" not in text, path
