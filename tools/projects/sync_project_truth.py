#!/usr/bin/env python3
"""Mount/sync Project Truth for registered projects into the Van gateway cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries" / "projects.json"


def git_sha(path: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def truth_payload(project_id: str, repo_path: Path) -> tuple[dict, str]:
    candidates = [
        repo_path / "docs" / "PROJECT_TRUTH_PROTOCOL.md",
        repo_path / "PROJECT_TRUTH_PROTOCOL.md",
        repo_path / "PROJECT_CANONICAL_STATE.json",
    ]
    for cand in candidates:
        if cand.exists():
            text = cand.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return {
                "project_id": project_id,
                "truth_path": str(cand.relative_to(repo_path)).replace("\\", "/"),
                "excerpt_sha256": digest,
                "bytes": len(text.encode("utf-8")),
            }, digest
    raise FileNotFoundError(f"no_project_truth:{project_id}:{repo_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Project Truth into Van gateway")
    parser.add_argument("--gateway", default="http://127.0.0.1:8787")
    parser.add_argument("--project", action="append", dest="projects", help="project_id=path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    known = {p["id"]: p for p in registry.get("projects", [])}

    mounts: list[tuple[str, Path]] = []
    for item in args.projects or []:
        if "=" not in item:
            print(f"FAIL invalid mount spec: {item}", file=sys.stderr)
            return 2
        pid, path = item.split("=", 1)
        mounts.append((pid, Path(path).expanduser().resolve()))

    if not mounts:
        print("FAIL no mounts provided (use --project id=path)", file=sys.stderr)
        return 2

    failures = 0
    for project_id, repo_path in mounts:
        if project_id not in known:
            print(f"FAIL unknown_project:{project_id}", file=sys.stderr)
            failures += 1
            continue
        if not repo_path.exists():
            print(f"FAIL repo_unavailable:{project_id}:{repo_path}", file=sys.stderr)
            failures += 1
            continue
        try:
            truth, truth_sha = truth_payload(project_id, repo_path)
        except FileNotFoundError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            failures += 1
            continue
        repo = git_sha(repo_path)
        payload = {"truth": truth, "truth_sha": truth_sha, "repo_sha": repo}
        print(f"OK {project_id} truth_sha={truth_sha[:12]} repo_sha={repo}")
        if args.dry_run:
            continue
        resp = httpx.put(f"{args.gateway.rstrip('/')}/v1/projects/{project_id}/truth", json=payload, timeout=30.0)
        if resp.status_code >= 400:
            print(f"FAIL gateway:{project_id}:{resp.status_code}:{resp.text}", file=sys.stderr)
            failures += 1
            continue
        body = resp.json()
        if not body.get("ok"):
            print(f"FAIL truth_not_ok:{project_id}:{body}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
