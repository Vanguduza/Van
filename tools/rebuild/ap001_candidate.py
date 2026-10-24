#!/usr/bin/env python3
"""Verify the complete AP-001 candidate package against the admitted package and print its digest.

  python3 tools/rebuild/ap001_candidate.py <candidate-dir> [--write]

The candidate is produced by tools/rebuild/ap001_dryrun.py on a copy of the admitted package. This
checks every property admission depends on, so a reviewer can re-derive the result:
  files       the changed-file set is exactly the expected set; nothing else moved
  additive    every admitted test, requirement, action, truth atom, surface and context is unchanged;
              the only new tests are the patch's 14; no plan unit lost an acceptance identity or
              changed any field other than its acceptance list; markdown only gained lines
  counts      authority, scope counts, effective registry and plan agree on 1,624 / 324 / 131
  manifest    MANIFEST.json lists every file with its true bytes and sha256
  lock        the scope lock is still unsigned and its file hashes are current
  pointers    every file CANONICAL_AUTHORITY names exists
  gates       the five gate units now have acceptance identities
  lineage     Rev1.17 history sentences are byte-identical in the active documents
It writes CANDIDATE_VERIFICATION.json (with --write) and refuses to run on the admitted package.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMITTED = (ROOT / "docs/review-inputs/van-rev115/package").resolve()
PATCH = ROOT / "docs/rebuild/rev118/pre002/AP-001/AP-001_PATCH.json"
OUT = ROOT / "docs/rebuild/rev118/pre002/AP-001/CANDIDATE_VERIFICATION.json"
GATES = ["BQ-003", "BQ-004", "QA-002", "QA-003", "REL-002"]
EXPECTED_CHANGED = {
    "CANONICAL_AUTHORITY.json", "MANIFEST.json", "amendments/AP-001.json",
    "VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_18_20261021.md", "VATI_SELF_OPTIMIZING_EXECUTION_AND_CRYPTO_BLUEPRINT_REV5_20261018.md",
    "consolidation/GENERATED_SCOPE_COUNTS.json", "contracts/whole_product/ACCEPTANCE_REFINEMENTS.json",
    "plan/DEVELOPMENT_PLAN.json", "plan/PLAN_INPUT_PROVENANCE.json", "plan/PROPOSED_SCOPE_LOCK.json",
    "plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_18.md", "plan/compile_rev118.py",
    "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json", "verification/TEST_CONTRACTS.json",
    "verification/verify_experience_learning.py", "verification/verify_model_hardening.py",
    "verification/verify_review_contracts.py", "verification/verify_whole_product.py",
}
UNCHANGED_REGISTRIES = [
    "traceability/REQUIREMENTS_AND_DU_MAPPING.json", "traceability/LEGACY_349_ACTIONS.json", "traceability/PRODUCT_TRUTH.json",
    "design/ALL_SURFACE_CONTRACTS.json", "contracts/whole_product/FEATURE_CONTEXT_BINDINGS.json",
    "contracts/whole_product/ACTION_CONTRACTS.json", "contracts/whole_product/DOMAIN_SCENARIOS.json",
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def files(root: Path) -> dict[str, str]:
    return {q.relative_to(root).as_posix(): sha(q) for q in sorted(root.rglob("*"))
            if q.is_file() and "__pycache__" not in q.parts and ".git" not in q.parts}


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__); return 2
    cand = Path(argv[1]).resolve()
    if cand == ADMITTED or ADMITTED in cand.parents:
        print("refusing to treat the admitted package as a candidate"); return 2
    patch = json.loads(PATCH.read_text())
    new_ids = sorted(c["id"] for c in patch["new_acceptance_contracts"])
    a_files, c_files = files(ADMITTED), files(cand)
    checks: dict[str, dict] = {}

    def check(name: str, ok: bool, detail=None):
        checks[name] = {"passed": bool(ok), "detail": detail}

    changed = sorted(p for p in set(a_files) | set(c_files) if a_files.get(p) != c_files.get(p))
    check("files.exact_changed_set", set(changed) == EXPECTED_CHANGED,
          {"unexpected": sorted(set(changed) - EXPECTED_CHANGED), "missing": sorted(EXPECTED_CHANGED - set(changed))})
    check("files.none_removed", not (set(a_files) - set(c_files)), sorted(set(a_files) - set(c_files)))

    for reg in UNCHANGED_REGISTRIES:
        check(f"additive.unchanged:{reg}", a_files.get(reg) == c_files.get(reg))

    rd = lambda root, rel: json.loads((root / rel).read_text())
    owner_adds = patch["owner_additions"]
    for rel in ("verification/TEST_CONTRACTS.json", "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json"):
        a_t = {t["id"]: t for t in rd(ADMITTED, rel)["tests"]}
        c_t = {t["id"]: t for t in rd(cand, rel)["tests"]}
        altered, widened = [], {}
        for i, at in a_t.items():
            ct = c_t.get(i)
            if ct is None:
                altered.append(i); continue
            strip = lambda x: {k: v for k, v in x.items() if k != "additional_units"}
            if canon(strip(at)) != canon(strip(ct)):
                altered.append(i); continue
            before, after = set(at.get("additional_units", [])), set(ct.get("additional_units", []))
            if not before <= after or (after - before) - set(owner_adds.get(i, [])):
                altered.append(i)
            elif after - before:
                widened[i] = sorted(after - before)
        check(f"additive.tests_preserved:{rel}", not altered, altered[:10])
        check(f"additive.only_declared_owner_additions:{rel}",
              all(set(v) <= set(owner_adds.get(i, [])) for i, v in widened.items()),
              {"identities_gaining_owners": len(widened)})
        check(f"additive.only_patch_tests_added:{rel}", sorted(set(c_t) - set(a_t)) == new_ids, sorted(set(c_t) - set(a_t)))

    a_units = {u["id"]: u for u in rd(ADMITTED, "plan/DEVELOPMENT_PLAN.json")["units"]}
    c_plan = rd(cand, "plan/DEVELOPMENT_PLAN.json")
    c_units = {u["id"]: u for u in c_plan["units"]}
    lost = {u: sorted(set(a_units[u].get("acceptance_test_ids", [])) - set(c_units[u].get("acceptance_test_ids", []))) for u in a_units}
    lost = {u: v for u, v in lost.items() if v}
    other = sorted(u for u in a_units if canon({k: v for k, v in a_units[u].items() if k != "acceptance_test_ids"})
                   != canon({k: v for k, v in c_units[u].items() if k != "acceptance_test_ids"}))
    check("additive.no_unit_lost_acceptance", not lost, lost)
    check("additive.units_otherwise_unchanged", set(a_units) == set(c_units) and not other, other)
    a_ext = rd(ADMITTED, "plan/DEVELOPMENT_PLAN.json")["acceptance_owner_extensions"]
    shrunk = sorted(k for k, v in a_ext.items() if not set(v) <= set(c_plan["acceptance_owner_extensions"].get(k, [])))
    check("additive.owner_extensions_superset", not shrunk, shrunk)

    md_insert_only = {}
    for rel in sorted(p for p in changed if p.endswith(".md")):
        a_lines = (ADMITTED / rel).read_text().splitlines()
        c_lines = (cand / rel).read_text().splitlines()
        ops = {op for op, *_ in difflib.SequenceMatcher(None, a_lines, c_lines, autojunk=False).get_opcodes() if op != "equal"}
        md_insert_only[rel] = sorted(ops)
    rendered = "plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_18.md"
    check("additive.blueprints_insert_only",
          all(v == ["insert"] for k, v in md_insert_only.items() if k != rendered), md_insert_only)
    check("lineage.rev117_sentence_kept",
          all("324 requirements and 1,610 planned application tests" in (cand / r).read_text()
              for r in ("VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_18_20261021.md", "VATI_SELF_OPTIMIZING_EXECUTION_AND_CRYPTO_BLUEPRINT_REV5_20261018.md")))
    check("lineage.rev117_master_untouched",
          a_files["VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md"] == c_files["VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_17_20261018.md"])

    auth = rd(cand, "CANONICAL_AUTHORITY.json")
    eff = rd(cand, "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json")
    counts = rd(cand, "consolidation/GENERATED_SCOPE_COUNTS.json")
    check("counts.authority", auth["active_application_test_count"] == 1624 and auth["active_requirement_count"] == 324,
          {k: auth[k] for k in ("active_application_test_count", "active_requirement_count")})
    check("counts.effective_registry", len(eff["tests"]) == 1624 and eff.get("count") in (1624, None), len(eff["tests"]))
    check("counts.units", len(c_units) == 131, len(c_units))
    flat = json.dumps(counts)
    check("counts.scope_counts_no_stale_1610", "1610" not in flat.replace('"original_test_objects_preserved": 1610', ""),
          {k: v for k, v in counts.items() if not isinstance(v, dict)})

    man = rd(cand, "MANIFEST.json")
    bad = sorted(p for p, m in man["files"].items() if c_files.get(p) != m["sha256"] or (cand / p).stat().st_size != m["bytes"])
    unlisted = sorted(set(c_files) - set(man["files"]) - {"MANIFEST.json"})
    check("manifest.complete_and_true", not bad and not unlisted and man["file_count_excluding_manifest"] == len(man["files"]),
          {"wrong": bad[:10], "unlisted": unlisted[:10]})

    lock = rd(cand, "plan/PROPOSED_SCOPE_LOCK.json")
    stale_lock = sorted(p for p, h in lock["file_hashes"].items() if (cand / p).is_file() and sha(cand / p) != h)
    check("lock.unsigned", lock["status"] == "PREPARED_PENDING_OWNER_SIGNATURE" and lock.get("signature") is None, lock["status"])
    check("lock.file_hashes_current", not stale_lock, stale_lock)

    pointers = {k: v for k, v in auth.items() if isinstance(v, str) and (ADMITTED / v).is_file()}
    missing = sorted(f"{k}={v}" for k, v in pointers.items() if not (cand / v).exists())
    check("pointers.authority_targets_exist", not missing, missing)

    without = [g for g in GATES if not c_units[g].get("acceptance_test_ids")]
    check("gates.five_units_have_acceptance", not without, {g: len(c_units[g].get("acceptance_test_ids", [])) for g in GATES})

    tree = hashlib.sha256("".join(f"{p}\0{h}\n" for p, h in sorted(c_files.items())).encode()).hexdigest()
    result = {
        "schema": "van.rebuild.ap001.candidate-verification/1",
        "state": "CANDIDATE_VERIFIED_BY_AUTHOR_NOT_ADMITTED",
        "admitted_package": {"path": "docs/review-inputs/van-rev115/package", "manifest_sha256": a_files["MANIFEST.json"],
                             "file_tree_sha256": hashlib.sha256("".join(f"{p}\0{h}\n" for p, h in sorted(a_files.items())).encode()).hexdigest()},
        "candidate_digest": {
            "file_tree_sha256": tree,
            "definition": "sha256 over sorted lines 'path\\0sha256(file)\\n' for every file except __pycache__",
            "manifest_sha256": c_files["MANIFEST.json"],
            "amendment_record_sha256": c_files["amendments/AP-001.json"],
            "patch_sha256": sha(PATCH),
            "generator_sha256": sha(ROOT / "tools/rebuild/ap001_dryrun.py"),
        },
        "changed_files": [{"path": p, "admitted_sha256": a_files.get(p), "candidate_sha256": c_files.get(p)} for p in changed],
        "checks": checks,
        "passed": all(c["passed"] for c in checks.values()),
        "reproduce": ["cp -a docs/review-inputs/van-rev115/package <copy>",
                      "python3 tools/rebuild/ap001_dryrun.py <copy>   # all 10 package checks must exit 0",
                      "python3 tools/rebuild/ap001_candidate.py <copy>   # prints this result"],
        "admission_action": [
            "Independent reviewer reviews AP-001 (AP-001_REVIEW.md, AP-001_PATCH.json) and this verification, and approves or rejects.",
            "Owner admits it through the package protocol (CONSOLIDATION_APPLY_PROTOCOL.md step 4): select the amended package as the "
            "one active candidate, update the authority selector and prepared scope fingerprints, keep old schedules historical.",
            "Deliver the amended package as Rev1.18.1 in a new path with its own archive digest; the admitted Rev1.18 package "
            "(manifest above) stays byte-identical as lineage. Re-sign the scope lock over the Rev1.18.1 hashes (OQ-05).",
            "Re-run PRE-001 trace (1,624 identities), ap001.py check, the ten package checks and manifest.py check at the frozen F15 baseline."],
    }
    print(json.dumps({"passed": result["passed"], "failed": [k for k, v in checks.items() if not v["passed"]],
                      "file_tree_sha256": tree, "changed": len(changed)}, indent=1))
    if "--write" in argv:
        OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
