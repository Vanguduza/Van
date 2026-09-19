#!/usr/bin/env python3
"""Maturity gate — the control that would have prevented most of the audit's findings.

The whole-system audit found the same defect shape over and over: a component was built,
never wired to a producer or a consumer, and then described in a canonical document as
BUILT. Twenty classes in the cognition layer had no production caller at all. The tests
passed, the code was real, and nobody could tell the difference from the outside.

This gate makes that shape a CI failure rather than a discovery. It enforces, mechanically:

  1. Every finding in the register is assigned to a remediation gate.
  2. Every non-integrated component carries exactly one disposition.
  3. A component may only claim the INTEGRATED_AND_EVIDENCED terminal state when it names
     a producer, a consumer, a production caller, tests and runtime evidence.
  4. A component claiming DELIBERATELY_REMOVED must no longer exist at its stated path.
  5. Bidirectional coverage: no orphan finding, no orphan component.
  6. Forbidden production routes stay absent.

Run:  python3 tools/ci/maturity_gate.py [--strict]

Exit 0 = gate passes. Exit 1 = a claim is not backed. Exit 2 = the ledgers are unreadable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINDINGS = ROOT / "evidence" / "van-system-audit" / "findings.json"
COMPONENTS = ROOT / "evidence" / "van-system-audit" / "component_ledger.json"
BLUEPRINT = ROOT / "docs" / "VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md"

TERMINAL_STATES = {
    "INTEGRATED_AND_EVIDENCED",
    "DELIBERATELY_REMOVED_CANON_CORRECTED",
    "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE",
}

#: Required when a component claims it is integrated. These are the maturity invariant's
#: machine-checkable elements; the human-judged ones (failure semantics, degraded behaviour)
#: are gate-review questions, not CI assertions.
INTEGRATION_EVIDENCE_FIELDS = (
    "producer",
    "consumer",
    "production_caller",
    "tests",
    "runtime_evidence",
)

#: Routes that must never exist in the production application. The audit found a live
#: Google transport could be hot-swapped for a fake on the running app.
FORBIDDEN_PRODUCTION_ROUTES = (
    ("/v1/google/test-transport", ROOT / "backend" / "van_gateway" / "app.py"),
)


class Failure(Exception):
    """A claim that the repository does not back."""


def _load(path: Path) -> dict:
    if not path.is_file():
        raise Failure(f"ledger missing: {path.relative_to(ROOT)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Failure(f"ledger is not valid JSON: {path.relative_to(ROOT)}: {exc}") from exc


def check_findings_assigned(findings: dict) -> list[str]:
    """Every finding must name the gate that closes it."""
    problems = []
    seen_ids = set()
    for f in findings.get("findings", []):
        fid = f.get("id")
        if not fid:
            problems.append("a finding has no id")
            continue
        if fid in seen_ids:
            problems.append(f"{fid}: duplicate finding id")
        seen_ids.add(fid)
        if not f.get("remediation_gate"):
            problems.append(f"{fid}: no remediation_gate — an unassigned finding is a planning defect")
        if f.get("current_status") not in {"OPEN", "CLOSED", "IN_PROGRESS", "SUPERSEDED"}:
            problems.append(f"{fid}: current_status {f.get('current_status')!r} is not a recognised state")
    return problems


def check_component_dispositions(components: dict) -> list[str]:
    """Every component carries one disposition, and any terminal claim is backed."""
    problems = []
    valid_dispositions = {"WIRE", "COMPLETE", "REPLACE", "DELETE"}
    for c in components.get("components", []):
        name = c.get("component", "<unnamed>")
        disp = c.get("disposition")
        if disp not in valid_dispositions:
            problems.append(f"{name}: disposition {disp!r} is not one of {sorted(valid_dispositions)}")

        terminal = c.get("terminal_state")
        if terminal is None:
            continue  # still in flight; that is legitimate until its gate closes

        if terminal not in TERMINAL_STATES:
            problems.append(f"{name}: terminal_state {terminal!r} is not an allowed terminal state")
            continue

        if terminal == "INTEGRATED_AND_EVIDENCED":
            missing = [k for k in INTEGRATION_EVIDENCE_FIELDS if not c.get(k)]
            if missing:
                problems.append(
                    f"{name}: claims INTEGRATED_AND_EVIDENCED but names no {', '.join(missing)}. "
                    "This is the exact shape the audit found 20 times over."
                )

        if terminal == "DELIBERATELY_REMOVED_CANON_CORRECTED":
            problems += _check_removal(c, name)
    return problems


def _check_removal(c: dict, name: str) -> list[str]:
    """Removal means the code is gone, not merely unreferenced.

    What "gone" means differs per component. Deleting a whole module means the file is
    absent. Deleting two methods from a module that legitimately survives means those
    symbols are absent from it. A component declares which via `removal_assertion`:

        {"kind": "file_absent"}                                  (default)
        {"kind": "symbols_absent", "symbols": ["message_agent"]}
    """
    problems = []
    path = c.get("path", "")
    assertion = c.get("removal_assertion") or {"kind": "file_absent"}
    kind = assertion.get("kind")

    if not path or path.startswith("("):
        return problems  # prose or external path; nothing mechanical to assert

    target = ROOT / path

    if kind == "file_absent":
        if target.is_file():
            problems.append(
                f"{name}: claims DELIBERATELY_REMOVED but {path} still exists. "
                "Removal means the code is gone, not merely unreferenced."
            )
    elif kind == "symbols_absent":
        symbols = assertion.get("symbols") or []
        if not symbols:
            problems.append(f"{name}: removal_assertion symbols_absent names no symbols")
        elif not target.is_file():
            problems.append(f"{name}: removal_assertion targets {path}, which does not exist")
        else:
            text = target.read_text(encoding="utf-8", errors="replace")
            still_defined = [
                sym for sym in symbols
                if re.search(rf"^\s*(?:async\s+)?def\s+{re.escape(sym)}\b", text, re.M)
                or re.search(rf"^\s*(?:suspend\s+)?fun\s+{re.escape(sym)}\b", text, re.M)
            ]
            if still_defined:
                problems.append(
                    f"{name}: claims DELIBERATELY_REMOVED but {path} still defines "
                    f"{', '.join(still_defined)}."
                )
    else:
        problems.append(f"{name}: removal_assertion kind {kind!r} is not recognised")
    return problems
    return problems


def check_bidirectional_coverage(findings: dict, components: dict) -> list[str]:
    """No orphan finding, no orphan component."""
    problems = []
    blueprint = BLUEPRINT.read_text(encoding="utf-8") if BLUEPRINT.is_file() else ""
    if not blueprint:
        problems.append("canonical blueprint missing; gate assignments cannot be validated")
        return problems

    gates_in_blueprint = set(re.findall(r"^# GATE (\d+)", blueprint, re.M))
    for f in findings.get("findings", []):
        gate = (f.get("remediation_gate") or "").replace("GATE ", "").strip()
        if gate and gate.isdigit() and gate not in gates_in_blueprint:
            problems.append(f"{f['id']}: assigned to GATE {gate}, which the blueprint does not define")

    for c in components.get("components", []):
        gate = (c.get("remediation_gate") or "").replace("GATE ", "").strip()
        if not gate:
            problems.append(f"{c.get('component')}: no remediation_gate")
        elif gate.isdigit() and gate not in gates_in_blueprint:
            problems.append(f"{c.get('component')}: assigned to GATE {gate}, which the blueprint does not define")
        if c.get("disposition") == "DELETE" and not c.get("rationale"):
            problems.append(f"{c.get('component')}: DELETE without a rationale is not a disposition")
    return problems


def check_citations_resolve(findings: dict) -> list[str]:
    """Every file:line citation must point at a file that exists.

    The register is executed over months. One launcher-icon commit already shifted
    AndroidManifest.xml by two lines, and the original write-up carried elided
    `android/.../Foo.kt` paths that no tool could resolve. A citation nobody can follow
    is not evidence.
    """
    problems = []
    cite = re.compile(r"^([^\s:]+\.(?:py|kt|kts|mjs|sh|json|yaml|yml|md|xml)):(\d+)")
    for f in findings.get("findings", []):
        for ev in f.get("repository_evidence", []):
            m = cite.match(str(ev).strip())
            if not m:
                continue
            path, line = m.group(1), int(m.group(2))
            target = ROOT / path
            if not target.is_file():
                problems.append(f"{f['id']}: cites {path}, which does not exist")
                continue
            try:
                total = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                continue
            if line > total:
                problems.append(f"{f['id']}: cites {path}:{line} but the file has {total} lines")
    return problems


def check_forbidden_routes() -> list[str]:
    problems = []
    for route, path in FORBIDDEN_PRODUCTION_ROUTES:
        if path.is_file() and route in path.read_text(encoding="utf-8"):
            problems.append(
                f"forbidden production route {route} present in {path.relative_to(ROOT)} "
                "(closes under blueprint Gate 1; remove before the gate review)"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on forbidden production routes that are scheduled for a later gate",
    )
    args = parser.parse_args()

    try:
        findings = _load(FINDINGS)
        components = _load(COMPONENTS)
    except Failure as exc:
        print(f"MATURITY GATE: cannot read ledgers — {exc}", file=sys.stderr)
        return 2

    blocking: list[str] = []
    blocking += check_findings_assigned(findings)
    blocking += check_component_dispositions(components)
    blocking += check_bidirectional_coverage(findings, components)
    blocking += check_citations_resolve(findings)

    scheduled = check_forbidden_routes()
    if args.strict:
        blocking += scheduled

    n_find = len(findings.get("findings", []))
    n_comp = len(components.get("components", []))
    closed = sum(1 for f in findings.get("findings", []) if f.get("current_status") == "CLOSED")
    terminal = sum(1 for c in components.get("components", []) if c.get("terminal_state"))

    print(f"findings:   {n_find} registered, {closed} closed")
    print(f"components: {n_comp} inventoried, {terminal} at a terminal state")

    if scheduled and not args.strict:
        print("\nscheduled (not blocking until their gate):")
        for s in scheduled:
            print(f"  - {s}")

    if blocking:
        print(f"\nMATURITY GATE FAILED — {len(blocking)} unbacked claim(s):", file=sys.stderr)
        for p in blocking:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("\nMATURITY GATE PASSED — every claim in the ledgers is backed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
