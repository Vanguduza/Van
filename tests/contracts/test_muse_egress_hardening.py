"""Hardening contracts for the Meta Muse enclave.

The canonical path is now:
Hermes/Gateway -> existing Harness/Stagehand -> loopback CDP -> gVisor Muse sandbox
-> sandbox-only SOCKS bridge -> hardened US/Canada WireGuard egress.

The tests intentionally check source/deployment contracts only. Live qualification belongs
to qualify-muse-egress and qualify-muse-sandbox on VAN Trading Core.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MUSE = ROOT / "deploy" / "van-trading-core" / "muse"


def _read(relative: str) -> str:
    return (MUSE / relative).read_text(encoding="utf-8")


def test_trading_core_exposes_egress_proxy_on_loopback_only():
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


def test_gvisor_is_pinned_and_loaded_without_restarting_trading_containers():
    installer = _read("sandbox/install-muse-sandbox.sh")
    assert "GVISOR_RELEASE=release-20260928.0" in installer
    assert "fc23acbf56a98f9e95267eec431870cff9354dca7e0620da48749f881eed85b6" in installer
    assert '"runtimeArgs":["--platform=systrap"]' in installer
    assert "dockerd --validate" in installer
    assert "systemctl reload docker" in installer
    assert "systemctl restart docker" not in installer


def test_sandbox_has_no_direct_route_and_only_proxy_is_admitted():
    firewall = _read("sandbox/runtime/van-muse-sandbox-firewall.sh")
    service = _read("sandbox/systemd/van-muse-sandbox.service")
    installer = _read("sandbox/install-muse-sandbox.sh")
    qualifier = _read("sandbox/qualify-muse-sandbox.sh")

    assert "docker network create --driver bridge --internal" in installer
    assert 'iifname "$MUSE_SANDBOX_BRIDGE" drop' in firewall
    assert "MUSE_SANDBOX_PROXY_PORT" in firewall
    assert "--network=${MUSE_SANDBOX_NETWORK}" in service
    assert "--runtime=runsc-muse" in service
    assert "--network=host" not in service
    assert "1.1.1.1 443" in qualifier
    assert "169.254.169.254 80" in qualifier
    assert '"$CORE_IP" 9133' in qualifier
    assert "socks_only_path" in qualifier


def test_sandbox_root_supervisor_does_not_mean_root_chromium():
    supervisor = _read("sandbox/supervisor.py")
    service = _read("sandbox/systemd/van-muse-sandbox.service")
    dockerfile = _read("sandbox/Dockerfile")

    assert "sandbox supervisor must be root inside gVisor" in supervisor
    assert "CHROME_UID = 10001" in supervisor
    assert "--reuid={CHROME_UID}" in supervisor
    assert '"sandbox_supervisor_uid": os.geteuid()' in supervisor
    assert '"browser_uid": CHROME_UID' in supervisor
    assert '"shell_endpoint": False' in supervisor
    assert '"arbitrary_exec": False' in supervisor
    assert "--cap-drop=ALL" in service
    for cap in ("SETUID", "SETGID", "KILL"):
        assert f"--cap-add={cap}" in service
    assert "--privileged" not in service
    assert "/var/run/docker.sock" not in service
    assert "--no-sandbox" not in supervisor
    assert "USER 10001" not in dockerfile


def test_sandbox_rootfs_mounts_and_resources_are_bounded():
    service = _read("sandbox/systemd/van-muse-sandbox.service")
    qualifier = _read("sandbox/qualify-muse-sandbox.sh")
    env = _read("sandbox/runtime.env.example")

    assert "--read-only" in service
    assert "--pids-limit=${MUSE_SANDBOX_PIDS}" in service
    assert "--memory=${MUSE_SANDBOX_MEMORY}" in service
    assert "--cpus=${MUSE_SANDBOX_CPU}" in service
    assert "dst=/home/muse/profile" in service\n    assert "dst=/home/muse/downloads" in service\n    assert "control-token" in service
    assert "bind_mount_allowlist" in qualifier
    assert "MUSE_SANDBOX_PROFILE_MAX_MIB=8192" in env
    assert "MUSE_SANDBOX_DOWNLOAD_MAX_MIB=2048" in env


def test_existing_harness_and_stagehand_reuse_sandbox_cdp():
    harness = (ROOT / "deploy/van-trading-core/browser/harness_service.py").read_text(encoding="utf-8")
    runtime = (ROOT / "deploy/van-trading-core/browser/runtime.env.example").read_text(encoding="utf-8")
    stagehand = (ROOT / "deploy/van-trading-core/browser/stagehand_service.mjs").read_text(encoding="utf-8")
    profiles = (ROOT / "config/browser/profiles.yaml").read_text(encoding="utf-8")

    assert "VAN_BROWSER_EXTERNAL_CDP_MAP" in harness
    assert "EXTERNAL_CDP_HANDOFF_INVALID" in harness
    assert "muse_owner=http://127.0.0.1:17922" in runtime
    assert "readCdpEndpoint(alias)" in stagehand
    assert "  muse_owner:" in profiles


def test_cdp_is_loopback_only_on_host_and_published_as_external_handoff():
    bridge = _read("sandbox/systemd/van-muse-cdp-bridge.service")
    publish = _read("sandbox/runtime/van-muse-publish-cdp.sh")
    qualifier = _read("sandbox/qualify-muse-sandbox.sh")

    assert "bind=127.0.0.1" in bridge
    assert "muse_owner" in publish
    assert "external_managed:true" in publish
    assert "cdp_loopback" in qualifier
    assert "cdp_handoff" in qualifier


def test_no_real_wireguard_meta_or_control_secret_is_committed():
    for path in MUSE.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "BEGIN PRIVATE KEY" not in text, path
        assert "MUSE_WG_PRIVATE_KEY=" not in text, path
        assert "facebook.com;c_user=" not in text, path
        assert "Authorization: Bearer deadbeef" not in text, path


def test_socks_daemon_is_unprivileged_and_uses_namespace_dns():
    installer = _read("install-muse-egress.sh")
    service = _read("systemd/van-muse-socks.service")
    dante = _read("danted.conf")
    assert "id vanmuse" in installer
    assert "install -d -m 0700 /opt/van-muse-egress/secrets" in installer
    assert "User=vanmuse" in service
    assert "Group=vanmuse" in service
    assert "NetworkNamespacePath=/run/netns/van-muse" in service
    assert "BindReadOnlyPaths=/etc/netns/van-muse/resolv.conf:/etc/resolv.conf" in service
    assert "CapabilityBoundingSet=" in service
    assert "user.privileged: vanmuse" in dante
    assert "user.unprivileged: vanmuse" in dante
