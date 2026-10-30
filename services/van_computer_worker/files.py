#!/usr/bin/env python3
"""Bounded /workspace text-file helper. No command execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path("/workspace").resolve()
MAX_TEXT = 256 * 1024
MAX_ENTRIES = 1000


def safe(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve(strict=False)
    if resolved != ROOT and ROOT not in resolved.parents:
        raise SystemExit("path_outside_workspace")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "read", "write"])
    parser.add_argument("--path", required=True)
    args = parser.parse_args()
    path = safe(args.path)
    if args.action == "list":
        if not path.is_dir():
            raise SystemExit("not_a_directory")
        rows = []
        for child in sorted(path.iterdir(), key=lambda p: p.name)[:MAX_ENTRIES]:
            rows.append({
                "name": child.name,
                "path": str(child),
                "kind": "directory" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else None,
            })
        print(json.dumps(rows, separators=(",", ":")))
        return 0
    if args.action == "read":
        if not path.is_file():
            raise SystemExit("not_a_file")
        data = path.read_bytes()
        if len(data) > MAX_TEXT:
            raise SystemExit("file_too_large")
        sys.stdout.write(data.decode("utf-8"))
        return 0
    data = sys.stdin.buffer.read(MAX_TEXT + 1)
    if len(data) > MAX_TEXT:
        raise SystemExit("text_too_large")
    data.decode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(json.dumps({"path": str(path), "bytes": len(data)}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
