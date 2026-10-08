#!/usr/bin/env python3
"""Prepare declared VAN core routing; never authorize or apply an estate deployment."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes

BACKEND_ADDRESS = "10.77.0.4"
CONTROL_ADDRESS = "10.77.0.1"
INGRESS_ADDRESS = "10.77.0.2"
CAPABILITY = "VAN_OWNER_TLS_PASSTHROUGH_V1"


def required(profile: dict, name: str) -> str:
    value = profile.get(name)
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError(f"missing_or_invalid:{name}")
    return value


def absolute_path(profile: dict, name: str) -> Path:
    value = required(profile, name)
    # These are non-secret path selectors, never shell expansions or private key data.
    if not value.startswith("/") or any(c in value for c in "\n\r\"'\\%$"):
        raise ValueError(f"absolute_literal_path_required:{name}")
    return Path(value).resolve()


def public_url(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if (not value.startswith("https://") or parsed.scheme != "https" or not parsed.hostname or "@" in parsed.netloc
            or parsed.path not in ("", "/") or "?" in value or "#" in value
            or parsed.netloc.endswith(":")):
        raise ValueError("invalid_public_gateway_url")
    port = parsed.port or 443
    if not 1024 <= port <= 65535:
        raise ValueError("dedicated_unprivileged_ingress_port_required")
    hostname = parsed.hostname.lower()
    if (hostname in {"localhost", "62.83.35.103"} or hostname.endswith(
            (".local", ".localhost", ".internal", ".invalid", ".test", ".onion"))):
        raise ValueError("historical_or_local_phone_route_refused")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise ValueError("qualified_public_gateway_hostname_required")
        if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", hostname):
            raise ValueError("invalid_public_gateway_hostname")
        if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
               for label in hostname.split(".")):
            raise ValueError("invalid_public_gateway_hostname")
        if re.fullmatch(r"[0-9.]+", hostname):
            raise ValueError("invalid_public_gateway_address")
    else:
        if not address.is_global:
            raise ValueError("phone_route_must_be_public")
    return value.rstrip("/"), port


def render(profile: dict) -> dict[str, bytes]:
    if type(profile.get("schema_version")) is not int or profile.get("schema_version") != 1:
        raise ValueError("profile_schema_version_required")
    for name, expected in {"backend_host": "van-trading-core", "hermes_host": "dial-control",
                           "ingress_host": "oracle-admin"}.items():
        if profile.get(name) != expected:
            raise ValueError(f"wrong_host_role:{name}")
    profile_id = required(profile, "profile_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", profile_id):
        raise ValueError("invalid_profile_id")
    receipt = required(profile, "ingress_capability_receipt")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", receipt):
        raise ValueError("invalid_ingress_capability_receipt")
    url, port = public_url(required(profile, "public_gateway_url"))
    bind = ipaddress.ip_address(required(profile, "ingress_bind_address"))
    if (bind.version != 4 or bind.is_unspecified or bind.is_loopback or bind.is_multicast
            or bind in ipaddress.ip_network("10.77.0.0/24")):
        raise ValueError("dedicated_observed_ingress_vnic_address_required")
    hermes_value = required(profile, "hermes_api_url")
    hermes = urlsplit(hermes_value)
    # WireGuard encrypts this fixed peer-to-peer lane. It is not the DDS product proxy.
    if (not hermes_value.startswith("http://") or hermes.scheme != "http" or hermes.hostname != CONTROL_ADDRESS or hermes.port is None
            or not 1024 <= hermes.port <= 65535 or hermes.path not in ("", "/")
            or "@" in hermes.netloc or "?" in hermes.geturl() or "#" in hermes.geturl()):
        raise ValueError("explicit_private_hermes_api_port_required")
    ca_file = absolute_path(profile, "gateway_ca_file")
    pem = ca_file.read_bytes()
    if (len(base64.b64encode(pem)) > 65536 or not re.fullmatch(
            rb"\s*-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*", pem)):
        raise ValueError("public_ca_certificate_only")
    certificate = x509.load_pem_x509_certificate(pem)
    if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("gateway_ca_required")
    try:
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound:
        usage = None
    if usage is not None and not usage.key_cert_sign:
        raise ValueError("gateway_ca_certificate_signing_required")
    now = datetime.now(timezone.utc)
    if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
        raise ValueError("gateway_ca_not_current")
    ca_sha = certificate.fingerprint(hashes.SHA256()).hex()
    signing_key = absolute_path(profile, "connectivity_signing_key_file")
    runtime_token = absolute_path(profile, "hermes_runtime_token_file")
    mtls = absolute_path(profile, "mtls_directory")
    database = absolute_path(profile, "database_file")
    if not database.is_relative_to(mtls.parent) or database.is_relative_to(mtls.parent / "runtime"):
        raise ValueError("persistent_owner_database_outside_runtime_required")
    commander_token = absolute_path(profile, "commander_token_file")
    commander_ca = absolute_path(profile, "commander_ca_file")
    commander_value = required(profile, "commander_api_url")
    commander = urlsplit(commander_value)
    if (not commander_value.startswith("https://") or commander.scheme != "https" or commander.hostname not in {"10.0.1.233", BACKEND_ADDRESS}
            or commander.port != 9133 or commander.path not in ("", "/") or "@" in commander.netloc
            or "?" in commander.geturl() or "#" in commander.geturl()):
        raise ValueError("explicit_private_typed_commander_endpoint_required")
    kid = required(profile, "connectivity_signing_kid")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", kid):
        raise ValueError("invalid_connectivity_signing_kid")
    properties = {
        "VAN_DEPLOYMENT_PROFILE_VERSION": "1", "VAN_DEPLOYMENT_PROFILE_ID": profile_id,
        "VAN_BACKEND_HOST": "van-trading-core", "VAN_HERMES_HOST": "dial-control",
        "VAN_GATEWAY_INGRESS_HOST": "oracle-admin",
        "VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT": receipt,
        "VAN_GATEWAY_BASE_URL": url, "VAN_GATEWAY_CA_SHA256": ca_sha,
        "VAN_GATEWAY_CA_PEM_B64": base64.b64encode(pem).decode("ascii"),
    }
    gateway_env = {
        "VAN_ENV": "production", "VAN_REQUIRE_DEVICE_BINDING": "true",
        "VAN_ALLOW_LOOPBACK_IN_PRODUCTION": "false", "VAN_PUBLIC_BASE_URL": url,
        "VAN_HERMES_BASE_URL": hermes.geturl().rstrip("/"), "VAN_HERMES_PROFILE": "van",
        "VAN_LOOPBACK_HOST": "127.0.0.1", "VAN_LOOPBACK_PORT": "8787",
        "VAN_MTLS_ENABLED": "true", "VAN_MTLS_BIND": BACKEND_ADDRESS, "VAN_MTLS_PORT": "8443",
        "VAN_MTLS_DIR": str(mtls), "VAN_CONNECTIVITY_SIGNING_KEY_FILE": str(signing_key),
        "VAN_CONNECTIVITY_SIGNING_KID": kid,
        "VAN_DATABASE_PATH": str(database), "VAN_COMMANDER_URL": commander.geturl().rstrip("/"),
        "VAN_COMMANDER_TOKEN_FILE": str(commander_token), "VAN_COMMANDER_CA_FILE": str(commander_ca),
    }
    # Optional operator-managed bindings are selectors only. Their absence keeps
    # the backend's unavailable defaults; never copy provider/CA contents here.
    for name, variable in {
        "browser_artifact_providers_file": "VAN_BROWSER_ARTIFACT_PROVIDERS_FILE",
        "mtls_machine_client_ca_file": "VAN_MTLS_MACHINE_CLIENT_CA_FILE",
    }.items():
        if profile.get(name) not in (None, ""):
            gateway_env[variable] = str(absolute_path(profile, name))
    # No HTTP TLS termination, PROXY protocol, forwarded certificate header or route rewriting.
    ingress = f"""# VAN-only capability {CAPABILITY}; deployment authority pending independent verification.
global
    maxconn 128
defaults
    mode tcp
    timeout connect 5s
    timeout client 75s
    timeout server 75s
frontend van_owner_phone
    bind {bind}:{port}
    default_backend van_owner_private_core
backend van_owner_private_core
    server van_core {BACKEND_ADDRESS}:8443 source {INGRESS_ADDRESS} check
"""
    relay = f"""# Private scoped-token lane, dial-control only; WireGuard wg-dial firewall required.
global
    maxconn 64
defaults
    mode tcp
    timeout connect 5s
    timeout client 75s
    timeout server 75s
frontend van_hermes_internal
    bind {BACKEND_ADDRESS}:8787
    acl dial_control src {CONTROL_ADDRESS}/32
    tcp-request connection reject if !dial_control
    default_backend van_gateway_loopback
backend van_gateway_loopback
    server gateway 127.0.0.1:8787 check
"""
    dropin = """[Service]
MemoryAccounting=true
MemoryHigh=768M
MemoryMax=1024M
CPUAccounting=true
CPUQuota=100%
CPUWeight=20
IOWeight=20
TasksMax=128
"""
    result = {
        "android-owner-core.properties": "".join(f"{k}={v}\n" for k, v in properties.items()).encode(),
        "owner-core.env": "".join(f'{k}="{v}"\n' for k, v in gateway_env.items()).encode(),
        "oracle-admin-van-ingress.cfg": ingress.encode(), "core-hermes-relay.cfg": relay.encode(),
        "van-gateway-resource-limits.conf": dropin.encode(),
        "hermes-runtime.env": (f'VAN_OWNER_RUNTIME_HOST="van-trading-core"\n'
                               f'VAN_OWNER_RUNTIME_URL="http://{BACKEND_ADDRESS}:8787"\n'
                               f'VAN_OWNER_RUNTIME_TOKEN_FILE="{runtime_token}"\n').encode(),
    }
    declaration = {
        "schema_version": 1, "status": "PREPARED_NOT_DEPLOYED", "profile_id": profile_id,
        "deployed": False, "live_qualified": False, "ingress_authority_verified": False,
        "ingress_capability": CAPABILITY, "ingress_capability_receipt": receipt,
        "gateway_ca_sha256": ca_sha,
        "artifact_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in result.items()},
        "required_network_lanes": [
            {"source": "owner_phone", "target_host": "oracle-admin", "target_address": str(bind), "port": port, "protocol": "TLS_PASSTHROUGH"},
            {"source": INGRESS_ADDRESS, "target_host": "van-trading-core", "target_address": BACKEND_ADDRESS, "port": 8443, "protocol": "TCP_OVER_WIREGUARD"},
            {"source": CONTROL_ADDRESS, "target_host": "van-trading-core", "target_address": BACKEND_ADDRESS, "port": 8787, "protocol": "SCOPED_TOKEN_HTTP_OVER_WIREGUARD"},
            {"source": BACKEND_ADDRESS, "target_host": "dial-control", "target_address": CONTROL_ADDRESS, "port": hermes.port, "protocol": "HERMES_PROFILE_HTTP_OVER_WIREGUARD"},
        ],
        "pending_checks": ["governed_ingress_recipe_and_exact_receipt_scope", "fresh_host_identity_and_wireguard_handshakes",
                           "port_scoped_hub_forwarding_without_nat", "private_listeners_and_firewall",
                           "matching_server_SAN_and_device_CA", "pinned_proxy_binary", "immutable_clean_source_SHA",
                           "separate_scoped_credentials_and_google_attestation_roots", "trading_resource_headroom",
                           "host_readiness_and_phone_e2e_receipts"],
    }
    result["declaration.json"] = (json.dumps(declaration, indent=2) + "\n").encode()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        artifacts = render(json.loads(args.profile.read_text()))
        # Validate everything before creating output. Never overwrite artifacts on a failed profile.
        args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, content in artifacts.items():
            descriptor, temporary = tempfile.mkstemp(prefix=".van-profile-", dir=args.output)
            try:
                with os.fdopen(descriptor, "wb") as file:
                    os.fchmod(file.fileno(), 0o600)
                    file.write(content)
                os.replace(temporary, args.output / name)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    except (OSError, ValueError, x509.ExtensionNotFound):
        # Do not echo input or exception strings: malformed input can contain credentials.
        print(json.dumps({"status": "BLOCKED", "reason": "invalid_or_unbound_deployment_profile", "deployed": False}))
        return 2
    print(json.dumps({"status": "PREPARED_NOT_DEPLOYED", "artifacts": sorted(artifacts), "deployed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
