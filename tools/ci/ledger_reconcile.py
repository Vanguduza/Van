#!/usr/bin/env python3
"""Catch the component ledger claiming a thing is unreached when the source disagrees.

`evidence/van-system-audit/component_ledger.json` records, per component, a maturity class
— NEVER_CONSTRUCTED, NO_CALLER, TEST_ONLY, IMPLEMENTED_BUT_ISOLATED and so on — and a
disposition. It was written at Gate 0 and it is the register that says how much system is
left to build.

It stopped being true. The closure programme tracked `findings.json` and left this file
alone, so by the time the finding register reached zero the component ledger still listed
sixty-five entries as unfinished, and the twenty-odd checked by hand were all reached by
production code. A register nobody updates is worse than no register: it is a number people
quote.

The maturity gate cannot catch this, and should not be blamed for it. It checks that claims
are *backed* — a component asserting INTEGRATED_AND_EVIDENCED must name its producer,
consumer, caller, tests and runtime evidence. A component claiming to be unreached asserts
nothing, so there is nothing to back and nothing to check. Understating is invisible to a
gate built to catch overstating.

This is the other direction. For every component that declares itself unreached and names
the symbols to look for, it asks the source whether that is still true.

A component opts in by carrying `reachability_symbols`. Without it, the entry is reported
as unverifiable rather than assumed correct — a conceptual component like "Compose state
restoration" has no symbol to grep for, and pretending otherwise would put a confident
wrong answer where an honest gap belongs.

**It cannot see transitive deadness, and that is a real limit.** A reference counts as
production use if it is outside the component's own file and outside tests. It is not
outside *other dead code*: `MissionParsing` is referenced by `MissionRepository`, which
nothing constructs, and the first version of this tool read that as integration. Choosing
the symbols is therefore part of the claim, not a formality — pick the ones a live caller
would name. Where a whole cluster is dead together, one symbol's staleness verdict is worth
no more than the judgement behind it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "evidence" / "van-system-audit" / "component_ledger.json"

#: Where production code lives. A reference from anywhere else is not a production consumer.
PRODUCTION_ROOTS = ("backend/van_gateway", "android/app/src/main", "trading", "registries")

#: Searched in pure Python rather than by shelling out to ripgrep.
#:
#: The first version ran `rg`. It passed here and failed in CI with FileNotFoundError,
#: because the GitHub runner has no ripgrep — a checker built to run in the authority that
#: could not run in the authority. Depending on a binary that may not exist is the same
#: class of assumption as depending on a network the proxy refuses, and this programme has
#: now been caught by both.
SEARCHABLE_SUFFIXES = frozenset({".py", ".kt", ".kts", ".json", ".yaml", ".yml", ".xml"})

#: Maturity classes that assert nothing reaches this component. These are the claims this
#: tool can falsify; the rest (STUB, ABSENT, PARTIAL, SIMULATED) are claims about what the
#: code *does*, which no reference check can settle.
CLAIMS_UNREACHED = {
    "NEVER_CONSTRUCTED",
    "NEVER_CALLED",
    "NO_CALLER",
    "NO_CONSTRUCTOR",
    "NO_PRODUCER",
    "NEVER_REGISTERED",
    "TEST_ONLY",
    "UNUSED",
    "DEAD_CODE",
    "NOT_WIRED",
    "IMPLEMENTED_BUT_ISOLATED",
}


def is_production_file(
    path: str, own_path: str | None = None, excludes: list[str] | None = None
) -> bool:
    """Whether a reference from this file counts as production use.

    Pure, and separated from the search so both exclusions can be tested directly. They
    overlap on every file in this repository — `trading/tests/test_heat_governor.py` is
    caught by either — so a mutation removing one survives any test driven through the
    search, and the guard that cannot be falsified is the guard nobody knows is broken.

    The path rule covers `trading/tests/conftest.py`. The filename rule is narrower than it
    looks: any nested `test_*.py` already contains the substring `/test`, so the only case
    it alone catches is a module at the top of a search root. It is kept because a root is a
    configuration value and the day someone adds one whose top level holds a `test_*.py` is
    not the day to discover this.
    """
    if "/test" in path:
        return False
    if Path(path).name.startswith("test_"):
        return False
    if own_path is not None and path == own_path:
        return False
    return path not in set(excludes or [])


def _production_references(
    symbol: str, own_path: str | None, excludes: list[str] | None = None
) -> list[str]:
    """Files outside the component's own file that name this symbol in production code.

    `excludes` names files that are themselves unreached, so a reference from them proves
    nothing. Without it the checker reports a dead cluster as integrated because its members
    call each other — which is how `MissionRepository`, constructed by nothing, made the
    gateway reads it wraps look alive.
    """
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SEARCHABLE_SUFFIXES:
                continue
            relative = path.relative_to(ROOT).as_posix()
            if not is_production_file(relative, own_path, excludes):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pattern.search(text):
                hits.append(relative)
    return sorted(hits)


#: §40.5 — the Remote Browser programme ledger. It is a programme register, not a maturity
#: authority, and the whole point of reading it here is that a programme row must never be
#: able to claim more about a component than the component ledger itself records.
DEFAULT_MATRIX = ROOT / "docs" / "project-state" / "REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json"

RB_STATUSES = {
    "NOT_STARTED",
    "BUILT_UNWIRED",
    "WIRED_UNPROVEN",
    "LIVE_UNVERIFIED",
    "VERIFIED_UNCERTIFIED",
    "CERTIFIED",
    "BLOCKED",
    "DELIBERATELY_REMOVED",
}

LEDGER_EXPECTATIONS = {
    "NONE",
    "NON_TERMINAL",
    "INTEGRATED_AND_EVIDENCED",
    "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE",
    "DELIBERATELY_REMOVED_CANON_CORRECTED",
}

#: §40.4 — a row's status constrains what it may expect of the component ledger. The
#: interesting entries are the short ones: CERTIFIED may expect nothing weaker than full
#: integration, and DELIBERATELY_REMOVED may expect nothing but removal.
ALLOWED_EXPECTATION = {
    "NOT_STARTED": {"NONE", "NON_TERMINAL"},
    "BUILT_UNWIRED": {"NONE", "NON_TERMINAL"},
    "WIRED_UNPROVEN": {"NONE", "NON_TERMINAL"},
    "LIVE_UNVERIFIED": {"NONE", "NON_TERMINAL"},
    "VERIFIED_UNCERTIFIED": {"NONE", "NON_TERMINAL"},
    "CERTIFIED": {"INTEGRATED_AND_EVIDENCED"},
    "BLOCKED": {"NONE", "NON_TERMINAL", "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE"},
    "DELIBERATELY_REMOVED": {"DELIBERATELY_REMOVED_CANON_CORRECTED"},
}

#: The five fields a component must name before anything may call it integrated. Same list
#: the maturity gate enforces; repeated here because this is the other direction of travel —
#: a programme row pointing at a component that has not earned them.
INTEGRATION_EVIDENCE_FIELDS = ("producer", "consumer", "production_caller", "tests", "runtime_evidence")

#: The engineering ladder of §40.6, in order. A row cannot be verified without being live,
#: or live without being wired. Nothing here says a row must be anything; it says a row
#: cannot skip a rung and still describe itself coherently.
PROGRESS_LADDER = ("built", "wired", "reachable", "live", "verified")

#: What each status asserts about the booleans. A status and a set of booleans that
#: contradict each other is the same defect one level up from a component claiming
#: integration with no caller: two registers, one of them wrong, and nothing comparing them.
STATUS_REQUIRES = {
    "NOT_STARTED": {"built": False},
    "BUILT_UNWIRED": {"built": True, "wired": False},
    "WIRED_UNPROVEN": {"built": True, "wired": True, "verified": False},
    "LIVE_UNVERIFIED": {"live": True, "verified": False},
    "VERIFIED_UNCERTIFIED": {"verified": True, "certified": False},
    "CERTIFIED": {"certified": True},
    "BLOCKED": {"certified": False},
    "DELIBERATELY_REMOVED": {"certified": False},
}


def check_matrix(matrix_path: Path | None = None, ledger_path: Path | None = None) -> list[str]:
    """§40.5 — enforce the RB programme ledger against the component ledger.

    Returns one line per violation. An absent matrix is not a violation: the bridge exists
    for a programme that may not have started in a given checkout.
    """
    path = matrix_path or DEFAULT_MATRIX
    if not path.is_file():
        return []

    matrix = json.loads(path.read_text())
    rows = matrix["rows"] if isinstance(matrix, dict) else matrix

    ledger = json.loads((ledger_path or DEFAULT_LEDGER).read_text())
    components = ledger["components"] if isinstance(ledger, dict) else ledger
    by_n = {c.get("n"): c for c in components}

    problems: list[str] = []
    for r in rows:
        rid = r.get("id", "<unnamed>")
        status = r.get("status")
        if status not in RB_STATUSES:
            problems.append(f"{rid}: status {status!r} is not one of {sorted(RB_STATUSES)}")
            continue

        expectation = r.get("ledger_expectation", "NONE")
        if expectation not in LEDGER_EXPECTATIONS:
            problems.append(f"{rid}: ledger_expectation {expectation!r} is not a known value")
            continue
        if expectation not in ALLOWED_EXPECTATION[status]:
            problems.append(
                f"{rid}: status {status} may not expect {expectation}; allowed: "
                f"{sorted(ALLOWED_EXPECTATION[status])}"
            )

        for field, required in STATUS_REQUIRES[status].items():
            if bool(r.get(field, False)) is not required:
                problems.append(
                    f"{rid}: status {status} requires {field}={required}, row says "
                    f"{field}={bool(r.get(field, False))}"
                )

        reached_false = False
        for rung in PROGRESS_LADDER:
            if reached_false and r.get(rung):
                problems.append(
                    f"{rid}: claims {rung} while an earlier rung of the ladder is false. "
                    "A row cannot be verified without being live, or live without being wired."
                )
                break
            if not r.get(rung):
                reached_false = True
        if r.get("certified") and not all(r.get(rung) for rung in PROGRESS_LADDER):
            problems.append(f"{rid}: certified with an incomplete ladder {PROGRESS_LADDER}")

        # §40.5 — the column that says which rows a commit can still move.
        #
        # An empty list could mean either "nothing external is blocking this" or "nobody
        # filled this in", and those are the two answers a reader most needs to tell
        # apart: the first says the row is waiting on hardware, the second says the row
        # has never been thought about. Forty rows carried an empty list, including
        # several that were genuinely blocked, so the column could not be used for the
        # one question it exists to answer. A row with no external blocker now says so in
        # words, and the empty list becomes a violation rather than a silence.
        if status != "CERTIFIED" and not (r.get("external_gates") or []):
            problems.append(
                f"{rid}: status {status} names no external_gates. A row with nothing "
                "external says so in words; an empty list cannot be told from an "
                "unfilled one."
            )

        refs = r.get("component_refs") or []
        if refs and expectation == "NONE":
            problems.append(
                f"{rid}: names component_refs {refs} while expecting NONE of the ledger. "
                "A reference that expects nothing cannot be checked."
            )
        for n in refs:
            component = by_n.get(n)
            if component is None:
                problems.append(f"{rid}: component_ref {n} is not in the component ledger")
                continue
            terminal = component.get("terminal_state")
            name = component.get("component", f"n={n}")

            if expectation == "NON_TERMINAL" and terminal:
                problems.append(
                    f"{rid}: expects a non-terminal component but {name} is {terminal}"
                )
            elif expectation in {
                "INTEGRATED_AND_EVIDENCED",
                "EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE",
                "DELIBERATELY_REMOVED_CANON_CORRECTED",
            } and terminal != expectation:
                problems.append(
                    f"{rid}: expects {name} to be {expectation}, ledger says {terminal!r}"
                )

            if expectation == "INTEGRATED_AND_EVIDENCED":
                missing = [f for f in INTEGRATION_EVIDENCE_FIELDS if not component.get(f)]
                if missing:
                    problems.append(
                        f"{rid}: {name} is claimed integrated but names no {', '.join(missing)}"
                    )
    return problems


def reconcile(ledger_path: Path | None = None) -> tuple[list[str], list[str], list[str]]:
    ledger = json.loads((ledger_path or DEFAULT_LEDGER).read_text())
    components = ledger["components"] if isinstance(ledger, dict) else ledger

    contradicted: list[str] = []
    unverifiable: list[str] = []
    confirmed: list[str] = []

    for c in components:
        if c.get("terminal_state"):
            continue
        if c.get("maturity_class") not in CLAIMS_UNREACHED:
            continue

        name = c.get("component", "<unnamed>")
        symbols = c.get("reachability_symbols")
        if not symbols:
            unverifiable.append(f"{name} ({c.get('maturity_class')})")
            continue

        excludes = c.get("reachability_excludes") or []
        reached = {s: _production_references(s, c.get("path"), excludes) for s in symbols}
        alive = {s: f for s, f in reached.items() if f}
        if alive:
            detail = "; ".join(f"{s} <- {', '.join(f[:2])}" for s, f in alive.items())
            contradicted.append(f"{name}: claims {c.get('maturity_class')} but {detail}")
        else:
            confirmed.append(name)

    return contradicted, unverifiable, confirmed


def _matrix_summary(matrix_path: Path | None = None) -> str:
    """One line so a silently absent matrix cannot look like a passing one."""
    path = matrix_path or DEFAULT_MATRIX
    if not path.is_file():
        return "absent"
    rows = json.loads(path.read_text())["rows"]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.get("status", "?")] = counts.get(r.get("status", "?"), 0) + 1
    ordered = ", ".join(f"{n} {s}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    return f"{len(rows)} rows — {ordered}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true",
        help="also fail when an entry declares no reachability_symbols",
    )
    parser.add_argument(
        "--matrix", type=Path, default=None,
        help="a Remote Browser programme matrix to check instead of the repository's, for "
             "the self-test. §40.5's rules are only worth as much as a run that has been "
             "shown to refuse an invalid combination.",
    )
    parser.add_argument(
        "--ledger", type=Path, default=None,
        help="a ledger to check instead of the repository's. Used by the self-test, which "
             "feeds it a deliberately stale entry: a checker that has stopped checking "
             "passes the real ledger exactly as convincingly as one that works.",
    )
    args = parser.parse_args()

    contradicted, unverifiable, confirmed = reconcile(args.ledger)
    matrix_problems = check_matrix(args.matrix, args.ledger)

    print(f"{len(confirmed)} unreached claims confirmed against the source")
    for name in confirmed:
        print(f"  still unreached  {name}")

    if unverifiable:
        print(f"\n{len(unverifiable)} entries declare no reachability_symbols:")
        for name in unverifiable:
            print(f"  unverifiable     {name}")
        print("  These are judged by hand. Adding `reachability_symbols` brings one under CI.")

    if matrix_problems:
        print(f"\n{len(matrix_problems)} Remote Browser matrix violations (§40.5):")
        for line in matrix_problems:
            print(f"  RB  {line}")
        print(
            "\nA programme row may never claim more about a component than the component "
            "ledger records. Fix the row, or earn the component state it is asserting."
        )

    if contradicted:
        print(f"\n{len(contradicted)} STALE — the ledger says unreached, the source disagrees:")
        for line in contradicted:
            print(f"  STALE  {line}")
        print(
            "\nThe work was done and the ledger was not updated. Give each a terminal_state "
            "with its evidence, or correct the maturity_class."
        )
        return 1

    if matrix_problems:
        return 1

    if args.strict and unverifiable:
        return 1

    print(f"\nRemote Browser matrix: {_matrix_summary(args.matrix)}")
    print("\nLEDGER RECONCILED — no component understates its own integration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
