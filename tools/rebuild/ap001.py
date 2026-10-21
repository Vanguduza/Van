#!/usr/bin/env python3
"""AP-001 omission verifier: plan units with no executable acceptance, judged against the
admitted Rev1.18 package and the proposed additive patch.

The package's own verifiers (verify_review_contracts.py 79/79, verify_whole_product.py 26/26)
accept a plan in which five gate units list zero acceptance identities. This tool detects
that class of omission and checks that the AP-001 patch closes it without loss.

  python3 tools/rebuild/ap001.py check      current package (expected: findings) and patched view
  python3 tools/rebuild/ap001.py selftest   induce each failure class and require detection

The package is read, never written. Exit 0: patched view clean and preserving; 1 otherwise.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "docs/review-inputs/van-rev115/package"
PATCH = ROOT / "docs/rebuild/rev118/pre002/AP-001/AP-001_PATCH.json"
KINDS = ("POS", "NEG", "REC")
# Units whose exit is gate evidence must cover positive, negative and recovery behaviour.
GATE_PREFIXES = ("BQ-", "QA-", "REL-", "BG-", "PRE-")


def load(p: Path):
    return json.loads(p.read_text())


def registries():
    return (load(PKG / "plan/DEVELOPMENT_PLAN.json"),
            load(PKG / "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json")["tests"])


def kind_of(test_id: str, contract: dict | None, overrides: dict) -> str | None:
    if test_id in overrides:
        return overrides[test_id]
    if contract and contract.get("kind") in KINDS:
        return contract["kind"]
    tail = test_id.rsplit("-", 1)[-1]
    return {"POS": "POS", "P": "POS", "NEG": "NEG", "N": "NEG", "REC": "REC", "INT": "POS",
            "SEC": "NEG"}.get(tail)


def omissions(plan: dict, tests: list, overrides: dict, scope: set[str] | None = None) -> list[str]:
    """Units with no acceptance at all, references to unknown identities, and gate units in
    `scope` lacking a POS, NEG or REC identity."""
    by_id = {t["id"]: t for t in tests}
    out = []
    for u in plan["units"]:
        ids = u.get("acceptance_test_ids") or []
        if not ids:
            out.append(f"UNIT_WITHOUT_ACCEPTANCE:{u['id']}")
            continue
        for t in ids:
            if t not in by_id:
                out.append(f"UNKNOWN_ACCEPTANCE_ID:{u['id']}:{t}")
        if scope is not None and u["id"] in scope and u["id"].startswith(GATE_PREFIXES):
            have = {kind_of(t, by_id.get(t), overrides) for t in ids}
            for k in KINDS:
                if k not in have:
                    out.append(f"GATE_UNIT_MISSING_{k}:{u['id']}")
    return sorted(out)


def apply(plan: dict, tests: list, patch: dict) -> tuple[dict, list, list[str]]:
    p, t = copy.deepcopy(plan), copy.deepcopy(tests)
    problems = []
    units = {u["id"]: u for u in p["units"]}
    existing = {x["id"] for x in t}
    for c in patch["new_acceptance_contracts"]:
        if c["id"] in existing:
            problems.append(f"NEW_ID_COLLIDES:{c['id']}")
        if c["unit"] not in units:
            problems.append(f"NEW_ID_UNKNOWN_UNIT:{c['id']}:{c['unit']}")
        if c.get("execution_state") != "NOT_RUN":
            problems.append(f"NEW_ID_CLAIMS_RESULT:{c['id']}")
        for field in ("expectation", "environment", "kind"):
            if not c.get(field):
                problems.append(f"NEW_ID_MISSING_{field.upper()}:{c['id']}")
        existing.add(c["id"])
        t.append(c)
    for uid, ids in patch["unit_acceptance_additions"].items():
        if uid not in units:
            problems.append(f"PATCH_UNKNOWN_UNIT:{uid}")
            continue
        cur = units[uid].setdefault("acceptance_test_ids", [])
        for i in ids:
            if i not in cur:
                cur.append(i)
    return p, t, problems


def preservation(before_plan, before_tests, after_plan, after_tests) -> list[str]:
    out = []
    a_ids = {t["id"]: t for t in after_tests}
    for t in before_tests:
        if t["id"] not in a_ids:
            out.append(f"TEST_REMOVED:{t['id']}")
        elif a_ids[t["id"]] != t:
            out.append(f"TEST_REWRITTEN:{t['id']}")
    au = {u["id"]: u for u in after_plan["units"]}
    for u in before_plan["units"]:
        if u["id"] not in au:
            out.append(f"UNIT_REMOVED:{u['id']}")
            continue
        b, a = u.get("acceptance_test_ids") or [], au[u["id"]].get("acceptance_test_ids") or []
        if a[:len(b)] != b:
            out.append(f"UNIT_ACCEPTANCE_NOT_PREFIX_PRESERVED:{u['id']}")
        for k in ("dependencies", "exit_contract", "title"):
            if u.get(k) != au[u["id"]].get(k):
                out.append(f"UNIT_FIELD_CHANGED:{u['id']}:{k}")
    if after_plan.get("requirement_ownership") != before_plan.get("requirement_ownership"):
        out.append("REQUIREMENT_OWNERSHIP_CHANGED_BY_TEST_PATCH")
    return out


def evaluate(plan, tests, patch) -> dict:
    scope = set(patch["unit_acceptance_additions"])
    overrides = patch.get("co_listed_kind_overrides", {})
    before = omissions(plan, tests, overrides)
    p2, t2, problems = apply(plan, tests, patch)
    after = omissions(p2, t2, overrides, scope)
    pres = preservation(plan, tests, p2, t2)
    return {"current_package_findings": before, "patched_findings": after, "patch_problems": problems,
            "preservation_findings": pres, "counts": {"before": len(tests), "after": len(t2)},
            "patched_clean": not (after or problems or pres)}


def cmd_check() -> int:
    plan, tests = registries()
    r = evaluate(plan, tests, load(PATCH))
    print(json.dumps(r, indent=1))
    return 0 if r["patched_clean"] else 1


def cmd_selftest() -> int:
    plan, tests = registries()
    patch = load(PATCH)
    results = []

    def case(name, mutate, expect):
        p, t, pa = copy.deepcopy(plan), copy.deepcopy(tests), copy.deepcopy(patch)
        mutate(p, t, pa)
        r = evaluate(p, t, pa)
        ok = expect(r)
        results.append({"id": name, "passed": ok,
                        "evidence": (r["patched_findings"] + r["patch_problems"] + r["preservation_findings"])[:3]})

    case("POSITIVE_CONTROL_PATCH_CLOSES_OMISSIONS", lambda p, t, pa: None, lambda r: r["patched_clean"])
    case("CURRENT_PACKAGE_OMISSION_DETECTED", lambda p, t, pa: None,
         lambda r: sum(f.startswith("UNIT_WITHOUT_ACCEPTANCE") for f in r["current_package_findings"]) == 5)
    case("UNIT_LEFT_EMPTY", lambda p, t, pa: pa["unit_acceptance_additions"].__setitem__("QA-002", []) or
         pa.__setitem__("new_acceptance_contracts", [c for c in pa["new_acceptance_contracts"] if c["unit"] != "QA-002"]),
         lambda r: "UNIT_WITHOUT_ACCEPTANCE:QA-002" in r["patched_findings"])
    case("GATE_UNIT_WITHOUT_NEGATIVE",
         lambda p, t, pa: pa["unit_acceptance_additions"].__setitem__(
             "REL-002", [i for i in pa["unit_acceptance_additions"]["REL-002"] if not i.endswith("-NEG")]),
         lambda r: "GATE_UNIT_MISSING_NEG:REL-002" in r["patched_findings"])
    case("REFERENCE_TO_NONEXISTENT_IDENTITY",
         lambda p, t, pa: pa["unit_acceptance_additions"]["BQ-003"].append("T-BE-999-INT"),
         lambda r: "UNKNOWN_ACCEPTANCE_ID:BQ-003:T-BE-999-INT" in r["patched_findings"])
    # Loss is judged against the untouched registry, so these mutate the patched result.
    p2, t2, _ = apply(plan, tests, patch)
    t2 = [x for x in t2 if x["id"] != "T-NX-071"]
    results.append({"id": "PATCH_THAT_DELETES_AN_IDENTITY",
                    "passed": "TEST_REMOVED:T-NX-071" in preservation(plan, tests, p2, t2)})
    p3, t3, _ = apply(plan, tests, patch)
    next(u for u in p3["units"] if u["id"] == "BQ-001")["acceptance_test_ids"].pop(0)
    results.append({"id": "PATCH_THAT_REORDERS_OR_DROPS_EXISTING_UNIT_ACCEPTANCE",
                    "passed": "UNIT_ACCEPTANCE_NOT_PREFIX_PRESERVED:BQ-001" in preservation(plan, tests, p3, t3)})
    case("NEW_IDENTITY_CLAIMING_A_RESULT",
         lambda p, t, pa: pa["new_acceptance_contracts"][0].__setitem__("execution_state", "PASSED"),
         lambda r: any(x.startswith("NEW_ID_CLAIMS_RESULT") for x in r["patch_problems"]))
    case("NEW_IDENTITY_COLLIDING_WITH_EXISTING",
         lambda p, t, pa: pa["new_acceptance_contracts"][0].__setitem__("id", "T-NX-054"),
         lambda r: any(x.startswith("NEW_ID_COLLIDES") for x in r["patch_problems"]))
    passed = sum(r["passed"] for r in results)
    print(json.dumps({"passed": passed, "total": len(results), "cases": results}, indent=1))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("check", "selftest"):
        print(__doc__)
        sys.exit(2)
    sys.exit(cmd_check() if sys.argv[1] == "check" else cmd_selftest())
