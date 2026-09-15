#!/usr/bin/env python3
"""Physical Samsung certification helper.

Fails closed when no device is attached. When a device is present, installs the
debug APK if provided and prints the EXTERNAL_GATES checklist for owner sign-off.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = [
    "install",
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
]


def adb(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(["adb", *args], capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


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

    if args.install:
        if not args.apk.exists():
            report["reason"] = "APK_MISSING"
            print(json.dumps(report, indent=2))
            return 3
        code, out = adb(["install", "-r", str(args.apk)])
        report["install"] = {"ok": code == 0, "detail": out[-400:]}
        if code != 0:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 4

    report["ok"] = False
    report["blocked"] = True
    report["next"] = "Owner must execute docs/EXTERNAL_GATES.md physical device checklist and record PASS evidence."
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
