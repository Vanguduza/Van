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


def test_netcup_qualification_reads_workspace_as_forge_user():
    qualifier = _text("qualify-netcup-authoring.sh")
    assert 'runuser -u "$FORGE_USER" -- git -C "$WORKSPACE" rev-parse HEAD' in qualifier
    assert 'runuser -u "$FORGE_USER" -- git -C "$WORKSPACE" status --porcelain' in qualifier
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
