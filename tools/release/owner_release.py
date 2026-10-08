#!/usr/bin/env python3
"""Build and inspect an owner-core APK packet; never claim deployment or phone acceptance."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import re
import struct
import subprocess
import sys
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/runtime"))
from prepare_owner_core_deployment import public_url


class ReleaseRefused(ValueError):
    pass


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fingerprint(value: str) -> str:
    normalized = value.replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ReleaseRefused("owner_release_signer_unbound")
    return normalized


def profile_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "!")):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in values or not re.fullmatch(r"VAN_[A-Z0-9_]+", key):
            raise ReleaseRefused("invalid_deployment_properties")
        values[key] = value
    required = {"VAN_DEPLOYMENT_PROFILE_VERSION": "2", "VAN_DEPLOYMENT_TOPOLOGY": "CORE_ONLY_V2",
                "VAN_BACKEND_HOST": "van-trading-core", "VAN_HERMES_HOST": "van-trading-core",
                "VAN_GATEWAY_INGRESS_HOST": "van-trading-core"}
    if any(values.get(k) != v for k, v in required.items()):
        raise ReleaseRefused("owner_core_host_roles_unbound")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", values.get("VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT", ""))
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", values.get("VAN_DEPLOYMENT_PROFILE_ID", ""))):
        raise ReleaseRefused("owner_core_profile_or_ingress_receipt_unbound")
    try:
        normalized, _ = public_url(values["VAN_GATEWAY_BASE_URL"])
        pem = base64.b64decode(values["VAN_GATEWAY_CA_PEM_B64"], validate=True)
        cert = x509.load_pem_x509_certificate(pem)
        if (len(values["VAN_GATEWAY_CA_PEM_B64"]) > 65536 or not re.fullmatch(
                rb"\s*-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*", pem)):
            raise ValueError("extraneous_ca_data")
        if not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("not_ca")
        if not cert.not_valid_before_utc <= datetime.now(timezone.utc) < cert.not_valid_after_utc:
            raise ValueError("not_current")
        try:
            if not cert.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
                raise ValueError("ca_cannot_sign")
        except x509.ExtensionNotFound:
            pass
        if cert.fingerprint(hashes.SHA256()).hex() != values["VAN_GATEWAY_CA_SHA256"].lower():
            raise ValueError("wrong_ca")
    except (KeyError, ValueError, x509.ExtensionNotFound) as exc:
        raise ReleaseRefused("invalid_owner_core_gateway_trust") from exc
    if normalized != values["VAN_GATEWAY_BASE_URL"]:
        raise ReleaseRefused("canonical_gateway_root_required")
    return values


def trusted_keys(raw: str) -> dict[str, ec.EllipticCurvePublicKey]:
    result = {}
    for line in raw.strip().splitlines():
        kid, separator, pem = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", kid) or kid in result:
            raise ReleaseRefused("invalid_manifest_verification_anchors")
        try:
            key = serialization.load_pem_public_key(pem.replace("\\n", "\n").encode())
        except ValueError as exc:
            raise ReleaseRefused("invalid_manifest_verification_anchors") from exc
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ReleaseRefused("p256_manifest_verification_anchor_required")
        result[kid] = key
    if not result:
        raise ReleaseRefused("manifest_verification_anchors_unbound")
    return result


def require_native_page_alignment(data: bytes) -> None:
    """Reject arm64 binaries whose load segments cannot use Android's 16 KiB pages."""
    if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise ReleaseRefused("owner_release_native_arm64_elf_required")
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    if size < 56 or not 1 <= count <= 128 or offset < 64 or offset + size * count > len(data):
        raise ReleaseRefused("owner_release_native_elf_program_headers_invalid")
    loads = 0
    for index in range(count):
        header = offset + index * size
        if struct.unpack_from("<I", data, header)[0] != 1:
            continue
        loads += 1
        file_offset, virtual_address = struct.unpack_from("<QQ", data, header + 8)
        file_size, memory_size, alignment = struct.unpack_from("<QQQ", data, header + 32)
        if (alignment < 16384 or alignment & (alignment - 1)
                or file_offset % alignment != virtual_address % alignment
                or file_size > memory_size or file_offset + file_size > len(data)):
            raise ReleaseRefused("owner_release_native_16kb_alignment_required")
    if not loads:
        raise ReleaseRefused("owner_release_native_load_segment_required")


def apk_identity(apk: Path, apksigner: str, aapt: str) -> dict:
    # apksigner verifies the entire APK signature before its identity is accepted.
    try:
        signed = subprocess.run([apksigner, "verify", "--print-certs", str(apk)],
                                capture_output=True, text=True, timeout=60, check=True)
        package = subprocess.run([aapt, "dump", "badging", str(apk)],
                                 capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReleaseRefused("apk_signature_or_manifest_verification_failed") from exc
    signers = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F:]+)$", signed.stdout, re.M)
    if len(signers) != 1 or re.search(r"certificate DN:.*(?:CN=Android Debug|CN=AndroidDebug)", signed.stdout, re.I):
        raise ReleaseRefused("one_owner_apk_signer_required")
    info = re.search(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']*)'", package.stdout, re.M)
    if not info or info[1] != "com.dial.van" or "application-debuggable" in package.stdout:
        raise ReleaseRefused("owner_release_package_required")
    with zipfile.ZipFile(apk) as archive:
        abis = {entry.split("/")[1] for entry in archive.namelist() if entry.startswith("lib/") and entry.endswith(".so")}
        if abis != {"arm64-v8a"}:
            raise ReleaseRefused("owner_release_arm64_only_required")
        for entry in archive.infolist():
            if not entry.filename.startswith("lib/arm64-v8a/") or not entry.filename.endswith(".so"):
                continue
            require_native_page_alignment(archive.read(entry))
            if entry.compress_type == zipfile.ZIP_STORED:
                archive.fp.seek(entry.header_offset)
                local = archive.fp.read(30)
                if len(local) != 30 or local[:4] != b"PK\x03\x04":
                    raise ReleaseRefused("owner_release_native_zip_header_invalid")
                name_size, extra_size = struct.unpack_from("<HH", local, 26)
                if (entry.header_offset + 30 + name_size + extra_size) % 16384:
                    raise ReleaseRefused("owner_release_native_16kb_zip_alignment_required")
    return {"package": info[1], "version_code": int(info[2]), "version_name": info[3],
            "signer_sha256": fingerprint(signers[0]), "abi": "arm64-v8a", "debuggable": False,
            "native_page_alignment_bytes": 16384}


def source_check(repository: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ReleaseRefused("immutable_expected_source_required")
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=all"], text=True)
    if head != expected or dirty:
        raise ReleaseRefused("exact_clean_release_source_required")


def create_packet(apk: Path, profile: Path, anchors: Path, *, build_config: Path, expected_sha: str,
                  expected_signer: str, apksigner: str, aapt: str, repository: Path = ROOT) -> dict:
    source_check(repository, expected_sha)
    values = profile_values(profile)
    trusted_keys(anchors.read_text())
    generated = build_config.read_text()
    for name, expected in {"APPLICATION_ID": "com.dial.van", "VAN_GATEWAY_BASE_URL": values["VAN_GATEWAY_BASE_URL"],
                           "VAN_GATEWAY_CA_PEM_B64": values["VAN_GATEWAY_CA_PEM_B64"],
                           "VAN_CONNECTIVITY_TRUSTED_KEYS": anchors.read_text().strip()}.items():
        match = re.search(r"public static final String " + name + r' = ("(?:\\.|[^"\\])*");', generated)
        if not match or json.loads(match[1]) != expected:
            raise ReleaseRefused("compiled_release_inputs_mismatch")
    identity = apk_identity(apk, apksigner, aapt)
    if identity["signer_sha256"] != fingerprint(expected_signer):
        raise ReleaseRefused("apk_owner_signer_mismatch")
    return {"schema_version": 1, "status": "OWNER_RELEASE_ARTIFACT_VERIFIED", "repository_sha": expected_sha,
            "source_clean": True, "apk": {"sha256": digest(apk), "bytes": apk.stat().st_size, **identity},
            "profile": {"sha256": digest(profile), "profile_id": values["VAN_DEPLOYMENT_PROFILE_ID"],
                        "gateway_url": values["VAN_GATEWAY_BASE_URL"], "gateway_ca_sha256": values["VAN_GATEWAY_CA_SHA256"],
                        "backend_host": "van-trading-core", "hermes_host": "van-trading-core", "ingress_host": "van-trading-core",
                        "ingress_capability_receipt": values["VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT"]},
            "trusted_keys_sha256": digest(anchors), "deployed": False, "provisioned": False,
            "compiled_build_config_sha256": digest(build_config), "producer_authenticity_verified": False,
            "live_qualified": False, "owner_e2e_verified": False}


def verify_packet(packet: dict, apk: Path, profile: Path, anchors: Path, *, expected_sha: str,
                  expected_signer: str, device_gateway_url: str, apksigner: str, aapt: str) -> dict:
    if not isinstance(packet, dict) or not isinstance(packet.get("profile"), dict) or not isinstance(packet.get("apk"), dict):
        raise ReleaseRefused("invalid_owner_release_packet")
    values = profile_values(profile)
    trusted_keys(anchors.read_text())
    identity = apk_identity(apk, apksigner, aapt)
    expected_profile = {"sha256": digest(profile), "profile_id": values["VAN_DEPLOYMENT_PROFILE_ID"],
                        "gateway_url": values["VAN_GATEWAY_BASE_URL"], "gateway_ca_sha256": values["VAN_GATEWAY_CA_SHA256"],
                        "backend_host": "van-trading-core", "hermes_host": "van-trading-core", "ingress_host": "van-trading-core",
                        "ingress_capability_receipt": values["VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT"]}
    if (type(packet.get("schema_version")) is not int or packet.get("schema_version") != 1 or packet.get("source_clean") is not True
            or packet.get("status") != "OWNER_RELEASE_ARTIFACT_VERIFIED"
            or not re.fullmatch(r"[0-9a-f]{40}", expected_sha) or packet.get("repository_sha") != expected_sha
            or packet.get("apk") != {"sha256": digest(apk), "bytes": apk.stat().st_size, **identity}
            or identity["signer_sha256"] != fingerprint(expected_signer)
            or packet.get("trusted_keys_sha256") != digest(anchors)
            or packet["profile"] != expected_profile
            or any(packet.get(k) is not False for k in ("deployed", "provisioned", "live_qualified", "owner_e2e_verified", "producer_authenticity_verified"))
            or device_gateway_url.rstrip("/") != values["VAN_GATEWAY_BASE_URL"]):
        raise ReleaseRefused("owner_release_packet_or_independent_binding_mismatch")
    return values


def properties_escape(value: str) -> str:
    encoded = value.encode("utf-16-be")
    return "".join("\\" + chr(unit) if chr(unit) in "\\:=#! " else f"\\u{unit:04x}"
                   if unit < 32 or unit > 126 else chr(unit)
                   for unit in (int.from_bytes(encoded[n:n + 2], "big") for n in range(0, len(encoded), 2)))


def restore_ci_inputs() -> None:
    # Bound environment settings only; never secrets in argv/output. GitHub masks
    # the original values, but files are private and cleanup remains mandatory.
    task_dir = Path(os.environ["VAN_OWNER_RELEASE_INPUT_DIR"]).resolve()
    if task_dir.exists() or task_dir.is_relative_to(ROOT):
        raise ReleaseRefused("fresh_release_input_directory_required")
    required = ["VAN_OWNER_KEYSTORE_BASE64", "VAN_OWNER_KEYSTORE_PASSWORD", "VAN_OWNER_KEY_ALIAS",
                "VAN_OWNER_KEY_PASSWORD", "VAN_OWNER_SIGNER_SHA256", "VAN_OWNER_CORE_PROFILE_BASE64",
                "VAN_CONNECTIVITY_TRUSTED_KEYS"]
    if any(not os.environ.get(k) for k in required):
        raise ReleaseRefused("owner_release_environment_bindings_missing")
    fingerprint(os.environ["VAN_OWNER_SIGNER_SHA256"])
    trusted_keys(os.environ["VAN_CONNECTIVITY_TRUSTED_KEYS"])
    if os.environ["VAN_OWNER_KEY_ALIAS"] == "androiddebugkey":
        raise ReleaseRefused("production_key_alias_required")
    keystore = base64.b64decode(os.environ["VAN_OWNER_KEYSTORE_BASE64"], validate=True)
    profile = base64.b64decode(os.environ["VAN_OWNER_CORE_PROFILE_BASE64"], validate=True)
    if not keystore or len(keystore) > 1024 * 1024 or len(profile) > 128 * 1024:
        raise ReleaseRefused("invalid_bound_release_inputs")
    task_dir.mkdir(mode=0o700, parents=True)
    try:
        for name, content in {"owner-release.jks": keystore, "android-owner-core.properties": profile,
                              "connectivity-trusted-keys.txt": os.environ["VAN_CONNECTIVITY_TRUSTED_KEYS"].encode()}.items():
            path = task_dir / name
            path.write_bytes(content)
            path.chmod(0o600)
        profile_values(task_dir / "android-owner-core.properties")
        properties = {"storeFile": str(task_dir / "owner-release.jks"),
                      "storePassword": os.environ["VAN_OWNER_KEYSTORE_PASSWORD"],
                      "keyAlias": os.environ["VAN_OWNER_KEY_ALIAS"], "keyPassword": os.environ["VAN_OWNER_KEY_PASSWORD"]}
        target = ROOT / "android/keystore.properties"
        if target.exists():
            raise ReleaseRefused("existing_keystore_configuration_refused")
        target.write_text("".join(k + "=" + properties_escape(v) + "\n" for k, v in properties.items()))
        target.chmod(0o600)
    except BaseException:
        import shutil
        shutil.rmtree(task_dir)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("restore-ci-inputs")
    packet = sub.add_parser("packet")
    packet.add_argument("--apk", type=Path, required=True)
    packet.add_argument("--profile", type=Path, required=True)
    packet.add_argument("--trusted-keys", type=Path, required=True)
    packet.add_argument("--build-config", type=Path, required=True)
    packet.add_argument("--expected-sha", required=True)
    packet.add_argument("--expected-signer", required=True)
    packet.add_argument("--apksigner", required=True)
    packet.add_argument("--aapt", required=True)
    packet.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "restore-ci-inputs":
            restore_ci_inputs()
        else:
            result = create_packet(args.apk, args.profile, args.trusted_keys, build_config=args.build_config, expected_sha=args.expected_sha,
                                   expected_signer=args.expected_signer, apksigner=args.apksigner, aapt=args.aapt)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile):
        print(json.dumps({"status": "BLOCKED", "reason": "owner_release_inputs_or_artifacts_refused", "live_qualified": False}))
        return 2
    print(json.dumps({"status": "RELEASE_INPUTS_READY" if args.command == "restore-ci-inputs" else "OWNER_RELEASE_ARTIFACT_VERIFIED",
                      "live_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
