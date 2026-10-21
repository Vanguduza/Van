"""Exercise real release packet bytes and cryptographic provisioning handoff failures."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import time
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from van_gateway.connectivity.provisioning import build_provisioning_payload, sign_provisioning_payload

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/release"))
import owner_release as release

spec = importlib.util.spec_from_file_location("packet_owner_installer", ROOT / "tools/provisioning/provision_owner_device.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
profile_spec = importlib.util.spec_from_file_location("packet_profile_fixture", ROOT / "tests/contracts/test_owner_core_deployment_profile.py")
profile_module = importlib.util.module_from_spec(profile_spec)
profile_spec.loader.exec_module(profile_module)
profile = profile_module.profile

SHA, SIGNER = "a" * 40, "b" * 64
PROVENANCE_ASSET = "assets/van-build-provenance.json"


def provenance(values, anchors):
    return {"schema_version": 1, "application_id": "com.dial.van", "source_sha": SHA,
            "gateway_url": values["VAN_GATEWAY_BASE_URL"],
            "gateway_ca_pem_b64_sha256": hashlib.sha256(values["VAN_GATEWAY_CA_PEM_B64"].encode()).hexdigest(),
            "connectivity_trusted_keys_sha256": hashlib.sha256(anchors.read_text().strip().encode()).hexdigest()}


def replace_asset(apk, content):
    with zipfile.ZipFile(apk) as archive:
        entries = {entry.filename: archive.read(entry) for entry in archive.infolist()
                   if entry.filename != PROVENANCE_ASSET}
    with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        if content is not None:
            archive.writestr(PROVENANCE_ASSET, content)


def native_fixture(alignment=16384):
    data = bytearray(120)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", data, 18, 183)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HH", data, 54, 56, 1)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 0, 0, 0, len(data), len(data), alignment)
    return bytes(data)


@pytest.fixture
def packet_inputs(profile, tmp_path, monkeypatch):
    properties = tmp_path / "android-owner-core.properties"
    properties.write_bytes(profile_module.module.render(profile)["android-owner-core.properties"])
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    anchors = tmp_path / "connectivity-trusted-keys.txt"
    anchors.write_text("synthetic-test-key=" + pem.replace("\n", "\\n") + "\n")
    apk = tmp_path / "owner.apk"
    with zipfile.ZipFile(apk, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lib/arm64-v8a/libfixture.so", native_fixture())
        archive.writestr("classes.dex", "synthetic fixture")
    values = release.profile_values(properties)
    with zipfile.ZipFile(apk, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PROVENANCE_ASSET, json.dumps(provenance(values, anchors)))
    build_config = tmp_path / "BuildConfig.java"
    build_config.write_text("\n".join("public static final String " + k + " = " + json.dumps(v) + ";" for k, v in
                           {"APPLICATION_ID": "com.dial.van", "VAN_SOURCE_SHA": SHA,
                            "VAN_GATEWAY_BASE_URL": values["VAN_GATEWAY_BASE_URL"],
                            "VAN_GATEWAY_CA_PEM_B64": values["VAN_GATEWAY_CA_PEM_B64"],
                            "VAN_CONNECTIVITY_TRUSTED_KEYS": anchors.read_text().strip()}.items()))
    calls = []
    def verifier(argv, **kwargs):
        calls.append(argv)
        output = ("Signer #1 certificate SHA-256 digest: " + SIGNER + "\n" if "verify" in argv else
                  "package: name='com.dial.van' versionCode='5' versionName='0.5.0'\n")
        return subprocess.CompletedProcess(argv, 0, stdout=output)
    monkeypatch.setattr(release.subprocess, "run", verifier)
    monkeypatch.setattr(release, "source_check", lambda root, sha: None)
    packet = release.create_packet(apk, properties, anchors, build_config=build_config,
                                   expected_sha=SHA, expected_signer=SIGNER, apksigner="synthetic-apksigner", aapt="synthetic-aapt")
    return apk, properties, anchors, build_config, key, packet, calls


def verify(inputs, **overrides):
    apk, properties, anchors, _, _, packet, _ = inputs
    values = release.profile_values(properties)
    args = {"expected_sha": SHA, "expected_signer": SIGNER, "device_gateway_url": values["VAN_GATEWAY_BASE_URL"],
            "apksigner": "synthetic-apksigner", "aapt": "synthetic-aapt", **overrides}
    return release.verify_packet(packet, apk, properties, anchors, **args)


def test_packet_matches_exact_bytes_without_claiming_live_or_producer_authenticity(packet_inputs):
    values = verify(packet_inputs)
    packet, calls = packet_inputs[5:]
    assert values["VAN_BACKEND_HOST"] == "van-trading-core"
    assert all(packet[name] is False for name in ["deployed", "provisioned", "live_qualified", "owner_e2e_verified", "producer_authenticity_verified"])
    assert calls[0][1:3] == ["verify", "--print-certs"]
    with zipfile.ZipFile(packet_inputs[0]) as archive:
        assert packet["compiled_provenance_sha256"] == hashlib.sha256(archive.read(PROVENANCE_ASSET)).hexdigest()


@pytest.mark.parametrize("defect", ["4kb", "invalid_elf", "unaligned_zip"])
def test_release_inspection_refuses_native_libraries_that_cannot_load_on_16kb_devices(packet_inputs, defect):
    apk = packet_inputs[0]
    content = b"not an ELF" if defect == "invalid_elf" else native_fixture(4096 if defect == "4kb" else 16384)
    compression = zipfile.ZIP_STORED if defect == "unaligned_zip" else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(apk, "w", compression=compression) as archive:
        archive.writestr("lib/arm64-v8a/libfixture.so", content)
    with pytest.raises(release.ReleaseRefused, match="native_"):
        release.apk_identity(apk, "synthetic-apksigner", "synthetic-aapt")


@pytest.mark.parametrize("defect", ["apk", "profile", "anchors", "signer", "source", "route", "abi", "package", "debuggable"])
def test_packet_refuses_artifact_identity_and_independent_binding_drift(packet_inputs, monkeypatch, defect):
    apk, properties, anchors, _, _, _, _ = packet_inputs
    overrides = {}
    if defect == "apk":
        with zipfile.ZipFile(apk, "a") as archive:
            archive.writestr("changed", "unreviewed byte change")
    elif defect == "profile":
        properties.write_text(properties.read_text().replace("synthetic-test-core", "other-profile"))
    elif defect == "anchors":
        anchors.write_text(anchors.read_text().replace("synthetic-test-key", "other-key"))
    elif defect == "signer":
        overrides["expected_signer"] = "c" * 64
    elif defect == "source":
        overrides["expected_sha"] = "d" * 40
    elif defect == "route":
        overrides["device_gateway_url"] = "https://other.example:8443"
    elif defect == "abi":
        with zipfile.ZipFile(apk, "a") as archive:
            archive.writestr("lib/x86_64/libfixture.so", "wrong handset build")
    else:
        def bad_manifest(argv, **kwargs):
            output = ("Signer #1 certificate SHA-256 digest: " + SIGNER + "\n" if "verify" in argv else
                      "package: name='" + ("wrong.app" if defect == "package" else "com.dial.van") +
                      "' versionCode='5' versionName='0.5.0'\n" + ("application-debuggable\n" if defect == "debuggable" else ""))
            return subprocess.CompletedProcess(argv, 0, stdout=output)
        monkeypatch.setattr(release.subprocess, "run", bad_manifest)
    with pytest.raises(release.ReleaseRefused):
        verify(packet_inputs, **overrides)


def test_packet_refuses_build_config_for_different_route(packet_inputs):
    apk, properties, anchors, build_config, *_ = packet_inputs
    build_config.write_text(build_config.read_text().replace("owner-ingress.example", "other.example"))
    with pytest.raises(release.ReleaseRefused, match="compiled_release_inputs"):
        release.create_packet(apk, properties, anchors, build_config=build_config, expected_sha=SHA,
                              expected_signer=SIGNER, apksigner="synthetic-apksigner", aapt="synthetic-aapt")


@pytest.mark.parametrize("source", [None, "c" * 40])
def test_packet_refuses_missing_or_stale_compiled_source(packet_inputs, source):
    apk, properties, anchors, build_config, *_ = packet_inputs
    old = 'public static final String VAN_SOURCE_SHA = "' + SHA + '";'
    build_config.write_text(build_config.read_text().replace(old, "" if source is None else
                            'public static final String VAN_SOURCE_SHA = "' + source + '";'))
    with pytest.raises(release.ReleaseRefused, match="compiled_release_inputs"):
        release.create_packet(apk, properties, anchors, build_config=build_config, expected_sha=SHA,
                              expected_signer=SIGNER, apksigner="synthetic-apksigner", aapt="synthetic-aapt")


@pytest.mark.parametrize("name", ["VAN_GATEWAY_CA_PEM_B64", "VAN_CONNECTIVITY_TRUSTED_KEYS"])
def test_packet_refuses_compiled_trust_drift(packet_inputs, name):
    apk, properties, anchors, build_config, *_ = packet_inputs
    lines = build_config.read_text().splitlines()
    build_config.write_text("\n".join('public static final String ' + name + ' = "changed";'
                                    if line.startswith("public static final String " + name + " = ") else line
                                    for line in lines))
    with pytest.raises(release.ReleaseRefused, match="compiled_release_inputs"):
        release.create_packet(apk, properties, anchors, build_config=build_config, expected_sha=SHA,
                              expected_signer=SIGNER, apksigner="synthetic-apksigner", aapt="synthetic-aapt")


@pytest.mark.parametrize("defect", ["source_sha", "gateway_url", "gateway_ca_pem_b64_sha256",
                                    "connectivity_trusted_keys_sha256", "missing", "malformed", "oversized", "duplicate",
                                    "boolean_schema", "extra_field"])
def test_packet_refuses_actual_apk_provenance_drift_even_with_current_build_config(packet_inputs, defect):
    apk, properties, anchors, build_config, *_ = packet_inputs
    metadata = provenance(release.profile_values(properties), anchors)
    if defect in metadata:
        metadata[defect] = "stale-build-value"
    if defect == "boolean_schema":
        metadata["schema_version"] = True
    if defect == "extra_field":
        metadata["extra"] = "unrecognized provenance"
    content = None if defect == "missing" else b"[" if defect == "malformed" else b" " * 4097 if defect == "oversized" else json.dumps(metadata)
    replace_asset(apk, content)
    if defect == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"):
            with zipfile.ZipFile(apk, "a") as archive:
                archive.writestr(PROVENANCE_ASSET, json.dumps(metadata))
    with pytest.raises(release.ReleaseRefused, match="apk_build_provenance"):
        release.create_packet(apk, properties, anchors, build_config=build_config, expected_sha=SHA,
                              expected_signer=SIGNER, apksigner="synthetic-apksigner", aapt="synthetic-aapt")


def test_independent_installer_rejects_stale_apk_even_if_unsigned_packet_is_relabelled(packet_inputs):
    apk, properties, anchors, _, _, packet, _ = packet_inputs
    metadata = provenance(release.profile_values(properties), anchors)
    metadata["source_sha"] = "c" * 40
    replace_asset(apk, json.dumps(metadata))
    # The packet is a review artifact, not a signature: changing its hash must not
    # be sufficient to relabel the source embedded inside the verified APK.
    packet["apk"]["sha256"] = release.digest(apk)
    packet["apk"]["bytes"] = apk.stat().st_size
    with pytest.raises(release.ReleaseRefused, match="apk_build_provenance"):
        verify(packet_inputs)


def test_independent_installer_requires_the_actual_signed_metadata_digest(packet_inputs):
    packet_inputs[5]["compiled_provenance_sha256"] = "0" * 64
    with pytest.raises(release.ReleaseRefused, match="independent_binding_mismatch"):
        verify(packet_inputs)


@pytest.mark.parametrize("defect", ["clean", "wrong_head", "dirty", "untracked"])
def test_exact_release_source_check_uses_real_git_head_and_worktree(tmp_path, defect):
    repository = tmp_path / "checkout"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    tracked = repository / "source.txt"
    tracked.write_text("selected source\n")
    subprocess.run(["git", "-C", str(repository), "add", "source.txt"], check=True)
    subprocess.run(["git", "-C", str(repository), "-c", "user.name=Synthetic test",
                    "-c", "user.email=synthetic@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], check=True)
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    if defect == "dirty":
        tracked.write_text("changed source\n")
    if defect == "untracked":
        (repository / "unreviewed.txt").write_text("unreviewed\n")
    if defect == "clean":
        release.source_check(repository, head)
    else:
        with pytest.raises(release.ReleaseRefused, match="exact_clean_release_source"):
            release.source_check(repository, "f" * 40 if defect == "wrong_head" else head)


def envelope(inputs):
    values = release.profile_values(inputs[1])
    payload = build_provisioning_payload(gateway_url=values["VAN_GATEWAY_BASE_URL"], bootstrap_token="synthetic-bootstrap-" + "a" * 40,
                                         pairing_token="synthetic-pairing-" + "b" * 40, attestation_challenge="synthetic-challenge")
    private = inputs[4].private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return {"payload": payload, "kid": "synthetic-test-key", "signature": sign_provisioning_payload(payload, private_pem=private)}


def test_installer_verifies_actual_gateway_p256_signature_before_handoff(packet_inputs):
    installer.verify_handoff(envelope(packet_inputs), packet_inputs[2], release.profile_values(packet_inputs[1])["VAN_GATEWAY_BASE_URL"])


@pytest.mark.parametrize("defect", ["signature", "expired", "route", "kid", "standing_credential", "lifetime", "challenge"])
def test_installer_refuses_unusable_or_wrong_trust_envelope(packet_inputs, defect):
    signed = envelope(packet_inputs)
    if defect == "signature":
        signed["signature"] = "00" * 64
    elif defect == "expired":
        signed["payload"]["expires_at_ms"] = 1
    elif defect == "route":
        signed["payload"]["gateway_url"] = "https://other.example:8443"
    elif defect == "kid":
        signed["kid"] = "unknown-key"
    elif defect == "standing_credential":
        signed["payload"]["access_token"] = "synthetic-standing-token"
    elif defect == "lifetime":
        signed["payload"]["expires_at_ms"] = signed["payload"]["issued_at_ms"] + 3_600_000
    else:
        signed["payload"]["attestation_challenge"] = ""
    with pytest.raises(installer.ProvisioningFailed, match="release trust, route or lifetime"):
        installer.verify_handoff(signed, packet_inputs[2], release.profile_values(packet_inputs[1])["VAN_GATEWAY_BASE_URL"])


def test_java_properties_secret_escapes_do_not_create_extra_assignments():
    escaped = release.properties_escape("secret\nkeyAlias=androiddebugkey\r\t\\snowman ☃")
    assert "\n" not in escaped and "\r" not in escaped and "\t" not in escaped
    assert "\\u000a" in escaped and "\\u2603" in escaped


def test_missing_bound_release_secrets_refuse_before_creating_material(tmp_path, monkeypatch):
    target = tmp_path / "missing-inputs"
    monkeypatch.setenv("VAN_OWNER_RELEASE_INPUT_DIR", str(target))
    monkeypatch.delenv("VAN_OWNER_KEYSTORE_BASE64", raising=False)
    with pytest.raises(release.ReleaseRefused, match="bindings_missing"):
        release.restore_ci_inputs()
    assert not target.exists()


def test_release_workflow_keeps_secrets_private_and_delivers_verified_packet():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/van-owner-release.yml").read_text())
    job = workflow["jobs"]["owner-release"]
    assert job["environment"] == "van-owner-release"
    upload = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/upload-artifact"))
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["path"].endswith("/van-owner-release-packet/")
    cleanup = job["steps"][-1]
    assert cleanup["if"] == "always()" and "rm -f android/keystore.properties" in cleanup["run"]
    preparation = next(s for s in job["steps"] if s.get("name") == "Prepare source-locked generic voice assets")
    restore = next(s for s in job["steps"] if s.get("name") == "Restore bound owner release inputs")
    build = next(s for s in job["steps"] if s.get("name") == "Build owner release from the bound deployment profile")
    assert job["steps"].index(preparation) < job["steps"].index(restore) < job["steps"].index(build)
    commands = preparation["run"].splitlines()
    assert commands == ["python android/tools/package_voice_assets.py --acquire",
                        "python android/tools/package_voice_assets.py --verify"]

