#!/usr/bin/env python3
"""Rev 1.5 §43 — check the Production Acceptance register against the blueprint.

RB-058. §43 says Remote Browser Rev 1.5 is production complete only when one hundred and
four things are true, and then lists them. A list of a hundred and four requirements is
also a hundred and four places for a claim to sit unchallenged, so the register is data
and this is the check.

Four rules, and the last one is the one that matters:

* **every requirement §43 names is present.** Parsed out of the blueprint, not copied, so
  a requirement cannot go missing because somebody found it inconvenient — and a
  requirement added to the authority makes this fail until it is classified;
* **every status is one of the four**, and a REPOSITORY_PROVEN row cites evidence that
  exists on disk — a Python citation naming a test must name one that can actually be run;
* **every other status names what is missing**, in words rather than as a flag;
* **the verdict is recomputed rather than read.** `PRODUCTION_ACCEPTED` requires every
  requirement to be proven or not applicable. A stored verdict that disagrees with the
  rows is the failure this exists to prevent: a ledger that says accepted while its own
  rows say otherwise.

The last rule is why this is a program and not a document. A human writes the verdict at
the top of a ledger once and it is never re-derived; a check that recomputes it cannot be
out of date.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTER = ROOT / "evidence" / "van-system-audit" / "production_acceptance.json"
BLUEPRINT = ROOT / "docs" / "VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md"

STATUSES = {
    "REPOSITORY_PROVEN",
    "BLOCKED_EXTERNAL",
    "OWNER_DEPLOYMENT_DECISION",
    "NOT_APPLICABLE_WITH_REASON",
}

#: The two statuses that let a requirement count as done.
SETTLED = {"REPOSITORY_PROVEN", "NOT_APPLICABLE_WITH_REASON"}

ACCEPTED = "PRODUCTION_ACCEPTED"
PENDING = "REPOSITORY_COMPLETE_PENDING_EXTERNAL"


def blueprint_requirements(blueprint: Path | None = None) -> list[str]:
    """§43's list, read from the authority.

    Read rather than copied on purpose. A copy drifts, and the direction it drifts is
    always the same: the copy is the one that gets shorter.
    """
    text = (blueprint or BLUEPRINT).read_text(encoding="utf-8")
    start = text.index("# 43. DEFINITION OF PRODUCTION COMPLETE")
    tail = text[start:]
    end = re.search(r"\n# \d+\. ", tail[10:])
    section = tail[: 10 + end.start()] if end else tail

    items, current = [], None
    for line in section.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
        elif line.startswith("- ") and current:
            items.append(line[2:].strip().rstrip(";").rstrip("."))
    return items


def _resolves_in_python(path: Path, chain: tuple[str, ...]) -> bool:
    """Whether `Class::test` is actually nested that way, by reading the module's AST."""
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


def check(register_path: Path | None = None, blueprint: Path | None = None) -> list[str]:
    path = register_path or DEFAULT_REGISTER
    if not path.is_file():
        return [f"{path} does not exist"]

    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("requirements", [])
    problems: list[str] = []

    declared = blueprint_requirements(blueprint)
    registered = [r.get("requirement") for r in rows]
    for item in declared:
        if item not in registered:
            problems.append(f"§43 requires {item!r} and the register does not carry it")
    for item in registered:
        if item not in declared:
            problems.append(f"the register carries {item!r}, which §43 does not require")

    for row in rows:
        label = f"{row.get('n')} {row.get('requirement', '<unnamed>')!r}"
        status = row.get("status")
        if status not in STATUSES:
            problems.append(f"{label}: status {status!r} is not one of {sorted(STATUSES)}")
            continue

        if status == "REPOSITORY_PROVEN":
            evidence = row.get("evidence") or []
            if not evidence:
                problems.append(f"{label}: REPOSITORY_PROVEN with nothing cited")
            for citation in evidence:
                file_part, _, name_part = citation.partition("::")
                target = ROOT / file_part
                if not target.is_file():
                    problems.append(f"{label}: evidence {file_part} does not exist")
                    continue
                if name_part and target.suffix == ".py":
                    chain = tuple(p for p in name_part.split("::") if p)
                    if not _resolves_in_python(target, chain):
                        problems.append(
                            f"{label}: evidence {citation} is not a runnable pytest node id"
                        )
        elif not row.get("blocked_by"):
            problems.append(
                f"{label}: {status} must name what is missing, not merely that "
                "something is"
            )

    # The rule that makes this a check rather than a record.
    expected = ACCEPTED if all(r.get("status") in SETTLED for r in rows) else PENDING
    if doc.get("verdict") != expected:
        problems.append(
            f"the stored verdict is {doc.get('verdict')!r} and the rows say {expected!r}"
        )
    blocked = sum(1 for r in rows if r.get("status") not in SETTLED)
    if doc.get("blocked_count") != blocked:
        problems.append(
            f"blocked_count says {doc.get('blocked_count')} and the rows say {blocked}"
        )

    return problems


def summarise(register_path: Path | None = None) -> str:
    path = register_path or DEFAULT_REGISTER
    if not path.is_file():
        return "absent"
    doc = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for row in doc.get("requirements", []):
        counts[row.get("status", "?")] = counts.get(row.get("status", "?"), 0) + 1
    detail = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    return f"{len(doc.get('requirements', []))} requirements — {detail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=None)
    parser.add_argument("--blueprint", type=Path, default=None)
    args = parser.parse_args(argv)

    problems = check(args.register, args.blueprint)
    print(f"\nProduction acceptance (§43): {summarise(args.register)}")
    if problems:
        print(f"\n{len(problems)} problems:")
        for line in problems:
            print(f"  - {line}")
        print("\nPRODUCTION ACCEPTANCE REGISTER FAILED")
        return 1

    doc = json.loads((args.register or DEFAULT_REGISTER).read_text(encoding="utf-8"))
    print(f"Verdict: {doc['verdict']} ({doc['blocked_count']} not repository-proven)")
    print("\nPRODUCTION ACCEPTANCE CHECKED — the verdict follows from the rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
