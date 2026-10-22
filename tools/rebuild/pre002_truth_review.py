#!/usr/bin/env python3
"""Author-prepared review of requirements without a Product Truth link (dossier flag
NO_PRODUCT_TRUTH_TRACE). Distinguishes missing required traceability from requirements governed by
another authoritative registry. No link is created: candidate atoms are listed for the reviewer and
owner, because Product Truth is owner authority.

  python3 tools/rebuild/pre002_truth_review.py generate|check
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "docs/review-inputs/van-rev115/package"
OUT = ROOT / "docs/rebuild/rev118/pre002/challenge/review/PRODUCT_TRUTH_TRACE_REVIEW.json"
STATE = "AUTHOR_REVIEWED_PENDING_INDEPENDENT_CHALLENGE"

SCOPE = ("PRODUCT_TRUTH.json holds 22 owner-intent atoms (18 owner-conversation candidates PENDING_OWNER_FREEZE, 4 recorded "
         "owner instructions of 2026-10-18). The master's F0_OWNER_INTENT_PRODUCT_TRUTH gate requires 'exact latest owner "
         "backend-first direction, original design hashes, signed final scope/decisions and full feature coverage', and "
         "VAN-PT-18 defines the chain requirements → Product Truth → DUs. So an owner-facing product requirement needs a "
         "Product Truth trace; an engineering correction or directive-governed contract may instead trace to its own "
         "authoritative registry.")

# family -> (classification, governing registries, reasoning)
FAMILY = {
 "VAN-CX": ("COVERED_BY_OTHER_AUTHORITATIVE_REGISTRY",
   ["contracts/CORRECTIVE_IMPLEMENTATION_CONTRACTS.json", "verification/GAP_CLOSURE_REGISTER.json", "consolidation/IMPLEMENTATION_ADMISSION_REGISTER.json"],
   "Consolidation corrective contracts (graded CONSOLIDATION_CORRECTION_PENDING_INDEPENDENT_REVIEW). They specify how existing intent is met correctly (protection parity, limit-price invariants, expiry propagation, authority) rather than adding owner product intent; every one appears in all three governing registries."),
 "VAN-HVA": ("COVERED_BY_OTHER_AUTHORITATIVE_REGISTRY",
   ["traceability/HIGH_VALUE_ADOPTION_CROSSWALK.json", "traceability/REVIEW_FINDINGS_DISPOSITION.json", "verification/GAP_CLOSURE_REGISTER.json"],
   "Owner-directed high-value trading adoptions with source_adoption_ids, all 32 present in the adoption crosswalk and findings disposition. Owner intent is carried by the directive registry; when Product Truth is frozen it should reference that directive (candidate VAN-PT-07, VAN-PT-SO-01) rather than restate each adoption."),
 "VAN-EL": ("COVERED_BY_OTHER_AUTHORITATIVE_REGISTRY",
   ["traceability/REV116_REQUIREMENTS.json", "contracts/self_optimization/EXPERIENCE_LEARNING_CONTRACT.json", "verification/REV116_ACCEPTANCE_CONTRACTS.json"],
   "Owner-directed experience-learning requirements (source_refs to the 2026-10-18 owner direction) carried by the Rev1.16 registry and contract. Closest atom VAN-PT-SO-02; link is an admission act, not made here."),
 "VAN-JM": ("COVERED_BY_OTHER_AUTHORITATIVE_REGISTRY",
   ["traceability/REV117_REQUIREMENTS.json", "contracts/self_optimization/MODEL_USE_CONTRACT.json", "verification/REV117_ACCEPTANCE_CONTRACTS.json"],
   "Owner-directed Jev/model hardening (OWNER_JEV_ARGON_DEEPSEEK_20261018) carried by the Rev1.17 registry and contract. Closest atoms VAN-PT-SO-01/SO-02."),
 "VAN-ML-REQ": ("COVERED_BY_ORIGINAL_FORECAST_PROVENANCE",
   ["traceability/FORECAST_PACKET_CROSSWALK.json", "lineage/forecast_rev1_1/plan/REQUIREMENTS.json", "lineage/forecast_rev1_1/plan/IMPLEMENTATION_PLAN.json"],
   "All 90 requirement hashes and 48 packet hashes reproduce from the bundled original JSON records using json.dumps(record, sort_keys=True, ensure_ascii=False), UTF-8 and default separators. The previous unverifiable-provenance claim was an instrument error. tools/rebuild/forecast_provenance.py checks the hashes, mappings and retained obligations without changing source or recorded digests. This establishes documentary provenance, not independent admission or product behavior."),
 "VAN-NX-BF": ("MISSING_REQUIRED_TRACE_ATOM_ABSENT",
   [],
   "Backend-first clauses. F0 names the owner's backend-first direction as part of Product Truth, but none of the 22 atoms states it (VAN-PT-18 describes the engineering chain, not backend-first ordering). Their source_row_sha256 equals sha256 of each clause's own text (18/18), so it is self-referential, not evidence of an external source. Owner action: add or confirm a backend-first atom; nothing is linked here."),
}

# The 14 owner-facing NX rows: candidate atoms for the reviewer (not links).
NX = {
 "VAN-NX-018": (["VAN-PT-14", "VAN-PT-12"], "Continuity of memory, decisions, research and automation is preservation of original capability (PT-14); no atom names memory explicitly."),
 "VAN-NX-034": (["VAN-PT-07"], "Owner trading-behaviour diagnostics sit in the full trading scope; no atom names diagnostics."),
 "VAN-NX-035": (["VAN-PT-07", "VAN-PT-SO-01"], "Owner pattern extraction into candidate strategies is strategy development under the trading scope and self-optimization."),
 "VAN-NX-039": (["VAN-PT-15", "VAN-PT-18"], "Look-ahead sentinel and network kill-switch in research tests protect against false results; an engineering-integrity requirement."),
 "VAN-NX-059": (["VAN-PT-10", "VAN-PT-07"], "History separating funding cash flow from trading P&L belongs to account/funds and trading history."),
 "VAN-NX-066": (["VAN-PT-13"], "Memory privacy, consent and erasure; PT-13 covers authority boundaries but no atom names privacy or erasure. Likely a genuine missing atom."),
 "VAN-NX-067": ([], "Owner-editable memory learning goals: no atom covers memory or learning goals. Genuine missing intent trace."),
 "VAN-NX-068": (["VAN-PT-14"], "Automation scheduling readback continues an original capability."),
 "VAN-NX-072": (["VAN-PT-SO-01", "VAN-PT-07"], "Continuous governed strategy development is self-optimization of the trading scope."),
 "VAN-NX-073": (["VAN-PT-LEAN-01", "VAN-PT-15"], "Ledger verification cost bounded by a verified anchor: lean runtime without weakening integrity."),
 "VAN-NX-074": (["VAN-PT-07", "VAN-PT-15"], "Per-instrument slippage bounds: execution correctness in the trading scope."),
 "VAN-NX-075": (["VAN-PT-15", "VAN-PT-13"], "Tick quantisation never widens the approved stop: protection integrity."),
 "VAN-NX-076": (["VAN-PT-07", "VAN-PT-15"], "Entry type executed as requested or refused, never coerced: execution truthfulness."),
 "VAN-NX-077": (["VAN-PT-17", "VAN-PT-13"], "Recoverable lockouts and owner-signed reset: mode/risk governance and owner authority."),
}


def main(argv):
    pt = json.loads((PKG / "traceability/PRODUCT_TRUTH.json").read_text())
    atoms = {a["id"] for a in pt["truth_atoms"]}
    reqs = {r["id"]: r for r in json.loads((PKG / "traceability/REQUIREMENTS_AND_DU_MAPPING.json").read_text())["requirements"]}
    forecast = {r["id"]: r for r in json.loads((PKG / "lineage/forecast_rev1_1/plan/REQUIREMENTS.json").read_text())["requirements"]}
    dossiers = json.loads((ROOT / "docs/rebuild/rev118/pre002/challenge/DOSSIERS.json").read_text())["dossiers"]
    flagged = [d["id"] for d in dossiers if "NO_PRODUCT_TRUTH_TRACE" in d["author_flags"]]
    problems, rows = [], []
    for rid in flagged:
        fam = rid.rsplit("-", 1)[0]
        if fam == "VAN-NX":
            if rid not in NX:
                problems.append(f"{rid} has no NX judgement"); continue
            cands, why = NX[rid]
            bad = [c for c in cands if c not in atoms]
            if bad:
                problems.append(f"{rid}: unknown atoms {bad}")
            rows.append({"id": rid, "classification": "MISSING_REQUIRED_TRACE", "candidate_atoms_not_linked": cands,
                         "reasoning": why, "state": STATE})
        elif fam in FAMILY:
            cls, regs, why = FAMILY[fam]
            for reg in regs:
                text = (PKG / reg).read_text()
                if reg.endswith(".json") and fam not in ("VAN-ML-REQ", "VAN-NX-BF") and f'"{rid}"' not in text:
                    problems.append(f"{rid} absent from {reg}")
            if fam == "VAN-ML-REQ" and reqs[rid]["source_packet"] not in (PKG / regs[0]).read_text():
                problems.append(f"{rid} packet absent from crosswalk")
            if fam == "VAN-ML-REQ" and hashlib.sha256(json.dumps(forecast[rid], sort_keys=True, ensure_ascii=False).encode()).hexdigest() != reqs[rid]["source_obligation_sha256"]:
                problems.append(f"{rid}: original forecast record hash does not match")
            if fam == "VAN-NX-BF" and hashlib.sha256(reqs[rid]["text"].encode()).hexdigest() != reqs[rid]["source_row_sha256"]:
                problems.append(f"{rid}: source_row_sha256 is not sha256(text) as recorded")
            rows.append({"id": rid, "classification": cls, "governing_registries": regs, "state": STATE})
        else:
            problems.append(f"{rid}: unhandled family {fam}")
    if problems:
        print("\n".join(problems)); return 1
    counts = {}
    for r in rows:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    out = {"schema": "van.rebuild.pre002.truth-trace-review/1", "state": STATE, "product_truth_scope": SCOPE,
           "families": {k: {"classification": v[0], "governing_registries": v[1], "reasoning": v[2]} for k, v in FAMILY.items()},
           "counts": counts, "reviews": rows,
           "owner_actions": ["Add or confirm a Product Truth atom for the backend-first direction (18 VAN-NX-BF clauses).",
                             "Decide atoms for memory privacy/learning goals (VAN-NX-066, VAN-NX-067), which no atom covers.",
                             "Admit or correct candidate atoms for the other 12 owner-facing NX rows."],
           "reviewer_actions": ["Independently reproduce all 90 requirement and 48 packet hashes with tools/rebuild/forecast_provenance.py check; original source and hashes are unchanged."]}
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    if (argv[1] if len(argv) > 1 else "check") == "generate":
        OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(text)
    drift = not OUT.is_file() or OUT.read_text() != text
    print(json.dumps({"counts": counts, "total": len(rows), "drift": drift}))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
