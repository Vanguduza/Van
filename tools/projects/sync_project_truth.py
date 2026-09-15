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
MOUNTS = ROOT / "registries" / "project_mounts.json"

TRUTH_CANDIDATES = (
    "docs/PROJECT_TRUTH_PROTOCOL.md",
    "PROJECT_TRUTH_PROTOCOL.md",
    "PROJECT_CANONICAL_STATE.json",
    "agent-system/canon/PROJECT_TRUTH.md",
    "docs/00_PROJECT_TRUTH.md",
    "docs/truth/PROJECT_TRUTH.md",
)


def git_sha(path: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def truth_payload(project_id: str, repo_path: Path, preferred: str | None = None) -> tuple[dict, str]:
    ordered: list[str] = []
    if preferred:
        ordered.append(preferred.replace("\\", "/"))
    for rel in TRUTH_CANDIDATES:
        if rel not in ordered:
            ordered.append(rel)
    for rel in ordered:
        cand = repo_path / rel
        if cand.exists():
            text = cand.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return {
                "project_id": project_id,
                "truth_path": rel.replace("\\", "/"),
                "excerpt_sha256": digest,
                "bytes": len(text.encode("utf-8")),
            }, digest
    raise FileNotFoundError(f"no_project_truth:{project_id}:{repo_path}")


def load_default_mounts() -> list[tuple[str, Path]]:
    if not MOUNTS.exists():
        return []
    data = json.loads(MOUNTS.read_text(encoding="utf-8"))
    out: list[tuple[str, Path]] = []
    for item in data.get("mounts", []):
        out.append((item["project_id"], Path(item["path"]).expanduser()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Project Truth into Van gateway")
    parser.add_argument("--gateway", default="http://127.0.0.1:8787")
    parser.add_argument("--project", action="append", dest="projects", help="project_id=path")
    parser.add_argument("--from-mounts", action="store_true", help="Use registries/project_mounts.json")
    parser.add_argument("--offline-cache", action="store_true", help="Write local cache under artifacts/project-truth without gateway")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    known = {p["id"]: p for p in registry.get("projects", [])}

    mounts: list[tuple[str, Path]] = []
    if args.from_mounts:
        mounts.extend(load_default_mounts())
    for item in args.projects or []:
        if "=" not in item:
            print(f"FAIL invalid mount spec: {item}", file=sys.stderr)
            return 2
        pid, path = item.split("=", 1)
        mounts.append((pid, Path(path).expanduser().resolve()))

    if not mounts:
        print("FAIL no mounts provided (use --project id=path or --from-mounts)", file=sys.stderr)
        return 2

    cache_dir = ROOT / "artifacts" / "project-truth"
    if args.offline_cache:
        cache_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    results = []
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
            preferred = known[project_id].get("truth_path")
            truth, truth_sha = truth_payload(project_id, repo_path, preferred=preferred)
        except FileNotFoundError as exc:
            print(f"FAIL {exc}", file=sys.stderr)
            failures += 1
            continue
        repo = git_sha(repo_path)
        payload = {"truth": truth, "truth_sha": truth_sha, "repo_sha": repo}
        print(f"OK {project_id} truth_sha={truth_sha[:12]} repo_sha={repo}")
        results.append({"project_id": project_id, "truth_sha": truth_sha, "repo_sha": repo, "truth_path": truth["truth_path"]})
        if args.dry_run:
            continue
        if args.offline_cache:
            (cache_dir / f"{project_id}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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

    summary = {"ok": failures == 0, "mounted": results, "failures": failures}
    if args.offline_cache and not args.dry_run:
        (cache_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
