#!/usr/bin/env python3
"""Collect bounded, authenticated live health evidence without changing deployment.

This checks the actual HTTPS services and persisted canary readiness. It neither
runs owner commands nor certifies a handset, provider execution, or deployed SHA.
Credentials and existing client-certificate paths come only from the environment;
receipts contain booleans, status codes and body hashes, never response bodies.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward a scoped credential to a different host or route.
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def base_url(value: str, *, allow_loopback_http: bool = False) -> str:
    parsed = urllib.parse.urlsplit(value)
    local_http = (allow_loopback_http and parsed.scheme == "http"
                  and parsed.hostname in {"127.0.0.1", "::1", "localhost"})
    if ((parsed.scheme != "https" and not local_http) or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment):
        raise ValueError("a live target must be an HTTPS URL without credentials, query or fragment")
    return value.rstrip("/")


def gateway_default() -> tuple[str, str]:
    properties = dict(line.split("=", 1) for line in (ROOT / "android/van-gateway.properties").read_text().splitlines()
                      if "=" in line and not line.lstrip().startswith("#"))
    overridden = os.environ.get("VAN_LIVE_GATEWAY_BASE_URL")
    # The committed CA belongs only to its committed endpoint.
    return (base_url(overridden or properties["VAN_GATEWAY_BASE_URL"]),
            "" if overridden else properties["VAN_GATEWAY_CA_PEM_B64"])


def gateway_context(committed_ca: str) -> ssl.SSLContext:
    ca_file = os.environ.get("VAN_LIVE_GATEWAY_CA_FILE")
    if ca_file:
        context = ssl.create_default_context(cafile=ca_file)
    elif committed_ca:
        pem = base64.b64decode(committed_ca, validate=True).decode("ascii")
        context = ssl.create_default_context(cadata=pem)
    else:
        raise ValueError("VAN_LIVE_GATEWAY_CA_FILE is required for an overridden endpoint")
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(os.environ["VAN_LIVE_CLIENT_CERT_FILE"],
                            os.environ["VAN_LIVE_CLIENT_KEY_FILE"])
    return context


def get_json(url: str, context: ssl.SSLContext, headers: dict[str, str], timeout: float) -> tuple[dict, dict]:
    # ProxyHandler keeps the session's supported proxy and credential injection.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(url, headers={**headers, "Accept": "application/json"}, method="GET")
    with opener.open(request, timeout=timeout) as response:
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("health response exceeds the evidence size limit")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("health response is not a JSON object")
        return data, {"http_status": response.status, "body_sha256": hashlib.sha256(body).hexdigest()}


def runtime_ready(data: object, now_ms: int, max_age_seconds: int) -> bool:
    if not isinstance(data, dict):
        return False
    timestamp = data.get("verified_at_ms")
    version = data.get("runtime_version")
    expected = data.get("expected_version")
    return (data.get("state") == "READY" and data.get("configured") is True
            and data.get("egress_enabled") is True and data.get("contains_secrets") is False
            and isinstance(data.get("evidence_pointer"), str) and bool(data["evidence_pointer"].strip())
            and isinstance(timestamp, int) and not isinstance(timestamp, bool)
            and -60_000 <= now_ms - timestamp <= max_age_seconds * 1000
            and isinstance(version, str) and bool(version)
            and (not expected or version == expected))


def evaluate(name: str, data: dict, *, now_ms: int, max_age_seconds: int) -> bool:
    def section(key: str) -> dict:
        value = data.get(key)
        return value if isinstance(value, dict) else {}

    if name == "gateway":
        hermes = section("hermes")
        return (data.get("ok") is True and data.get("service") == "van-gateway"
                and isinstance(hermes, dict) and hermes.get("ok") is True and hermes.get("profile") == "van")
    if name == "hermes":
        return data.get("ok") is True and data.get("profile", "van") == "van"
    if name == "runtime":
        return (data.get("hermes_is_sole_agent_runtime") is True
                and data.get("signed_command_authority_required") is True)
    if name == "automation":
        return (runtime_ready(data.get("runtime"), now_ms, max_age_seconds)
                and section("governance").get("production_activation_permitted") is True)
    if name == "browser":
        return (all(runtime_ready(data.get(key), now_ms, max_age_seconds) for key in ("harness", "stagehand"))
                and section("governance").get("production_activation_permitted") is True)
    if name == "operator":
        device = section("device_pki")
        days = device.get("days_remaining")
        return (section("audit_chain").get("ok") is True
                and section("scheduler").get("running") is True
                and device.get("configured") is True and device.get("present") is True
                and isinstance(days, (int, float)) and not isinstance(days, bool) and days > 30)
    raise ValueError("unknown live check")


def collect(*, timeout: float = 10, max_age_seconds: int = 24 * 3600) -> dict:
    result = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "kind": "LIVE_HEALTH_AND_RECORDED_CANARY_CHECK", "checks": [],
              "verification_enabled": True, "owner_command_executed": False,
              "handset_verified": False, "deployed_source_verified": False,
              "canary_max_age_seconds": max_age_seconds}
    client_names = ("VAN_LIVE_CLIENT_CERT_FILE", "VAN_LIVE_CLIENT_KEY_FILE")
    try:
        gateway, ca = gateway_default()
    except (OSError, ValueError, KeyError) as exc:
        result["checks"].append({"name": "gateway_configuration", "outcome": "BLOCKED",
                                  "reason": type(exc).__name__})
        gateway, ca = "", ""
    context = None
    plans = (
        ("gateway", "/health", "VAN_INGRESS_TOKEN", "X-Van-Ingress-Token"),
        ("runtime", "/v1/runtime/status", "VAN_LIVE_RUNTIME_TOKEN", "X-Van-Internal-Token"),
        ("automation", "/v1/automation/health", "VAN_LIVE_RUNTIME_TOKEN", "X-Van-Internal-Token"),
        ("browser", "/v1/browser/health", "VAN_LIVE_RUNTIME_TOKEN", "X-Van-Internal-Token"),
        ("operator", "/v1/observability/health", "VAN_OBSERVABILITY_TOKEN", "X-Van-Internal-Token"),
    )
    for name, path, token_name, header_name in plans:
        check = {"name": name, "outcome": "BLOCKED"}
        missing = [key for key in (*client_names, token_name) if not os.environ.get(key)]
        if not gateway:
            missing.append("valid_gateway_configuration")
        if missing:
            check["missing_requirements"] = missing
        else:
            try:
                if context is None:
                    context = gateway_context(ca)
                data, evidence = get_json(gateway + path, context,
                                          {header_name: os.environ[token_name]}, timeout)
                check.update(evidence)
                ready = evaluate(name, data, now_ms=int(time.time() * 1000), max_age_seconds=max_age_seconds)
                check["outcome"] = "PASS" if ready else "FAIL"
                check["readiness_predicate_satisfied"] = ready
            except urllib.error.HTTPError as exc:
                check.update(outcome="FAIL", http_status=exc.code, reason="HTTP_refused")
            except (OSError, ValueError, KeyError) as exc:
                # Exception text may contain URLs or remote bodies: retain only its type.
                check.update(outcome="FAIL", reason=type(exc).__name__)
        result["checks"].append(check)
    hermes = {"name": "hermes", "outcome": "BLOCKED"}
    names = ("VAN_HERMES_BASE_URL", "VAN_HERMES_BEARER_TOKEN")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        hermes["missing_requirements"] = missing
    else:
        try:
            # The documented Hermes profile listener is host-local HTTP. This is
            # usable only when the runner already has an authorized host route;
            # public credential-bearing requests still require verified HTTPS.
            url = base_url(os.environ[names[0]], allow_loopback_http=True) + "/p/van/health"
            data, evidence = get_json(url, ssl.create_default_context(),
                                      {"Authorization": "Bearer " + os.environ[names[1]], "X-Hermes-Profile": "van"}, timeout)
            hermes.update(evidence)
            hermes["outcome"] = "PASS" if evaluate("hermes", data, now_ms=0, max_age_seconds=max_age_seconds) else "FAIL"
        except urllib.error.HTTPError as exc:
            hermes.update(outcome="FAIL", http_status=exc.code, reason="HTTP_refused")
        except (OSError, ValueError) as exc:
            hermes.update(outcome="FAIL", reason=type(exc).__name__)
    result["checks"].append(hermes)
    outcomes = {check["outcome"] for check in result["checks"]}
    result["outcome"] = "PASS_HEALTH_ONLY" if outcomes == {"PASS"} else "FAIL" if "FAIL" in outcomes else "BLOCKED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-canary-age-seconds", type=int, default=24 * 3600)
    args = parser.parse_args()
    if not 0 < args.timeout <= 30 or args.max_canary_age_seconds <= 0:
        parser.error("timeout must be in (0, 30] and canary age must be positive")
    receipt = collect(timeout=args.timeout, max_age_seconds=args.max_canary_age_seconds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["outcome"] == "PASS_HEALTH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
