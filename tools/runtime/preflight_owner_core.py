#!/usr/bin/env python3
"""Fail closed on local core deployment inputs; this is not an estate approval receipt."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import ipaddress
from urllib.parse import urlsplit


def read_environment(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and re.fullmatch(r"VAN_[A-Z0-9_]+", key):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    return values


def effective_environment(google: Path, gateway: Path, trading: Path | None = None,
                          profile: Path | None = None) -> dict[str, str]:
    """Exact unit order, with no invoking-shell fallback; selected profile wins last."""
    values = {**read_environment(google), **read_environment(gateway)}
    for optional in (trading, profile):
        if optional is not None and optional.is_file():
            values.update(read_environment(optional))
    return values


def commander_credential_separate(values: dict[str, str], token: str) -> bool:
    others = {values.get(name, "") for name in ("VAN_DEVICE_ENROLMENT_TOKEN", "VAN_INTERNAL_CONTROL_TOKEN",
              "VAN_HERMES_BEARER_TOKEN", "VAN_INGRESS_TOKEN")}
    others.update(entry.strip().partition(":")[2].strip()
                  for entry in values.get("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", "").split(";"))
    return bool(token) and token not in others


def browser_credential_checks(values: dict[str, str]) -> dict[str, bool]:
    """Only the native control credential may attest the configured core TLS CN.

    Fingerprints are public deployment identifiers. Actual token bytes stay in
    the core's protected scoped-credential environment and each producer's own file.
    """
    try:
        profiles = json.loads(values.get("VAN_BROWSER_CONTROL_PROFILE_CLIENTS", "{}"))
    except (ValueError, TypeError):
        return {"browser_profile_client_map_valid": False}
    if not isinstance(profiles, dict):
        return {"browser_profile_client_map_valid": False}
    if not values.get("VAN_BROWSER_CONTROL_CLIENT_ADDRESS") and not profiles:
        return {}
    cn = values.get("VAN_BROWSER_CONTROL_CLIENT_COMMON_NAME", "van-trading-core")
    if profiles:
        if any(alias not in {"public_research", "authenticated_owner"} or not isinstance(binding, dict)
               or binding.get("caller_common_name") != cn for alias, binding in profiles.items()):
            return {"browser_profile_client_map_valid": False}
        pairs = [(binding.get("proxy_principal_sha256", ""), binding.get("stream_principal_sha256", ""))
                 for binding in profiles.values()]
    else:
        pairs = [(values.get("VAN_BROWSER_CONTROL_BROKER_TOKEN_SHA256", ""),
                  values.get("VAN_BROWSER_STREAM_BROKER_TOKEN_SHA256", ""))]
    fingerprints = [value for pair in pairs for value in pair]
    distinct = all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in fingerprints)
    distinct = distinct and len(set(fingerprints)) == len(fingerprints)
    controls = {pair[0] for pair in pairs if isinstance(pair[0], str)}
    token_scopes: dict[str, set[str]] = {}
    for entry in values.get("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", "").replace("\n", ";").split(";"):
        scopes, separator, token = entry.strip().partition(":")
        if separator and token.strip():
            fingerprint = hashlib.sha256(token.strip().encode()).hexdigest()
            token_scopes.setdefault(fingerprint, set()).update(part.strip() for part in scopes.split(","))
    try:
        bindings = json.loads(values.get("VAN_BROWSER_CONTROL_PROXY_BINDINGS", "{}"))
    except (ValueError, TypeError):
        bindings = None
    return {
        "browser_role_fingerprints_distinct": bool(distinct),
        "browser_role_credentials_narrow": distinct and all(
            token_scopes.get(value) == {"browser_stream_producer"} for value in fingerprints),
        "browser_control_proxy_identity_bound": bool(distinct and isinstance(bindings, dict)
            and set(bindings) == controls and all(isinstance(bindings[value], list)
                and cn in bindings[value] and all(isinstance(name, str) and name for name in bindings[value])
                for value in controls)
            and (bool(profiles) or values.get("VAN_BROWSER_CONTROL_PROXY_PRINCIPAL_SHA256") == pairs[0][0])),
    }


def _public_core_endpoint(value: str, port: int) -> bool:
    try:
        public = urlsplit(value)
        host = (public.hostname or "").lower()
        if (not value.startswith("https://") or public.scheme != "https" or public.port != port
                or not 1024 <= port <= 65535 or port in {8787, 9133}
                or not host or "@" in public.netloc or "?" in value or "#" in value
                or public.path not in ("", "/") or public.netloc.endswith(":")
                or host in {"localhost", "62.83.35.103"} or host.endswith(
                    (".local", ".localhost", ".internal", ".invalid", ".test", ".onion"))):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return bool("." in host and re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
                and not re.fullmatch(r"[0-9.]+", host)
                and all(label and len(label) <= 63 and not label.startswith("-") and not label.endswith("-") for label in host.split(".")))
        return address.version == 4 and address.is_global
    except (ValueError, TypeError):
        return False


def core_only_endpoint_checks(values: dict[str, str]) -> dict[str, bool]:
    try:
        public = urlsplit(values.get("VAN_PUBLIC_BASE_URL", ""))
        hermes = urlsplit(values.get("VAN_HERMES_BASE_URL", ""))
        address = ipaddress.IPv4Address(values.get("VAN_MTLS_BIND", ""))
        port = int(values.get("VAN_MTLS_PORT", "0"))
        return {
            "direct_core_mtls_endpoint": _public_core_endpoint(values.get("VAN_PUBLIC_BASE_URL", ""), port),
            "specific_core_ingress_bind": not (address.is_unspecified or address.is_loopback or address.is_multicast or address.is_link_local or address.is_reserved)
                and address not in ipaddress.ip_network("10.77.0.0/24")
                and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,14}", values.get("VAN_MTLS_INTERFACE", "")))
                and values.get("VAN_MTLS_INTERFACE") != "lo",
            "local_core_hermes_endpoint": values.get("VAN_HERMES_BASE_URL", "").startswith("http://")
                and "?" not in values.get("VAN_HERMES_BASE_URL", "") and "#" not in values.get("VAN_HERMES_BASE_URL", "") and hermes.scheme == "http" and hermes.hostname == "127.0.0.1"
                and hermes.port is not None and 1024 <= hermes.port <= 65535 and hermes.port not in {port, 8787, 9133}
                and hermes.username is None and hermes.password is None and hermes.path in ("", "/")
                and not hermes.query and not hermes.fragment,
        }
    except (ValueError, TypeError):
        return {"core_only_endpoint_bindings": False}


def configuration_checks(values: dict[str, str]) -> dict[str, bool]:
    required = {"VAN_ENV": "production", "VAN_REQUIRE_DEVICE_BINDING": "true",
                "VAN_ALLOW_LOOPBACK_IN_PRODUCTION": "false", "VAN_MTLS_ENABLED": "true",
                "VAN_DEPLOYMENT_TOPOLOGY": "CORE_ONLY_V2",
                "VAN_LOOPBACK_HOST": "127.0.0.1", "VAN_LOOPBACK_PORT": "8787", "VAN_HERMES_PROFILE": "van"}
    key_names = ("VAN_DEVICE_SECRET_FERNET_KEY", "VAN_GOOGLE_TOKEN_FERNET_KEY",
                 "VAN_HERMES_BEARER_TOKEN", "VAN_INTERNAL_CONTROL_SCOPED_TOKENS", "VAN_DEVICE_ENROLMENT_TOKEN")
    signer = values.get("VAN_OWNER_DEVICE_SIGNING_CERT_SHA256", "").replace(":", "")
    roots = values.get("VAN_OWNER_DEVICE_ATTESTATION_ROOTS", "").split(",")
    return {
        "core_only_profile": all(values.get(key) == value for key, value in required.items()),
        **core_only_endpoint_checks(values),
        "ingress_credential_present": len(values.get("VAN_INGRESS_TOKEN", "")) >= 32,
        "separate_service_credentials_present": all(values.get(key) for key in key_names),
        "enrolment_credential_separated_from_runtime": bool(values.get("VAN_DEVICE_ENROLMENT_TOKEN"))
            and values.get("VAN_DEVICE_ENROLMENT_TOKEN") not in values.get("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", "")
            and "device_enrolment" not in values.get("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", ""),
        "legacy_all_scope_control_disabled": not values.get("VAN_INTERNAL_CONTROL_TOKEN"),
        "owner_release_signer_bound": bool(re.fullmatch(r"[0-9a-fA-F]{64}", signer)),
        "google_attestation_roots_bound": bool(roots) and all(re.fullmatch(r"[0-9a-fA-F]{64}", value.strip().replace(":", "")) for value in roots),
    }


def memory_headroom_ok(meminfo: str) -> bool:
    match = re.search(r"^MemAvailable:\s+(\d+)\s+kB$", meminfo, re.M)
    # Gateway hard limit 1 GiB, with a 4 GiB availability floor reserved for existing
    # trading/system work. The live trading placement governor can demand more.
    return bool(match) and int(match[1]) >= 5 * 1024 * 1024


def optional_operator_file_checks(values: dict[str, str]) -> dict[str, bool]:
    """Observe optional file selectors and permissions without reading contents."""
    checks = {}
    for variable, private in {"VAN_BROWSER_ARTIFACT_PROVIDERS_FILE": True,
                              "VAN_MTLS_MACHINE_CLIENT_CA_FILE": False}.items():
        value = values.get(variable, "")
        if not value:
            continue
        path = Path(value)
        literal = path.is_absolute() and not any(c in value for c in "\n\r\"'\\%$")
        checks[variable.lower() + "_bound_file"] = literal and path.is_file() and not path.is_symlink()
        if private:
            checks[variable.lower() + "_private_mode"] = literal and path.is_file() and not (path.stat().st_mode & 0o077)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-env", type=Path, required=True)
    parser.add_argument("--gateway-env", type=Path, required=True)
    parser.add_argument("--google-env", type=Path, required=True)
    parser.add_argument("--trading-env", type=Path)
    parser.add_argument("--resource-dropin", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    checks = {}
    try:
        profile_values = read_environment(args.profile_env)
        trading = args.trading_env or args.gateway_env.parent / "trading-commander.env"
        values = effective_environment(args.google_env, args.gateway_env, trading, args.profile_env)
        checks.update(configuration_checks(values))
        checks.update(browser_credential_checks(values))
        checks.update(optional_operator_file_checks(values))
        checks["selected_profile_controls_effective_settings"] = all(values.get(key) == value for key, value in profile_values.items())
        checks["credential_file_modes_private"] = all(not (path.stat().st_mode & 0o077)
                                                       for path in (args.gateway_env, args.google_env, args.profile_env, trading) if path.is_file())
        checks["retained_core_host_identity"] = platform.node() == "van-trading-core" and platform.machine() == "aarch64"
        checks["trading_memory_headroom"] = memory_headroom_ok(Path("/proc/meminfo").read_text())
        expected = args.expected_sha
        current = subprocess.check_output(["git", "-C", str(args.repository), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(args.repository), "status", "--porcelain", "--untracked-files=all"], text=True)
        checks["exact_clean_immutable_source"] = bool(re.fullmatch(r"[0-9a-f]{40}", expected)) and current == expected and not dirty
        interfaces = json.loads(subprocess.check_output(["ip", "-j", "address", "show", "dev", "wg-dial"], text=True))
        checks["core_wireguard_interface"] = any(entry.get("local") == "10.77.0.4"
                                                for item in interfaces for entry in item.get("addr_info", []))
        ingress_interfaces = json.loads(subprocess.check_output(["ip", "-j", "address", "show", "dev", values["VAN_MTLS_INTERFACE"]], text=True))
        checks["observed_core_ingress_VNIC_address"] = any(entry.get("local") == values["VAN_MTLS_BIND"]
            for item in ingress_interfaces for entry in item.get("addr_info", []))
        dropin = args.resource_dropin.read_text()
        limits = {line.strip() for line in dropin.splitlines()}
        checks["bounded_gateway_cgroup"] = {"MemoryAccounting=true", "MemoryHigh=768M", "MemoryMax=1024M",
                                              "CPUQuota=100%", "CPUWeight=20", "TasksMax=128"} <= limits
        selected_state = Path(os.environ.get("VAN_STATE_ROOT", str(Path.home() / ".local/share/van"))).resolve()
        database = Path(values.get("VAN_DATABASE_PATH", "")).resolve()
        checks["persistent_owner_database"] = database.is_relative_to(selected_state) and not database.is_relative_to(selected_state / "runtime")
        checks["commander_credential_lane"] = bool(values.get("VAN_COMMANDER_URL")) and Path(values.get("VAN_COMMANDER_CA_FILE", "")).is_file()
        checks["commander_credential_separated_from_other_planes"] = commander_credential_separate(
            values, Path(values.get("VAN_COMMANDER_TOKEN_FILE", "")).read_text().strip())
        for label, path in {"device_ca_directory": values.get("VAN_MTLS_DIR", ""),
                            "manifest_signing_key": values.get("VAN_CONNECTIVITY_SIGNING_KEY_FILE", ""),
                            "gateway_commander_token": values.get("VAN_COMMANDER_TOKEN_FILE", "")}.items():
            selected = Path(path)
            checks[label + "_private_mode"] = selected.is_absolute() and selected.exists() and not (selected.stat().st_mode & 0o077)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        checks["local_inputs_and_observations_available"] = False
    ok = bool(checks) and all(checks.values())
    print(json.dumps({"status": "LOCAL_PREFLIGHT_PASS" if ok else "BLOCKED", "checks": checks,
                      "deployment_authority_verified": False, "deployed": False, "live_qualified": False,
                      "pending_external_checks": ["governed_exact_scope_ingress_and_deployment_recipe", "fresh_overlay_handshake_and_firewall",
                                                  "trading_placement_admission", "server_SAN_and_CA_matching_APK", "rollback_and_backup_receipt"]}))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
