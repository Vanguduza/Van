#!/usr/bin/env python3
"""Build AP-002 alone or AP-001 + AP-002 on a fresh copy; never admit a package.

Usage: amendment_candidates.py OUTPUT AP-002 [--write-report]
       amendment_candidates.py OUTPUT AP-001 AP-002 [--write-report]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/review-inputs/van-rev115/package"
PROPOSALS = ROOT / "docs/rebuild/rev118/pre002"
VERIFIERS = [
    ["plan/compile_rev118.py", "--check"], ["plan/render_plan.py", "--check"],
    ["verification/verify_whole_product.py"], ["verification/verify_rev117.py", "--json"],
    ["verification/verify_rev117.py", "--selftest", "--json"],
    ["verification/verify_review_contracts.py"], ["verification/verify_experience_learning.py"],
    ["verification/verify_model_hardening.py"], ["verification/verify_theme_readability.py"],
    ["verification/verify_rev117.py", "--check-package", "--json"],
]


def read(root, path):
    return json.loads((root / path).read_text())


def write(root, path, value):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_candidate(target, names):
    """An independent comparison to the original, not a regenerated-lock assertion."""
    findings = []
    patches = [read(PROPOSALS / n, n + "_PATCH.json") for n in names]
    additions = {t["id"]: t for patch in patches for t in patch["new_acceptance_contracts"]}
    owner_additions = {}
    for patch in patches:
        for tid, units in patch["owner_additions"].items():
            owner_additions.setdefault(tid, set()).update(units)
    for rel in ("verification/TEST_CONTRACTS.json", "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json"):
        before = read(BASE, rel)["tests"]
        after = read(target, rel)["tests"]
        indexed = {t["id"]: t for t in after}
        if len(indexed) != len(after): findings.append("DUPLICATE_TEST:" + rel)
        if [t["id"] for t in after[:len(before)]] != [t["id"] for t in before]:
            findings.append("ORIGINAL_TEST_ORDER_OR_SET:" + rel)
        if set(indexed) != {t["id"] for t in before} | set(additions):
            findings.append("UNDECLARED_TEST_SET:" + rel)
        for original in before:
            actual = copy.deepcopy(indexed.get(original["id"], {}))
            expected = copy.deepcopy(original)
            if rel.endswith("EFFECTIVE_TEST_CONTRACTS_REV118.json") and original["id"] in owner_additions:
                expected["additional_units"] = sorted((set(expected.get("additional_units", [])) |
                    owner_additions[original["id"]]) - {expected["unit"]})
            if actual != expected: findings.append("ORIGINAL_TEST_CHANGED:" + original["id"])
        for tid, expected in additions.items():
            actual = indexed.get(tid, {})
            if any(actual.get(k) != v for k, v in expected.items()):
                findings.append("PROPOSED_ORACLE_CHANGED:" + tid)
    before = read(BASE, "plan/DEVELOPMENT_PLAN.json")
    after = read(target, "plan/DEVELOPMENT_PLAN.json")
    b_units = {u["id"]: u for u in before["units"]}
    a_units = {u["id"]: u for u in after["units"]}
    if set(b_units) != set(a_units): findings.append("UNIT_SET_CHANGED")
    for identity, unit in b_units.items():
        candidate = a_units.get(identity, {})
        strip = lambda u: {k: v for k, v in u.items() if k != "acceptance_test_ids"}
        if strip(unit) != strip(candidate): findings.append("UNIT_CONTRACT_CHANGED:" + identity)
        if not set(unit.get("acceptance_test_ids", [])) <= set(candidate.get("acceptance_test_ids", [])):
            findings.append("UNIT_ACCEPTANCE_REMOVED:" + identity)
    original_files, candidate_files = hashes(BASE), hashes(target)
    for path in original_files:
        if path not in candidate_files: findings.append("FILE_REMOVED:" + path)
        if (path.startswith(("lineage/", "traceability/")) or path.endswith("REV1_17_20261018.md")) and original_files[path] != candidate_files.get(path):
            findings.append("HISTORICAL_OR_TRACE_SOURCE_CHANGED:" + path)
    lock = read(target, "plan/PROPOSED_SCOPE_LOCK.json")
    if lock.get("signature") is not None or lock["status"] != "PREPARED_PENDING_OWNER_SIGNATURE":
        findings.append("FALSE_SIGNATURE_OR_ADMISSION")
    if read(target, "CANONICAL_AUTHORITY.json")["active_application_test_count"] != 1610 + len(additions):
        findings.append("AUTHORITY_COUNT_MISMATCH")
    manifest = read(target, "MANIFEST.json")
    for path, record in manifest["files"].items():
        if candidate_files.get(path) != record["sha256"] or (target / path).stat().st_size != record["bytes"]:
            findings.append("MANIFEST_MISMATCH:" + path)
    if set(manifest["files"]) != set(candidate_files) - {"MANIFEST.json"}:
        findings.append("MANIFEST_FILE_SET")
    return findings


def prepare(target, names):
    target = target.resolve()
    if target == BASE.resolve() or BASE.resolve() in target.parents or target in BASE.resolve().parents:
        raise ValueError("candidate must not overlap the original package")
    if target.exists():
        raise ValueError("output must be a fresh, nonexistent directory")
    patches = [read(PROPOSALS / n, n + "_PATCH.json") for n in names]
    base_tests = read(BASE, "verification/TEST_CONTRACTS.json")
    plan = read(BASE, "plan/DEVELOPMENT_PLAN.json")
    refinements = read(BASE, "contracts/whole_product/ACCEPTANCE_REFINEMENTS.json")
    tests = copy.deepcopy(base_tests)
    by_id = {t["id"]: t for t in tests["tests"]}
    unit_ids = {u["id"] for u in plan["units"]}
    for name, patch in zip(names, patches):
        for item in patch["new_acceptance_contracts"]:
            if item["id"] in by_id or item["unit"] not in unit_ids or item["execution_state"] != "NOT_RUN":
                raise ValueError("invalid proposed identity: " + item["id"])
            tests["tests"].append(copy.deepcopy(item))
            by_id[item["id"]] = tests["tests"][-1]
        for tid, units in patch["owner_additions"].items():
            if tid not in by_id or not set(units) <= unit_ids:
                raise ValueError("unknown proposed owner binding: " + tid)
            for destination in (refinements["owner_additions"], plan["acceptance_owner_extensions"]):
                destination[tid] = sorted(set(destination.get(tid, [])) | set(units))
    count = len(tests["tests"])
    tests["count"] = count
    plan["preservation_invariant"] = plan["preservation_invariant"].replace("1610 planned", f"{count} planned")
    renderer = import_file("candidate_plan_renderer", BASE / "plan/render_plan.py")
    acceptance = renderer.acceptance_index(plan, tests["tests"])
    for unit in plan["units"]:
        unit["acceptance_test_ids"] = acceptance[unit["id"]]
    shutil.copytree(BASE, target, ignore=shutil.ignore_patterns("__pycache__"))
    write(target, "verification/TEST_CONTRACTS.json", tests)
    write(target, "plan/DEVELOPMENT_PLAN.json", plan)
    write(target, "contracts/whole_product/ACCEPTANCE_REFINEMENTS.json", refinements)
    authority = read(target, "CANONICAL_AUTHORITY.json")
    authority["active_application_test_count"] = count
    write(target, "CANONICAL_AUTHORITY.json", authority)
    scope_counts = read(target, "consolidation/GENERATED_SCOPE_COUNTS.json")

    def update_counts(d):
        for key, value in d.items():
            if isinstance(value, dict): update_counts(value)
            elif value == 1610 and key != "original_test_objects_preserved": d[key] = count
    update_counts(scope_counts)
    write(target, "consolidation/GENERATED_SCOPE_COUNTS.json", scope_counts)
    for script in ("verify_experience_learning.py", "verify_model_hardening.py", "verify_review_contracts.py", "verify_whole_product.py"):
        p = target / "verification" / script
        p.write_text(p.read_text().replace("==1610", f"=={count}").replace("1,610", f"{count:,}"))
    p = target / "plan/compile_rev118.py"
    p.write_text(p.read_text().replace("Compiled 1610", f"Compiled {count}"))
    p = target / "verification/verify_whole_product.py"
    old = "current={x['id']:digest(x) for x in rd(file)[key]};test('PRESERVE_'+name,current==baseline['objects'][name])"
    new = ("current={x['id']:digest(x) for x in rd(file)[key]};base=baseline['objects'][name];"
           "allowed=set().union(*[set(json.loads(a.read_text())['added'].get(name,[])) for a in sorted((P/'amendments').glob('*.json'))]);"
           "test('PRESERVE_'+name,all(current.get(k)==v for k,v in base.items()) and set(current)-set(base)==allowed)")
    assert old in p.read_text()
    p.write_text(p.read_text().replace(old, new))
    p = target / "verification/verify_model_hardening.py"
    old = "('REMOVE_TEST',lambda x:x['tests']['tests'].pop(),'TEST_NOT_IN_MAIN:')"
    new = ("('REMOVE_TEST',lambda x:x['tests']['tests'].remove(next(t for t in x['tests']['tests'] "
           "if t['id']==x['new_tests']['tests'][0]['id'])),'TEST_NOT_IN_MAIN:')")
    assert old in p.read_text()
    p.write_text(p.read_text().replace(old, new))
    for name, patch in zip(names, patches):
        write(target, f"amendments/{name}.json", {
            "amendment": name, "status": "CANDIDATE_NOT_ADMITTED",
            "base_package_tree": patch["base_package_tree"],
            "added": {"tests": sorted(t["id"] for t in patch["new_acceptance_contracts"])},
            "owner_additions": patch["owner_additions"],
            "full_proposed_acceptance": patch["new_acceptance_contracts"],
            "citation_errata": patch.get("citation_errata", {}),
        })
    focus, master = target / authority["focused_blueprint"], target / authority["master"]
    old_focus = focus.read_text().rstrip()
    note = (f"\n\n**Rev1.18 amendment candidate {' + '.join(names)} (not admitted).** "
            f"The active totals are 324 requirements and {count:,} planned application tests, all NOT_RUN. "
            "Original revision narratives above remain historical. Full proposed oracles and citation errata "
            "are retained under amendments/. No signature, independent admission or product qualification is issued.\n")
    assert master.read_text().count(old_focus) == 1
    focus.write_text(old_focus + note)
    master.write_text(master.read_text().replace(old_focus, old_focus + note.rstrip(), 1))

    def run(cmd):
        return subprocess.run([sys.executable, "-B", *cmd], cwd=target, capture_output=True, text=True)
    result = run(["plan/compile_rev118.py"])
    if result.returncode: raise ValueError(result.stdout + result.stderr)
    verifier = import_file("candidate_lock_verifier", target / "verification/verify_rev117.py")
    data = {k: verifier.read(path) for k, path in verifier.FILES.items()}
    maps = {"requirements": data["requirements"]["requirements"], "tests": data["tests"]["tests"],
            "actions": data["actions"]["actions"], "truth": data["truth"]["truth_atoms"],
            "units": data["plan"]["units"], "surfaces": data["surfaces"]["surfaces"]}
    lock = read(target, "plan/PROPOSED_SCOPE_LOCK.json")
    assert lock["status"] == "PREPARED_PENDING_OWNER_SIGNATURE" and lock.get("signature") is None
    lock["objects"] = {k: {o["id"]: verifier.digest(o) for o in values} for k, values in maps.items()}
    for path in lock["file_hashes"]:
        if (target / path).is_file(): lock["file_hashes"][path] = hashlib.sha256((target / path).read_bytes()).hexdigest()
    write(target, "plan/PROPOSED_SCOPE_LOCK.json", lock)
    result = run(["plan/render_plan.py"])
    if result.returncode: raise ValueError(result.stdout + result.stderr)
    manifest = read(target, "MANIFEST.json")
    manifest["files"] = {p: {"bytes": (target / p).stat().st_size, "sha256": h}
                         for p, h in hashes(target).items() if p != "MANIFEST.json"}
    manifest["file_count_excluding_manifest"] = len(manifest["files"])
    write(target, "MANIFEST.json", manifest)
    results = []
    for command in VERIFIERS:
        r = run(command)
        results.append({"command": " ".join(command), "exit": r.returncode,
                        "output_sha256": hashlib.sha256((r.stdout + r.stderr).encode()).hexdigest(),
                        "diagnostic": (r.stdout + r.stderr)[-2000:] if r.returncode else None})
    original, candidate = hashes(BASE), hashes(target)
    report = {
        "schema": "van.rebuild.amendment-candidate/1", "amendments": names,
        "status": "CANDIDATE_NOT_ADMITTED", "acceptance_count": count,
        "package_tree_sha256": hashlib.sha256("".join(f"{p}\0{h}\n" for p, h in sorted(candidate.items())).encode()).hexdigest(),
        "changed_files": sorted(p for p in set(original) | set(candidate) if original.get(p) != candidate.get(p)),
        "removed_files": sorted(set(original) - set(candidate)), "verifiers": results,
        "preservation_findings": audit_candidate(target, names),
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("amendments", nargs="+", choices=["AP-001", "AP-002"])
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    if args.amendments not in (["AP-002"], ["AP-001", "AP-002"]):
        parser.error("supported candidates are AP-002 alone or AP-001 followed by AP-002")
    report = prepare(args.output, args.amendments)
    print(json.dumps(report, indent=1))
    if args.write_report:
        name = "CUMULATIVE" if len(args.amendments) > 1 else "STANDALONE"
        write(PROPOSALS / "AP-002", name + "_CANDIDATE_VERIFICATION.json", report)
    return int(bool(report["removed_files"] or report["preservation_findings"]) or any(v["exit"] for v in report["verifiers"]))


if __name__ == "__main__":
    raise SystemExit(main())
