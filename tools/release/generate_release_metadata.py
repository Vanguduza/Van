#!/usr/bin/env python3
"""Deterministic SBOM + provenance + checksums for VAN release artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "release"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    commit = git_sha()
    files: list[Path] = []
    for pattern in [
        "VERSION",
        "README.md",
        "visual-authority/rive_contract.json",
        "registries/projects.json",
        "backend/requirements.txt",
        "hermes/VERSION",
        "android/app/build/outputs/apk/debug/app-debug.apk",
    ]:
        p = ROOT / pattern
        if p.exists():
            files.append(p)

    checksums = {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in files}
    (OUT / "SHA256SUMS").write_text(
        "\n".join(f"{digest}  {path}" for path, digest in sorted(checksums.items())) + "\n",
        encoding="utf-8",
    )

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "component": {"type": "application", "name": "van", "version": version},
        },
        "components": [
            {"type": "library", "name": "fastapi", "version": ">=0.115.0"},
            {"type": "library", "name": "aiosqlite", "version": ">=0.20.0"},
            {"type": "library", "name": "cryptography", "version": ">=43.0.0"},
            {"type": "library", "name": "httpx", "version": ">=0.27.0"},
            {"type": "application", "name": "android-app", "version": version, "purl": "pkg:apk/com.dial.van@" + version},
            {"type": "application", "name": "hermes-profile-van", "version": (ROOT / "hermes" / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "hermes" / "VERSION").exists() else version},
        ],
    }
    (OUT / "sbom.cdx.json").write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")

    provenance = {
        "product": "van",
        "version": version,
        "git_commit": commit,
        "built_at_unix": int(time.time()),
        "builder": "tools/release/generate_release_metadata.py",
        "artifacts": checksums,
        "notes": "Repository-side provenance. Live Hermes/Google/device certification are separate gates.",
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
