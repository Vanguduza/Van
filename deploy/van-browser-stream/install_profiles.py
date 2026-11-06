#!/usr/bin/env python3
"""Install already-prepared isolated browser profiles; no service is started or enabled."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile

from prepare_profiles import render, PROFILE_ROOT, TRANSFER_ROOT, ETC


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60).stdout.strip()


def private_file(path):
    selected = Path(path)
    mode = selected.lstat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("protected_credential_file_required")
    return selected


def check_credentials(declaration):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID
    cert_hashes, key_hashes = set(), set()
    ingress = declaration.get("ingress_copy_selectors", {})
    if ingress:
        certificate = x509.load_pem_x509_certificate(Path(ingress["media.crt"]).read_bytes())
        private = serialization.load_pem_private_key(private_file(ingress["media.key"]).read_bytes(), password=None)
        if certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
            raise ValueError("matching_media_ingress_tls_identity_required")
    for instance in declaration["instances"]:
        copies = instance["copy_selectors"]
        for role in ("control", "stream"):
            value = private_file(copies[role + "-pki/producer.token"]).read_bytes().strip()
            if (not 32 <= len(value) <= 8192 or any(c < 33 or c > 126 for c in value)
                    or hashlib.sha256(value).hexdigest() != instance["expected_token_sha256"][role]):
                raise ValueError("producer_credential_fingerprint_mismatch")
            cert = x509.load_pem_x509_certificate(Path(copies[role + "-pki/broker-client.crt"]).read_bytes())
            key = serialization.load_pem_private_key(private_file(copies[role + "-pki/broker-client.key"]).read_bytes(), password=None)
            actual = cert.fingerprint(hashes.SHA256()).hex()
            public = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            public_hash = hashlib.sha256(public).hexdigest()
            try:
                client_eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            except x509.ExtensionNotFound as exc:
                raise ValueError("role_broker_client_auth_certificate_required") from exc
            if (actual in cert_hashes or public_hash in key_hashes
                    or not cert.not_valid_before_utc <= datetime.now(timezone.utc) < cert.not_valid_after_utc
                    or ExtendedKeyUsageOID.CLIENT_AUTH not in client_eku
                    or public
                    != key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)):
                raise ValueError("distinct_matching_role_broker_tls_identity_required")
            cert_hashes.add(actual)
            key_hashes.add(public_hash)
        for name, path in copies.items():
            if name.endswith(".key"):
                private_file(path)
            elif not Path(path).is_file() or Path(path).is_symlink():
                raise ValueError("literal_provisioned_public_material_required")


def directory(path, owner="root", group="root", mode=0o700):
    Path(path).mkdir(parents=True, exist_ok=True)
    run(["chown", owner + ":" + group, str(path)])
    Path(path).chmod(mode)


def write_file(path, content, owner="root", group="root", mode=0o600):
    target = Path(path)
    fd, name = tempfile.mkstemp(dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), mode)
        run(["chown", owner + ":" + group, name])
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def firewall(declaration):
    # Create then flush only our dedicated table, making boot/restart application
    # idempotent without touching the host's existing firewall rules.
    rules = ["table inet van_browser_cdp {}", "flush table inet van_browser_cdp",
             "table inet van_browser_cdp {", "  chain output {", "    type filter hook output priority -50; policy accept;"]
    identities = {}
    for instance in declaration["instances"]:
        for user in instance["users"] + [instance["egress_user"]]:
            uid = pwd.getpwnam(user).pw_uid
            if uid <= 0 or uid in identities.values():
                raise ValueError("distinct_nonroot_browser_service_uids_required")
            identities[user] = uid
    for instance in declaration["instances"]:
        uids = [0] + [identities[user] for user in instance["users"]]
        rules.append("    ip daddr 127.0.0.1 tcp dport " + str(instance["cdp_port"]) +
                     " meta skuid { " + ", ".join(map(str, uids)) + " } accept")
        rules.append("    ip daddr 127.0.0.1 tcp dport " + str(instance["cdp_port"]) + " reject with tcp reset")
    for instance in declaration["instances"]:
        browser_uid = str(identities[instance["users"][0]])
        # Chromium may use only its own exact-IP proxy or answer admitted CDP
        # clients. All other IPv4/IPv6/UDP output from this identity is refused.
        rules.append("    meta skuid " + browser_uid + " ip daddr 127.0.0.1 tcp dport " + str(instance["egress_port"]) + " accept")
        rules.append("    meta skuid " + browser_uid + " ip saddr 127.0.0.1 ip daddr 127.0.0.1 tcp sport " + str(instance["cdp_port"]) + " ct state established ct direction reply accept")
        rules.append("    meta skuid " + browser_uid + " reject")
    rules.extend(["  }", "}"])
    return ("\n".join(rules) + "\n").encode()


def install(data, artifacts):
    if os.geteuid() != 0:
        raise ValueError("admitted_root_recipe_required")
    declaration = json.loads(artifacts["declaration.json"])
    # All credentials and exact binary are checked before users/permissions/config
    # change. Values are never returned in diagnostics or passed as command args.
    if hashlib.sha256(Path(declaration["chromium_executable"]).read_bytes()).hexdigest() != declaration["chromium_sha256"]:
        raise ValueError("observed_chromium_binary_hash_mismatch")
    if hashlib.sha256(Path(declaration["nginx_executable"]).read_bytes()).hexdigest() != declaration["nginx_sha256"]:
        raise ValueError("observed_nginx_binary_hash_mismatch")
    check_credentials(declaration)
    for instance in ("public", "owner"):
        for service in ("chromium", "control-agent", "stream", "transfer-stage", "egress-proxy"):
            active = subprocess.run(["systemctl", "is-active", "--quiet", "van-browser-" + service + "@" + instance + ".service"],
                                    capture_output=True, timeout=10).returncode == 0
            if active:
                raise ValueError("browser_services_must_be_quiesced_before_install")
    for service in ("chromium", "control-agent", "stream", "transfer-stage", "egress-proxy"):
        if subprocess.run(["systemctl", "is-active", "--quiet", "van-browser-" + service + ".service"],
                          capture_output=True, timeout=10).returncode == 0:
            raise ValueError("legacy_shared_browser_stack_must_be_quiesced")
    for service in ("media-ingress", "ingress-stage"):
        if subprocess.run(["systemctl", "is-active", "--quiet", "van-browser-" + service + ".service"], capture_output=True, timeout=10).returncode == 0:
            raise ValueError("media_ingress_must_be_quiesced")
    for binary in ("nft", "cryptsetup", "findmnt", "rsync", "useradd", "usermod", "groupadd", "systemctl"):
        if not shutil.which(binary):
            raise ValueError("required_host_installer_tool_missing")
    source = run(["findmnt", "-n", "-o", "SOURCE", "--target", PROFILE_ROOT])
    if source != "/dev/mapper/van-browser-profiles":
        raise ValueError("preexisting_encrypted_profile_mount_required")
    status = run(["cryptsetup", "status", "van-browser-profiles"])
    selected = str(Path(declaration["encrypted_profile_device"]).resolve())
    observed = {key.strip(): value.strip() for line in status.splitlines() for key, separator, value in [line.partition(":")] if separator}
    if not observed.get("type", "").startswith("LUKS") or str(Path(observed.get("device", "")).resolve()) != selected:
        raise ValueError("existing_encrypted_volume_identity_mismatch")
    # Stop at existing identity conflicts rather than silently changing privileged
    # memberships or introducing a second identity for an established service.
    existing_uids = set()
    for instance in declaration["instances"]:
        for user in instance["users"] + [instance["egress_user"]]:
            try:
                existing = pwd.getpwnam(user)
            except KeyError:
                continue
            allowed = {user}
            if user.startswith(("van-browser-", "van-stream-")):
                allowed.add(instance["transfer_group"])
            if existing.pw_uid == 0 or existing.pw_uid in existing_uids or set(run(["id", "-Gn", user]).split()) - allowed:
                raise ValueError("existing_service_identity_conflict")
            existing_uids.add(existing.pw_uid)
    directory(ETC, mode=0o711)
    directory(PROFILE_ROOT, mode=0o711)
    directory(PROFILE_ROOT + "/.transfers", mode=0o711)
    directory(TRANSFER_ROOT, mode=0o711)
    try:
        ingress_user = pwd.getpwnam("van-browser-ingress")
    except KeyError:
        run(["useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin", "van-browser-ingress"])
    else:
        if ingress_user.pw_uid == 0 or set(run(["id", "-Gn", "van-browser-ingress"]).split()) != {"van-browser-ingress"}:
            raise ValueError("media_ingress_identity_conflict")
    directory(PROFILE_ROOT + "/.ingress", "van-browser-ingress", "van-browser-ingress")
    directory(TRANSFER_ROOT + "/.ingress", "van-browser-ingress", "van-browser-ingress")
    for parent in (PROFILE_ROOT + "/.ingress", TRANSFER_ROOT + "/.ingress"):
        for sub in ("client", "proxy", "fastcgi", "uwsgi", "scgi"):
            directory(parent + "/" + sub, "van-browser-ingress", "van-browser-ingress")
    directory(Path(ETC).parent / "ingress", "van-browser-ingress", "van-browser-ingress")
    directory("/run/van-browser-ingress", "van-browser-ingress", "van-browser-ingress")
    for destination, selector in declaration["ingress_copy_selectors"].items():
        write_file(Path(ETC).parent / "ingress" / destination, Path(selector).read_bytes(), "van-browser-ingress", "van-browser-ingress", 0o600 if destination.endswith(".key") else 0o644)
    write_file(Path(ETC).parent / "media-ingress.conf", artifacts["media-ingress.conf"], "van-browser-ingress", "van-browser-ingress")
    run([declaration["nginx_executable"], "-t", "-c", str(Path(ETC).parent / "media-ingress.conf")])
    for instance in declaration["instances"]:
        name, users, group = instance["instance"], instance["users"], instance["transfer_group"]
        for user in users + [instance["egress_user"]]:
            try:
                pwd.getpwnam(user)
            except KeyError:
                run(["useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin", user])
        if subprocess.run(["getent", "group", group], capture_output=True).returncode:
            run(["groupadd", "--system", group])
        for user in (users[0], users[2]):
            run(["usermod", "-a", "-G", group, user])
        directory(PROFILE_ROOT + "/" + name, users[0], users[0])
        directory(PROFILE_ROOT + "/" + name + "/" + instance["profile_alias"], users[0], users[0])
        directory(PROFILE_ROOT + "/.transfers/" + name, users[2], group, 0o1770)
        directory(TRANSFER_ROOT + "/" + name, users[2], group, 0o1770)
        location = ETC + "/" + name
        directory(location, mode=0o711)
        for role, user in (("control", users[1]), ("stream", users[2])):
            directory(location + "/" + role + "-pki", user, user)
            directory("/var/log/van-browser-stream/" + name + "/" + role, user, user)
        for destination, selector in instance["copy_selectors"].items():
            owner = users[1] if destination.startswith("control-pki/") else users[2] if destination.startswith("stream-pki/") else "root"
            mode = 0o600 if destination.endswith((".key", ".token")) else 0o644
            write_file(location + "/" + destination, Path(selector).read_bytes(), owner, owner, mode)
        for role in ("chromium", "control", "stream", "egress"):
            write_file(location + "/" + role + ".env", artifacts[name + "/" + role + ".env"])
    # A dedicated UID-scoped CDP table prevents a compromised public stack from
    # connecting to owner Chromium's loopback debugger. Never flush other tables.
    nft_path = Path(ETC).parent / "cdp-isolation.nft"
    nft_data = firewall(declaration)
    found = subprocess.run(["nft", "list", "table", "inet", "van_browser_cdp"], capture_output=True).returncode == 0
    if found and not nft_path.is_file():
        raise ValueError("unowned_existing_cdp_firewall_table_refused")
    with tempfile.NamedTemporaryFile() as stream:
        stream.write(nft_data)
        stream.flush()
        run(["nft", "-c", "-f", stream.name])
        run(["nft", "-f", stream.name])
    write_file(nft_path, nft_data)
    # Install runtime source and profile units only after successful preflight.
    repository = Path(__file__).resolve().parents[2]
    directory("/opt/van-browser-stream/src", mode=0o755)
    run(["rsync", "-a", "--delete", "--exclude=__pycache__", str(repository / "services"), "/opt/van-browser-stream/src/"])
    run(["rsync", "-a", "--delete", "--exclude=__pycache__", str(repository / "backend/van_gateway"), "/opt/van-browser-stream/src/"])
    for name, content in artifacts.items():
        if name.startswith("systemd/"):
            write_file("/etc/systemd/system/" + name.partition("/")[2], content, mode=0o644)
    tmpfiles = "".join("e " + TRANSFER_ROOT + "/" + i + " 1770 van-stream-" + i + " van-transfer-" + i + " 1d -\n" for i in ("public", "owner"))
    write_file("/etc/tmpfiles.d/van-browser-profiles.conf", tmpfiles.encode(), mode=0o644)
    write_file(Path(ETC).parent / "gateway-browser-profile-bindings.env", artifacts["gateway-browser-profile-bindings.env"])
    write_file(Path(ETC).parent / "profiles-declaration.json", artifacts["declaration.json"])
    for service in ("chromium", "control-agent", "stream", "transfer-stage", "egress-proxy"):
        unit = "van-browser-" + service + ".service"
        if Path("/etc/systemd/system", unit).exists():
            run(["systemctl", "disable", unit])
    run(["systemctl", "daemon-reload"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    mutation_started = False
    try:
        data = json.loads(args.profile.read_text())
        artifacts = render(data)
        if not args.dry_run:
            mutation_started = True
            install(data, artifacts)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print(json.dumps({"status": "INSTALL_FAILED_RECONCILE" if mutation_started else "BLOCKED", "mutation_started": mutation_started,
                          "services_started": False, "live_qualified": False}))
        return 2
    print(json.dumps({"status": "PREPARED_NOT_INSTALLED" if args.dry_run else "INSTALLED_SERVICES_STOPPED", "mutation_started": mutation_started,
                      "services_started": False, "live_qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
