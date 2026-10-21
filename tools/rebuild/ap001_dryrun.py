#!/usr/bin/env python3
"""Dry-run AP-001 admission against a COPY of the admitted package.

  python3 tools/rebuild/ap001_dryrun.py <copy-of-package-dir>

Applies the patch the way the package's own generators expect: new contracts into
verification/TEST_CONTRACTS.json, co-listings into plan unit acceptance lists, owner additions
into ACCEPTANCE_REFINEMENTS.json and plan.acceptance_owner_extensions, then the count pins
(authority, scope counts, plan invariant, verifier constants and blueprint total sentences).
It then runs compile_rev118.py and render_plan.py, re-runs every package verifier, and prints
the files changed and each verifier's result. It refuses to run on the admitted package path.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMITTED = (ROOT / "docs/review-inputs/van-rev115/package").resolve()
PATCH = ROOT / "docs/rebuild/rev118/pre002/AP-001/AP-001_PATCH.json"
OLD, NEW = 1610, 1624
VERIFIERS = [
    ["plan/compile_rev118.py", "--check"], ["plan/render_plan.py", "--check"],
    ["verification/verify_whole_product.py"], ["verification/verify_rev117.py", "--json"],
    ["verification/verify_rev117.py", "--selftest", "--json"], ["verification/verify_review_contracts.py"],
    ["verification/verify_experience_learning.py"], ["verification/verify_model_hardening.py"],
    ["verification/verify_theme_readability.py"], ["verification/verify_rev117.py", "--check-package", "--json"],
]


def rw(path: Path, fn):
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(pkg: Path) -> int:
    pkg = pkg.resolve()
    if pkg == ADMITTED or ADMITTED in pkg.parents:
        print("refusing to modify the admitted package")
        return 2
    patch = json.loads(PATCH.read_text())
    contract_fields = ("id", "unit", "expectation", "environment", "execution_state", "receipt_required", "scope_revision")

    def add_tests(d):
        for c in patch["new_acceptance_contracts"]:
            d["tests"].append({k: c[k] for k in contract_fields})
        d["count"] = d["tests"] if isinstance(d["count"], list) else len(d["tests"])
        if isinstance(d.get("tests"), list):
            d["count"] = len(d["tests"])
    rw(pkg / "verification/TEST_CONTRACTS.json", add_tests)

    def add_refinements(d):
        for t, units in patch["owner_additions"].items():
            d["owner_additions"][t] = sorted(set(d["owner_additions"].get(t, [])) | set(units))
    rw(pkg / "contracts/whole_product/ACCEPTANCE_REFINEMENTS.json", add_refinements)

    def add_plan(d):
        units = {u["id"]: u for u in d["units"]}
        for uid, ids in patch["unit_acceptance_additions"].items():
            cur = units[uid].setdefault("acceptance_test_ids", [])
            cur.extend(i for i in ids if i not in cur)
        for t, us in patch["owner_additions"].items():
            d["acceptance_owner_extensions"][t] = sorted(set(d["acceptance_owner_extensions"].get(t, [])) | set(us))
        d["preservation_invariant"] = d["preservation_invariant"].replace(f"{OLD} planned", f"{NEW} planned")
    rw(pkg / "plan/DEVELOPMENT_PLAN.json", add_plan)

    rw(pkg / "CANONICAL_AUTHORITY.json", lambda d: d.__setitem__("active_application_test_count", NEW))

    def counts(d):
        for k, v in list(d.items()):
            if v == OLD and k != "original_test_objects_preserved":
                d[k] = NEW
            if isinstance(v, dict):
                counts(v)
    rw(pkg / "consolidation/GENERATED_SCOPE_COUNTS.json", counts)

    for v in ("verify_experience_learning.py", "verify_model_hardening.py", "verify_review_contracts.py",
              "verify_whole_product.py"):
        f = pkg / "verification" / v
        f.write_text(f.read_text().replace(f"=={OLD}", f"=={NEW}").replace("1,610", "1,624"))
    f = pkg / "plan/compile_rev118.py"
    f.write_text(f.read_text().replace(f"Compiled {OLD}", f"Compiled {NEW}"))
    # The verifiers read the active totals from the master and focused blueprint named by
    # CANONICAL_AUTHORITY. Those documents state the totals inside the Rev1.17 revision paragraph,
    # which is history and stays byte-identical; the amendment appends its own statement instead.
    # Lineage documents (the Rev1.17 master and anything not named by authority) are untouched.
    authority = json.loads((pkg / "CANONICAL_AUTHORITY.json").read_text())
    note = (f"\n\n**Rev1.18.1 amendment AP-001 (proposed, not admitted).** Adds {NEW - OLD} acceptance identities for "
            f"the five gate units that had none (BQ-003, BQ-004, QA-002, QA-003, REL-002) and binds 39 existing identities "
            f"to them. The active totals are 324 requirements and {NEW:,} planned application tests; the Rev1.17 "
            f"paragraph above records that revision's totals and is preserved unchanged.\n")
    # The master embeds the focused blueprint verbatim (verifiers check `focus in master`), so the
    # note is appended to the focused blueprint and the master's embedded copy is replaced with it.
    focus_md, master_md = pkg / authority["focused_blueprint"], pkg / authority["master"]
    old_focus = focus_md.read_text().rstrip()
    new_focus = old_focus + note.rstrip("\n")
    master_text = master_md.read_text()
    assert master_text.count(old_focus) == 1, "master no longer embeds the focused blueprint exactly once"
    focus_md.write_text(new_focus + "\n")
    master_md.write_text(master_text.replace(old_focus, new_focus, 1))

    # Unit acceptance lists are derived (render_plan.acceptance_index, registry order), so the
    # amendment regenerates them with the package's own function instead of appending.
    import importlib.util
    spec = importlib.util.spec_from_file_location("render_plan_copy", pkg / "plan/render_plan.py")
    rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rp)
    tests_now = json.loads((pkg / "verification/TEST_CONTRACTS.json").read_text())["tests"]

    def derive(d):
        idx = rp.acceptance_index(d, tests_now)
        for u in d["units"]:
            u["acceptance_test_ids"] = idx[u["id"]]
    rw(pkg / "plan/DEVELOPMENT_PLAN.json", derive)

    run = lambda *a: subprocess.run([sys.executable, "-B", *a], cwd=pkg, capture_output=True, text=True)

    # Amendment lineage: the exact identities AP-001 adds, so preservation can stay strict for
    # every parent object while accepting only declared additions.
    (pkg / "amendments").mkdir(exist_ok=True)
    (pkg / "amendments/AP-001.json").write_text(json.dumps({
        "amendment": "AP-001", "status": "DRY_RUN_NOT_ADMITTED", "base_package_tree": patch["base_package_tree"],
        "added": {"tests": sorted(c["id"] for c in patch["new_acceptance_contracts"])},
        "owner_additions": patch["owner_additions"]}, indent=2, sort_keys=True) + "\n")
    f = pkg / "verification/verify_whole_product.py"
    t = f.read_text()
    old_line = "current={x['id']:digest(x) for x in rd(file)[key]};test('PRESERVE_'+name,current==baseline['objects'][name])"
    new_line = ("current={x['id']:digest(x) for x in rd(file)[key]};base=baseline['objects'][name];"
                "allowed=set().union(*[set(json.loads(a.read_text())['added'].get(name,[])) for a in sorted((P/'amendments').glob('*.json'))]) if (P/'amendments').is_dir() else set();"
                "test('PRESERVE_'+name,all(current.get(k)==v for k,v in base.items()) and set(current)-set(base)==allowed&set(current))")
    assert old_line in t, "verify_whole_product preservation line changed upstream"
    f.write_text(t.replace(old_line, new_line))
    f = pkg / "verification/verify_model_hardening.py"
    t = f.read_text()
    old_mut = "('REMOVE_TEST',lambda x:x['tests']['tests'].pop(),'TEST_NOT_IN_MAIN:')"
    new_mut = ("('REMOVE_TEST',lambda x:x['tests']['tests'].remove(next(t for t in x['tests']['tests'] "
               "if t['id']==x['new_tests']['tests'][0]['id'])),'TEST_NOT_IN_MAIN:')")
    assert old_mut in t, "verify_model_hardening mutation changed upstream"
    f.write_text(t.replace(old_mut, new_mut))

    # Order matters: compile the registry, re-prepare the lock, then render (the renderer's
    # provenance hashes the lock), then the manifest last.
    gen = [run("plan/compile_rev118.py")]

    # Re-prepare (not sign) the scope lock with the verifier's own digest.
    import hashlib
    sys.path.insert(0, str(pkg / "verification"))
    spec = importlib.util.spec_from_file_location("v117_copy", pkg / "verification/verify_rev117.py")
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    d = {k: v.read(x) for k, x in v.FILES.items()}
    maps = {"requirements": d["requirements"]["requirements"], "tests": d["tests"]["tests"],
            "actions": d["actions"]["actions"], "truth": d["truth"]["truth_atoms"],
            "units": d["plan"]["units"], "surfaces": d["surfaces"]["surfaces"]}

    def relock(lock):
        lock["objects"] = {n: {o["id"]: v.digest(o) for o in seq} for n, seq in maps.items()}
        for path in list(lock["file_hashes"]):
            q = pkg / path
            if q.is_file():
                lock["file_hashes"][path] = hashlib.sha256(q.read_bytes()).hexdigest()
        assert lock["status"] == "PREPARED_PENDING_OWNER_SIGNATURE" and lock.get("signature") is None
    rw(pkg / "plan/PROPOSED_SCOPE_LOCK.json", relock)
    gen.append(run("plan/render_plan.py"))
    rendered = {"plan/VAN_NEXT_DETERMINISTIC_PLAN_REV1_18.md", "plan/PLAN_INPUT_PROVENANCE.json"}
    if rendered & set(json.loads((pkg / "plan/PROPOSED_SCOPE_LOCK.json").read_text())["file_hashes"]):
        rw(pkg / "plan/PROPOSED_SCOPE_LOCK.json", relock)  # lock covers rendered outputs: refresh once

    def manifest(m):
        files = {}
        for q in sorted(pkg.rglob("*")):
            rel = q.relative_to(pkg).as_posix()
            if q.is_file() and rel != "MANIFEST.json" and not rel.startswith(".git/") and "__pycache__" not in rel:
                files[rel] = {"bytes": q.stat().st_size, "sha256": hashlib.sha256(q.read_bytes()).hexdigest()}
        m["files"] = files
        m["file_count_excluding_manifest"] = len(files)
    rw(pkg / "MANIFEST.json", manifest)
    results = []
    for cmd in VERIFIERS:
        r = run(*cmd)
        tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]
        fails = re.findall(r'"id": "([A-Z0-9_]+)",\s*"passed": false', r.stdout)
        results.append({"cmd": " ".join(cmd), "exit": r.returncode, "failed_cases": fails[:12], "tail": tail[0][:200]})
    import filecmp
    changed = sorted(q.relative_to(pkg).as_posix() for q in pkg.rglob("*") if q.is_file() and "__pycache__" not in q.parts
                     and not ((ADMITTED / q.relative_to(pkg)).is_file() and filecmp.cmp(q, ADMITTED / q.relative_to(pkg), shallow=False)))
    print(json.dumps({"generators": [g.returncode for g in gen], "generator_output": [g.stdout.strip()[:200] for g in gen],
                      "verifiers": results, "changed_files": changed}, indent=1))
    return 0 if all(r["exit"] == 0 for r in results) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
