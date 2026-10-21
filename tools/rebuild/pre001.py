#!/usr/bin/env python3
"""PRE-001 read-only evidence and feature inventory (VAN-PKT-001, Rev1.18).

Builds four deterministic artefacts under docs/rebuild/rev118/pre001/ from Git objects and
the admitted Rev1.18 package, then judges them:

  REF_INVENTORY.json        every live branch and PR head against the 70-branch evaluation
  SOURCE_LEDGER.json        every tracked file in the active roots: blob, input provenance,
                            symbols (Python AST exact; Kotlin declarations approximate)
  OVERLAP_PRESERVATION.json symbols present in any consolidation input but absent at HEAD
  TRACE_CHECK.json          bidirectional requirement/unit/test/action/context/feature links

Judgements (DISPOSITIONS.json) are hand-authored and separate from the generated facts. The
generator never classifies anything; an undisposed row stays open and blocks PRE-001.

  python3 tools/rebuild/pre001.py build      regenerate artefacts (no network)
  python3 tools/rebuild/pre001.py check      regenerate in memory, compare, report status
  python3 tools/rebuild/pre001.py selftest   induce each failure class and require rejection

No source file is modified (T-NX-071). Exit: 0 artefacts consistent (status may still be
OPEN), 1 artefact drift or failed selftest, 2 usage error.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/rebuild/rev118/pre001"
PKG = ROOT / "docs/review-inputs/van-rev115/package"
ACTIVE_ROOTS = ("android", "backend", "trading", "services", "hermes")
# Historical/document roots excluded by CLAUDE.md source boundaries; everything else at the
# frozen consolidation head is inventoried (deploy, tools, root tests, CI, registries, config,
# locked visual authority, root files).
HISTORICAL_ROOTS = ("docs", "evidence", "artifacts")
REFS_SNAPSHOT = OUT / "REMOTE_REFS_20261021.txt"
PR_STATE = OUT / "PR_STATE_20261021.json"
DISPOSITIONS = OUT / "DISPOSITIONS.json"

# Consolidation inputs (CONSOLIDATION_STATE.json) plus the main merge base they share.
INPUTS = {
    "main": "8eb1889822fc8a83f219977c15340172e16acd91",
    "base_bdd63a40": "bdd63a40174d36ccdd0ceb8f3fb258c612df8bbe",
    "opus_a39f241b": "a39f241b0135cf92cc5a6b9a28af226aa294603d",
    "accounts_3b2c9e04": "3b2c9e04df8736f0fbbccd16fcd3905cf1dbe240",
}
CONSOLIDATION_HEAD = "b02075f327ea8180ab6d269eba358cf8c5479878"

KT_DECL = re.compile(
    r"^[ \t]*(?:(?:public|private|internal|protected|override|open|abstract|sealed|data|enum|"
    r"inline|suspend|operator|infix|tailrec|external|annotation|inner|value|const|lateinit|"
    r"actual|expect|fun\s+interface)\s+)*(fun|class|object|interface)\s+"
    r"(?:<[^>]*>\s*)?((?:[A-Za-z_][\w]*\.)*[A-Za-z_`][\w`]*)",
    re.M,
)


def git(*args: str, binary: bool = False):
    out = subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True)
    return out.stdout if binary else out.stdout.decode()


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load(p: Path):
    return json.loads(p.read_text())


def dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- refs

def ref_inventory(refs_text: str, pr_state: dict, evaluation: dict, contains) -> dict:
    heads, pulls = {}, {}
    for line in refs_text.splitlines():
        sha, ref = line.split("\t")
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/"):]] = sha
        elif re.fullmatch(r"refs/pull/\d+/head", ref):
            pulls[int(ref.split("/")[2])] = sha
    evaluated = {b["branch"]: b for b in evaluation["branches"]}
    rows = []
    for name in sorted(set(heads) | set(evaluated)):
        e, live = evaluated.get(name), heads.get(name)
        if e and live == e["sha"]:
            state = "UNCHANGED_SINCE_EVALUATION"
        elif e and live:
            state = "MOVED_SINCE_EVALUATION"
        elif e:
            state = "DELETED_SINCE_EVALUATION"
        else:
            state = "NEW_SINCE_EVALUATION"
        rows.append({"kind": "branch", "id": name, "live_sha": live, "evaluated_sha": e and e["sha"],
                     "evaluation_disposition": e and e["disposition"],
                     "archive_tag": e and e.get("archive_tag"), "state": state,
                     "needs_disposition": state != "UNCHANGED_SINCE_EVALUATION"})
    evaluated_shas = {b["sha"] for b in evaluation["branches"]}
    reachable = None
    for num in sorted(pulls):
        sha = pulls[num]
        covered = sha in evaluated_shas or contains(sha)
        row = {"kind": "pull", "id": f"PR-{num}", "live_sha": sha,
               "pr_state": pr_state["pulls"].get(str(num), "UNKNOWN_NOT_READ_BACK"),
               "head_contained_in_evaluated_tip": covered,
               "state": "COVERED_BY_BRANCH_EVALUATION", "needs_disposition": False}
        if not covered:
            # History was rewritten (canonical-main prune), so ancestry alone under-reports.
            # Content layer: every post-image blob of the PR's own diff must exist somewhere in
            # the evaluated tips' history; otherwise its content is not preserved by any branch.
            if reachable is None:
                reachable = reachable_objects(sorted(evaluated_shas))
            base = git("merge-base", sha, INPUTS["main"]).strip()
            missing = []
            total = 0
            for line in git("diff", "--raw", "--no-abbrev", "--no-renames", base, sha).splitlines():
                meta, path = line.split("\t", 1)
                new_blob, status = meta.split()[3], meta.split()[4]
                if status == "D":
                    continue
                total += 1
                if new_blob not in reachable:
                    missing.append(path)
            head_paths = set(git("ls-tree", "-r", "--name-only", CONSOLIDATION_HEAD).splitlines()) if missing else set()
            row.update(diff_base=base, changed_blobs=total, missing_blob_paths=sorted(missing),
                       missing_paths_absent_at_consolidation_head=sorted(m for m in missing if m not in head_paths),
                       state="PR_ONLY_HEAD_CONTENT_PRESERVED" if not missing else "PR_ONLY_HEAD_CONTENT_NOT_PRESERVED",
                       needs_disposition=bool(missing))
        rows.append(row)
    if git("rev-parse", "--is-shallow-repository").strip() != "false":
        raise SystemExit("shallow clone: ancestry and reachability are unreliable; run git fetch --unshallow")
    return {"schema": "van.rebuild.pre001.refs/1", "refs_snapshot": REFS_SNAPSHOT.name,
            "refs_snapshot_sha256": sha256(refs_text.encode()), "pr_state": PR_STATE.name,
            "branch_count": len(heads), "pull_count": len(pulls), "rows": rows}


def reachable_objects(tips: list[str]) -> set[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "rev-list", "--objects", *tips],
                         check=True, capture_output=True, text=True).stdout
    return {line[:40] for line in out.splitlines()}


def git_contains_factory(evaluation: dict):
    tips = sorted({b["sha"] for b in evaluation["branches"]})

    def contains(sha: str) -> bool:
        for tip in tips:
            r = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", sha, tip],
                               capture_output=True)
            if r.returncode == 0:
                return True
        return False
    return contains


# ---------------------------------------------------------------- source

def py_symbols(src: bytes) -> list[list]:
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [["<syntax-error>", "error", exc.lineno or 0, ""]]
    out: list[list] = []

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}{ch.name}"
                body = ast.dump(ch, include_attributes=False).encode()
                out.append([q, "class" if isinstance(ch, ast.ClassDef) else "def", ch.lineno, sha256(body)[:16]])
                walk(ch, q + ".")
    walk(tree, "")
    return out


def kt_symbols(src: bytes) -> list[list]:
    text = src.decode("utf-8", "replace")
    out = []
    for m in KT_DECL.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append([m.group(2).strip("`"), m.group(1), line, ""])
    return out


def symbols_for(path: str, blob: bytes) -> tuple[list, str]:
    if path.endswith(".py"):
        return py_symbols(blob), "PYTHON_AST_EXACT"
    if path.endswith((".kt", ".kts")):
        return kt_symbols(blob), "KOTLIN_DECLARATION_REGEX_APPROXIMATE"
    return [], "NOT_PARSED"


def inventory_roots() -> list[str]:
    return [n for n in git("ls-tree", "--name-only", CONSOLIDATION_HEAD).splitlines() if n not in HISTORICAL_ROOTS]


def tree(commit: str) -> dict[str, str]:
    out = {}
    for line in git("ls-tree", "-r", commit, "--", *inventory_roots()).splitlines():
        meta, path = line.split("\t", 1)
        _, typ, blob = meta.split()
        if typ == "blob":
            out[path] = blob
    return out


def source_ledger(head: str) -> tuple[dict, dict]:
    head_tree = tree(head)
    input_trees = {k: tree(v) for k, v in INPUTS.items()}
    blobs = {}
    rows = []
    for path in sorted(head_tree):
        blob = head_tree[path]
        same = sorted(k for k, t in input_trees.items() if t.get(path) == blob)
        present = sorted(k for k, t in input_trees.items() if path in t)
        if same:
            prov = "IDENTICAL_TO_INPUT"
        elif present:
            prov = "CONSOLIDATION_MODIFIED"
        else:
            prov = "CONSOLIDATION_ADDED"
        data = git("cat-file", "blob", blob, binary=True)
        blobs[blob] = data
        syms, method = symbols_for(path, data)
        rows.append({"path": path, "blob": blob, "bytes": len(data), "provenance": prov,
                     "identical_inputs": same, "present_in_inputs": present,
                     "symbol_method": method, "symbols": syms,
                     "evidence_grade": "OBSERVED_GIT_OBJECT"})
    summary = {}
    for r in rows:
        summary[r["provenance"]] = summary.get(r["provenance"], 0) + 1
    ledger = {"schema": "van.rebuild.pre001.source/1", "head": head, "roots": inventory_roots(),
              "excluded_historical_roots": list(HISTORICAL_ROOTS),
              "inputs": INPUTS, "file_count": len(rows),
              "symbol_count": sum(len(r["symbols"]) for r in rows),
              "provenance_counts": summary, "rows": rows}
    return ledger, {"head_tree": head_tree, "input_trees": input_trees}


def overlap_preservation(trees: dict) -> dict:
    """Symbols defined by any input version of a file but absent from the HEAD version."""
    head_tree, inputs = trees["head_tree"], trees["input_trees"]
    main = inputs["main"]
    rows = []
    paths = set(head_tree)
    for k, t in inputs.items():
        paths |= set(t)
    for path in sorted(paths):
        if not path.endswith((".py", ".kt", ".kts")):
            continue
        changers = sorted(k for k, t in inputs.items()
                          if k != "main" and path in t and t[path] != main.get(path))
        if not changers:
            continue
        head_blob = head_tree.get(path)
        head_syms = set()
        if head_blob:
            head_syms = {s[0] for s in symbols_for(path, git("cat-file", "blob", head_blob, binary=True))[0]}
        for k in changers + (["main"] if path in main else []):
            in_syms = {s[0] for s in symbols_for(path, git("cat-file", "blob", inputs[k][path], binary=True))[0]}
            missing = sorted(in_syms - head_syms)
            if missing or head_blob is None:
                rows.append({"path": path, "input": k, "head_present": head_blob is not None,
                             "missing_symbols": missing, "changed_by_inputs": changers,
                             "id": f"OVL:{path}:{k}"})
    return {"schema": "van.rebuild.pre001.overlap/1",
            "rule": "A symbol defined by an input version and absent at HEAD is a preservation finding until dispositioned (T-HVA-002).",
            "rows": rows}


# ---------------------------------------------------------------- traceability

def trace_check(pkg: Path) -> dict:
    plan = load(pkg / "plan/DEVELOPMENT_PLAN.json")
    tests = load(pkg / "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json")["tests"]
    reqs = load(pkg / "traceability/REQUIREMENTS_AND_DU_MAPPING.json")["requirements"]
    actions = load(pkg / "traceability/LEGACY_349_ACTIONS.json")["actions"]
    action_contracts = load(pkg / "contracts/whole_product/ACTION_CONTRACTS.json")["actions"]
    bindings = load(pkg / "contracts/whole_product/FEATURE_CONTEXT_BINDINGS.json")
    features = load(pkg / "traceability/REV2_93_FEATURE_CROSSWALK.json")["features"]
    atoms = load(pkg / "traceability/REV2_171_ATOM_CROSSWALK.json")["requirements"]
    truth = load(pkg / "traceability/PRODUCT_TRUTH.json")["mappings"]
    surfaces = load(pkg / "design/ALL_SURFACE_CONTRACTS.json")["surfaces"]
    scenarios = load(pkg / "contracts/whole_product/DOMAIN_SCENARIOS.json")["scenarios"]

    f: list[str] = []
    units = {u["id"]: u for u in plan["units"]}
    test_ids = {t["id"] for t in tests}
    req_ids = {r["id"] for r in reqs}
    owned = plan["requirement_ownership"]

    def dup(name, ids):
        seen = set()
        for i in ids:
            if i in seen:
                f.append(f"DUPLICATE_{name}:{i}")
            seen.add(i)
    dup("UNIT", [u["id"] for u in plan["units"]])
    dup("TEST", [t["id"] for t in tests])
    dup("REQUIREMENT", [r["id"] for r in reqs])
    dup("ACTION", [a["id"] for a in actions])

    # requirement <-> unit
    owners: dict[str, set] = {}
    for u, rs in owned.items():
        if u not in units:
            f.append(f"OWNERSHIP_UNKNOWN_UNIT:{u}")
        for r in rs:
            owners.setdefault(r, set()).add(u)
            if r not in req_ids:
                f.append(f"OWNERSHIP_UNKNOWN_REQUIREMENT:{u}:{r}")
    for r in reqs:
        if not owners.get(r["id"]):
            f.append(f"UNOWNED_REQUIREMENT:{r['id']}")
        declared = set(r.get("backend_units", [])) | set(r.get("frontend_units", [])) | set(r.get("other_units", []))
        for u in declared - owners.get(r["id"], set()):
            f.append(f"REQUIREMENT_UNIT_NOT_IN_OWNERSHIP:{r['id']}:{u}")
        if r.get("test_id") and r["test_id"] not in test_ids:
            f.append(f"REQUIREMENT_TEST_MISSING:{r['id']}:{r['test_id']}")

    # unit <-> test
    listed: dict[str, set] = {}
    for u in plan["units"]:
        for t in u.get("acceptance_test_ids", []):
            listed.setdefault(t, set()).add(u["id"])
            if t not in test_ids:
                f.append(f"UNIT_TEST_MISSING:{u['id']}:{t}")
        if not u.get("acceptance_test_ids"):
            f.append(f"UNIT_WITHOUT_TESTS:{u['id']}")
        for d in u.get("dependencies", []):
            if d not in units:
                f.append(f"UNKNOWN_DEPENDENCY:{u['id']}:{d}")
    for t in tests:
        if t.get("unit") not in units:
            f.append(f"TEST_UNKNOWN_UNIT:{t['id']}:{t.get('unit')}")
        if t["id"] not in listed:
            f.append(f"TEST_NOT_LISTED_BY_ANY_UNIT:{t['id']}")

    # actions -> contract, context, test, units
    contracts = {a["action_id"]: a for a in action_contracts}
    surface_ids = {s["surface_id"] if "surface_id" in s else s.get("id") for s in surfaces}
    for a in actions:
        if a["id"] not in contracts:
            f.append(f"ACTION_WITHOUT_CONTRACT:{a['id']}")
        if a.get("test_id") not in test_ids:
            f.append(f"ACTION_TEST_MISSING:{a['id']}:{a.get('test_id')}")
        for u in a.get("backend_units", []) + a.get("frontend_units", []):
            if u not in units:
                f.append(f"ACTION_UNKNOWN_UNIT:{a['id']}:{u}")
        if not a.get("backend_units"):
            f.append(f"ACTION_WITHOUT_BACKEND_OWNER:{a['id']}")
        if a.get("surface_id") not in surface_ids:
            f.append(f"ACTION_UNKNOWN_SURFACE:{a['id']}:{a.get('surface_id')}")
    for aid in contracts:
        if aid not in {a["id"] for a in actions}:
            f.append(f"CONTRACT_WITHOUT_ACTION:{aid}")

    # contexts / features / atoms / truth / scenarios
    feature_ids = {x["id"] for x in features}
    ctx = bindings["contexts"]
    bound_features = set()
    for c in ctx:
        for u in c.get("backend_units", []) + c.get("frontend_units", []):
            if u not in units:
                f.append(f"CONTEXT_UNKNOWN_UNIT:{c['context_id']}:{u}")
        for fid in c.get("feature_ids", []) + c.get("features", []):
            bound_features.add(fid)
        for aid in c.get("legacy_action_ids", []):
            if aid not in contracts:
                f.append(f"CONTEXT_UNKNOWN_ACTION:{c['context_id']}:{aid}")
    if len({c["context_id"] for c in ctx}) != len(ctx):
        f.append("DUPLICATE_CONTEXT")
    feature_map = bindings.get("features")
    if isinstance(feature_map, list):
        for fe in feature_map:
            fid = fe.get("feature_id") or fe.get("id")
            if fe.get("context_ids") or fe.get("contexts"):
                bound_features.add(fid)
    for fid in sorted(feature_ids - bound_features):
        f.append(f"FEATURE_WITHOUT_CONTEXT:{fid}")
    for a in atoms:
        if a.get("feature_id") and a["feature_id"] not in feature_ids:
            f.append(f"ATOM_UNKNOWN_FEATURE:{a['id']}:{a['feature_id']}")
    for m in truth:
        for r in m["van_requirements"]:
            if r not in req_ids:
                f.append(f"TRUTH_UNKNOWN_REQUIREMENT:{m['id']}:{r}")

    counts = {"requirements": len(reqs), "acceptance_identities": len(tests), "units": len(units),
              "owner_actions": len(actions), "contexts": len(ctx), "surfaces": len(surfaces),
              "features": len(features), "source_atoms": len(atoms), "truth_atoms": len(truth),
              "domain_scenarios": len(scenarios)}
    expected = {"requirements": 324, "acceptance_identities": 1610, "units": 131, "owner_actions": 349,
                "contexts": 234, "features": 93, "source_atoms": 171, "truth_atoms": 22, "domain_scenarios": 72}
    for k, v in expected.items():
        if counts[k] != v:
            f.append(f"COUNT_MISMATCH:{k}:{counts[k]}!={v}")
    return {"schema": "van.rebuild.pre001.trace/1", "counts": counts, "findings": sorted(set(f)),
            "scope": "Registry linkage only. A linked row is not an implementation; implementation presence is judged per unit at its own exit."}


# ---------------------------------------------------------------- classification

RULES = OUT / "CLASSIFICATION_RULES.json"


def classify(ledger: dict, rules_doc: dict, unit_ids: set[str]) -> dict:
    """Apply the hand-authored ordered rules to every ledger file (first match wins)."""
    rules = [(r, re.compile(r["re"])) for r in rules_doc["rules"]]
    kinds, classes = set(rules_doc["kinds"]), set(rules_doc["classes"])
    rows, hits, problems = [], {r["id"]: 0 for r, _ in rules}, []
    for r, _ in rules:
        if r["kind"] not in kinds:
            problems.append(f"RULE_UNKNOWN_KIND:{r['id']}:{r['kind']}")
        if r["class"] not in classes:
            problems.append(f"RULE_UNKNOWN_CLASS:{r['id']}:{r['class']}")
        for u in r["units"]:
            if u not in unit_ids:
                problems.append(f"RULE_UNKNOWN_UNIT:{r['id']}:{u}")
        if not r["units"] or not r.get("why"):
            problems.append(f"RULE_WITHOUT_OWNER_OR_REASON:{r['id']}")
    for f in ledger["rows"]:
        rule = next((r for r, rx in rules if rx.search(f["path"])), None)
        if rule:
            hits[rule["id"]] += 1
        rows.append({"path": f["path"], "rule": rule and rule["id"], "kind": rule and rule["kind"],
                     "units": rule and rule["units"], "class": rule and rule["class"]})
    for rid, n in hits.items():
        if n == 0:
            problems.append(f"RULE_MATCHES_NOTHING:{rid}")
    counts: dict = {}
    for r in rows:
        for key in ("kind", "class"):
            counts.setdefault(key, {}).setdefault(str(r[key]), 0)
            counts[key][str(r[key])] += 1
    unit_files: dict = {}
    for r in rows:
        for u in r["units"] or []:
            unit_files[u] = unit_files.get(u, 0) + 1
    return {"schema": "van.rebuild.pre001.classification/1", "rules_sha256": sha256(dump(rules_doc).encode()),
            "file_count": len(rows), "unmatched": sorted(r["path"] for r in rows if not r["rule"]),
            "rule_problems": sorted(problems), "rule_hits": hits, "counts": counts,
            "files_per_unit": dict(sorted(unit_files.items())), "rows": rows}


# ---------------------------------------------------------------- judgement

def judge(refs: dict, ledger: dict, overlap: dict, trace: dict, disp: dict, classification: dict) -> dict:
    d_refs = disp.get("refs", {})
    d_ovl = disp.get("overlap", {})
    problems = []

    def valid(entry, where):
        if not isinstance(entry, dict) or not entry.get("decision") or not entry.get("evidence"):
            problems.append(f"DISPOSITION_WITHOUT_DECISION_AND_EVIDENCE:{where}")
            return False
        if entry.get("evidence_grade") == "OBSERVED" and entry.get("basis") == "INFERRED":
            problems.append(f"INFERRED_REPORTED_AS_OBSERVED:{where}")
            return False
        return True

    def covers_paths(r):
        missing = set(r.get("missing_blob_paths") or [])
        uncovered = missing - set((d_refs[r["id"]].get("paths") or {}))
        if uncovered:
            problems.append(f"DISPOSITION_MISSING_PATHS:{r['id']}:{len(uncovered)}")
        return not uncovered

    open_refs = [r["id"] for r in refs["rows"] if r["needs_disposition"]
                 and not (r["id"] in d_refs and valid(d_refs[r["id"]], r["id"]) and covers_paths(r))]
    open_ovl = [r["id"] for r in overlap["rows"]
                if not (r["id"] in d_ovl and valid(d_ovl[r["id"]], r["id"]))]
    unclassified = list(classification["unmatched"])
    problems.extend(classification["rule_problems"])
    for k in d_refs:
        if k not in {r["id"] for r in refs["rows"]}:
            problems.append(f"DISPOSITION_FOR_UNKNOWN_REF:{k}")
    complete = not (open_refs or open_ovl or unclassified or trace["findings"] or problems)
    return {"status": "EVIDENCE_COMPLETE_PENDING_INDEPENDENT_REVIEW" if complete else "OPEN",
            "refs_open": {"count": len(open_refs), "of": len(refs["rows"]), "ids": open_refs},
            "overlap_open": {"count": len(open_ovl), "of": len(overlap["rows"]), "ids": open_ovl},
            "source_unclassified": {"count": len(unclassified), "of": ledger["file_count"]},
            "trace_findings": len(trace["findings"]), "disposition_problems": problems,
            "note": "EVIDENCE_COMPLETE is not PRE-001 acceptance: the exit requires independent review of the no-loss mapping."}


# ---------------------------------------------------------------- driver

def generate(head: str):
    evaluation = load(ROOT / "docs/consolidation/BRANCH_EVALUATION.json")
    refs = ref_inventory(REFS_SNAPSHOT.read_text(), load(PR_STATE), evaluation, git_contains_factory(evaluation))
    ledger, trees = source_ledger(head)
    overlap = overlap_preservation(trees)
    trace = trace_check(PKG)
    units = {u["id"] for u in load(PKG / "plan/DEVELOPMENT_PLAN.json")["units"]}
    classification = classify(ledger, load(RULES), units)
    return {"REF_INVENTORY.json": refs, "SOURCE_LEDGER.json": ledger,
            "OVERLAP_PRESERVATION.json": overlap, "TRACE_CHECK.json": trace,
            "SOURCE_CLASSIFICATION.json": classification}


def source_head() -> str:
    """PRE-001 freezes the admitted source candidate; later rebuild commits are not inventoried."""
    return CONSOLIDATION_HEAD


def summary(arts: dict, disp: dict) -> dict:
    s = judge(arts["REF_INVENTORY.json"], arts["SOURCE_LEDGER.json"], arts["OVERLAP_PRESERVATION.json"],
              arts["TRACE_CHECK.json"], disp, arts["SOURCE_CLASSIFICATION.json"])
    s["artefact_sha256"] = {k: sha256(dump(v).encode()) for k, v in sorted(arts.items())}
    s["source_head"] = arts["SOURCE_LEDGER.json"]["head"]
    s["unit"] = "PRE-001"
    s["packet"] = "VAN-PKT-001"
    return s


def cmd_build() -> int:
    arts = generate(source_head())
    for name, obj in arts.items():
        (OUT / name).write_text(dump(obj))
    disp = load(DISPOSITIONS) if DISPOSITIONS.exists() else {}
    (OUT / "STATUS.json").write_text(dump(summary(arts, disp)))
    print(dump(load(OUT / "STATUS.json") | {"refs_open": "...", "overlap_open": "..."}))
    return 0


def cmd_check() -> int:
    arts = generate(source_head())
    drift = [n for n, o in arts.items() if not (OUT / n).exists() or (OUT / n).read_text() != dump(o)]
    disp = load(DISPOSITIONS) if DISPOSITIONS.exists() else {}
    s = summary(arts, disp)
    if not (OUT / "STATUS.json").exists() or load(OUT / "STATUS.json") != s:
        drift.append("STATUS.json")
    print(json.dumps({"drift": drift, "status": s["status"], "refs_open": s["refs_open"]["count"],
                      "overlap_open": s["overlap_open"]["count"],
                      "source_unclassified": s["source_unclassified"],
                      "trace_findings": s["trace_findings"],
                      "disposition_problems": s["disposition_problems"]}, indent=1))
    return 1 if drift else 0


def cmd_selftest() -> int:
    """Each case breaks one invariant and requires the judge or trace check to reject it."""
    arts = {n: load(OUT / n) for n in ("REF_INVENTORY.json", "SOURCE_LEDGER.json",
                                       "OVERLAP_PRESERVATION.json", "TRACE_CHECK.json",
                                       "SOURCE_CLASSIFICATION.json")}
    disp = load(DISPOSITIONS) if DISPOSITIONS.exists() else {}
    full = {"refs": {r["id"]: {"decision": "X", "evidence": "x",
                               "paths": {m: "X" for m in r.get("missing_blob_paths") or []}}
                     for r in arts["REF_INVENTORY.json"]["rows"] if r["needs_disposition"]},
            "overlap": {r["id"]: {"decision": "X", "evidence": "x"} for r in arts["OVERLAP_PRESERVATION.json"]["rows"]}}
    clean_trace = dict(arts["TRACE_CHECK.json"], findings=[])
    clean_class = dict(arts["SOURCE_CLASSIFICATION.json"], unmatched=[], rule_problems=[])
    results = []

    def run(name, mutate, expect_open):
        a, d = copy.deepcopy(arts), copy.deepcopy(full)
        a["TRACE_CHECK.json"] = copy.deepcopy(clean_trace)
        a["SOURCE_CLASSIFICATION.json"] = copy.deepcopy(clean_class)
        mutate(a, d)
        s = judge(a["REF_INVENTORY.json"], a["SOURCE_LEDGER.json"], a["OVERLAP_PRESERVATION.json"],
                  a["TRACE_CHECK.json"], d, a["SOURCE_CLASSIFICATION.json"])
        ok = (s["status"] == "OPEN") == expect_open
        results.append({"id": name, "passed": ok, "status": s["status"]})

    run("POSITIVE_CONTROL_ALL_DISPOSITIONED", lambda a, d: None, False)
    run("DISCARD_BRANCH_WITHOUT_DISPOSITION",
        lambda a, d: d["refs"].pop(next(iter(d["refs"]))) if d["refs"] else
        a["REF_INVENTORY.json"]["rows"].append({"id": "x", "needs_disposition": True}), True)
    run("PR_ONLY_HEAD_UNDISPOSITIONED",
        lambda a, d: a["REF_INVENTORY.json"]["rows"].append(
            {"kind": "pull", "id": "PR-999", "state": "PR_ONLY_HEAD", "needs_disposition": True}), True)
    run("INFERRED_EFFECT_REPORTED_AS_OBSERVED",
        lambda a, d: next(iter(d["refs"].values())).update(evidence_grade="OBSERVED", basis="INFERRED"), True)
    run("DISPOSITION_WITHOUT_EVIDENCE",
        lambda a, d: next(iter(d["overlap"].values())).pop("evidence"), True)
    run("UNCLASSIFIED_SOURCE_FILE",
        lambda a, d: a["SOURCE_CLASSIFICATION.json"]["unmatched"].append("backend/van_gateway/new.py"), True)

    # Classification-level mutations run the real rules against the real ledger.
    rules_doc = load(RULES)
    unit_ids = {u["id"] for u in load(PKG / "plan/DEVELOPMENT_PLAN.json")["units"]}

    def class_mut(name, edit, expect):
        doc = copy.deepcopy(rules_doc)
        edit(doc)
        c = classify(arts["SOURCE_LEDGER.json"], doc, unit_ids)
        results.append({"id": name, "passed": expect(c), "problems": c["rule_problems"][:2],
                        "unmatched": len(c["unmatched"])})

    class_mut("RULE_NAMES_UNKNOWN_UNIT", lambda d: d["rules"][0]["units"].append("BE-999"),
              lambda c: any(p.startswith("RULE_UNKNOWN_UNIT") for p in c["rule_problems"]))
    class_mut("REMOVED_RULE_LEAVES_FILES_UNOWNED",
              lambda d: d["rules"].__setitem__(slice(None), [r for r in d["rules"] if r["id"] != "R-SERVICES"]),
              lambda c: any(u.startswith("services/") for u in c["unmatched"]))
    class_mut("SHADOWED_RULE_DETECTED",
              lambda d: d["rules"].insert(0, {"id": "R-SHADOW", "re": "^backend/", "kind": "TOOLING",
                                              "units": ["BE-033"], "class": "RETAIN", "why": "x"}),
              lambda c: any(p.startswith("RULE_MATCHES_NOTHING") for p in c["rule_problems"]))
    run("REF_DISPOSITION_OMITS_A_PATH",
        lambda a, d: (a["REF_INVENTORY.json"]["rows"].append(
            {"kind": "pull", "id": "PR-998", "needs_disposition": True, "missing_blob_paths": ["a.py", "b.kt"]}),
            d["refs"].__setitem__("PR-998", {"decision": "X", "evidence": "x", "paths": {"a.py": "PRESERVED"}})), True)
    run("DROPPED_SYMBOL_IN_OVERLAP",
        lambda a, d: a["OVERLAP_PRESERVATION.json"]["rows"].append(
            {"id": "OVL:x.py:opus", "missing_symbols": ["AccountService.lockout"]}), True)

    # Trace-level mutations run against the real package registries in memory. A case passes
    # only if it produces a finding absent from the unmutated baseline.
    baseline = set(trace_check(PKG)["findings"])
    def trace_mut(name, edit):
        pkg_copy = {}
        orig = load

        def patched(p: Path):
            obj = orig(p)
            rel = str(Path(p).resolve().relative_to(PKG.resolve())) if str(p).startswith(str(PKG)) else None
            return edit(rel, obj) if rel else obj
        globals()["load"] = patched
        try:
            t = trace_check(PKG)
        finally:
            globals()["load"] = orig
        new = sorted(set(t["findings"]) - baseline)
        results.append({"id": name, "passed": bool(new), "new_findings": new[:3]})

    def drop_action(rel, obj):
        if rel == "traceability/LEGACY_349_ACTIONS.json":
            obj["actions"] = obj["actions"][1:]
        return obj

    def unown_requirement(rel, obj):
        if rel == "plan/DEVELOPMENT_PLAN.json":
            victim = "VAN-NX-071"
            obj["requirement_ownership"] = {u: [r for r in rs if r != victim]
                                            for u, rs in obj["requirement_ownership"].items()}
        return obj

    def orphan_test(rel, obj):
        if rel == "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json":
            obj["tests"][0]["unit"] = "NONEXISTENT-UNIT"
        return obj

    def drop_unit_test(rel, obj):
        if rel == "plan/DEVELOPMENT_PLAN.json":
            obj["units"][0]["acceptance_test_ids"] = obj["units"][0]["acceptance_test_ids"][1:]
        return obj

    trace_mut("DELETE_INHERITED_ACTION", drop_action)
    trace_mut("UNOWNED_REQUIREMENT", unown_requirement)
    trace_mut("TEST_WITH_UNKNOWN_UNIT", orphan_test)
    trace_mut("TEST_REMOVED_FROM_OWNING_UNIT", drop_unit_test)
    passed = sum(r["passed"] for r in results)
    print(json.dumps({"passed": passed, "total": len(results), "cases": results,
                      "real_dispositions_loaded": bool(disp)}, indent=1))
    return 0 if passed == len(results) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "check", "selftest"])
    a = ap.parse_args()
    return {"build": cmd_build, "check": cmd_check, "selftest": cmd_selftest}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
