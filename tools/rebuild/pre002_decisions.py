#!/usr/bin/env python3
"""Deduplicated owner-decision register for PRE-002, with verified requirement dependencies.

The dossier screen linked a requirement to every open question on any of its owning units (402 pairs).
This tool classifies each pair: a topical screen first, then the author's explicit overrides after
reading each DIRECT pair and the narrowly scoped UNIT_SHARED pairs. Options and recommendations come from
the master's own framing; no financial value, signature or permission is invented.

  python3 tools/rebuild/pre002_decisions.py generate|check
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "docs/rebuild/rev118/pre002/OWNER_DECISION_REGISTER.json"
DOSSIERS = ROOT / "docs/rebuild/rev118/pre002/challenge/DOSSIERS.json"
OUT = ROOT / "docs/rebuild/rev118/pre002/challenge/review/DECISION_REGISTER.json"
MASTER = ROOT / "docs/review-inputs/van-rev115/package/VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_18_20261021.md"
STATE = "AUTHOR_PREPARED_PENDING_OWNER_DECISION_AND_INDEPENDENT_CHALLENGE"

TOPIC = {
 "OQ-01": r"manual.{0,40}(budget|risk)|per-strategy budget|manual risk|manual adds",
 "OQ-02": r"\bATR\b|stop (policy|placement)|stop.{0,20}instrument class|initial stop|stop and optional TP",
 "OQ-03": r"demo (before|acceptance|period)|demo before live",
 "OQ-05": r"signed decision record|non-self-issued|owner signature|scope lock",
 "OQ-06": r"news|calendar|licen",
 "OQ-07": r"missing.?stop|unprotected|re-?attach|flatten|stop confirmation|protection parity|per-fill protection|SL/TP management|dead-man|recovery priority|stop/amend|unknown-order",
 "OQ-08": r"shadow|news path|D4|D5",
 "OQ-09": r"news.{0,30}risk|risk increase|materiality|multiplier|D1",
 "OQ-11": r"feed|bundle",
 "OQ-12": r"event strateg|daily cap|news trading|ARMED|armed release",
 "OQ-13": r"behaviou?r(al)? (notice|diagnostic)|trading-behaviour",
 "OQ-14": r"chart|renderer",
 "OQ-15": r"delet|archiv|grace",
 "OQ-16": r"reporting currency|base currency|combined|multi-broker|portfolio projection|portfolio view",
 "OQ-17": r"replay",
 "OQ-18": r"account lifecycle|account editing|account creation|account profile|reconcile exact function",
 "OQ-19": r"deposit|withdraw|rail|funding and account deletion",
 "OQ-20": r"temperament|trading mode",
 "OQ-21": r"lockout|cooldown|probation",
 "OQ-CRYPTO-01": r"crypto|exchange/product|spot|venue (filters|capability)|CEX",
 "OQ-SO-01": r"self-optimi|estimator|learningboundary|learned.state|learned policy|operational vs learned|urgency cannot fall back|hierarchical fallback",
}
# After reading every DIRECT pair and the narrow UNIT_SHARED lists: (oq, requirement) -> relation.
OVERRIDE = {
 ("OQ-07", "VAN-NX-062"): "UNIT_SHARED_ONLY", ("OQ-07", "VAN-CX-009"): "UNIT_SHARED_ONLY",
 ("OQ-07", "VAN-SO-002"): "UNIT_SHARED_ONLY", ("OQ-07", "VAN-SO-005"): "UNIT_SHARED_ONLY",
 ("OQ-07", "VAN-SO-014"): "UNIT_SHARED_ONLY", ("OQ-07", "VAN-RV-006"): "UNIT_SHARED_ONLY",
 ("OQ-07", "VAN-RV-008"): "UNIT_SHARED_ONLY", ("OQ-07", "VAN-EL-005"): "UNIT_SHARED_ONLY",
 ("OQ-05", "VAN-NX-BF-011"): "UNIT_SHARED_ONLY", ("OQ-05", "VAN-ML-REQ-003"): "UNIT_SHARED_ONLY",
 ("OQ-05", "VAN-HVA-032"): "UNIT_SHARED_ONLY",
 ("OQ-14", "VAN-CX-020"): "UNIT_SHARED_ONLY", ("OQ-14", "VAN-LEAN-006"): "UNIT_SHARED_ONLY",
 ("OQ-16", "VAN-SO-040"): "UNIT_SHARED_ONLY",
 ("OQ-21", "VAN-CX-016"): "UNIT_SHARED_ONLY",
 ("OQ-19", "VAN-CRYPTO-004"): "UNIT_SHARED_ONLY",
 ("OQ-02", "VAN-NX-027"): "DIRECT", ("OQ-02", "VAN-NX-010"): "DIRECT", ("OQ-01", "VAN-NX-031"): "DIRECT",
 ("OQ-09", "VAN-NX-032"): "DIRECT", ("OQ-SO-01", "VAN-RV-006"): "UNIT_SHARED_ONLY",
 ("OQ-SO-01", "VAN-SO-022"): "UNIT_SHARED_ONLY", ("OQ-CRYPTO-01", "VAN-SO-005"): "UNIT_SHARED_ONLY", ("OQ-11", "VAN-NX-013"): "DIRECT", ("OQ-06", "VAN-NX-038"): "UNIT_SHARED_ONLY",
}

# id -> (class, options, recommendation, proceeds_before_decision)
DECIDE = {
 "OQ-01": ("OWNER_FINANCIAL_POLICY", ["Set owner.manual risk budget in the next signed mandate (a value at or below max_risk_per_trade)"],
   "Owner sets the value; master §7.4.2 already bounds it (never above max_risk_per_trade; shares 25/50/75/100%; counts toward account limits).",
   "BE-011 builds ManualStopPolicy/ManualIntentFactory with the budget read from the signed mandate; manual entry stays refused until a mandate includes owner.manual."),
 "OQ-02": ("OWNER_FINANCIAL_POLICY", ["Owner-signed ATR multiple per instrument class"],
   "Owner sets multiples; engineering supplies measured stop-out statistics per class from backtests to inform the choice.",
   "Policy table, validation (venue stop/freeze level, never widened by quantisation) and tests with fixture multiples; no live value."),
 "OQ-03": ("OWNER_FINANCIAL_POLICY", ["Demo duration and/or trade-count criteria before LIMITED_LIVE manual trading"],
   "Owner sets the criterion; master recommends demo first, then LIMITED_LIVE after owner signature.",
   "All manual-trading code and DEMO_TRADER operation; only the LIMITED_LIVE promotion waits."),
 "OQ-05": ("OWNER_SIGNATURE_MECHANISM", ["Use an existing trusted signed mechanism to approve the scope lock (see pre003/F15_AND_IDENTITY_REQUIREMENTS.md and the OQ-05 recommendation)"],
   "See the OQ-05 mechanism recommendation in pre003; no new signature format.",
   "Nothing implementation-bearing: PRE-003 cannot exit without it."),
 "OQ-06": ("OWNER_PROCUREMENT", ["Select licensed news/calendar providers after current API, licence and latency evidence"],
   "Owner selects after BE-014 produces current measured evidence; vendor research figures are historical, not quotes.",
   "Provider-neutral ingest adapters, source health and cross-checking against public/official sources; no purchase."),
 "OQ-07": ("OWNER_FINANCIAL_POLICY", ["A: keep immediate flatten + kill switch for automated trades (current router, F-031)",
                                      "B: apply the Rev1.2 re-read → re-attach (≤2 attempts, seconds) → flatten sequence to automated trades too"],
   "Master states the trade-off: a few seconds' exposure versus a guaranteed spread cost and a halted account. Author recommends B for parity with manual trades, with PROTECTION_UNCONFIRMED shown as full exposure at risk; the choice is the owner's.",
   "Both paths are implemented behind the policy and tested; manual trades already use the sequence by canon."),
 "OQ-08": ("OWNER_LIVE_PROMOTION", ["Sign promotion of each news path D4/D5 from shadow after per-path evidence"],
   "Per-path owner signature by design; not a blocker.", "Shadow operation and evidence collection for every path."),
 "OQ-09": ("OWNER_FINANCIAL_POLICY", ["Keep: news never directly increases risk (D1–D6 reduce/defer; D7 creates trades only via validated strategies)", "Change: allow direct size increase"],
   "Master recommends keeping the rule; author concurs (a direct increase bypasses strategy evidence).",
   "D1–D7 implementation under the keep rule, which is the safe default the canon already describes."),
 "OQ-11": ("OWNER_PROCUREMENT", ["Choose the feed bundle and authorize its monthly budget"],
   "Owner decides after measured latency/terms evidence; the master's $230–650/month is a historical estimate.",
   "Ingest with free/official sources; paid feeds admitted later without code change."),
 "OQ-12": ("OWNER_FINANCIAL_POLICY", ["Event strategies, budget, daily cap and first classes for news trading"],
   "Owner signs per class after paper and shadow evidence (§8.10.9).", "Bundle mechanics, arming proofs, paper and shadow."),
 "OQ-13": ("TECHNICAL_WITH_OWNER_COPY_APPROVAL", ["Engineering defines the calibration method; owner approves owner-facing wording"],
   "Not a START blocker for BE-022: calibration is an engineering method; wording is presentation, after BG-001.",
   "BE-022 diagnostics payload, calibration evaluation; copy drafted in UX later."),
 "OQ-14": ("TECHNICAL_DECISION_WITHIN_AUTHORITY", ["Native canvas", "New native engine", "Qualified web engine"],
   "Resolved as an engineering decision by measurement after BG-001 against §15.1 budgets (60 fps chart gestures on S24, lifecycle soak); the renderer-independent capability contract makes any choice swappable. Not an owner question.",
   "All backend chart contracts (BE-018) and the capability contract; renderer selection happens in FE-007 after BG-001."),
 "OQ-15": ("OWNER_RETENTION_POLICY", ["7 days (older text)", "30 days (source record recommendation)", "Other owner-selected duration"],
   "Owner selects; author notes 30 days gives more recovery time for an accidental delete while credentials are destroyed immediately either way.",
   "Grace period implemented as a signed parameter; delete blocked by open exposure regardless."),
 "OQ-16": ("OWNER_PREFERENCE", ["USD", "Another base currency"],
   "Display preference only (limits stay per account). Author suggests USD, the denomination of most broker accounts, but the owner chooses.",
   "Combined view with an explicit base-currency parameter and FX source/time; no money effect."),
 "OQ-17": ("OWNER_PRODUCT_SCOPE", ["Practice actions in replay are simulation-only (no broker route)", "Broader scope"],
   "Recommend simulation-only; any broker route from replay would contradict §18.2 'never execute from a chart' spirit.",
   "Replay sandbox with simulation-only actions."),
 "OQ-18": ("RESOLVED_BY_EXISTING_OWNER_INSTRUCTION", ["Retain as migration baseline (consolidation)", "Reject"],
   "Already settled: feature/rea-trading-accounts-tactile-20261015 is a selected source input (CONSOLIDATION_STATE.json source_inputs, 3b2c9e04) and existing Android code remains the migration baseline per the owner's standing instruction; its presentation is not frontend authority before BG-001.",
   "Everything; this is not an open question."),
 "OQ-19": ("OWNER_PROCUREMENT_AND_MONEY", ["Select the first funding provider rail and its sandbox authority"],
   "Owner selects; master rollout: one rail in sandbox/demo first, then reversal reconciliation; no production credentials during preparation.",
   "Funding ledger, hosted-flow state machine and sandbox adapters."),
 "OQ-20": ("OWNER_FINANCIAL_POLICY", ["Sign temperament percentage values and live evidence thresholds"],
   "Owner signs after backtest/walk-forward per mode (DU-30); AGGRESSIVE stays unbound until an edge-evidence producer qualifies.",
   "Mode mechanics, passive monitoring and refusal logic."),
 "OQ-21": ("OWNER_RUNTIME_SIGNATURE", ["Sign runtime activation of the already-accepted OD-39 values"],
   "Values are decided (24 h cooldown, ×0.5 probation, >2 cooldowns/7 d escalation); only the runtime signing act remains.",
   "All lockout code (defaults already equal OD-39 values)."),
 "OQ-CRYPTO-01": ("OWNER_OR_PROVIDER_DECISION", ["Select the initial eligible spot exchange/account/product from currently permitted access"],
   "Owner selects from accounts already held/permitted; no procurement inferred.",
   "Exchange-neutral capability matrix, filters, precision and adapters against public/sandbox endpoints."),
 "OQ-SO-01": ("OWNER_FINANCIAL_ACTIVATION", ["Approve the operational policy domain, estimator/update rules, bounds and qualification before consequential use"],
   "Owner approval before consequential use, by design; not a build blocker.",
   "Full self-optimization machinery in shadow/qualification without financial effect."),
}


def main(argv):
    reg = {q["id"]: q for q in json.loads(REG.read_text())["questions"]}
    dossiers = json.loads(DOSSIERS.read_text())["dossiers"]
    master = MASTER.read_text()
    rx = {k: re.compile(v, re.I) for k, v in TOPIC.items()}
    problems = []
    if set(DECIDE) != set(reg):
        problems.append(f"decision coverage differs: {sorted(set(DECIDE) ^ set(reg))}")
    deps = {q: {"DIRECT": [], "UNIT_SHARED_ONLY": []} for q in reg}
    seen = set()
    for d in dossiers:
        blob = " ".join([d["text"], json.dumps(d["acceptance"])] +
                        [str(a.get("expectation") or "") for a in d["acceptance_identities"] if a.get("cited")])
        for q in d["open_owner_questions"]:
            rel = OVERRIDE.get((q, d["id"])) or ("DIRECT" if rx[q].search(blob) else "UNIT_SHARED_ONLY")
            deps[q][rel].append(d["id"]); seen.add((q, d["id"]))
    stale = [k for k in OVERRIDE if k not in seen]
    if stale:
        problems.append(f"overrides for pairs that do not exist: {stale}")
    if problems:
        print("\n".join(problems)); return 1
    rows = []
    for q in sorted(reg, key=lambda s: (len(s), s)):
        cls, options, rec, proceed = DECIDE[q]
        rows.append({"id": q, "question": reg[q]["text"], "gate": reg[q]["gate"], "units": reg[q]["units"],
                     "class": cls, "cited_in_master": bool(re.search(rf"\b{re.escape(q)}\b", master)),
                     "verified_dependent_requirements": sorted(deps[q]["DIRECT"]),
                     "unit_shared_only_count": len(deps[q]["UNIT_SHARED_ONLY"]),
                     "options": options, "author_recommendation": rec, "can_proceed_before_decision": proceed})
    direct_reqs = sorted({r for q in deps for r in deps[q]["DIRECT"]})
    counts = {"questions": len(rows), "pairs": sum(len(v["DIRECT"]) + len(v["UNIT_SHARED_ONLY"]) for v in deps.values()),
              "direct_pairs": sum(len(v["DIRECT"]) for v in deps.values()),
              "requirements_with_a_real_dependency": len(direct_reqs),
              "requirements_flagged_by_screen": len({d["id"] for d in dossiers if d["open_owner_questions"]}),
              "by_class": {}}
    for r in rows:
        counts["by_class"][r["class"]] = counts["by_class"].get(r["class"], 0) + 1
    owner = [r["id"] for r in rows if r["class"] not in ("TECHNICAL_DECISION_WITHIN_AUTHORITY", "RESOLVED_BY_EXISTING_OWNER_INSTRUCTION", "TECHNICAL_WITH_OWNER_COPY_APPROVAL")]
    out = {"schema": "van.rebuild.pre002.decision-register/1", "state": STATE,
           "method": "Pairs from dossier open_owner_questions; topical screen then explicit author overrides after reading every DIRECT pair "
                     "and every UNIT_SHARED pair for the narrowly scoped questions. Options and recommendations follow the master's framing.",
           "counts": counts, "remaining_owner_decisions": owner, "decisions": rows}
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    if (argv[1] if len(argv) > 1 else "check") == "generate":
        OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(text)
    drift = not OUT.is_file() or OUT.read_text() != text
    print(json.dumps({"counts": counts, "remaining_owner_decisions": len(owner), "drift": drift}))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
