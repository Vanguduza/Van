#!/usr/bin/env python3
"""Physical Samsung certification helper.

Fails closed when no device is attached. When a device is present, records which handset
it is (the target is a Galaxy S24 Ultra, SM-S928*), installs the debug APK if provided and
prints the checklist in docs/DEVICE_ACCEPTANCE_CHECKLIST.md for owner sign-off. It never
marks an item as passed: that is the owner's evidence to record.

The run order and the prerequisites (gateway ingress, provisioning, battery settings) are
in docs/PHYSICAL_TEST_RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: The handset every device gate is measured on (Character Forge M4, Rev 1.5 §0D.3).
TARGET_MODEL_PREFIX = "SM-S928"
#: Mirrors the rows of docs/DEVICE_ACCEPTANCE_CHECKLIST.md; a contract test keeps them equal.
CHECKLIST = [
    "install",
    "provisioning",
    "overlay",
    "notification_listener",
    "mic",
    "tts",
    "biometric",
    "drag_dock",
    "rotation",
    "process_kill",
    "doze",
    "reboot",
    "offline_queue",
    "reconnect",
    "secret_notification",
    "barge_in",
    "share_to_van",
    "google_capability_status",
    "rive_failure_to_canvas",
    "reduced_motion",
    "wake_word",
    "embodiment_candidate_b",
    "flame_aura",
    "trading_aura_overlay",
]


def adb(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(["adb", *args], capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def device_properties(serial: str) -> dict[str, str]:
    """Model and Android release of one attached handset, as the device reports them."""
    props: dict[str, str] = {}
    for key, prop in (("model", "ro.product.model"), ("android_release", "ro.build.version.release"),
                      ("sdk", "ro.build.version.sdk")):
        code, out = adb(["-s", serial, "shell", "getprop", prop])
        props[key] = out.strip() if code == 0 else ""
    props["target_device"] = str(props["model"].startswith(TARGET_MODEL_PREFIX)).lower()
    return props


def devices() -> list[str]:
    code, out = adb(["devices"])
    if code != 0:
        return []
    found: list[str] = []
    for line in out.splitlines():
        if "\tdevice" in line:
            found.append(line.split("\t", 1)[0].strip())
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, default=ROOT / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--serial", help="adb serial, when more than one device is attached")
    parser.add_argument("--report", type=Path, default=ROOT / "artifacts" / "release" / "device_cert_probe.json")
    args = parser.parse_args()

    attached = devices()
    report = {
        "ok": False,
        "blocked": True,
        "devices": attached,
        "checklist": CHECKLIST,
        "reason": "PHYSICAL_DEVICE_REQUIRED" if not attached else "DEVICE_ATTACHED_MANUAL_CERT_PENDING",
    }
    if not attached:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    serial = args.serial or (attached[0] if len(attached) == 1 else None)
    if serial is None or serial not in attached:
        report["reason"] = "DEVICE_AMBIGUOUS_PASS_SERIAL"
        print(json.dumps(report, indent=2))
        return 5
    report["device"] = {"serial": serial, **device_properties(serial)}

    if args.install:
        if not args.apk.exists():
            report["reason"] = "APK_MISSING"
            print(json.dumps(report, indent=2))
            return 3
        code, out = adb(["-s", serial, "install", "-r", str(args.apk)])
        report["install"] = {"ok": code == 0, "detail": out[-400:]}
        if code != 0:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 4

    report["ok"] = False
    report["blocked"] = True
    report["next"] = (
        "Owner must execute docs/DEVICE_ACCEPTANCE_CHECKLIST.md on the target handset, in the order "
        "of docs/PHYSICAL_TEST_RUNBOOK.md, and record PASS evidence."
    )
    if report["device"]["target_device"] != "true":
        report["warning"] = "NOT_THE_TARGET_HANDSET: device gates only count on an SM-S928*"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
