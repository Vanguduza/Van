#!/usr/bin/env python3
"""Execute retargeted legacy cases with controls and retain their actual failure oracles.

Runs in place through the original journalled harness. Do not run other tests or
edit source concurrently. The reference is the last committed invalid-registry
receipt, not a mutable list that can silently shrink after a successful run.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/audit"))
import mutation_suite as suite
from mutation import run

REFERENCE = "e56a38c8d5b51b7c64d3d4ac04e2d8a59f6c9b36"
RECEIPT = "docs/rebuild/rev118/ci/MUTATION_REGISTRY_PREFLIGHT.json"


def reference_cases():
    receipt = json.loads(subprocess.check_output(["git", "show", f"{REFERENCE}:{RECEIPT}"], cwd=ROOT))
    return {row["mutation"] for row in receipt["findings"] if "mutation" in row}


def preservation():
    source = subprocess.check_output(["git", "show", f"{REFERENCE}:tools/audit/mutation_suite.py"], cwd=ROOT).decode()
    prior = {"__file__": str(ROOT / "tools/audit/mutation_suite.py"), "__name__": "_reference_suite"}
    exec(compile(source, "reference_suite", "exec"), prior)
    old = [m[-1] for _, ms, _ in prior["groups"]() for m in ms] + [m[-1] for m in prior["KOTLIN"]]
    new = [m[-1] for _, ms, _ in suite.groups() for m in ms] + [m[-1] for m in suite.KOTLIN]
    if Counter(old) != Counter(new):
        raise ValueError("mutation identities changed")
    return len(old)


def valid_python_edits(mutations, root):
    for mutation in mutations:
        edits = mutation[0] if len(mutation) == 2 else [mutation[:3]]
        changed = {}
        for name, old, new in edits:
            path = root / name
            text = changed.get(path, path.read_text())
            if old not in text:
                raise ValueError(f"missing anchor: {mutation[-1]}")
            changed[path] = text.replace(old, new, 1)
        for path, text in changed.items():
            if path.suffix == ".py":
                ast.parse(text, filename=str(path))


def classify(kind, result, kotlin=False):
    output = result.stdout + result.stderr
    if kind == "baseline":
        return "PASS" if result.returncode == 0 else "INVALID_CONTROL"
    if result.returncode == 0:
        return "SURVIVED"
    if kotlin:
        if (re.search(r"(?:compile\w*Kotlin FAILED|Compilation error|Unresolved reference)", output)
            or not re.search(r"\d+ tests? completed, \d+ failed", output)):
            return "INVALID_EXECUTION"
    elif result.returncode != 1 or not re.search(r"^FAILED \S+", output, re.MULTILINE):
        return "INVALID_EXECUTION"
    return "ASSERTION_DETECTED"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=["python", "browser-agent", "kotlin"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--reason", help="Optional substring selecting a failed case for requalification")
    args = parser.parse_args()
    count = preservation()
    selected = reference_cases()
    if args.reason:
        selected = {reason for reason in selected if args.reason in reason}
        if not selected:
            raise ValueError("selector matches no reference mutation")
    args.logs.mkdir(parents=True, exist_ok=True)
    rows, groups = [], []
    if args.part in {"python", "browser-agent"}:
        for tests, mutations, options in suite.groups(family=args.part):
            mutations = [m for m in mutations if m[-1] in selected]
            if mutations:
                root = Path(options.get("root", ROOT / "backend"))
                cwd = Path(options.get("cwd", ROOT / "backend"))
                valid_python_edits(mutations, root)
                groups.append((tests, mutations, {"root": root, "cwd": cwd}))
    else:
        mutations = [m for m in suite.KOTLIN if m[-1] in selected]
        groups.append(([], mutations, {"root": ROOT, "cwd": ROOT / "android/verification",
                      "command": ["gradle", "test", "--console=plain", "--offline", "--rerun-tasks"]}))
    started = time.time()
    report = {"schema": "van.rebuild.mutation-reconciliation/1", "part": args.part,
              "reference": REFERENCE, "preserved_case_count": count,
              "selected_case_count": sum(len(ms) for _, ms, _ in groups),
              "registry_sha256": hashlib.sha256((ROOT / "tools/audit/mutation_suite.py").read_bytes()).hexdigest(),
              "results": rows, "status": "RUNNING"}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    def observe(kind, reason, result):
        output = result.stdout + result.stderr
        log = args.logs / f"{len(rows):03}-{kind}.txt"
        log.write_text(output)
        verdict = classify(kind, result, args.part == "kotlin")
        rows.append({"kind": kind, "mutation": reason, "exit": result.returncode,
                     "verdict": verdict, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                     "failed_oracles": re.findall(r"^(?:FAILED \S+.*|.* > .* FAILED)$", output, re.MULTILINE),
                     "summary": output[-1600:]})
        save()
        if verdict in {"INVALID_CONTROL", "INVALID_EXECUTION"}:
            raise RuntimeError(f"{verdict}: {reason}; inspect {log}")

    save()
    try:
        for tests, mutations, options in groups:
            print(f"CONTROL: {tests or 'Gradle JVM'}; {len(mutations)} mutations", flush=True)
            run(mutations, tests, observe=observe, **options)
        failures = [r for r in rows if r["verdict"] not in {"PASS", "ASSERTION_DETECTED"}]
        report["status"] = "FAILED" if failures else "PASS"
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = str(exc)
        raise
    finally:
        report["duration_seconds"] = round(time.time() - started, 3)
        save()
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
