#!/usr/bin/env python3
"""Rev 1.5 ADR-RB-026 / §0D.2 — provision the owner's phone, with nothing for them to type.

§0D.2 forbids the production build from exposing an editable Gateway URL or a pairing
token, and ADR-RB-026 says what replaces them: the first installation is provisioned by the
deployment pipeline. This is that pipeline's provisioning step.

Production invocation requires the verified owner release packet, independent source and
signer bindings, exact admitted serial/model and the operator-only DEVICE_ENROLMENT
credential. See deploy/van-owner-core/README.md for the complete recipe inputs.

What it does, in order, and why the order is the order:

1. verifies the owner release packet, checks the exact selected device/model and installs
   the APK;
2. asks the Gateway for one signed provisioning payload
   (`POST /v1/devices/provisioning-payload`, internal-control credential). The Gateway
   mints both single-use tokens and the attestation challenge and sets the expiry, so an
   installer cannot extend a provisioning window or reuse a token by asking for it;
3. hands the payload to the app by starting `ProvisioningActivity` with it;
4. waits for the Gateway's verified binding, pairing, certificate and actual session
   admission receipt. Payload staging and an activity launch are not enrollment receipts.

**The credential never touches this machine's disk.** It is fetched, passed once and
dropped. A file would outlive the ten-minute window the payload is valid for, and the one
thing worse than a short-lived secret in a log is a short-lived secret in a file nobody
remembers writing.

The admission receipt establishes the observed transport, not the current liveness of a
socket or Hermes's ability to execute an owner command. Live owner-command acceptance is
a separate gate. This tool cannot run without an authorized device.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "release"))
from owner_release import trusted_keys, verify_packet
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

#: The extra `ProvisioningActivity` reads. Pinned by a contract test against the Kotlin.
PROVISIONING_EXTRA = "van_provisioning"

#: The component the installer starts. Explicit: this activity has no intent filter, on
#: purpose, so it cannot be reached by anything that has not been told its name.
PROVISIONING_COMPONENT = "com.dial.van/.provisioning.ProvisioningActivity"

PROVISIONING_ROUTE = "/v1/devices/provisioning-payload"
PROVISIONING_STATUS_ROUTE = "/v1/devices/provisioning-status"


class ProvisioningFailed(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The installer credential must never follow a redirect to another service.
        return None


def request_payload(
    gateway: str, internal_token: str, *, device_gateway_url: str, note: str | None,
    ca_file: str | None = None,
) -> dict:
    """Ask the Gateway for the signed envelope. One call, and it mints everything."""
    return request_json(gateway, internal_token, PROVISIONING_ROUTE,
                        {"gateway_url": device_gateway_url, "note": note}, ca_file=ca_file)


def request_json(gateway: str, internal_token: str, route: str, body: dict, *, ca_file: str | None = None) -> dict:
    try:
        address = urlsplit(gateway)
    except ValueError as exc:
        raise ProvisioningFailed("gateway URL invalid") from exc
    local_http = address.scheme == "http" and address.hostname in {"localhost", "127.0.0.1", "::1"}
    if ((address.scheme != "https" and not local_http) or not address.hostname
            or address.username or address.password or address.query or address.fragment
            or address.path not in {"", "/"} or address.netloc.endswith(":")
            or any(c.isspace() or ord(c) < 32 for c in gateway)):
        raise ProvisioningFailed("gateway must be a trusted HTTPS URL or authorized loopback HTTP")
    if not internal_token or any(ord(c) < 32 or ord(c) == 127 for c in internal_token):
        raise ProvisioningFailed("installer credential invalid")
    encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        gateway.rstrip("/") + route,
        data=encoded_body,
        headers={
            "Content-Type": "application/json",
            "X-Van-Internal-Token": internal_token,
        },
        method="POST",
    )
    try:
        context = ssl.create_default_context(cafile=ca_file)
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), RefuseRedirects())
        with opener.open(request, timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ProvisioningFailed("gateway receipt exceeded bounded response size")
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, dict):
                raise ProvisioningFailed("gateway receipt must be an object")
            return result
    except urllib.error.HTTPError as exc:
        # Response bodies can contain credentials; status is enough to identify refusal.
        raise ProvisioningFailed(f"gateway refused {route} ({exc.code})",
                                 retryable=exc.code == 429 or exc.code >= 500) from exc
    except urllib.error.URLError as exc:
        raise ProvisioningFailed(f"gateway unreachable ({type(exc.reason).__name__})", retryable=True) from exc
    except (ValueError, TimeoutError, OSError) as exc:
        raise ProvisioningFailed(f"gateway receipt unavailable ({type(exc).__name__})", retryable=True) from exc


def wait_for_admission(gateway: str, internal_token: str, bootstrap_token: str, *,
                       wait_seconds: float, ca_file: str | None = None) -> dict:
    deadline = time.monotonic() + wait_seconds
    last_state = "NO_RECEIPT"
    while True:
        try:
            receipt = request_json(gateway, internal_token, PROVISIONING_STATUS_ROUTE,
                                   {"bootstrap_token": bootstrap_token}, ca_file=ca_file)
        except ProvisioningFailed as exc:
            if not exc.retryable or time.monotonic() >= deadline:
                raise
            time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
            continue
        last_state = str(receipt.get("state", "INVALID_RECEIPT"))
        if last_state == "SESSION_ADMITTED":
            required = ("binding", "pairing", "tls_certificate", "session_admitted")
            steps, transport = receipt.get("steps"), receipt.get("transport_receipt")
            if (not isinstance(steps, dict) or not isinstance(transport, dict)
                    or not all(steps.get(step) is True for step in required)
                    or not isinstance(transport.get("audit_id"), str) or not transport["audit_id"]
                    or not isinstance(transport.get("van_session_id"), str) or not transport["van_session_id"]):
                raise ProvisioningFailed("gateway returned an incomplete admission receipt")
            return receipt
        if last_state in {"REVOKED", "EXPIRED"}:
            raise ProvisioningFailed(f"enrollment refused: {last_state}")
        if time.monotonic() >= deadline:
            raise ProvisioningFailed(f"enrollment acceptance timed out: {last_state}")
        time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))


def encode_envelope(envelope: dict) -> str:
    """Base64 of the envelope, exactly as `ProvisioningActivity` decodes it.

    Sorted keys and no whitespace, so the same envelope encodes the same way twice. The
    device rebuilds its own canonical bytes before checking the signature, so this spelling
    does not affect verification — it affects whether two runs of this tool are comparable,
    which is what makes a failure reproducible.
    """
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def verify_handoff(envelope: dict, anchors: Path, device_url: str) -> None:
    """Refuse a wrong signer/route or unusable credential before the phone handoff."""
    try:
        payload = envelope["payload"]
        keys = trusted_keys(anchors.read_text())
        key = keys[envelope["kid"]]
        signature = bytes.fromhex(envelope["signature"])
        now = int(time.time() * 1000)
        issued, expires = payload["issued_at_ms"], payload["expires_at_ms"]
        forbidden = {"ingress_token", "device_access_token", "device_secret", "internal_control_token",
                     "hermes_token", "access_token", "refresh_token", "client_secret", "private_key"}
        if (not isinstance(payload, dict) or forbidden.intersection(payload)
                or payload.get("payload_version") != 1 or len(signature) != 64
                or type(issued) is not int or type(expires) is not int
                or not issued <= now + 60_000 or not now < expires
                or not 0 < expires - issued <= 600_000
                or payload.get("gateway_url") != device_url.rstrip("/")
                or not isinstance(payload.get("provisioning_id"), str) or not payload["provisioning_id"]
                or any(not isinstance(payload.get(name), str) or len(payload[name]) < 32
                       for name in ("bootstrap_token", "pairing_token"))
                or not isinstance(payload.get("attestation_challenge"), str) or not payload["attestation_challenge"]):
            raise ValueError("invalid_handoff")
        der = utils.encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"))
        key.verify(der, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(), ec.ECDSA(hashes.SHA256()))
    except (OSError, ValueError, TypeError, KeyError, InvalidSignature) as exc:
        raise ProvisioningFailed("signed provisioning envelope does not match release trust, route or lifetime") from exc


def adb_argv(serial: str | None, *args: str) -> list[str]:
    """`adb` with the device selector in front, so a bench with two phones is unambiguous."""
    argv = ["adb"]
    if serial:
        argv += ["-s", serial]
    return argv + list(args)


def start_argv(serial: str | None, encoded: str) -> list[str]:
    """The exact command that hands the payload over.

    `--es` rather than a file, because an app cannot read `/data/local/tmp` on a modern
    Android and pushing into the app's own directory needs the app to already be running as
    a debuggable build — which a release build is not. The cost is that the payload passes
    through a shell and can reach a device log, and that is survivable only because of what
    ADR-RB-026 requires of it: it expires in minutes, it is consumed once, and it is not
    sufficient on its own to enrol without a hardware attestation.
    """
    return adb_argv(
        serial, "shell", "am", "start", "-n", PROVISIONING_COMPONENT,
        "--es", PROVISIONING_EXTRA, encoded,
    )


def run(argv: list[str], *, timeout: int = 120) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        # TimeoutExpired carries the full argv, including the signed payload.
        raise ProvisioningFailed(f"adb operation failed ({type(exc).__name__})") from exc
    if result.returncode != 0:
        raise ProvisioningFailed(f"adb operation failed ({result.returncode})")
    return result.stdout


def read_back(serial: str | None) -> str:
    """What the device said. The reasons are refusal names, never secrets.

    `ProvisioningPayload.loggableFields` excludes both tokens and the attestation
    challenge, so everything this reads is safe to print and safe to paste into a ticket.
    """
    return run(adb_argv(serial, "logcat", "-d", "-s", "VanProvisioning:*"), timeout=30)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True,
                        help="the Gateway this installer talks to")
    parser.add_argument("--device-gateway-url", default=None,
                        help="the Gateway URL the phone should use; defaults to --gateway")
    parser.add_argument("--internal-token", default=None,
                        help="legacy inline credential; prefer --internal-token-env")
    parser.add_argument("--internal-token-env", default="VAN_DEVICE_ENROLMENT_TOKEN",
                        help="environment variable containing the DEVICE_ENROLMENT credential")
    parser.add_argument("--ca-file", default=None, help="trusted Gateway CA file, if using a private CA")
    parser.add_argument("--wait-seconds", type=float, default=360,
                        help="wait for Gateway-recorded session admission (1..540 seconds)")
    parser.add_argument("--apk", default=None, help="an APK to install first")
    parser.add_argument("--serial", default=None, help="adb device serial")
    parser.add_argument("--expected-model", default="SM_S928B", help="independently admitted owner handset model")
    parser.add_argument("--release-packet", type=Path)
    parser.add_argument("--deployment-profile", type=Path)
    parser.add_argument("--trusted-keys", type=Path)
    parser.add_argument("--expected-release-sha", default=None)
    parser.add_argument("--expected-signer", default=None)
    parser.add_argument("--apksigner", default="apksigner")
    parser.add_argument("--aapt", default="aapt")
    parser.add_argument("--allow-development-artifact", action="store_true",
                        help="explicit development-only enrollment; never qualifies owner-core release wiring")
    parser.add_argument("--note", default=None, help="recorded in the Gateway's audit row")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be run and request nothing")
    args = parser.parse_args(argv)

    device_url = args.device_gateway_url or args.gateway
    if args.dry_run:
        # No payload is requested: a dry run that minted a credential would burn a
        # single-use token to print a command line.
        print(" ".join(start_argv(args.serial, "<payload>")))
        return 0

    if not 1 <= args.wait_seconds <= 540:
        raise ProvisioningFailed("wait-seconds must be 1..540, within the payload window")
    if not args.serial or not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", args.serial):
        raise ProvisioningFailed("explicit admitted adb serial required")
    if not args.expected_model or any(ord(c) < 32 for c in args.expected_model):
        raise ProvisioningFailed("explicit admitted handset model required")
    if not args.allow_development_artifact:
        if not all([args.apk, args.release_packet, args.deployment_profile, args.trusted_keys,
                    args.expected_release_sha, args.expected_signer]):
            raise ProvisioningFailed("owner release APK, packet, profile, anchors, source and signer bindings required")
        try:
            verify_packet(json.loads(args.release_packet.read_text()), Path(args.apk), args.deployment_profile,
                          args.trusted_keys, expected_sha=args.expected_release_sha, expected_signer=args.expected_signer,
                          device_gateway_url=device_url, apksigner=args.apksigner, aapt=args.aapt)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ProvisioningFailed("owner release artifact bindings refused") from exc
    internal_token = args.internal_token or os.environ.get(args.internal_token_env, "")
    if not internal_token.strip():
        raise ProvisioningFailed("DEVICE_ENROLMENT credential unavailable in installer environment")
    if run(adb_argv(args.serial, "get-state")).strip() != "device":
        raise ProvisioningFailed("selected adb device is not ready")
    if run(adb_argv(args.serial, "shell", "getprop", "ro.product.model")).strip() != args.expected_model:
        raise ProvisioningFailed("selected adb handset model does not match admission")
    # Install before minting the short-lived payload: a slow APK transfer must not spend
    # the enrollment window before Android ever receives it.
    if args.apk:
        print(f"installing {args.apk}", file=sys.stderr)
        run(adb_argv(args.serial, "install", "-r", args.apk), timeout=600)

    envelope = request_payload(
        args.gateway, internal_token, device_gateway_url=device_url, note=args.note,
        ca_file=args.ca_file,
    )
    for field in ("payload", "signature", "kid"):
        if field not in envelope:
            raise ProvisioningFailed(f"gateway response has no {field}")
    payload = envelope["payload"]
    token = payload.get("bootstrap_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or len(token) < 32:
        raise ProvisioningFailed("gateway response has no valid bootstrap token")
    if not args.allow_development_artifact:
        verify_handoff(envelope, args.trusted_keys, device_url)

    print("handing the payload to the device", file=sys.stderr)
    run(start_argv(args.serial, encode_envelope(envelope)))
    receipt = wait_for_admission(args.gateway, internal_token, token,
                                 wait_seconds=args.wait_seconds, ca_file=args.ca_file)
    # Only the server's allowlisted receipt is printed. Never print the envelope or ADB
    # output containing extras. No token or hardware attestation goes into diagnostics.
    print(json.dumps({"provisioning_id": envelope["payload"].get("provisioning_id"),
                      "state": receipt["state"], "steps": receipt["steps"],
                      "transport_receipt": receipt["transport_receipt"],
                      "owner_release_artifact_verified": not args.allow_development_artifact,
                      "device_serial": args.serial, "device_model": args.expected_model,
                      "owner_e2e_verified": False, "hermes_verified": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisioningFailed as failure:
        print(f"provisioning failed: {failure}", file=sys.stderr)
        raise SystemExit(2) from failure
