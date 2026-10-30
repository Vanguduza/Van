#!/usr/bin/env python3
"""Run source tests while refusing runtime storage in the checkout's data roots.

This is test instrumentation, not an operating-system sandbox. Run from the
frozen product checkout; the instrument itself may be pinned independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote,urlsplit


class StorageAudit:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.forbidden = (self.root / "data", self.root / "backend" / "data")
        self.physical = tuple(p.resolve() for p in self.forbidden)
        self.violations: list[dict] = []
        self.enabled = True

    def __call__(self, event, args):
        if not self.enabled:
            return
        paths = ()
        if event == "sqlite3.connect":
            paths = ((args[0], None),)
        elif event == "open":
            _, mode, flags = args
            writable = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writable:
                paths = ((args[0], None),)
        elif event == "os.mkdir":
            paths = ((args[0], args[2]),)
        elif event in {"os.remove", "os.rmdir"}:
            paths = ((args[0], args[1]),)
        elif event in {"os.rename", "os.link"}:
            paths = ((args[0], args[2]), (args[1], args[3]))
        elif event == "os.symlink":
            paths = ((args[0], args[2]), (args[1], args[2]))
        for raw, directory_fd in paths:
            if isinstance(raw, int):
                continue  # An existing fd has no path identity in this audit event.
            name = os.fsdecode(raw)
            if name == ":memory:":
                continue
            if event=="sqlite3.connect" and name.startswith("file:"):
                name=unquote(urlsplit(name).path)
            if not os.path.isabs(name) and directory_fd not in (None, -1, -100):
                try:
                    # Native *at operations resolve relative to this directory,
                    # including pytest's fd-based cleanup outside the checkout.
                    parent = os.readlink(f"/proc/self/fd/{directory_fd}")
                except OSError as exc:
                    self.violations.append({"event": event, "path": "UNRESOLVED_DIRECTORY_FD"})
                    raise AssertionError("source test directory-fd storage identity unavailable") from exc
                name = os.path.join(parent, name)
            logical=Path(os.path.abspath(name))
            path=logical.resolve()
            if (any(logical==base or logical.is_relative_to(base) for base in self.forbidden)
                or any(path==base or path.is_relative_to(base) for base in self.physical)):
                relative = str(logical.relative_to(self.root)) if logical.is_relative_to(self.root) else str(logical)
                self.violations.append({"event": event, "path": relative})
                raise AssertionError("source test attempted checkout runtime storage: " + relative)


def selftest():
    import sqlite3
    with tempfile.TemporaryDirectory(prefix="van-storage-audit-") as temp:
        root = Path(temp)
        (root / "data").mkdir()
        (root / "backend" / "data").mkdir(parents=True)
        (root / "alias").symlink_to(root/"data",target_is_directory=True)
        seed = root / "data" / "seed"
        seed.write_bytes(b"synthetic fixture")
        outside = root / "outside"
        outside.write_bytes(b"temporary fixture")
        audit = StorageAudit(root)
        sys.addaudithook(audit)
        probes = [
            lambda: seed.open("wb"), lambda: seed.open("ab"), lambda: seed.open("r+b"),
            lambda: (root / "data" / "new").open("xb"),
            lambda: os.open(seed, os.O_WRONLY), lambda: sqlite3.connect(seed),
            lambda: (root / "backend" / "data" / "new").mkdir(),
            lambda: seed.unlink(), lambda: seed.rename(outside),
            lambda: outside.rename(root / "data" / "moved"),
            lambda: os.link(outside, root / "data" / "linked"),
            lambda: os.symlink(outside, root / "data" / "symbolic"),
            lambda: (root/"alias"/"new").open("wb"),
            lambda: sqlite3.connect("file:"+str(root/"data"/"encoded.sqlite").replace("/data/","/data%2F"),uri=True),
        ]
        rejected = 0
        try:
            for probe in probes:
                try:
                    result = probe()
                except AssertionError as exc:
                    assert str(exc).startswith("source test attempted checkout runtime storage:")
                    rejected += 1
                else:
                    if hasattr(result, "close"):
                        result.close()
                    raise AssertionError("instrument failed to reject a planted runtime write")
            assert seed.read_bytes() == b"synthetic fixture"
            outside.write_bytes(b"allowed temporary write")
            assert outside.read_bytes() == b"allowed temporary write"
        finally:
            audit.enabled = False  # Probe-only hook ends before synthetic-tree cleanup.
        assert rejected == len(probes)
        return {"rejected": rejected, "allowed_read_and_external_write": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--report", type=Path)
    args, pytest_args = parser.parse_known_args()
    if args.selftest:
        print(json.dumps(selftest()))
        return 0
    if args.report is None:
        parser.error("--report is required")
    audit = StorageAudit(Path.cwd())
    report_path = args.report.resolve()
    sys.addaudithook(audit)
    tool_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    def report():
        report_path.write_text(json.dumps({
            "schema": "van.source-storage-audit/1", "forbidden_events": audit.violations,
            "source_sha256": tool_sha256,
            "root": str(audit.root), "scope": "SQLite opens, path-based writable opens and directory/link/rename/delete events under data and backend/data",
            "limits": "Python audit events only; directory-fd-relative open events lack their directory handle; existing fd writes, native-library raw I/O and external processes are not an OS sandbox. Git state is checked separately.",
        }, indent=2) + "\n")
    try:
        import pytest
        return pytest.main(pytest_args or ["backend/tests", "tests/contracts", "-q"])
    finally:
        # Persist the actual instrument result before interpreter globals clear.
        report()


if __name__ == "__main__":
    raise SystemExit(main())
