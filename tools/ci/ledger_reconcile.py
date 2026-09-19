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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "evidence" / "van-system-audit" / "component_ledger.json"

#: Where production code lives. A reference from anywhere else is not a production consumer.
PRODUCTION_ROOTS = ("backend/van_gateway", "android/app/src/main", "trading", "registries")

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
    result = subprocess.run(
        ["rg", "-l", "--no-messages", rf"\b{re.escape(symbol)}\b", *PRODUCTION_ROOTS],
        cwd=ROOT, capture_output=True, text=True,
    )
    files = [f for f in result.stdout.splitlines() if f]
    return [f for f in files if is_production_file(f, own_path, excludes)]


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true",
        help="also fail when an entry declares no reachability_symbols",
    )
    parser.add_argument(
        "--ledger", type=Path, default=None,
        help="a ledger to check instead of the repository's. Used by the self-test, which "
             "feeds it a deliberately stale entry: a checker that has stopped checking "
             "passes the real ledger exactly as convincingly as one that works.",
    )
    args = parser.parse_args()

    contradicted, unverifiable, confirmed = reconcile(args.ledger)

    print(f"{len(confirmed)} unreached claims confirmed against the source")
    for name in confirmed:
        print(f"  still unreached  {name}")

    if unverifiable:
        print(f"\n{len(unverifiable)} entries declare no reachability_symbols:")
        for name in unverifiable:
            print(f"  unverifiable     {name}")
        print("  These are judged by hand. Adding `reachability_symbols` brings one under CI.")

    if contradicted:
        print(f"\n{len(contradicted)} STALE — the ledger says unreached, the source disagrees:")
        for line in contradicted:
            print(f"  STALE  {line}")
        print(
            "\nThe work was done and the ledger was not updated. Give each a terminal_state "
            "with its evidence, or correct the maturity_class."
        )
        return 1

    if args.strict and unverifiable:
        return 1

    print("\nLEDGER RECONCILED — no component understates its own integration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
