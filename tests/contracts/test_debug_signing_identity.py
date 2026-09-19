"""P2-AND-016 — what signed the APK the owner installs, and whether it can upgrade.

The owner's first sideload of a CI-built APK failed with a bare "App not installed". One
cause fits every observation: Android generates a debug keystore per machine, a CI runner is
a fresh machine, so every run signed with a different key. Two builds of the same
application id signed by different keys cannot replace one another, and the dialog for that
is exactly the one the owner saw.

Two things were wrong and only one of them was the key. The other is that nothing in a run
said what the signature was, so the hypothesis could not be tested without the phone — the
audit's own distinction between NOT VERIFIED and NOT IMPLEMENTED, applied to a build.

These tests drive the two scripts rather than asserting the workflow mentions them. A test
that greps YAML for a step name passes just as well when the script it names is broken.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / ".github" / "workflows" / "van-ci.yml"
RESTORE = ROOT / "tools" / "ci" / "restore_debug_keystore.sh"
RECORD = ROOT / "tools" / "ci" / "record_apk_signing_identity.sh"

ANDROID_JOB = "android-and-visual-evidence"


def _step_names() -> list[str]:
    workflow = yaml.safe_load(LIVE.read_text(encoding="utf-8"))
    return [s.get("name", "") for s in workflow["jobs"][ANDROID_JOB]["steps"]]


def _index_of(fragment: str) -> int:
    names = _step_names()
    matches = [i for i, name in enumerate(names) if fragment in name]
    assert len(matches) == 1, f"{fragment!r} matched {matches} of {names}"
    return matches[0]


def test_the_key_is_restored_before_anything_is_built_with_it():
    """Restoring after the build would leave the APK signed by the runner's own key.

    The step would still succeed, the log would still say the owner's key was restored, and
    the artefact would still be unupgradable — a green run asserting the opposite of what
    happened.
    """
    assert _index_of("Debug signing key") < _index_of("Android unit tests, build and lint")


def test_the_signature_is_read_from_the_apk_that_is_published():
    """Between the build and the upload, so the identity describes the artefact."""
    assert _index_of("Android unit tests, build and lint") < _index_of("Debug APK signing identity")
    assert _index_of("Debug APK signing identity") < _index_of("Upload debug APK")


def test_the_identity_travels_with_the_apk():
    """An identity file that stays on the runner tells the owner nothing.

    The owner's question is about the APK in their downloads folder: can this replace what
    is already on the phone. That is answerable only if the certificate came with it.
    """
    workflow = yaml.safe_load(LIVE.read_text(encoding="utf-8"))
    upload = [
        s for s in workflow["jobs"][ANDROID_JOB]["steps"]
        if s.get("name", "").startswith("Upload debug APK")
    ][0]
    paths = upload["with"]["path"]
    assert "signing-identity.txt" in paths
    assert ".apk" in paths


def test_no_signing_key_is_committed_to_this_repository():
    """The obvious fix is the one that must not be taken.

    A debug keystore in the repository makes every build upgradable — including a build made
    by anyone who has the repository, over the owner's install, inheriting its data
    directory and the token vault in it. VAN holds a notification-listener grant. The key
    stays outside, supplied as a secret, and this is what stops a later reader from
    "fixing" it the short way.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    keys = [
        p for p in tracked
        if p.endswith((".keystore", ".jks", ".p12", ".pfx")) or Path(p).name == "debug.keystore"
    ]
    assert keys == [], f"signing material committed: {keys}"


def _run_restore(tmp_path: Path, secret: str | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("VAN_DEBUG_KEYSTORE_BASE64", None)
    if secret is not None:
        env["VAN_DEBUG_KEYSTORE_BASE64"] = secret
    return subprocess.run(
        ["bash", str(RESTORE), str(tmp_path / "debug.keystore")],
        capture_output=True, text=True, env=env,
    )


def test_a_run_with_no_secret_says_the_apk_cannot_upgrade(tmp_path):
    """The absence must be legible in the log, not inferred from a step that did nothing.

    This is the state every run of this programme has been in, and the reason the install
    failure went undiagnosed for a day: the build looked the same either way.
    """
    result = _run_restore(tmp_path, None)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "debug.keystore").exists()
    assert "cannot upgrade" in result.stdout


def test_a_secret_that_is_not_a_keystore_stops_the_build(tmp_path):
    """Not valid base64 at all: the script must fail rather than write rubbish."""
    result = _run_restore(tmp_path, "this is not base64 %%%")
    assert result.returncode != 0
    assert not (tmp_path / "debug.keystore").exists()


def _keytool_or_skip() -> str:
    keytool = shutil.which("keytool")
    if keytool is None:
        pytest.skip("keytool is not installed here; the CI runner has one via setup-java")
    return keytool


def _make_keystore(tmp_path: Path, *, alias: str, password: str) -> bytes:
    keytool = _keytool_or_skip()
    path = tmp_path / f"{alias}-{password}.keystore"
    subprocess.run(
        [
            keytool, "-genkeypair", "-keystore", str(path), "-storepass", password,
            "-keypass", password, "-alias", alias, "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "30", "-dname", "CN=Van Test, OU=closure, O=Van, C=ZA",
            "-storetype", "PKCS12",
        ],
        capture_output=True, text=True, check=True,
    )
    return base64.b64encode(path.read_bytes()).decode("ascii")


def test_a_supplied_keystore_is_restored_where_the_build_will_look(tmp_path):
    secret = _make_keystore(tmp_path, alias="androiddebugkey", password="android")
    target = tmp_path / "restored" / "debug.keystore"
    env = dict(os.environ, VAN_DEBUG_KEYSTORE_BASE64=secret)
    result = subprocess.run(
        ["bash", str(RESTORE), str(target)], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, result.stderr
    assert target.is_file()
    # The same key, not merely a file of the same length.
    listed = subprocess.run(
        [_keytool_or_skip(), "-list", "-keystore", str(target), "-storepass", "android",
         "-alias", "androiddebugkey"],
        capture_output=True, text=True,
    )
    assert listed.returncode == 0, listed.stdout + listed.stderr


def test_a_keystore_android_cannot_open_is_refused_before_the_build(tmp_path):
    """The failure mode this exists for: a key the packaging step would reject.

    Without the check the build runs for minutes and then fails on the key, while the log
    for this step says the owner's keystore was restored.
    """
    secret = _make_keystore(tmp_path, alias="someotherkey", password="hunter2hunter2")
    target = tmp_path / "restored" / "debug.keystore"
    env = dict(os.environ, VAN_DEBUG_KEYSTORE_BASE64=secret)
    result = subprocess.run(
        ["bash", str(RESTORE), str(target)], capture_output=True, text=True, env=env
    )
    assert result.returncode != 0
    assert not target.exists(), "a refused keystore must not be left where the build looks"
    assert "androiddebugkey" in result.stderr


def _fake_sdk(tmp_path: Path, script: str) -> Path:
    """An SDK layout with a stub apksigner, so the finder is exercised for real."""
    tools = tmp_path / "sdk" / "build-tools" / "34.0.0"
    tools.mkdir(parents=True)
    signer = tools / "apksigner"
    signer.write_text(script, encoding="utf-8")
    signer.chmod(0o755)
    return tmp_path / "sdk"


def _run_record(apk_dir: Path, sdk: Path | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("ANDROID_HOME", None)
    env.pop("ANDROID_SDK_ROOT", None)
    if sdk is not None:
        env["ANDROID_HOME"] = str(sdk)
    return subprocess.run(
        ["bash", str(RECORD), str(apk_dir)], capture_output=True, text=True, env=env
    )


def test_a_build_that_produced_no_apk_is_not_reported_as_signed(tmp_path):
    apk_dir = tmp_path / "debug"
    apk_dir.mkdir()
    sdk = _fake_sdk(tmp_path, "#!/bin/sh\necho 'Signer #1 certificate SHA-256 digest: abc'\n")
    result = _run_record(apk_dir, sdk)
    assert result.returncode != 0
    assert not (apk_dir / "signing-identity.txt").exists()


def test_the_certificate_digest_is_written_beside_the_apk(tmp_path):
    apk_dir = tmp_path / "debug"
    apk_dir.mkdir()
    (apk_dir / "app-debug.apk").write_bytes(b"not a real apk")
    digest = "11:22:33:44"
    sdk = _fake_sdk(
        tmp_path,
        f"#!/bin/sh\necho 'Signer #1 certificate SHA-256 digest: {digest}'\n",
    )
    result = _run_record(apk_dir, sdk)
    assert result.returncode == 0, result.stderr
    written = (apk_dir / "signing-identity.txt").read_text(encoding="utf-8")
    assert digest in written
    assert digest in result.stdout


def test_an_apksigner_that_prints_no_certificate_fails_the_run(tmp_path):
    """A published file that looks like evidence and contains none is the worse outcome.

    This is the silently-empty-search shape the ledger reconciler was caught in: a clean
    result and a clean result mean different things, and nothing could tell them apart.
    """
    apk_dir = tmp_path / "debug"
    apk_dir.mkdir()
    (apk_dir / "app-debug.apk").write_bytes(b"not a real apk")
    sdk = _fake_sdk(tmp_path, "#!/bin/sh\necho 'Verifies'\n")
    result = _run_record(apk_dir, sdk)
    assert result.returncode != 0


def test_a_runner_without_apksigner_says_so_rather_than_skipping(tmp_path):
    """Silence here would publish an APK whose signature nothing recorded."""
    if shutil.which("apksigner") is not None:
        pytest.skip("apksigner is on PATH here, so its absence cannot be constructed")
    apk_dir = tmp_path / "debug"
    apk_dir.mkdir()
    (apk_dir / "app-debug.apk").write_bytes(b"not a real apk")
    result = _run_record(apk_dir, None)
    assert result.returncode != 0
    assert "apksigner" in result.stderr
