#!/usr/bin/env python3
"""Observe admitted owner-core wiring before physical-device provisioning.

Run within the existing governed core deployment recipe. This collector has no
deployment, firewall, key-generation or device-enrolment effects. It reads private
machine settings locally and exports only predicates, status codes and hashes.
Recorded service canaries remain distinct from fresh provider execution.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools/runtime"))
sys.path.insert(0, str(ROOT / "backend"))
from preflight_owner_core import configuration_checks, effective_environment
from prepare_owner_core_deployment import public_url
from van_gateway.auth.control_scopes import ControlAuthority, ControlScope
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from tools.certification.run_live_acceptance import MAX_BODY, NoRedirect, evaluate


def properties(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key in result or not re.fullmatch(r"VAN_[A-Z0-9_]+", key):
            raise ValueError("invalid_public_profile")
        result[key] = value
    return result


def scoped_token(values: dict[str, str], scope: ControlScope) -> str:
    authority = ControlAuthority(scoped=values.get("VAN_INTERNAL_CONTROL_SCOPED_TOKENS", ""),
                                 observability_token=values.get("VAN_OBSERVABILITY_TOKEN", ""))
    # Acceptance uses existing narrow credentials, never an enrolment or legacy
    # all-scope token. An ambiguous selection needs an explicit bound credential.
    candidates = {credential.token for credential in authority.credentials
                  if authority.granted_scopes(credential.token) == frozenset({scope})}
    if len(candidates) != 1:
        raise ValueError("one_narrow_acceptance_credential_required")
    return next(iter(candidates))


def deployed_source_matches(state: Path, config: Path, expected: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        return False
    runtime = state / "runtime"
    metadata = json.loads((runtime / "DEPLOYED_SOURCE.json").read_text())
    if (metadata.get("source_clean") is not True or metadata.get("repository_sha") != expected
            or metadata.get("expected_repository_sha") != expected
            or (runtime / "DEPLOYED_SHA").read_text().strip() != expected):
        return False
    runtime_hashes = metadata.get("runtime_sha256")
    if not isinstance(runtime_hashes, dict) or not runtime_hashes:
        return False
    for name, digest in runtime_hashes.items():
        selected = Path(name)
        if (selected.is_absolute() or ".." in selected.parts
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or hashlib.sha256((runtime / selected).read_bytes()).hexdigest() != digest):
            return False
    names = {name for name in ("google-workspace.env", "gateway.env", "trading-commander.env", "owner-core.env")
             if (config / name).is_file()}
    config_hashes = metadata.get("configuration_sha256")
    return (isinstance(config_hashes, dict) and set(config_hashes) == names
            and {"google-workspace.env", "gateway.env", "owner-core.env"} <= names
            and all(hashlib.sha256((config / name).read_bytes()).hexdigest() == config_hashes[name] for name in names))


def bindings(config: Path, state: Path, profile_path: Path, expected: str) -> tuple[dict, dict, ssl.SSLContext]:
    paths = [config / name for name in ("google-workspace.env", "gateway.env", "owner-core.env")]
    trading = config / "trading-commander.env"
    if trading.is_file():
        paths.append(trading)
    if not all(path.is_file() and not path.stat().st_mode & 0o077 for path in paths):
        raise ValueError("private_machine_settings_required")
    values = effective_environment(paths[0], paths[1], trading, config / "owner-core.env")
    if not all(configuration_checks(values).values()):
        raise ValueError("production_machine_configuration_required")
    profile = properties(profile_path)
    roles = {"VAN_DEPLOYMENT_PROFILE_VERSION": "2", "VAN_DEPLOYMENT_TOPOLOGY": "CORE_ONLY_V2",
             "VAN_BACKEND_HOST": "van-trading-core", "VAN_HERMES_HOST": "van-trading-core",
             "VAN_GATEWAY_INGRESS_HOST": "van-trading-core"}
    if not all(profile.get(key) == value for key, value in roles.items()):
        raise ValueError("selected_owner_core_profile_required")
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", profile.get("VAN_DEPLOYMENT_PROFILE_ID", ""))
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", profile.get("VAN_GATEWAY_INGRESS_CAPABILITY_RECEIPT", ""))):
        raise ValueError("bound_profile_receipt_reference_required")
    url, public_port = public_url(profile["VAN_GATEWAY_BASE_URL"])
    if values.get("VAN_PUBLIC_BASE_URL") != url:
        raise ValueError("profile_and_effective_endpoint_disagree")
    hermes = urllib.parse.urlsplit(values.get("VAN_HERMES_BASE_URL", ""))
    if (hermes.scheme != "http" or hermes.hostname != "127.0.0.1" or "@" in hermes.netloc
            or hermes.port is None or not 1024 <= hermes.port <= 65535 or hermes.port in {public_port, 8787, 9133}
            or hermes.path not in ("", "/") or hermes.query or hermes.fragment):
        raise ValueError("measured_local_core_hermes_endpoint_required")
    pem = base64.b64decode(profile["VAN_GATEWAY_CA_PEM_B64"], validate=True)
    certificate = x509.load_pem_x509_certificate(pem)
    declared_sha = profile["VAN_GATEWAY_CA_SHA256"].replace(":", "").lower()
    actual_ca = x509.load_pem_x509_certificate((Path(values["VAN_MTLS_DIR"]) / "ca.crt").read_bytes())
    if certificate.fingerprint(hashes.SHA256()).hex() != declared_sha or actual_ca.fingerprint(hashes.SHA256()).hex() != declared_sha:
        raise ValueError("profile_and_deployed_ca_disagree")
    context = ssl.create_default_context(cadata=pem.decode("ascii"))
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
    # No client chain is loaded: the real phone key remains on its device.
    tokens = {"runtime": scoped_token(values, ControlScope.RUNTIME),
              "operator": scoped_token(values, ControlScope.OBSERVABILITY)}
    checks = {"selected_core_host": platform.node() == "van-trading-core" and platform.machine() == "aarch64",
              "effective_production_settings": True, "public_profile_matches_private_core": True,
              "exact_deployed_source_and_configuration": deployed_source_matches(state, config, expected)}
    return values | tokens, checks, context


def observe(url: str, context: ssl.SSLContext | None, headers: dict[str, str], timeout: float) -> tuple[dict, dict]:
    # Retain supported proxy routing; never turn a denied route into a direct socket.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(url, headers={"Accept": "application/json", **headers}, method="GET")
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("bounded_observation_required")
        try:
            data = json.loads(body)
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}, {
            "http_status": response.code, "body_sha256": hashlib.sha256(body).hexdigest()}


def collect(config: Path, state: Path, profile: Path, expected: str, *, timeout: float = 10,
            max_age_seconds: int = 24 * 3600) -> dict:
    result = {"kind": "PRE_PHONE_HOST_OBSERVATION", "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "checks": [], "handset_verified": False, "owner_command_executed": False,
              "fresh_provider_execution_verified": False, "owner_signed_apk_verified": False,
              "ingress_authority_verified": False, "firewall_admission_verified": False,
              "device_provisioning_permitted": False, "live_e2e_qualified": False,
              "canary_max_age_seconds": max_age_seconds}
    try:
        values, local_checks, context = bindings(config, state, profile, expected)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["checks"].append({"name": "host_bindings", "outcome": "BLOCKED", "reason": type(exc).__name__,
                                 "required_bindings": ["private_effective_core_configuration", "generated_android_profile",
                                                       "existing_device_CA", "narrow_runtime_and_observability_credentials",
                                                       "externally_selected_deployed_source_SHA"]})
        result["outcome"] = "BLOCKED"
        return result
    for name, passed in local_checks.items():
        result["checks"].append({"name": name, "outcome": "PASS" if passed else "FAIL"})
    if not all(local_checks.values()):
        result["outcome"] = "FAIL"
        return result
    loopback = "http://127.0.0.1:8787"
    plans = [("gateway", loopback + "/health", {"X-Van-Ingress-Token": values["VAN_INGRESS_TOKEN"]}, None),
             *[(name, loopback + path, {"X-Van-Internal-Token": values["runtime"]}, None) for name, path in
               (("runtime", "/v1/runtime/status"), ("automation", "/v1/automation/health"), ("browser", "/v1/browser/health"))],
             ("operator", loopback + "/v1/observability/health", {"X-Van-Internal-Token": values["operator"]}, None),
             ("hermes", values["VAN_HERMES_BASE_URL"].rstrip("/") + "/p/van/health",
              {"Authorization": "Bearer " + values["VAN_HERMES_BEARER_TOKEN"]}, None),
             ("unauthenticated_public_health_refused", values["VAN_PUBLIC_BASE_URL"] + "/health", {}, context),
             ("unauthenticated_public_websocket_upgrade_refused", values["VAN_PUBLIC_BASE_URL"] + "/v1/session/ws",
              {"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13",
               "Sec-WebSocket-Key": "cHJlcGhvbmVvYnNlcnZlZA=="}, context)]
    for name, url, headers, tls in plans:
        check = {"name": name, "outcome": "FAIL"}
        try:
            data, evidence = observe(url, tls, headers, timeout)
            if name == "unauthenticated_public_health_refused":
                passed = evidence["http_status"] == 403 and data.get("detail") == "client_certificate_required"
            elif name == "unauthenticated_public_websocket_upgrade_refused":
                passed = evidence["http_status"] == 403
            else:
                passed = evidence["http_status"] == 200 and evaluate(name, data, now_ms=int(time.time() * 1000),
                                                                   max_age_seconds=max_age_seconds)
            check.update(evidence, outcome="PASS" if passed else "FAIL")
        except (OSError, ValueError, KeyError) as exc:
            check["reason"] = type(exc).__name__
        result["checks"].append(check)
    result["outcome"] = "PASS_HOST_HEALTH_ONLY" if all(check["outcome"] == "PASS" for check in result["checks"]) else "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--android-profile", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-canary-age-seconds", type=int, default=24 * 3600)
    args = parser.parse_args()
    if not 0 < args.timeout <= 30 or args.max_canary_age_seconds <= 0:
        parser.error("timeout must be in (0, 30] and canary age must be positive")
    receipt = collect(args.config_root, args.state_root, args.android_profile, args.expected_sha,
                      timeout=args.timeout, max_age_seconds=args.max_canary_age_seconds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["outcome"] == "PASS_HOST_HEALTH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
