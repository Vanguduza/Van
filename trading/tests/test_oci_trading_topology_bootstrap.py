import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "deploy/van-trading-core/oci/harden-oracle-image-firewall.sh"
BOOTSTRAP = ROOT / "deploy/van-trading-core/bootstrap.sh"
QUALIFY = ROOT / "deploy/van-trading-core/qualify.sh"
REBUILD = ROOT / "deploy/van-trading-core/oci/rebuild-van-trading-core.py"
CADDY = ROOT / "deploy/van-trading-core/caddy/Caddyfile"

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



def test_caddyfile_uses_valid_multiline_handle_blocks_and_bootstrap_validates_it():
    text = CADDY.read_text()
    assert "handle @ea { reverse_proxy" not in text
    assert "handle @automation { reverse_proxy" not in text
    assert 'handle { respond "not found" 404 }' not in text
    assert "handle @ea {\n        reverse_proxy 127.0.0.1:9443\n    }" in text
    assert "handle @automation {\n        reverse_proxy 127.0.0.1:5678\n    }" in text
    boot = BOOTSTRAP.read_text()
    assert "caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile" in boot

def test_bootstrap_rejects_non_exact_commit_sha_before_provisioning():
    result = subprocess.run(["bash", str(BOOTSTRAP), "--dry-run", "--commit-sha=not-a-sha"], text=True, capture_output=True)
    assert result.returncode != 0
    assert "--commit-sha must be an exact 40-hex Git commit" in result.stderr
    subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)


def test_runtime_qualification_is_bound_to_exact_clean_repository_sha():
    qual = QUALIFY.read_text()
    rebuild = REBUILD.read_text()

    assert "VAN_EXPECTED_REPOSITORY_SHA" in qual
    assert 'git -C "$APP" rev-parse HEAD' in qual
    assert 'git -C "$APP" status --porcelain --untracked-files=all' in qual
    assert "--untracked-files=no" not in qual
    assert 'dirty="$(git -C "$APP" status --porcelain --untracked-files=all 2>/dev/null)" || status_ok=0' in qual
    assert 'elif (( status_ok == 0 )); then' in qual
    assert 'status --porcelain --untracked-files=all 2>/dev/null || true' not in qual
    assert "repository_exact_sha" in qual
    assert "repository_sha:$repository_sha" in qual
    assert "expected_repository_sha:$expected_repository_sha" in qual
    assert "jq -n" in qual

    assert "def resolve_repository_sha():" in rebuild
    assert "'git','ls-remote',REPO" in rebuild
    assert "EXPECTED_REPOSITORY_SHA" in rebuild
    assert "repository_sha')!=expected_sha" in rebuild

    boot = BOOTSTRAP.read_text()
    assert 'COMMIT_SHA="${VAN_COMMIT_SHA:-}"' in boot
    assert '--commit-sha=*) COMMIT_SHA="${a#*=}"' in boot
    assert 'checkout -q --detach "$COMMIT_SHA"' in boot
    assert 'reset -q --hard "$COMMIT_SHA"' in boot
    assert 'repo pinned to exact commit $COMMIT_SHA' in boot

    assert "git clone -q --no-checkout {shlex.quote(REPO)} /opt/van-bootstrap-source" in rebuild
    assert "checkout -q --detach {shlex.quote(expected_sha)}" in rebuild
    assert "--commit-sha={shlex.quote(expected_sha)}" in rebuild



def _run_firewall_verify(tmp_path, admin_cidrs):
    """Drive the helper's --verify path against a stub iptables and a fixture rules.v4."""
    import os
    import pytest
    if os.geteuid() != 0:
        pytest.skip("the helper refuses to run unless it is root")
    cidrs = [c for c in admin_cidrs.split(",") if c]
    managed = []
    for c in cidrs:
        managed.append(f'-A INPUT -s {c} -p tcp -m state --state NEW -m tcp --dport 22 -m comment --comment "VAN_TRADING_MANAGED admin-ssh" -j ACCEPT')
        managed.append(f'-A INPUT -s {c} -p tcp -m state --state NEW -m tcp --dport 9133 -m comment --comment "VAN_TRADING_MANAGED commander" -j ACCEPT')
    reject = "-A INPUT -j REJECT --reject-with icmp-host-prohibited"
    rules = tmp_path / "rules.v4"
    rules.write_text("# iptables configuration for Oracle Cloud Infrastructure\n*filter\n" + "\n".join(managed + [reject]) + "\nCOMMIT\n")
    live = tmp_path / "live.txt"
    live.write_text("-P INPUT ACCEPT\n" + "\n".join(managed + [reject]) + "\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "iptables"
    # -C succeeds only for rules present in the fixture; -S prints the fixture.
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'LIVE="{live}"\n'
        'if [[ "$1" == "-S" ]]; then cat "$LIVE"; exit 0; fi\n'
        'if [[ "$1" == "-C" ]]; then shift 2; want="-A INPUT"; for a in "$@"; do\n'
        '  if [[ "$a" == *" "* ]]; then want="$want \\"$a\\""; else want="$want $a"; fi; done\n'
        '  grep -Fxq -- "$want" "$LIVE"; exit $?; fi\n'
        "exit 0\n"
    )
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "VAN_ORACLE_RULES_V4": str(rules), "VAN_ADMIN_CIDRS": admin_cidrs}
    return subprocess.run(["bash", str(HELPER), "--verify"], text=True, capture_output=True, env=env)


def test_firewall_default_no_longer_admits_the_terminated_hermes_address():
    text = HELPER.read_text()
    assert 'ADMIN_CIDRS="${VAN_ADMIN_CIDRS:-10.0.0.123/32}"' in text
    for path in (HELPER, BOOTSTRAP, QUALIFY, REBUILD):
        body = path.read_text()
        # 10.0.0.184 may appear only in the comment that records why it was removed.
        assert "10.0.0.184/32" not in body, path


def test_firewall_verify_accepts_a_single_vcn_admin_source(tmp_path):
    result = _run_firewall_verify(tmp_path, "10.0.0.123/32")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("ORACLE_IMAGE_FIREWALL_GREEN")


def test_firewall_verify_rejects_overlay_and_empty_admin_lists(tmp_path):
    overlay = _run_firewall_verify(tmp_path, "10.77.0.1/32")
    assert overlay.returncode != 0
    assert "invalid admin CIDR: 10.77.0.1/32" in overlay.stderr


def test_firewall_verify_rejects_a_blank_admin_entry(tmp_path):
    blank = _run_firewall_verify(tmp_path, ",")
    assert blank.returncode != 0
    assert "ORACLE_IMAGE_FIREWALL_RED" in blank.stderr
