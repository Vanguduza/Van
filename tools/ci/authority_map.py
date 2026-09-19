#!/usr/bin/env python3
"""Authority map gate — which document owns which invariant, checked.

P3-DOC-005. Thirty-one canonical documents, around 13,700 lines, and nothing stating which
one is authoritative for a given rule. Two documents could each be locally correct and
jointly contradictory, and a reader had no way to know which to believe. The audit found
exactly that shape: a document describing a capability as BUILT surviving alongside one
describing the gap, because neither owned the claim.

A machine cannot detect a contradiction between two prose documents. What it can detect is
the condition that lets one persist — two documents claiming authority over the same
subject — and the weaker failure that makes the map decorative: an invariant whose owner,
implementation or test does not exist.

So this enforces, mechanically:

  1. Each subject is owned by exactly one document.
  2. Every owner document exists.
  3. Every implementation and test path exists.
  4. Every invariant names at least one implementation and at least one test. An invariant
     with no test is a claim, and this map does not hold claims.
  5. Every finding id referenced is in the register, and is closed. An invariant resting on
     an open finding is describing an intention.
  6. No two invariants share a statement, which is how one rule ends up owned twice under
     two names.
  7. An owner is one of the documents `owning_documents` declares. Without that, "a file
     under docs/" is the whole check and a derived document can acquire authority by being
     cited — which is how the implementation ledger came to certify workstreams against a
     blueprint it does not own.

Run:  python3 tools/ci/authority_map.py [--strict]

Exit 0 = the map is backed. Exit 1 = a claim is not. Exit 2 = the map is unreadable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "docs" / "project-state" / "AUTHORITY_MAP.yaml"
FINDINGS = ROOT / "evidence" / "van-system-audit" / "findings.json"

#: A subject is a dotted path. The first segment is the domain, which is how a reader finds
#: the owning document without reading all of them.
SUBJECT = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

REQUIRED_FIELDS = ("subject", "owner", "statement", "implemented_by", "tested_by")


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        print("authority_map: PyYAML is not installed", file=sys.stderr)
        raise SystemExit(2)
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - an unreadable map is exit 2, not a failure
        print(f"authority_map: {path} is unreadable: {exc}", file=sys.stderr)
        raise SystemExit(2)


def check() -> list[str]:
    data = _load_yaml(MAP)
    invariants = data.get("invariants")
    if not isinstance(invariants, list) or not invariants:
        return [f"{MAP.name} names no invariants"]

    findings = {
        f["id"]: f for f in json.loads(FINDINGS.read_text(encoding="utf-8"))["findings"]
    }

    permitted_owners = data.get("owning_documents")
    if not isinstance(permitted_owners, list) or not permitted_owners:
        return [f"{MAP.name} declares no owning_documents"]
    permitted = set(map(str, permitted_owners))

    problems: list[str] = []
    for document in sorted(permitted):
        if not (ROOT / document).is_file():
            problems.append(f"owning_documents names missing {document}")
    owners_by_subject: dict[str, set[str]] = defaultdict(set)
    statements: Counter[str] = Counter()

    for index, entry in enumerate(invariants):
        if not isinstance(entry, dict):
            problems.append(f"invariant #{index} is not a mapping")
            continue
        subject = str(entry.get("subject") or "")
        where = subject or f"invariant #{index}"

        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            problems.append(f"{where}: missing {', '.join(missing)}")
            continue

        if not SUBJECT.match(subject):
            problems.append(
                f"{where}: subject must be a dotted path like 'authority.action_class'"
            )

        owner = str(entry["owner"])
        owners_by_subject[subject].add(owner)
        if not (ROOT / owner).is_file():
            problems.append(f"{where}: owner {owner} does not exist")
        elif owner not in permitted:
            problems.append(
                f"{where}: {owner} is not in owning_documents, so it does not decide "
                "anything — a document acquiring authority by being cited is the defect "
                "this map exists to prevent"
            )

        statement = " ".join(str(entry["statement"]).split())
        statements[statement] += 1
        if not statement.endswith("."):
            problems.append(f"{where}: statement should be a sentence ending in a period")

        for field in ("implemented_by", "tested_by"):
            paths = entry.get(field) or []
            if not isinstance(paths, list) or not paths:
                problems.append(f"{where}: {field} must name at least one path")
                continue
            for relative in paths:
                if not (ROOT / str(relative)).exists():
                    problems.append(f"{where}: {field} names missing {relative}")

        for finding_id in entry.get("findings") or []:
            finding = findings.get(str(finding_id))
            if finding is None:
                problems.append(f"{where}: finding {finding_id} is not in the register")
            elif finding.get("current_status") != "CLOSED":
                problems.append(
                    f"{where}: rests on {finding_id}, which is still open — an invariant "
                    "resting on an open finding is describing an intention"
                )

    for subject, owners in sorted(owners_by_subject.items()):
        if len(owners) > 1:
            problems.append(
                f"{subject}: owned by {len(owners)} documents ({', '.join(sorted(owners))}); "
                "exactly one document decides each subject"
            )

    for statement, count in statements.items():
        if count > 1:
            problems.append(
                f"the same statement appears {count} times: {statement[:90]}... — one rule "
                "owned twice under two names is the condition this map exists to prevent"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true",
        help="also report every subject domain that owns only one invariant",
    )
    args = parser.parse_args()

    problems = check()
    data = _load_yaml(MAP)
    invariants = data.get("invariants") or []

    domains = Counter(str(e.get("subject", "")).split(".")[0] for e in invariants)
    owners = Counter(str(e.get("owner", "")) for e in invariants)
    print(f"invariants: {len(invariants)} across {len(domains)} domains, "
          f"{len(owners)} owning documents")
    for domain, count in sorted(domains.items()):
        print(f"  {domain:<16} {count}")

    if args.strict:
        for domain, count in sorted(domains.items()):
            if count == 1:
                print(f"  note: {domain} owns a single invariant")

    if problems:
        print(f"\nAUTHORITY MAP FAILED — {len(problems)} unbacked claim(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nAUTHORITY MAP PASSED — every invariant is owned once, implemented and tested.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
