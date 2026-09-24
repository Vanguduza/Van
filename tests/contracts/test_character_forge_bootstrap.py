from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "character-forge"


def _text(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_character_forge_shell_scripts_parse():
    for name in (
        "bootstrap-netcup-authoring.sh",
        "qualify-netcup-authoring.sh",
        "commander-worker.sh",
        "rive-cli-smoke.sh",
    ):
        result = subprocess.run(
            ["bash", "-n", str(DEPLOY / name)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_bootstrap_refuses_protected_non_control_hosts():
    script = _text("bootstrap-netcup-authoring.sh")
    for host in ("oracle-admin", "vekl-worker", "van-trading-core"):
        assert host in script


def test_rive_cli_release_is_repo_pinned_not_trust_on_first_use():
    script = _text("bootstrap-netcup-authoring.sh")
    assert 'RIVE_CLI_VERSION="1.1.1"' in script
    assert 'RIVE_CLI_SHA256="41684e9d99fea98e01c2c155e07ec985130b95b640410dc0fbe4ca30c271a7d5"' in script
    assert 'rive-linux-x64.tar.gz' in script
    assert 'sha256sum -c -' in script
    assert 'releases.rive.app/cli/v$RIVE_CLI_VERSION/$RIVE_CLI_ARCHIVE' in script
    assert 'install.sh' not in script
    assert 'RIVE_INSTALLER_LOCK' not in script


def test_android_command_line_tools_are_checksum_pinned():
    script = _text("bootstrap-netcup-authoring.sh")
    assert "commandlinetools-linux-15859902_latest.zip" in script
    assert "4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583" in script
    assert "sha256sum -c -" in script


def test_bootstrap_and_requirements_share_image_pins():
    script = _text("bootstrap-netcup-authoring.sh")
    requirements = _text("requirements-authoring.txt")
    for pin in (
        "rembg[cpu,cli]==2.0.85",
        "vtracer==0.6.15",
        "Pillow==12.3.0",
    ):
        assert pin in requirements
        assert pin in script


def test_commander_surface_cannot_perform_owner_or_release_authority():
    worker = _text("commander-worker.sh")
    forbidden = (
        "confirm-source",
        "record-core-verdict",
        "record-acceptance",
        "release promote",
    )
    for command in forbidden:
        assert command not in worker
    assert 'exec rive "$@"' not in worker
    for required in (
        "source-admit",
        "gate",
        "remove-bg",
        "vectorize",
        "rive-create)",
        "rive-verify)",
        "rive-build)",
        "rive-test)",
        "rive-screenshot)",
        "rive-smoke)",
        "android-build",
        "instrumentation",
        "import-toolchain-lock",
    ):
        assert required in worker
    assert 'RIVE_PROJECT_ROOT=' in worker
    assert 'project_path()' in worker
    assert 'RIVE_CLOUD_WRITE_SENTINEL=' in worker
    assert 'require_cloud_write' in worker


def test_bootstrap_cannot_promote_character_forge_truth():
    script = _text("bootstrap-netcup-authoring.sh")
    forbidden = (
        "OWNER_CONFIRMED_COMPLETE",
        "owner record-core-verdict",
        "OWNER_ACCEPTED",
        'qual_emb_01',
        "release promote",
    )
    for token in forbidden:
        assert token not in script
    assert "AUTHORING_WORKSTATION_READY" in script


def test_cloud_rive_writes_are_explicitly_gated():
    worker = _text("commander-worker.sh")
    push_block = worker[worker.index("  rive-push)"):worker.index("  rive-publish)")]
    publish_block = worker[worker.index("  rive-publish)"):worker.index("  android-build)")]
    assert "require_cloud_write" in push_block
    assert "require_cloud_write" in publish_block
    assert 'exec rive push "$project"' in push_block
    assert 'exec rive "$project" --publish' in publish_block


def test_rive_smoke_is_fail_closed_and_checks_interactive_schema():
    smoke = _text("rive-cli-smoke.sh")
    for required in (
        "rive create",
        "--verify --format=json",
        "--once --format=json",
        "rive inspect",
        "StateMachineBool",
        "StateMachineTrigger",
        "built_riv_sha256",
    ):
        assert required in smoke
    assert "set +e" not in smoke
    assert "|| true" not in smoke


def _worker_sandbox(tmp_path: Path):
    """Run the real worker script against a throwaway workspace. The jail and authority checks
    run before any external tool, so no Rive/rembg install is needed to prove refusals."""
    import os
    state = tmp_path / "state"
    workspace = state / "work" / "Van"
    (workspace / "visual-authority" / "character-forge" / "09-rive-working" / "rml" / "van").mkdir(parents=True)
    (workspace / "visual-authority" / "assets").mkdir(parents=True)
    authority = tmp_path / "etc-van-character-forge"
    authority.mkdir()
    env = dict(os.environ, CHARACTER_FORGE_STATE_ROOT=str(state), CHARACTER_FORGE_WORKSPACE=str(workspace),
               CHARACTER_FORGE_AUTHORITY_DIR=str(authority), CHARACTER_FORGE_INSTALL_ROOT=str(tmp_path / "opt"))

    def run(*args, stdin=b""):
        return subprocess.run(["bash", str(DEPLOY / "commander-worker.sh"), *args], env=env, input=stdin,
                              capture_output=True)
    return run, workspace, state, authority


def test_worker_jails_every_prep_path(tmp_path):
    run, workspace, state, _ = _worker_sandbox(tmp_path)
    forge = workspace / "visual-authority" / "character-forge"
    for args in (
        ("remove-bg", "/etc/passwd", str(forge / "03-masks" / "x.png")),
        ("remove-bg", str(workspace / "visual-authority" / "assets" / "a.png"), str(state / "allow-rive-cloud-write")),
        ("vectorize", str(workspace / "visual-authority" / "assets" / "a.png"), str(workspace / "docs" / "character_forge" / "STATUS.json")),
        ("vectorize", str(workspace / "visual-authority" / "assets" / "a.png"), str(forge / "06-vectors-clean" / "van_layers.svg")),
        ("svg-lint", "/etc/hostname"),
        ("rml-cat", str(workspace / "tools" / "character_forge" / "gates.py")),
    ):
        result = run(*args)
        assert result.returncode == 2, (args, result.stderr)
        assert b"refused" in result.stderr, args


def test_worker_rml_put_writes_only_inside_the_named_project(tmp_path):
    run, workspace, _, _ = _worker_sandbox(tmp_path)
    project = workspace / "visual-authority" / "character-forge" / "09-rive-working" / "rml" / "van"
    ok = run("rml-put", str(project), "scene.rml", stdin=b"<Artboard name=\"Van\"/>\n")
    assert ok.returncode == 0, ok.stderr
    assert (project / "scene.rml").read_bytes() == b"<Artboard name=\"Van\"/>\n"
    for relpath in ("../../../../../tools/x.rml", "scene.riv", "../van2/scene.rml", "run.sh"):
        assert run("rml-put", str(project), relpath, stdin=b"x").returncode == 2, relpath
    assert run("rml-put", str(project.parent), "scene.rml", stdin=b"x").returncode == 2


def test_worker_cloud_write_sentinel_cannot_be_forged_by_the_forge_user(tmp_path):
    """The old sentinel lived under the vanforge-owned state root, so any worker command that
    writes a file (remove-bg OUTPUT) could create it. Now it must be root-owned in a root-owned
    directory; a sentinel owned by anyone else is refused."""
    import os
    run, workspace, state, authority = _worker_sandbox(tmp_path)
    project = workspace / "visual-authority" / "character-forge" / "09-rive-working" / "rml" / "van"
    (state / "allow-rive-cloud-write").write_text("")  # the old, forgeable location
    assert run("rive-push", str(project)).returncode == 3
    sentinel = authority / "allow-rive-cloud-write"
    sentinel.write_text("")
    if os.geteuid() == 0:
        os.chown(sentinel, 65534, 65534)  # nobody: what a non-root writer would produce
    assert run("rive-push", str(project)).returncode == 3
    assert run("forge-push", "forge/core-1", "msg").returncode == 3


def test_worker_rive_login_is_not_a_commander_command(tmp_path):
    run, *_ = _worker_sandbox(tmp_path)
    assert run("rive-login").returncode == 2
    assert "rive login" not in _text("commander-worker.sh")


def test_qualifier_runs_as_the_forge_user_and_uses_private_temp():
    qualify = _text("qualify-netcup-authoring.sh")
    assert "as_forge()" in qualify
    assert "/tmp/" not in qualify
    assert "CHARACTER_FORGE_QUALIFY_STRICT" in qualify
    assert "binary_sha256" in qualify
    bootstrap = _text("bootstrap-netcup-authoring.sh")
    assert "CHARACTER_FORGE_QUALIFY_STRICT=1" in bootstrap
    assert "install -d -o root -g root -m 0755 /etc/van-character-forge" in bootstrap
    assert "touch /etc/van-character-forge" not in bootstrap


def test_bootstrap_records_a_bare_inkscape_version():
    """CF-OPUS-002: the lock carries the bare version `vectors admit` compares against."""
    bootstrap = _text("bootstrap-netcup-authoring.sh")
    assert "INKSCAPE_VERSION=\"$(grep -oE" in bootstrap
    assert 'INKSCAPE_VERSION="$(inkscape --version | head -n1)"' not in bootstrap


def test_rive_smoke_proves_number_inputs_and_probes_rebuild_determinism():
    smoke = _text("rive-cli-smoke.sh")
    assert "StateMachineNumber" in smoke
    assert "smoke_number" in smoke
    assert "reproducible_build" in smoke


def test_netcup_qualification_reads_workspace_as_forge_user():
    qualifier = _text("qualify-netcup-authoring.sh")
    assert 'as_forge git -C "$WORKSPACE" rev-parse HEAD' in qualifier
    assert 'as_forge git -C "$WORKSPACE" status --porcelain' in qualifier
    assert 'observed="$(git -C "$WORKSPACE"' not in qualifier


def test_character_forge_pins_java17_across_bootstrap_qualifier_and_worker():
    expected = '/usr/lib/jvm/java-17-openjdk-amd64'
    bootstrap = _text("bootstrap-netcup-authoring.sh")
    qualifier = _text("qualify-netcup-authoring.sh")
    worker = _text("commander-worker.sh")
    assert expected in bootstrap
    assert expected in qualifier
    assert expected in worker
    assert 'JAVA_VERSION="$("$JAVA_HOME/bin/java" -version' in bootstrap
    assert '"$JAVA_HOME/bin/java" -version' in qualifier
    assert 'export JAVA_HOME' in worker
    assert 'PATH="$JAVA_HOME/bin:' in worker


def test_avd_creation_does_not_depend_on_host_hardware_profile_catalog():
    bootstrap = _text("bootstrap-netcup-authoring.sh")
    assert '--package "system-images;android-31;google_apis;x86_64"' in bootstrap
    assert '--device "pixel_6"' not in bootstrap
    assert '|| die "Android AVD $AVD_NAME was not created"' in bootstrap


def test_android_avd_home_is_explicit_and_shared():
    bootstrap = _text("bootstrap-netcup-authoring.sh")
    qualifier = _text("qualify-netcup-authoring.sh")
    worker = _text("commander-worker.sh")
    for text in (bootstrap, qualifier, worker):
        assert 'ANDROID_USER_HOME=' in text
        assert 'ANDROID_AVD_HOME=' in text
    assert 'as_forge env ANDROID_USER_HOME="$ANDROID_USER_HOME" ANDROID_AVD_HOME="$ANDROID_AVD_HOME"' in qualifier
    assert 'export ANDROID_USER_HOME' in worker
    assert 'export ANDROID_AVD_HOME' in worker


def test_scripts_the_bootstrap_runs_do_not_depend_on_their_file_mode():
    # The first live Netcup run qualified GREEN and then died on "Permission denied":
    # bootstrap-production-v3.sh was committed 100644 and executed directly from the
    # checkout. Invoking through bash makes the mode irrelevant; the mode is fixed too.
    import subprocess
    text = (ROOT / "deploy" / "character-forge" / "bootstrap-netcup-authoring.sh").read_text()
    assert 'bash "$WORKSPACE/deploy/character-forge/bootstrap-production-v3.sh"' in text
    modes = subprocess.run(
        ["git", "ls-files", "-s", "deploy/character-forge"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    scripts = [line for line in modes if line.endswith(".sh")]
    assert scripts and all(line.startswith("100755") for line in scripts), scripts


def test_stretchy_build_uses_a_forge_owned_checksum_pinned_node():
    # Netcup's /usr/bin/node links into another user's home, and apt's nodejs/npm would
    # replace it. The forge installs its own official Node under INSTALL_ROOT, verified by
    # checksum, and the V3 step builds Stretchy Studio with that Node only.
    import re
    base = (ROOT / "deploy" / "character-forge" / "bootstrap-netcup-authoring.sh").read_text()
    v3 = (ROOT / "deploy" / "character-forge" / "bootstrap-production-v3.sh").read_text()
    assert re.search(r'^NODE_VERSION="\d+\.\d+\.\d+"$', base, re.M)
    assert re.search(r'^NODE_SHA256="[0-9a-f]{64}"$', base, re.M)
    assert 'NODE_URL="https://nodejs.org/dist/' in base
    assert 'echo "$NODE_SHA256  $TMP_NODE/$NODE_ARCHIVE" | sha256sum -c -' in base
    apt_block = base[base.index("apt-get install -y --no-install-recommends"):base.index("[[ -x \"$JAVA17_HOME")]
    assert not re.search(r"\b(nodejs|npm)\b", apt_block), "apt node would overwrite the host's /usr/bin/node"
    code = "\n".join(l for l in base.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"(ln|install|cp|mv)\b[^\n]*/usr/(local/)?bin/node\b", code)
    assert 'NODE_BIN="$INSTALL_ROOT/node/current/bin"' in v3
    assert 'env PATH="$NODE_BIN:' in v3 and "bash -lc" not in v3
