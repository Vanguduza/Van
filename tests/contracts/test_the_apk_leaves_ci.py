"""Gate 1 — the build being green is not the same as the build being obtainable.

CI has compiled, tested, assembled and linted the Android app since run 35451735330.
Nothing left the runner but preview images and a latency JSON. The APK that
`:app:assembleDebug` produced was deleted with the workspace, so Gate 14 — the owner
installing VAN on their own device — had no artefact to install and would have had to
reproduce an Android toolchain that this repository's development container demonstrably
cannot fetch.

These tests pin the upload, and pin it to a path that is actually where the APK lands
rather than to where I believed it lands. A path assertion that only agrees with itself
would pass forever while the artifact step failed on every run.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github" / "workflows" / "van-ci.yml"
ANDROID = ROOT / "android"

#: Where the upload step says the APK is. Every other assertion in this file exists to
#: show that this string names the real output of the task CI actually runs.
DECLARED_PATH = "android/app/build/outputs/apk/debug/*.apk"


def _workflow() -> str:
    return LIVE.read_text(encoding="utf-8")


def test_an_apk_is_uploaded_at_all():
    workflow = _workflow()
    assert "name: van-debug-apk" in workflow, (
        "no APK artifact is published, so a green Android job still leaves the owner "
        "with nothing to install; Gate 14 cannot begin."
    )
    assert DECLARED_PATH in workflow


def test_the_upload_fails_rather_than_publishing_an_empty_artefact():
    """An empty artifact named van-debug-apk is worse than no artifact.

    The owner downloads it, finds nothing, and cannot tell whether the build stopped
    producing an APK or the upload pointed somewhere wrong.
    """
    workflow = _workflow()
    apk_step = workflow[workflow.index("name: van-debug-apk") :]
    apk_step = apk_step[: apk_step.index("- name:")]
    assert "if-no-files-found: error" in apk_step


def test_the_upload_runs_after_the_task_that_produces_the_apk():
    workflow = _workflow()
    assert ":app:assembleDebug" in workflow
    assert workflow.index(":app:assembleDebug") < workflow.index("name: van-debug-apk")


def test_the_declared_path_names_the_module_the_build_assembles():
    """`:app` in the Gradle invocation and `android/app/` in the artifact path.

    If the module were renamed or the APK-producing module changed, the two would stop
    agreeing and this test is the only thing that would say so before a run failed.
    """
    settings = (ANDROID / "settings.gradle.kts").read_text(encoding="utf-8")
    assert 'include(":app")' in settings

    module_dir = DECLARED_PATH.split("/build/outputs/")[0]
    assert module_dir == "android/app"
    assert (ROOT / module_dir / "build.gradle.kts").is_file()


def test_the_module_is_one_that_produces_an_apk():
    """Only `com.android.application` emits an APK; a library module emits an AAR.

    Asserted so the path is tied to the module's nature rather than to its name.
    """
    build_file = (ANDROID / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert 'id("com.android.application")' in build_file


def test_the_apk_is_a_ci_artefact_and_not_something_committed():
    """The repository ignores *.apk, so the only honest source of one is a CI run."""
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.apk" in [line.strip() for line in ignored]
    assert not list(ROOT.glob("**/*.apk")), (
        "an APK is checked in somewhere; a committed binary is not evidence that the "
        "current tree builds, and Gate 14 must install what CI produced."
    )
