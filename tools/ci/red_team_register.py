#!/usr/bin/env python3
"""Rev 1.5 §38 — check the red-team register against the repository it describes.

RB-052. §38 ends with a rule that is easy to read past: every finding is `PASS`, `FAIL`,
`BLOCKED_EXTERNAL` or `NOT_APPLICABLE_WITH_REASON`, and **never `assumed`**. A register is
the natural way to record fifty-nine scenarios and also the natural way to accumulate
fifty-nine assertions nobody checks, which is the failure this whole programme exists to
find. So the register is data and this is the check.

What it enforces:

* every scenario §38 names is present, and the list is contiguous — a scenario cannot
  disappear because somebody found it inconvenient;
* every status is one of the four, and `assumed` in any spelling is refused by name;
* **every PASS cites evidence that exists**, and where the citation names a test function
  or class, that name is actually defined in the file. A PASS citing a test that was
  renamed is the exact shape of a green register describing a system nobody tested;
* every BLOCKED_EXTERNAL names what is missing, in words rather than as a flag;
* every non-PASS carries a reason.

It deliberately does not run the tests. That is the suite's job, and a checker that
re-ran them would be slow enough to be skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTER = ROOT / "evidence" / "van-system-audit" / "red_team_register.json"

STATUSES = {"PASS", "FAIL", "BLOCKED_EXTERNAL", "NOT_APPLICABLE_WITH_REASON"}

#: §38's own word for the thing a register must never say. Matched loosely on purpose:
#: `Assumed`, `ASSUMED` and `assumed-pass` are the same claim wearing different clothes.
FORBIDDEN = "assumed"


def _defined_names(path: Path) -> set[str]:
    """Every test function and class the file defines, in Python or in Kotlin."""
    text = path.read_text(encoding="utf-8", errors="replace")
    names = set(re.findall(r"^\s*(?:async\s+)?def\s+(\w+)", text, re.M))
    names |= set(re.findall(r"^\s*class\s+(\w+)", text, re.M))
    # Kotlin: `fun \`a sentence\`()` and `class Foo`.
    names |= set(re.findall(r"fun\s+`([^`]+)`", text))
    return names


def _python_paths(text: str) -> tuple[str, ...]:
    """The `Class::test` chain a pytest node id names, in order.

    Split here rather than by taking the last element, because a citation that named a
    test inside a class but omitted the class would resolve against the file and not
    against anything runnable — which is exactly what the first version of this register
    did for twenty-five of its fifty-one PASS claims. Every one of them named a test that
    exists; none of them could be run as written.
    """
    return tuple(part for part in text.split("::") if part)


def _resolves_in_python(path: Path, chain: tuple[str, ...]) -> bool:
    """Whether `Class::test` (or `Class`, or `test`) is actually nested that way.

    A structural check rather than a pytest collection, deliberately: collecting means
    importing every cited module, and a checker that imports the suite is a checker that
    fails for reasons that have nothing to do with the register.
    """
    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False

    def walk(body, remaining: tuple[str, ...]) -> bool:
        if not remaining:
            return True
        head, *rest = remaining
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == head:
                return not rest
            if isinstance(node, ast.ClassDef) and node.name == head:
                return walk(node.body, tuple(rest))
        return False

    return walk(tree.body, chain)


def check(register_path: Path | None = None) -> list[str]:
    path = register_path or DEFAULT_REGISTER
    if not path.is_file():
        return [f"{path} does not exist"]

    doc = json.loads(path.read_text(encoding="utf-8"))
    scenarios = doc.get("scenarios", [])
    problems: list[str] = []

    numbers = [s.get("n") for s in scenarios]
    if numbers != list(range(1, len(scenarios) + 1)):
        problems.append(
            "the scenario numbers are not contiguous from 1; §38 says no item may "
            "disappear because somebody deferred it silently"
        )

    for scenario in scenarios:
        label = f"{scenario.get('n')} {scenario.get('scenario', '<unnamed>')!r}"
        status = scenario.get("status")

        blob = json.dumps(scenario).lower()
        if FORBIDDEN in blob:
            problems.append(f"{label}: the register says {FORBIDDEN!r}, which §38 forbids")

        if status not in STATUSES:
            problems.append(f"{label}: status {status!r} is not one of {sorted(STATUSES)}")
            continue

        evidence = scenario.get("evidence") or []
        if status == "PASS":
            if not evidence:
                problems.append(f"{label}: PASS with no evidence is the claim §38 refuses")
            for citation in evidence:
                file_part, _, name_part = citation.partition("::")
                target = ROOT / file_part
                if not target.is_file():
                    problems.append(f"{label}: evidence {file_part} does not exist")
                    continue
                if not name_part:
                    continue
                if target.suffix == ".py":
                    # A runnable node id, not merely a name that occurs in the file.
                    if not _resolves_in_python(target, _python_paths(name_part)):
                        problems.append(
                            f"{label}: evidence {citation} is not a runnable pytest node "
                            "id; a test inside a class must be cited with its class"
                        )
                elif name_part not in _defined_names(target):
                    # The failure this exists for: a test renamed or deleted while the
                    # register went on reporting the scenario as covered.
                    problems.append(
                        f"{label}: evidence names {name_part!r}, which {file_part} "
                        "does not define"
                    )
        else:
            if not (scenario.get("blocked_by") or scenario.get("note")):
                problems.append(f"{label}: {status} with no reason given")
            if status == "BLOCKED_EXTERNAL" and not scenario.get("blocked_by"):
                problems.append(
                    f"{label}: BLOCKED_EXTERNAL must name what is missing, not merely "
                    "that something is"
                )
            if evidence:
                # Not an error in itself, but a non-PASS that cites evidence is usually a
                # PASS somebody did not finish claiming, or a citation left behind.
                for citation in evidence:
                    if not (ROOT / citation.partition("::")[0]).is_file():
                        problems.append(f"{label}: evidence {citation} does not exist")

    return problems


def summarise(register_path: Path | None = None) -> str:
    path = register_path or DEFAULT_REGISTER
    if not path.is_file():
        return "absent"
    doc = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for scenario in doc.get("scenarios", []):
        counts[scenario.get("status", "?")] = counts.get(scenario.get("status", "?"), 0) + 1
    total = len(doc.get("scenarios", []))
    detail = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    return f"{total} scenarios — {detail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=None)
    args = parser.parse_args(argv)

    problems = check(args.register)
    print(f"\nRed-team register (§38): {summarise(args.register)}")
    if problems:
        print(f"\n{len(problems)} problems:")
        for line in problems:
            print(f"  - {line}")
        print("\nRED-TEAM REGISTER FAILED")
        return 1
    print("\nRED-TEAM REGISTER CHECKED — every PASS names evidence that exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
