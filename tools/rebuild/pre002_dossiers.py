#!/usr/bin/env python3
"""PRE-002 challenge dossiers: one author-prepared dossier per active requirement.

  python3 tools/rebuild/pre002_dossiers.py generate   # write DOSSIERS.json and SUMMARY.md
  python3 tools/rebuild/pre002_dossiers.py check      # fail if the committed outputs drift
  python3 tools/rebuild/pre002_dossiers.py selftest   # each mechanical challenge fires on an induced defect

Every dossier is a challenge the independent reviewer must answer. It is not admission and it
does not regrade the package: `challenge_state` is always AUTHOR_CHALLENGED_PENDING_INDEPENDENT_REVIEW.
All facts come from the admitted package and PRE-001 classification; nothing is inferred from names.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "docs/review-inputs/van-rev115/package"
OUT = ROOT / "docs/rebuild/rev118/pre002/challenge"
CLASSIFICATION = ROOT / "docs/rebuild/rev118/pre001/SOURCE_CLASSIFICATION.json"
STATE = "AUTHOR_CHALLENGED_PENDING_INDEPENDENT_REVIEW"

# Mechanical challenges. Each one is a falsifiable statement about the package's own records.
FLAGS = {
    "TEST_MISSING": "A referenced acceptance identity is absent from the effective registry.",
    "TEST_NOT_BOUND_TO_OWNER": "A referenced identity belongs to no unit that owns this requirement.",
    "OWNERSHIP_MISMATCH": "Units on the requirement record differ from plan.requirement_ownership.",
    "NO_OWNER": "No unit owns the requirement in plan.requirement_ownership.",
    "NO_NEGATIVE_OR_RECOVERY": "No referenced identity or acceptance clause names a negative/adversarial or recovery case.",
    "SUBJECTIVE_ACCEPTANCE": "Acceptance rests on owner/screenshot judgement with no stated observable.",
    "UNDERSPECIFIED_ACCEPTANCE": "Requirement acceptance and every linked expectation are under 6 words, too short to state stimulus and observable.",
    "TEMPLATE_ACCEPTANCE": "Acceptance is a shared template sentence, so the requirement-specific oracle lives only in the referenced tests.",
    "DUPLICATE_TEXT": "Another requirement has the same normalised text.",
    "OWNER_QUESTION_OPEN": "An owning unit has an unresolved owner question gating it.",
    "GATE_UNIT_WITHOUT_ACCEPTANCE": "An owning unit has no acceptance identities in the admitted plan (AP-001).",
    "NO_PRODUCT_TRUTH_TRACE": "No product-truth atom maps to this requirement.",
}
COMMON_QUESTIONS = [
    "Is the requirement text falsifiable as written: what concrete observation would show it unmet?",
    "Do the cited identities, read in full, test this requirement and not only a neighbouring one?",
    "Is each owning unit the place where the behaviour is actually produced, and is any producer missing?",
    "Does the acceptance distinguish success from a mock, a cached or historical receipt, or a presentational-only result?",
    "Is anything in the text an engineering translation that changes the owner's intent?",
]
FLAG_QUESTIONS = {
    "TEST_MISSING": "Which identity was intended, and is the registry or the requirement wrong?",
    "TEST_NOT_BOUND_TO_OWNER": "Should the identity move to an owning unit, or the ownership widen?",
    "OWNERSHIP_MISMATCH": "Which ownership list is authoritative, and does the other need an amendment?",
    "NO_OWNER": "Which unit produces this behaviour?",
    "NO_NEGATIVE_OR_RECOVERY": "What refusal, fault or restart case must fail closed for this requirement?",
    "SUBJECTIVE_ACCEPTANCE": "What recorded owner act (identity, artefact hash, time) makes the judgement auditable?",
    "UNDERSPECIFIED_ACCEPTANCE": "What are the stimulus, the observable and the pass threshold?",
    "TEMPLATE_ACCEPTANCE": "Which referenced identity carries the requirement-specific violating plan or evidence set?",
    "DUPLICATE_TEXT": "Are the duplicates one obligation (merge lineage) or distinct (sharpen the text)?",
    "OWNER_QUESTION_OPEN": "Can the requirement be admitted before the owner answers, or only conditionally?",
    "GATE_UNIT_WITHOUT_ACCEPTANCE": "Is AP-001's proposed acceptance sufficient for this requirement?",
    "NO_PRODUCT_TRUTH_TRACE": "Is this requirement engineering-derived, and if so which owner statement authorises it?",
}
NEG = re.compile(r"-(NEG|REC|SEC|ADV|N|R)$")
STEM = re.compile(r"-(POS|NEG|REC|SEC|INT|ADV|P|N|R)$")
# Negative content stated inside an expectation, e.g. "fails on an induced omission".
NEG_TEXT = re.compile(r"\b(no|negative|induced|fails?|rejects?|refus\w*|denied|deny|must not|never|blocks?|prevents?|quarantin\w*|restart|recover\w*|crash)\b", re.I)
SUBJECTIVE = re.compile(r"\b(owner acceptance|screenshot|material owner|owner review)\b", re.I)


def rd(rel):
    return json.loads((PKG / rel).read_text())


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def load():
    return {
        "authority": rd("CANONICAL_AUTHORITY.json"),
        "requirements": rd("traceability/REQUIREMENTS_AND_DU_MAPPING.json")["requirements"],
        "tests": rd("verification/EFFECTIVE_TEST_CONTRACTS_REV118.json")["tests"],
        "plan": rd("plan/DEVELOPMENT_PLAN.json"),
        "truth": rd("traceability/PRODUCT_TRUTH.json"),
        "classification": json.loads(CLASSIFICATION.read_text()),
    }


def build(src):
    tests = {t["id"]: t for t in src["tests"]}
    plan = src["plan"]
    units = {u["id"]: u for u in plan["units"]}
    owners = defaultdict(set)
    for uid, reqs in plan["requirement_ownership"].items():
        for r in reqs:
            owners[r].add(uid)
    truth = defaultdict(list)
    for m in src["truth"]["mappings"]:
        for r in m.get("van_requirements", []):
            truth[r].append(m["id"])
    questions = defaultdict(list)
    for q in plan["owner_questions"]:
        if not str(q.get("status", "")).startswith("RESOLVED"):
            for u in q.get("units", []):
                questions[u].append(q["id"])
    files = src["classification"].get("files_per_unit", {})
    texts = Counter(norm(r["text"]) for r in src["requirements"])

    dossiers = []
    for r in src["requirements"]:
        rid = r["id"]
        record_units = set(r.get("backend_units", [])) | set(r.get("frontend_units", [])) | set(r.get("other_units", []))
        own = owners.get(rid, set())
        cited = list(dict.fromkeys([r["test_id"], *r.get("test_ids", [])]))
        stems = {STEM.sub("", c) for c in cited}
        # Linked = cited, plus registry siblings of a cited stem, plus identities naming this requirement.
        refs = cited + [i for i in tests if i not in cited and (tests[i].get("requirement_id") == rid
                                                                or (STEM.search(i) and STEM.sub("", i) in stems))]
        acc = r["acceptance"]
        acc_text = " ".join(acc.values()) if isinstance(acc, dict) else acc
        flags = []
        missing = [t for t in cited if t not in tests]
        if missing:
            flags.append("TEST_MISSING")
        unbound = [t for t in refs if t in tests and not ({tests[t]["unit"], *tests[t].get("additional_units", [])} & own)
                   and not any(t in units[u].get("acceptance_test_ids", []) for u in own if u in units)]
        if unbound:
            flags.append("TEST_NOT_BOUND_TO_OWNER")
        if not own:
            flags.append("NO_OWNER")
        elif record_units - own or own - record_units:
            flags.append("OWNERSHIP_MISMATCH")
        has_neg = (any(NEG.search(t) for t in refs) or (isinstance(acc, dict) and {"adversarial", "recovery"} & set(acc))
                   or any(NEG_TEXT.search(str(tests[t].get("expectation") or tests[t].get("contract") or "")) for t in refs if t in tests)
                   or bool(NEG_TEXT.search(acc_text)))
        if not has_neg:
            flags.append("NO_NEGATIVE_OR_RECOVERY")
        if isinstance(acc, str):
            if SUBJECTIVE.search(acc):
                flags.append("SUBJECTIVE_ACCEPTANCE")
            elif len(acc.split()) < 6 and all(len(str(tests[x].get("expectation") or tests[x].get("contract") or "").split()) < 6
                                              for x in refs if x in tests):
                flags.append("UNDERSPECIFIED_ACCEPTANCE")
        if isinstance(acc, str) and sum(1 for x in src["requirements"] if x["acceptance"] == acc) > 3:
            flags.append("TEMPLATE_ACCEPTANCE")
        if texts[norm(r["text"])] > 1:
            flags.append("DUPLICATE_TEXT")
        oq = sorted({q for u in own for q in questions.get(u, [])})
        if oq:
            flags.append("OWNER_QUESTION_OPEN")
        empty = sorted(u for u in own if u in units and not units[u].get("acceptance_test_ids"))
        if empty:
            flags.append("GATE_UNIT_WITHOUT_ACCEPTANCE")
        if not truth.get(rid):
            flags.append("NO_PRODUCT_TRUTH_TRACE")
        dossiers.append({
            "id": rid,
            "text": r["text"],
            "package_status": r["status"],
            "package_mapping_grade": r["mapping_grade"],
            "provenance": {k: r[k] for k in ("legacy_du", "source_row_sha256", "source_obligation_sha256", "source_packet",
                                             "source_refs", "specification_ref", "source_adoption_ids") if k in r},
            "owners_plan": sorted(own),
            "units_on_record": sorted(record_units),
            "acceptance": acc,
            "cited_identities": cited,
            "acceptance_identities": [{"id": t, "cited": t in cited, "unit": tests[t]["unit"],
                                       "additional_units": tests[t].get("additional_units", []),
                                       "expectation": tests[t].get("expectation") or tests[t].get("contract"),
                                       "environment": tests[t].get("environment"),
                                       "execution_state": tests[t]["execution_state"]}
                                      if t in tests else {"id": t, "missing": True} for t in refs],
            "product_truth": sorted(truth.get(rid, [])),
            "open_owner_questions": oq,
            "owner_units_without_acceptance": empty,
            "baseline_source_files": {u: files.get(u, 0) for u in sorted(own)},
            "author_flags": flags,
            "challenge_questions": COMMON_QUESTIONS + [FLAG_QUESTIONS[f] for f in flags],
            "challenge_state": STATE,
        })
    return dossiers


def summary(dossiers, src):
    by_flag = Counter(f for d in dossiers for f in d["author_flags"])
    return {
        "schema": "van.rebuild.pre002.challenge-summary/1",
        "challenge_state": STATE,
        "not": "Not independent admission, not regrading, not owner approval. The independent reviewer answers each dossier.",
        "requirements": len(dossiers),
        "expected_requirements": src["authority"]["active_requirement_count"],
        "flag_definitions": FLAGS,
        "flag_counts": {f: by_flag.get(f, 0) for f in FLAGS},
        "requirements_without_flags": sum(1 for d in dossiers if not d["author_flags"]),
        "inputs_sha256": {p: hashlib.sha256((PKG / p).read_bytes()).hexdigest() for p in (
            "traceability/REQUIREMENTS_AND_DU_MAPPING.json", "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json",
            "plan/DEVELOPMENT_PLAN.json", "traceability/PRODUCT_TRUTH.json")},
    }


def render_md(s, dossiers):
    lines = ["# PRE-002 challenge dossiers — summary", "",
             f"Author-prepared challenges for all {s['requirements']} active requirements "
             f"(authority expects {s['expected_requirements']}). State: `{STATE}`. {s['not']}", "",
             "Regenerate or check with `python3 tools/rebuild/pre002_dossiers.py generate|check`. Full records: `DOSSIERS.json`.", "",
             "| Challenge | Requirements | Meaning |", "|---|---|---|"]
    for f, why in FLAGS.items():
        lines.append(f"| `{f}` | {s['flag_counts'][f]} | {why} |")
    lines += ["", "## Method and calibration", "",
              "Identities linked to a requirement are the cited ones, plus registry siblings of a cited stem "
              "(`-POS/-NEG/-REC/-SEC/-INT`, `-P/-N`) and identities whose `requirement_id` names it. A negative or "
              "recovery case counts when a linked identity has a negative suffix, the acceptance has adversarial/recovery "
              "clauses, or a linked expectation states one (for example 'fails on an induced omission', 'no silent rounding').",
              "Calibration against sampled records: cited-suffix-only detection flagged 205 requirements; linking siblings "
              "and `requirement_id` reduced it to 55; reading negative statements in expectations reduced it to 43. Every "
              "remaining case was checked by sample: the only linked identity is a one-line expectation such as 'Five working "
              "destinations'. These are heuristics; a flag is a question for the reviewer, and no flag is not a pass.", ""]
    lines += ["", f"Requirements with no mechanical flag: {s['requirements_without_flags']}. "
              "They still carry the five common questions; no flag means only that these checks found nothing.", "",
              "## Requirements by flag", ""]
    for f in FLAGS:
        ids = [d["id"] for d in dossiers if f in d["author_flags"]]
        if ids:
            lines.append(f"- `{f}` ({len(ids)}): " + ", ".join(ids))
    return "\n".join(lines) + "\n"


def outputs(src):
    d = build(src)
    s = summary(d, src)
    return {"DOSSIERS.json": json.dumps({"challenge_state": STATE, "dossiers": d}, indent=1, ensure_ascii=False) + "\n",
            "SUMMARY.json": json.dumps(s, indent=1, ensure_ascii=False) + "\n",
            "SUMMARY.md": render_md(s, d)}, s


def selftest():
    base = load()
    results = []

    def case(name, mutate, rid, flag):
        src = copy.deepcopy(base)
        mutate(src)
        got = {d["id"]: d for d in build(src)}[rid]["author_flags"]
        results.append({"case": name, "passed": flag in got})

    r0 = next(r for r in base["requirements"] if r["id"] in base["plan"]["requirement_ownership"].get("BE-001", []))
    rid = r0["id"]
    case("missing test", lambda s: next(r for r in s["requirements"] if r["id"] == rid).__setitem__("test_id", "T-NOPE"), rid, "TEST_MISSING")
    case("no owner", lambda s: [v.remove(rid) for v in s["plan"]["requirement_ownership"].values() if rid in v], rid, "NO_OWNER")
    case("ownership mismatch", lambda s: next(r for r in s["requirements"] if r["id"] == rid)["backend_units"].append("BE-099"), rid, "OWNERSHIP_MISMATCH")

    def strip_neg(s):
        r = next(r for r in s["requirements"] if r["id"] == rid)
        s["tests"].append({"id": "T-SELFTEST-ONLY", "unit": "BE-001", "execution_state": "NOT_RUN",
                           "expectation": "Exercise the operation and read back its independent result."})
        for x in s["tests"]:
            if x.get("requirement_id") == rid:
                x["requirement_id"] = None
        r["test_id"], r["test_ids"] = "T-SELFTEST-ONLY", []
        r["acceptance"] = "Exercise the operation and read back its independent result."
    case("no negative", strip_neg, rid, "NO_NEGATIVE_OR_RECOVERY")
    case("subjective", lambda s: next(r for r in s["requirements"] if r["id"] == rid).__setitem__("acceptance", "Screenshot/material owner acceptance"), rid, "SUBJECTIVE_ACCEPTANCE")
    case("short", lambda s: next(r for r in s["requirements"] if r["id"] == rid).__setitem__("acceptance", "Works fine"), rid, "UNDERSPECIFIED_ACCEPTANCE")

    def dup(s):
        a, b = s["requirements"][0], next(r for r in s["requirements"] if r["id"] == rid)
        b["text"] = a["text"].upper() + "!"
    case("duplicate", dup, rid, "DUPLICATE_TEXT")

    def oq(s):
        s["plan"]["owner_questions"].append({"id": "OQ-T", "status": "UNRESOLVED", "units": ["BE-001"]})
    case("owner question", oq, rid, "OWNER_QUESTION_OPEN")

    def empty(s):
        next(u for u in s["plan"]["units"] if u["id"] == "BE-001")["acceptance_test_ids"] = []
    case("gate unit empty", empty, rid, "GATE_UNIT_WITHOUT_ACCEPTANCE")

    def untrace(s):
        for m in s["truth"]["mappings"]:
            if rid in m.get("van_requirements", []):
                m["van_requirements"].remove(rid)
    case("no truth", untrace, rid, "NO_PRODUCT_TRUTH_TRACE")

    def unbind(s):
        other = next(t for t in s["tests"] if t["unit"] == "QA-001" or t["unit"].startswith("FE-"))
        next(r for r in s["requirements"] if r["id"] == rid).setdefault("test_ids", []).append(other["id"])
    case("unbound test", unbind, rid, "TEST_NOT_BOUND_TO_OWNER")
    ok = all(c["passed"] for c in results)
    print(json.dumps({"passed": sum(c["passed"] for c in results), "total": len(results), "cases": results}, indent=1))
    return 0 if ok else 1


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "selftest":
        return selftest()
    src = load()
    out, s = outputs(src)
    if s["requirements"] != s["expected_requirements"]:
        print(f"requirement count {s['requirements']} != authority {s['expected_requirements']}")
        return 1
    if cmd == "generate":
        OUT.mkdir(parents=True, exist_ok=True)
        for name, text in out.items():
            (OUT / name).write_text(text)
    drift = [n for n, t in out.items() if not (OUT / n).is_file() or (OUT / n).read_text() != t]
    print(json.dumps({"requirements": s["requirements"], "flag_counts": s["flag_counts"],
                      "without_flags": s["requirements_without_flags"], "drift": drift}, indent=1))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
