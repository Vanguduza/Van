#!/usr/bin/env python3
"""Delete each guard of tools/ci/project_truth_ledger.py in turn and show a test fails.

Review I6 deleted the authorization append-only check and all 21 ledger tests still passed: the
guard was untested. Each guard in the checker carries a `# GUARD:<name>` marker; this script
writes a copy of the checker with exactly one guard disabled, runs
tests/contracts/test_project_truth_ledger.py against the copy (PROJECT_TRUTH_LEDGER_CHECKER_UNDER_TEST)
and reports the pytest exit code. A guard whose deletion leaves the suite green SURVIVES, and
the script exits 1.

    python tests/contracts/ledger_guard_mutations.py [--only NAME ...]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools" / "ci" / "project_truth_ledger.py"
TESTS = ROOT / "tests" / "contracts" / "test_project_truth_ledger.py"

# name -> (exact line fragment carrying the marker, its replacement with the guard deleted)
MUTATIONS: dict[str, tuple[str, str]] = {
    "scope": ("elif not auths.in_scope(aid, sha):", "elif False:"),
    "unscoped": ("if aid in self.scope_errors:", "if False:"),
    "record-append-only": ("if bad:", "if False:"),
    "intake-exemption": ("if added is not None:", "if False:"),
    "intake-pure-only": ("return None", "continue"),
    "glob": ("if not pat or not glob_match(path, pat):", "if not pat or not __import__('fnmatch').fnmatchcase(path, pat):"),
    "append-only": ("if is_append_only(old, new):", "if True:"),
    "unrecognised-annotation": ("else:", "else:\n                return True, None"),
    "binding-conflict": ("elif len(claims.get(aid, [])) > 1:", "elif False:"),
    "binding-cannot-rescope": ('elif rec.get("reusable") is True or "commit_scope" in rec:', "elif False:"),
    "allowed-narrow-only": ("& set(DEFAULT_ALLOWED)", ""),
    "baseline-ancestor-of-base": ("if anchor is not None and not repo.is_ancestor(sha, anchor):", "if False:"),
    "trust-base": ("trusted = base", "trusted = head"),
    "history": ('findings += [f"HISTORY_BROKEN_BY_CHANGE {f}" for f in hist]', "pass"),
    "ledger-append-only": ("if lost:", "if False:"),
    "digest": ('if r.get("commit_diff_sha256") != digest:', "if False:"),
    "merged-record-unchanged": ("any(repo.show_bytes(p, f) == new for p in parents[1:])", "True"),
}


def mutate(src: str, name: str) -> str:
    frag, repl = MUTATIONS[name]
    lines = src.split("\n")
    hits = [i for i, line in enumerate(lines) if line.rstrip().endswith(f"# GUARD:{name}")]
    if len(hits) != 1:
        raise SystemExit(f"guard {name}: expected one '# GUARD:{name}' marker, found {len(hits)}")
    line = lines[hits[0]]
    if frag not in line:
        raise SystemExit(f"guard {name}: marker line does not contain {frag!r}: {line.strip()}")
    lines[hits[0]] = line.replace(frag, repl, 1)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    src = CHECKER.read_text(encoding="utf-8")
    markers = set(re.findall(r"# GUARD:([a-z-]+)", src))
    unlisted = markers - set(MUTATIONS)
    if unlisted:
        print(f"guards with no mutation: {sorted(unlisted)}")
        return 1
    survived = []
    for name in ["control", *(args.only or sorted(MUTATIONS))]:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "project_truth_ledger.py"
            copy.write_text(src if name == "control" else mutate(src, name), encoding="utf-8")
            env = {**os.environ, "PROJECT_TRUTH_LEDGER_CHECKER_UNDER_TEST": str(copy)}
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x", str(TESTS)],
                                  cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            failed = [x.split("::")[-1].split(" ")[0] for x in proc.stdout.splitlines() if x.startswith("FAILED")]
            if name == "control":
                print(f"{'control (no mutation)':28s} pytest EXIT={proc.returncode}", flush=True)
                if proc.returncode != 0:
                    print("the unmutated suite fails; a mutation result would mean nothing")
                    return 2
                continue
            verdict = "KILLED" if proc.returncode != 0 else "SURVIVED"
            print(f"{name:28s} pytest EXIT={proc.returncode} {verdict} {failed[:1]}", flush=True)
            if proc.returncode == 0:
                survived.append(name)
    print(f"survived: {survived}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
