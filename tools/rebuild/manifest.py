#!/usr/bin/env python3
"""Hash manifest for the PRE-003 independent-review submission.

  python3 tools/rebuild/manifest.py build   write docs/rebuild/rev118/pre003/SUBMISSION_MANIFEST.json
  python3 tools/rebuild/manifest.py check   recompute and report any mismatch (exit 1)

Covers the rebuild evidence, its tools and tests, the admitted package tree and archive, and the
consolidation head. The manifest cannot name the commit that contains it; a reviewer pins
that commit with `git rev-parse` and then runs `check`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/rebuild/rev118/pre003/SUBMISSION_MANIFEST.json"
COVERED = ("docs/rebuild/rev118", "tools/rebuild", "tests/rebuild")
ARCHIVE = "docs/review-inputs/van-rev115/VAN_NEXT_WHOLE_PRODUCT_BLUEPRINT_PACK_REV1_18_20261021.zip"


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], check=True, capture_output=True, text=True).stdout.strip()


def files() -> list[str]:
    out = []
    for c in COVERED:
        for p in sorted((ROOT / c).rglob("*")):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and rel != OUT.relative_to(ROOT).as_posix() and "__pycache__" not in rel:
                out.append(rel)
    return out


def build() -> dict:
    return {
        "schema": "van.rebuild.pre003.submission-manifest/1",
        "consolidation_head": "b02075f327ea8180ab6d269eba358cf8c5479878",
        "package_tree": git("rev-parse", "HEAD:docs/review-inputs/van-rev115/package"),
        "archive_sha256": hashlib.sha256((ROOT / ARCHIVE).read_bytes()).hexdigest(),
        "files": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files()},
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("build", "check"):
        print(__doc__)
        return 2
    m = build()
    if sys.argv[1] == "build":
        OUT.write_text(json.dumps(m, indent=1, sort_keys=True) + "\n")
        print(f"{len(m['files'])} files")
        return 0
    old = json.loads(OUT.read_text())
    bad = sorted(k for k in set(old["files"]) | set(m["files"]) if old["files"].get(k) != m["files"].get(k))
    bad += [k for k in ("package_tree", "archive_sha256", "consolidation_head") if old[k] != m[k]]
    print(json.dumps({"mismatches": bad, "files": len(m["files"])}, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
