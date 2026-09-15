#!/usr/bin/env python3
"""Copy tools/ci/github-actions-ci.yml into .github/workflows/ci.yml when allowed.

Fails closed if the credential lacks workflow scope (GitHub rejects the push).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tools" / "ci" / "github-actions-ci.yml"
DST = ROOT / ".github" / "workflows" / "ci.yml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Copy workflow into .github/workflows/")
    parser.add_argument("--commit-push", action="store_true", help="Commit and push after apply (requires workflow scope)")
    args = parser.parse_args()

    if not SRC.exists():
        print(f"FAIL missing_source:{SRC}", file=sys.stderr)
        return 2

    if not args.apply:
        print(f"READY_TO_APPLY source={SRC} dest={DST}")
        print("Run with --apply (and optionally --commit-push) using a token with workflow scope.")
        return 0

    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DST)
    print(f"APPLIED {DST}")

    if not args.commit_push:
        return 0

    subprocess.check_call(["git", "add", str(DST.relative_to(ROOT))], cwd=ROOT)
    commit = subprocess.run(
        ["git", "commit", "-m", "Install canonical GitHub Actions workflow path"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
        print(commit.stdout + commit.stderr, file=sys.stderr)
        return commit.returncode
    push = subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    print(push.stdout + push.stderr)
    if push.returncode != 0:
        print(
            "FAIL: push rejected. Refresh GitHub auth with workflow scope:\n"
            "  gh auth refresh -h github.com -s workflow\n"
            "then re-run this tool.",
            file=sys.stderr,
        )
        return push.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
