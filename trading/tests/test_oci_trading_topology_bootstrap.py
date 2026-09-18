import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "deploy/van-trading-core/oci/harden-oracle-image-firewall.sh"
BOOTSTRAP = ROOT / "deploy/van-trading-core/bootstrap.sh"
QUALIFY = ROOT / "deploy/van-trading-core/qualify.sh"
REBUILD = ROOT / "deploy/van-trading-core/oci/rebuild-van-trading-core.py"

def test_oci_firewall_helper_is_syntax_valid_and_persistent():
    subprocess.run(["bash", "-n", str(HELPER)], check=True)
    text = HELPER.read_text()
    assert "/etc/iptables/rules.v4" in text
    assert "VAN_TRADING_MANAGED commander" in text
    assert "global SSH allow still present" in text
    assert "Commander rule for $cidr is not before OCI reject" in text

def test_bootstrap_applies_and_qualification_verifies_oci_firewall():
    boot = BOOTSTRAP.read_text()
    qual = QUALIFY.read_text()
    assert 'VAN_ADMIN_CIDRS="$ADMIN_CIDRS" VAN_PUBLIC_HOST="$PUBLIC_HOST" bash "$HERE/oci/harden-oracle-image-firewall.sh"' in boot
    assert 'harden-oracle-image-firewall.sh" --verify' in qual
    assert "oracle_image_firewall" in qual

def test_rebuild_protects_vekl_worker_and_control_nodes():
    text = REBUILD.read_text()
    assert "(\'oracle-admin\',\'dial-hermes-control\',\'vekl-worker\')" in text
    assert "VEKL_OCID" in text
    assert "protected instance selected for termination" in text


def test_public_caddy_template_uses_valid_multiline_handle_blocks():
    caddy = (ROOT / "deploy/van-trading-core/caddy/Caddyfile").read_text()
    assert "handle @ea { reverse_proxy" not in caddy
    assert "handle @automation { reverse_proxy" not in caddy
    assert 'handle { respond "not found" 404 }' not in caddy
    assert "handle @ea {\n        reverse_proxy 127.0.0.1:9443\n    }" in caddy
    assert "handle @automation {\n        reverse_proxy 127.0.0.1:5678\n    }" in caddy
