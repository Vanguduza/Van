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
    for required in (
        "source-admit",
        "gate",
        "remove-bg",
        "vectorize",
        "rive)",
        "android-build",
        "instrumentation",
        "import-toolchain-lock",
    ):
        assert required in worker


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
