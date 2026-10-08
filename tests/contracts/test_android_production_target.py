"""Execute the actual Gradle buildSrc target/trust validator without an Android SDK.

Synthetic public host names and CA keys are test inputs, never deployment receipts.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "android/buildSrc/src/main/java/com/dial/van/buildconfig/VanProductionTarget.java"


def _java_tool(name):
    configured = Path(os.environ.get("JAVA_HOME", "/nonexistent")) / "bin" / name
    prepared = Path("/workspace/.onboarding/jdk/usr/lib/jvm/java-21-openjdk-amd64/bin") / name
    return str(configured) if configured.is_file() else shutil.which(name) or (
        str(prepared) if prepared.is_file() else None
    )


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    javac, java = _java_tool("javac"), _java_tool("java")
    if not javac or not java:
        pytest.skip("actual production target validator requires a JDK")
    directory = tmp_path_factory.mktemp("production-target-classes")
    runner = directory / "TargetProbe.java"
    runner.write_text('''
import com.dial.van.buildconfig.VanProductionTarget;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
public final class TargetProbe {
    static Properties load(String name) throws Exception {
        if (name.equals("-")) return null;
        Properties result = new Properties();
        try (var stream = Files.newInputStream(Path.of(name))) { result.load(stream); }
        return result;
    }
    public static void main(String[] args) throws Exception {
        try {
            Properties historical = load(args[0]), profile = load(args[1]);
            var connection = VanProductionTarget.resolve(historical, profile,
                    args[3].equals("-") ? null : args[3],
                    args[4].equals("-") ? null : args[4]);
            if (args[2].equals("release")) {
                VanProductionTarget.requireReleaseProfile(profile, connection.baseUrl, connection.caPemB64);
            }
            System.out.println("ACCEPTED");
            if (args[2].equals("debug-values")) {
                System.out.println(connection.baseUrl);
                System.out.println(connection.caPemB64);
            }
        } catch (IllegalArgumentException invalid) {
            System.out.println("REFUSED: " + invalid.getMessage());
            System.exit(2);
        }
    }
}
''')
    result = subprocess.run([javac, "--release", "17", "-d", str(directory), str(HELPER), str(runner)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

    def run(profile_path=None, *, mode="release", url_override=None, ca_override=None):
        return subprocess.run([java, "-cp", str(directory), "TargetProbe",
                               str(ROOT / "android/van-gateway.properties"),
                               str(profile_path) if profile_path else "-", mode,
                               url_override if url_override is not None else "-",
                               ca_override if ca_override is not None else "-"],
                              capture_output=True, text=True, timeout=10)

    return run


def _ca(*, is_ca=True, offset=timedelta(0), private_suffix=False):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic VAN build test CA")])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now + offset - timedelta(hours=1))
            .not_valid_after(now + offset + timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    if private_suffix:
        pem += key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    return base64.b64encode(pem).decode(), cert.fingerprint(hashes.SHA256()).hex()


@pytest.fixture
def profile(tmp_path):
    encoded, fingerprint = _ca()
    values = {
        "VAN_DEPLOYMENT_PROFILE_VERSION": "1",
        "VAN_DEPLOYMENT_PROFILE_ID": "synthetic-owner-core-test",
        "VAN_BACKEND_HOST": "van-trading-core",
        "VAN_HERMES_HOST": "dial-control",
        "VAN_GATEWAY_INGRESS_HOST": "oracle-admin",
        "VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT": "synthetic-receipt-not-live",
        "VAN_GATEWAY_BASE_URL": "https://van-gateway.example.net:8443",
        "VAN_GATEWAY_CA_PEM_B64": encoded,
        "VAN_GATEWAY_CA_SHA256": fingerprint,
    }

    def write(**changes):
        selected = values | changes
        path = tmp_path / "owner-core.properties"
        path.write_text("\n".join(f"{key}={value}" for key, value in selected.items()) + "\n")
        return path

    return write


def test_release_refuses_the_historical_dial_control_fallback(probe):
    result = probe()
    assert result.returncode == 2
    assert "VAN_DEPLOYMENT_PROFILE_FILE is required" in result.stdout


def test_debug_preserves_the_historical_fixture_without_qualifying_it(probe):
    result = probe(mode="debug-values")
    assert result.returncode == 0
    assert result.stdout.splitlines()[1] == "https://62.83.35.103:8443"


def test_complete_core_profile_selects_matching_public_route_and_ca(probe, profile):
    assert probe(profile()).returncode == 0


def test_complete_core_profile_accepts_a_public_ipv6_literal(probe, profile):
    assert probe(profile(VAN_GATEWAY_BASE_URL="https://[2001:4860:4860::8888]:8443/")).returncode == 0


@pytest.mark.parametrize("field,value,reason", [
    ("VAN_DEPLOYMENT_PROFILE_VERSION", "0", "version must be 1"),
    ("VAN_DEPLOYMENT_PROFILE_ID", "", "profile ID"),
    ("VAN_DEPLOYMENT_PROFILE_ID", "bad id", "profile ID"),
    ("VAN_BACKEND_HOST", "dial-control", "backend must be van-trading-core"),
    ("VAN_HERMES_HOST", "van-trading-core", "Hermes host must remain dial-control"),
    ("VAN_GATEWAY_INGRESS_HOST", "dial-control", "separately admitted oracle-admin"),
    ("VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT", "", "capability receipt"),
    ("VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT", "unqualified receipt", "capability receipt"),
    ("VAN_GATEWAY_CA_SHA256", "", "fingerprint is missing"),
    ("VAN_GATEWAY_CA_SHA256", "0" * 64, "fingerprint does not match"),
    ("VAN_GATEWAY_CA_PEM_B64", "", "pinned CA certificate"),
])
def test_release_refuses_incomplete_stale_or_mismatched_profiles(probe, profile, field, value, reason):
    result = probe(profile(**{field: value}))
    assert result.returncode == 2
    assert reason in result.stdout


@pytest.mark.parametrize("url", [
    "https://10.77.0.4:8443", "https://192.168.1.4:8443", "https://172.16.1.2",
    "https://100.64.0.1", "https://127.0.0.1", "https://localhost",
    "https://[::1]:8443", "https://[fc00::4]:8443", "https://[::ffff:10.77.0.4]",
    "https://[2001:db8::1]", "https://203.0.113.7", "https://62.83.35.103:8443",
    "https://dial-control.internal", "http://van-gateway.example.net:8443",
    "https://user:pass@van-gateway.example.net", "https://van-gateway.example.net/path",
    "https://van-gateway.example.net//", "https://van-gateway.example.net?",
    "https://van-gateway.example.net#", "https://van-gateway.example.net:",
    "https://van-gateway.example.net:0", "https://van-gateway.example.net:65536",
    "https://van-gateway.example.net:443", "https://van-gateway.example.net",
    "https://256.1.2.3:8443",
])
def test_release_refuses_private_legacy_or_malformed_phone_routes(probe, profile, url):
    result = probe(profile(VAN_GATEWAY_BASE_URL=url))
    assert result.returncode == 2, result.stdout


@pytest.mark.parametrize("changes", [
    {"offset": timedelta(days=-1)}, {"offset": timedelta(days=1)},
    {"is_ca": False}, {"private_suffix": True},
])
def test_release_requires_one_current_ca_certificate(probe, profile, changes):
    encoded, fingerprint = _ca(**changes)
    result = probe(profile(VAN_GATEWAY_CA_PEM_B64=encoded, VAN_GATEWAY_CA_SHA256=fingerprint))
    assert result.returncode == 2


@pytest.mark.parametrize("overrides", [
    {"url_override": "https://van-gateway.example.net:8443"},
    {"ca_override": ""},
    {"url_override": "https://another.example.net", "ca_override": ""},
])
def test_profile_cannot_be_split_by_individual_build_overrides(probe, profile, overrides):
    result = probe(profile(), **overrides)
    assert result.returncode == 2
    assert "cannot be combined" in result.stdout


def test_debug_url_override_does_not_inherit_the_historical_ca(probe):
    result = probe(mode="debug-values", url_override="http://127.0.0.1:8000")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["ACCEPTED", "http://127.0.0.1:8000", ""]


def test_ca_only_override_is_refused(probe):
    result = probe(mode="debug", ca_override="QUJD")
    assert result.returncode == 2
    assert "matching gateway URL" in result.stdout


def test_actual_validator_is_called_by_every_release_task_graph():
    script = (ROOT / "android/app/build.gradle.kts").read_text()
    gate = script[script.index("gradle.taskGraph.whenReady"):script.index("compileOptions {")]
    assert 'task.project == project && task.name.contains("Release")' in gate
    assert gate.index("if (releaseRequested)") < gate.index("VanProductionTarget.requireReleaseProfile(")
    assert "productionGatewayProfile" in gate
    assert script.index("VanProductionTarget.resolve(") < script.index("android {")


@pytest.mark.skipif(not os.environ.get("VAN_ANDROID_GRADLE_BIN"), reason="opt-in actual AGP signing guard check")
def test_actual_agp_valid_target_still_refuses_missing_production_signing(profile, tmp_path):
    if (ROOT / "android/keystore.properties").exists():
        pytest.skip("requires an unconfigured production signing environment")
    result = subprocess.run(
        [os.environ["VAN_ANDROID_GRADLE_BIN"], "--no-daemon", "--console=plain", "--max-workers=2",
         ":app:packageRelease", "--dry-run", f"-PVAN_DEPLOYMENT_PROFILE_FILE={profile()}"],
        cwd=ROOT / "android", capture_output=True, text=True, timeout=180,
    )
    output = result.stdout + result.stderr
    (tmp_path / "valid-target-release.log").write_text(output)
    assert result.returncode != 0
    assert "Release signing refused: android/keystore.properties missing." in output
    assert "Release deployment target refused:" not in output
