#!/usr/bin/env python3
"""Rev 1.5 ADR-RB-026 / §0D.2 — provision the owner's phone, with nothing for them to type.

§0D.2 forbids the production build from exposing an editable Gateway URL or a pairing
token, and ADR-RB-026 says what replaces them: the first installation is provisioned by the
deployment pipeline. This is that pipeline's provisioning step.

    python3 tools/provisioning/provision_owner_device.py \\
        --gateway https://van.example \\
        --internal-token "$VAN_INTERNAL_CONTROL_TOKEN" \\
        --apk android/app/build/outputs/apk/release/app-release.apk

What it does, in order, and why the order is the order:

1. asks the Gateway for one signed provisioning payload
   (`POST /v1/devices/provisioning-payload`, internal-control credential). The Gateway
   mints both single-use tokens and the attestation challenge and sets the expiry, so an
   installer cannot extend a provisioning window or reuse a token by asking for it;
2. installs the APK, if one was given;
3. hands the payload to the app by starting `ProvisioningActivity` with it;
4. reads back what the device said.

**The credential never touches this machine's disk.** It is fetched, passed once and
dropped. A file would outlive the ten-minute window the payload is valid for, and the one
thing worse than a short-lived secret in a log is a short-lived secret in a file nobody
remembers writing.

**What this cannot do, said plainly.** It cannot verify the enrolment succeeded beyond what
the device logs, and it cannot run without a device. Whether a real S24 Ultra provisions
from a real Gateway is a physical measurement (Gate 14) and no amount of Python here
substitutes for it. What *is* checked in this repository is the payload's shape, its
refusals, and the exact argv this tool builds — see
`tests/contracts/test_owner_device_provisioning.py`.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request

#: The extra `ProvisioningActivity` reads. Pinned by a contract test against the Kotlin.
PROVISIONING_EXTRA = "van_provisioning"

#: The component the installer starts. Explicit: this activity has no intent filter, on
#: purpose, so it cannot be reached by anything that has not been told its name.
PROVISIONING_COMPONENT = "com.dial.van/.provisioning.ProvisioningActivity"

PROVISIONING_ROUTE = "/v1/devices/provisioning-payload"


class ProvisioningFailed(RuntimeError):
    pass


def request_payload(
    gateway: str, internal_token: str, *, device_gateway_url: str, note: str | None
) -> dict:
    """Ask the Gateway for the signed envelope. One call, and it mints everything."""
    body = json.dumps(
        {"gateway_url": device_gateway_url, "note": note}, separators=(",", ":")
    ).encode("utf-8")
    request = urllib.request.Request(
        gateway.rstrip("/") + PROVISIONING_ROUTE,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Van-Internal-Token": internal_token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise ProvisioningFailed(f"gateway refused provisioning ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProvisioningFailed(f"gateway unreachable: {exc.reason}") from exc


def encode_envelope(envelope: dict) -> str:
    """Base64 of the envelope, exactly as `ProvisioningActivity` decodes it.

    Sorted keys and no whitespace, so the same envelope encodes the same way twice. The
    device rebuilds its own canonical bytes before checking the signature, so this spelling
    does not affect verification — it affects whether two runs of this tool are comparable,
    which is what makes a failure reproducible.
    """
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


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
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ProvisioningFailed(
            f"{' '.join(argv[:3])} failed ({result.returncode}): {result.stderr.strip()}"
        )
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
    parser.add_argument("--internal-token", required=True,
                        help="the internal-control credential, at the DEVICE_ENROLMENT scope")
    parser.add_argument("--apk", default=None, help="an APK to install first")
    parser.add_argument("--serial", default=None, help="adb device serial")
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

    envelope = request_payload(
        args.gateway, args.internal_token, device_gateway_url=device_url, note=args.note
    )
    for field in ("payload", "signature", "kid"):
        if field not in envelope:
            raise ProvisioningFailed(f"gateway response has no {field}")

    if args.apk:
        print(f"installing {args.apk}", file=sys.stderr)
        run(adb_argv(args.serial, "install", "-r", args.apk), timeout=600)

    print("handing the payload to the device", file=sys.stderr)
    run(start_argv(args.serial, encode_envelope(envelope)))

    print(read_back(args.serial))
    print(
        "provisioning_id="
        + str(envelope["payload"].get("provisioning_id", "?")),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvisioningFailed as failure:
        print(f"provisioning failed: {failure}", file=sys.stderr)
        raise SystemExit(2) from failure
