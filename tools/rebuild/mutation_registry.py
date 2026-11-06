#!/usr/bin/env python3
"""Read-only preflight of every registered mutation; no case is dropped or executed."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "tools/audit/mutation_suite.py"


def suite_groups():
    sys.path.insert(0, str(ROOT / "tools/audit"))
    spec = importlib.util.spec_from_file_location("_van_mutation_registry_suite", REGISTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    groups = [(tests, mutations, Path(options.get("root", ROOT / "backend")),
               Path(options.get("cwd", ROOT / "backend"))) for tests, mutations, options in module.groups()]
    groups.append(([], module.KOTLIN, ROOT, ROOT / "android/verification"))
    return groups


def inspect(groups):
    findings, count, edits_checked = [], 0, 0
    for tests, mutations, source_root, test_cwd in groups:
        for target in tests:
            path = target.split("::", 1)[0]
            if ".py" in path and not path.startswith("-") and not (test_cwd / path).is_file():
                findings.append({"kind": "TEST_TARGET_MISSING", "path": path})
        for mutation in mutations:
            count += 1
            if len(mutation) == 2:
                edits, reason = mutation
            else:
                path, old, new, reason = mutation
                edits = [(path, old, new)]
            current = {}
            for path, old, new in edits:
                edits_checked += 1
                file = source_root / path
                if not file.is_file():
                    findings.append({"kind": "SOURCE_TARGET_MISSING", "path": path, "mutation": reason})
                    continue
                text = current.setdefault(path, file.read_text())
                if old not in text:
                    findings.append({"kind": "SOURCE_ANCHOR_MISSING", "path": path,
                                     "mutation": reason, "anchor": old[:100]})
                elif text.replace(old, new, 1) == text:
                    findings.append({"kind": "NO_OP_MUTATION", "path": path, "mutation": reason})
                else:
                    current[path] = text.replace(old, new, 1)
    return {"mutation_count": count, "edit_count": edits_checked, "findings": findings,
            "execution_state": "NOT_RUN", "status": "INVALID_REGISTRY" if findings else "ANCHORS_VALID_BASELINES_AND_MUTATIONS_NOT_EXECUTED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    report = {"schema": "van.rebuild.mutation-registry-preflight/1",
              "registry_sha256": hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),
              **inspect(suite_groups())}
    print(json.dumps(report, indent=2))
    return 2 if report["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
