"""The CI emulator and explicitly selected test native ABI must agree."""

from pathlib import Path
import os
import shlex
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def shell_commands(script):
    """Read literal CI command arguments, including the diagnostics' bash -c body."""
    lexer = shlex.shlex(script, posix=True, punctuation_chars=";&|\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    commands, current = [], []
    for token in lexer:
        if token and all(character in ";&|\n" for character in token):
            if current:
                commands.append(current)
                current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    for command in commands:
        if len(command) >= 3 and Path(command[0]).name in {"bash", "sh"} and command[1] == "-c":
            yield from shell_commands(command[2])
        else:
            yield command


def require_instrumentation_abi(script, architecture):
    commands = [command for command in shell_commands(script)
                if Path(command[0]).name == "gradlew" and ":app:connectedDebugAndroidTest" in command]
    assert len(commands) == 1, "one actual instrumentation Gradle invocation is required"
    overrides = [argument for argument in commands[0] if argument.startswith("-PVAN_TEST_ABI=")]
    assert overrides == [f"-PVAN_TEST_ABI={architecture}"], overrides


def test_ci_selects_the_emulator_native_abi_only_for_instrumentation():
    workflow = yaml.safe_load((ROOT / ".github/workflows/van-ci.yml").read_text())
    steps = workflow["jobs"]["android-instrumentation"]["steps"]
    runner = next(step for step in steps if step.get("uses", "").startswith("reactivecircus/android-emulator-runner@"))
    options = runner["with"]
    require_instrumentation_abi(options["script"], options["arch"])
    assert options["arch"] == "x86_64"
    for job_name, job in workflow["jobs"].items():
        if job_name != "android-instrumentation":
            assert "VAN_TEST_ABI" not in str(job)


@pytest.mark.parametrize("script", [
    "./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=x86_64",
    "bash -c 'set +e; ./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=x86_64; result=$?; echo diagnostics; exit \"$result\"'",
])
def test_abi_oracle_reads_direct_and_diagnostics_wrapped_commands(script):
    require_instrumentation_abi(script, "x86_64")


@pytest.mark.parametrize("script", [
    "./gradlew :app:connectedDebugAndroidTest",
    "./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=arm64-v8a",
    "./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=x86_64 -PVAN_TEST_ABI=arm64-v8a",
    "# ./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=x86_64",
    "echo ./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=x86_64",
    "bash -c 'echo ./gradlew :app:connectedDebugAndroidTest -PVAN_TEST_ABI=x86_64'",
])
def test_abi_oracle_rejects_missing_wrong_overridden_and_nonexecuting_declarations(script):
    with pytest.raises(AssertionError):
        require_instrumentation_abi(script, "x86_64")


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
