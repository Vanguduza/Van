"""The CI emulator and explicitly selected test native ABI must agree."""

from pathlib import Path
import os
import shlex
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_ci_selects_the_emulator_native_abi_only_for_instrumentation():
    workflow = yaml.safe_load((ROOT / ".github/workflows/van-ci.yml").read_text())
    steps = workflow["jobs"]["android-instrumentation"]["steps"]
    runner = next(step for step in steps if step.get("uses", "").startswith("reactivecircus/android-emulator-runner@"))
    options = runner["with"]
    commands = [shlex.split(line) for line in options["script"].splitlines() if line.strip()]
    command = next(command for command in commands if ":app:connectedDebugAndroidTest" in command)
    assert f"-PVAN_TEST_ABI={options['arch']}" in command
    assert options["arch"] == "x86_64"
    for job_name, job in workflow["jobs"].items():
        if job_name != "android-instrumentation":
            assert "VAN_TEST_ABI" not in str(job)


def test_test_override_preserves_default_handset_abi_and_refuses_release():
    source = (ROOT / "android/app/build.gradle.kts").read_text()
    assert 'providers.gradleProperty("VAN_TEST_ABI").orNull' in source
    assert 'vanTestAbi == null || vanTestAbi == "x86_64"' in source
    assert 'abiFilters += "arm64-v8a"' in source
    assert 'if (vanTestAbi != null)' in source
    assert 'abiFilters.clear()' in source
    gate = source[source.index('gradle.taskGraph.whenReady'):]
    assert 'task.project == project && task.name.contains("Release")' in gate
    assert 'require(vanTestAbi == null || !releaseRequested)' in gate
    assert '"Release ABI refused: VAN_TEST_ABI is test-only"' in gate
    assert 'if (releaseRequested)' in gate
    assert 'n == "assembleRelease"' not in gate


@pytest.mark.skipif(not os.environ.get("VAN_ANDROID_GRADLE_BIN"), reason="opt-in actual AGP release guard check")
def test_actual_agp_direct_package_release_refuses_missing_core_deployment_profile(tmp_path):
    """Opt in with the prepared SDK/JDK/proxy environment; no signing key is read."""
    if (ROOT / "android/keystore.properties").exists():
        pytest.skip("requires an unconfigured production signing environment")
    result = subprocess.run(
        [os.environ["VAN_ANDROID_GRADLE_BIN"], "--no-daemon", "--console=plain",
         "--max-workers=2", ":app:packageRelease", "--dry-run"],
        cwd=ROOT / "android", capture_output=True, text=True, timeout=180,
    )
    output = result.stdout + result.stderr
    (tmp_path / "direct-package-release.log").write_text(output)
    assert result.returncode != 0
    assert "Release deployment target refused:" in output
    assert "VAN_DEPLOYMENT_PROFILE_FILE is required for van-trading-core releases" in output
    assert "Release ABI refused" not in output
