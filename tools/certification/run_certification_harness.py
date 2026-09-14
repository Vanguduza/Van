#!/usr/bin/env python3
"""Repository-side certification harness. Live steps fail closed with explicit gate codes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def main() -> int:
    report: dict = {"product": "van", "gates": {}}

    code, out = run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT / "backend")
    report["gates"]["backend_pytest"] = {"ok": code == 0, "detail": out.strip().splitlines()[-1] if out.strip() else ""}

    code, out = run(
        [sys.executable, "-m", "pytest", "-q", "tests/contracts", "tests/scenarios", "tests/hermes", "hermes/policy/tests"],
        cwd=ROOT,
    )
    report["gates"]["cross_pytest"] = {"ok": code == 0, "detail": out.strip().splitlines()[-1] if out.strip() else ""}

    android = ROOT / "android"
    gradlew = android / ("gradlew.bat" if sys.platform.startswith("win") else "gradlew")
    if gradlew.exists():
        code, out = run([str(gradlew), ":app:testDebugUnitTest", ":app:assembleDebug", ":app:lintDebug", "--quiet"], cwd=android)
        report["gates"]["android_build_lint_test"] = {"ok": code == 0, "detail": "BUILD" if code == 0 else out[-500:]}
    else:
        report["gates"]["android_build_lint_test"] = {"ok": False, "detail": "gradlew_missing"}

    # External probes — never claim success on absence
    code, out = run(["adb", "devices"])
    devices = [ln for ln in out.splitlines() if "\tdevice" in ln]
    report["gates"]["physical_device"] = {
        "ok": False,
        "detail": f"devices={len(devices)}",
        "blocked": True,
        "reason": "PHYSICAL_DEVICE_REQUIRED" if not devices else "DEVICE_ATTACHED_MANUAL_CERT_PENDING",
    }

    code, out = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "ubuntu@84.12.94.18", "true"])
    report["gates"]["live_hermes_ssh"] = {
        "ok": False,
        "blocked": True,
        "reason": "HERMES_SSH_UNAVAILABLE",
        "detail": out.strip()[:200] or f"exit={code}",
    }

    report["gates"]["google_oauth_live"] = {
        "ok": False,
        "blocked": True,
        "reason": "GOOGLE_CREDENTIALS_REQUIRED",
    }
    report["gates"]["gemini_runtime"] = {
        "ok": False,
        "blocked": True,
        "reason": "GEMINI_CREDENTIAL_REQUIRED",
    }
    report["gates"]["artist_riv"] = {
        "ok": (ROOT / "visual-authority" / "rive" / "van_runtime.riv").exists(),
        "blocked": not (ROOT / "visual-authority" / "rive" / "van_runtime.riv").exists(),
        "reason": "RIVE_AUTHORING_REQUIRED",
    }

    out_path = ROOT / "artifacts" / "release" / "certification_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    repo_ok = all(report["gates"][k]["ok"] for k in ("backend_pytest", "cross_pytest", "android_build_lint_test"))
    return 0 if repo_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
