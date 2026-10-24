#!/usr/bin/env python3
"""Author-prepared semantic review of the requirements the dossier screen flagged
NO_NEGATIVE_OR_RECOVERY. The screen is an instrument; each judgement below was made by reading
the cited identity, the bound contexts' T-SURFACE identities, the owning units' domain NEG/REC
scenarios and the cited master sections. This script only checks the judgements against the
package (every referenced identity, context and section exists) and writes the review file.

  python3 tools/rebuild/pre002_neg_review.py generate|check
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "docs/review-inputs/van-rev115/package"
OUT = ROOT / "docs/rebuild/rev118/pre002/challenge/review/NEG_REC_REVIEW.json"
MASTER = "VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_18_20261021.md"
STATE = "AUTHOR_REVIEWED_PENDING_INDEPENDENT_CHALLENGE"

A, G = "ADEQUATE_EXISTING_COVERAGE", "GAP_REFINEMENT_PROPOSED"
SURF = "T-SURFACE identities of the bound contexts require stale/error, process death and deep-link restoration"

# (disposition, references, reasoning, proposed refinement or None, not-applicable note or None)
J = {
 "VAN-NX-001": (G, ["T-NX-001", "T-VAN-CX-020-NEG"],
   "Only owner screenshot acceptance. T-VAN-CX-020-NEG rejects legacy UI leaks and hidden safety states but nothing detects drift of the two locked authorities themselves.",
   "NEG: changing either locked dark/light authority (image bytes or derived tokens) without a new owner lock record fails the visual-lock check. REC: theme switch, process death and dynamic type keep both authorities' tokens; a rejected candidate restores the last locked authority.",
   "Recovery is narrow for a static artefact; the runtime theme-switch case is the applicable one."),
 "VAN-NX-003": (A, ["T-SURFACE-001", "T-SURFACE-002", "T-SURFACE-003", "T-SURFACE-006", "T-BE-030-NEG", "T-BE-030-REC"],
   f"{SURF}; WP-SC-MOBILE-NEG (T-BE-030-NEG) covers malformed/expired deep links, no network and low memory. Note: the Android ICU regex defect found in VanRoute.concreteRoute on 2026-10-21 lives on this path; T-NX-003 would catch it on device.", None, None),
 "VAN-NX-004": (A, ["T-SURFACE-001", "T-SURFACE-007", "T-SURFACE-102", "T-BE-030-NEG", "T-BE-030-REC", "master:18.2"],
   "WP-SC-HOME-NEG: stale task vs healthy market stream stays distinguishable, replay does not notify twice. §18.2: critical risk preempts a celebrating orb; orb tap with a pending A4 approval grants nothing.", None, None),
 "VAN-NX-006": (A, ["T-SURFACE-102", "T-SURFACE-103", "T-SURFACE-104", "T-SURFACE-105", "T-SURFACE-107", "T-BE-029-NEG", "T-BE-029-REC"],
   "WP-SC-FLOATING-NEG/REC: overlay denial, locked screen, service restart restriction, occlusion and battery saver use OS-compatible recovery without hidden mic capture.", None, None),
 "VAN-NX-008": (A, ["T-SURFACE-008", "T-SURFACE-019", "T-BE-030-NEG", "T-VAN-CX-020-NEG"],
   f"{SURF}; T-VAN-CX-020-NEG rejects unknown data that looks live; WP-SC-MOBILE-NEG covers no network and malformed deep links into the five destinations.", None, None),
 "VAN-NX-009": (A, ["T-SURFACE-021", "T-SURFACE-026", "T-BE-018-NEG", "T-BE-018-REC", "master:18.2"],
   "WP-SC-CHART-NEG/REC: reconnect gaps, renderer failure and malformed bridge inputs preserve precision and never execute from a chart. §18.2: quote stops while candles continue → STALE/OFFLINE, no synthetic tick.", None, None),
 "VAN-NX-010": (A, ["T-SURFACE-040", "T-SURFACE-041", "T-BE-009-NEG", "T-BE-009-REC", "master:18.2"],
   "WP-SC-ORDERS-NEG/REC: concurrent spend, partial fill, cancel race, unknown submission and restart preserve exposure and protection. §18.2 rows: fill without stop confirmation, close response lost (OUTCOME_UNKNOWN, no blind resend).", None, None),
 "VAN-NX-011": (A, ["T-SURFACE-010", "T-SURFACE-011", "T-BE-008-NEG", "T-BE-008-REC"],
   "BE-008 owns the requirement; WP-SC-MARKETS-NEG/REC: feed gap, delisting, alias collision, closure, entitlement denial, process death and duplicate alerts.", None, None),
 "VAN-NX-012": (A, ["T-SURFACE-072", "T-BE-014-NEG", "T-BE-014-REC", "master:18.2"],
   "WP-SC-NEWS-NEG: contradictory facts cannot create fabricated certainty. §18.2: an LLM-invented stop/probability/lot is rejected; deterministic facts only.", None, None),
 "VAN-NX-013": (A, ["T-SURFACE-072", "T-SURFACE-073", "T-BE-014-NEG", "T-BE-014-REC", "master:8.2#inherited"],
   "Inherited §8.2 (Live sources): a category below its minimum healthy sources shows 'news coverage degraded' and inside a high-impact window the gap is itself a risk; WP-SC-NEWS-NEG/REC.", None, None),
 "VAN-NX-014": (A, ["T-SURFACE-086", "T-SURFACE-087", "T-BE-023-NEG", "T-BE-023-REC"],
   "WP-SC-WORK-NEG/REC: stale revision, concurrent edit, failed review and lost cancellation never fabricate progress or dispatch twice; original task/job reconciled.", None, None),
 "VAN-NX-015": (A, ["T-SURFACE-086", "T-SURFACE-091", "T-BE-023-NEG", "master:18.2"],
   "WP-SC-WORK-NEG includes cycles and stale revisions. §18.2: moving a graph node is a layout change only; two agents claiming one task show a conflict, not a manufactured assignment.", None, None),
 "VAN-NX-017": (A, ["T-SURFACE-096", "T-SURFACE-097", "T-BE-024-NEG", "T-BE-024-REC", "master:18.2"],
   "WP-SC-AGENTS-NEG/REC: expired lease, late callback, revoked capability. §18.2: invalid/stale Muse provider approval refused with no click/retry side effect.", None, None),
 "VAN-NX-018": (A, ["T-SURFACE-108", "T-SURFACE-109", "T-BE-027-NEG", "T-BE-028-NEG", "T-BE-028-REC"],
   "BE-027 and BE-028 own the requirement. WP-SC-MEMORY-NEG: stale index, revoked source and backups cannot revive erased material; WP-SC-AUTOMATION-NEG/REC: missed schedule, overlapping run, timeout after effect reconcile before retry.", None, None),
 "VAN-NX-019": (A, ["T-SURFACE-112", "T-SURFACE-113", "T-BE-002-NEG", "T-BE-002-REC"],
   "WP-SC-BOOTSTRAP-NEG/REC: expired provisioning, rotated certificate, lost/replaced/revoked handset; an old device cannot regain authority. WP-SC-SETTINGS-NEG: stale setting revision and expired enrollment stay distinct.", None, None),
 "VAN-NX-020": (A, ["T-SURFACE-106", "T-BE-025-NEG", "T-BE-025-REC", "T-BE-026-NEG", "T-BE-026-REC", "T-BE-029-NEG"],
   "Owners include BE-025, BE-026 and BE-029. WP-SC-REMOTE-NEG (unknown click outcome, revoked lease), WP-SC-ARTEMIS-NEG (disconnect, wrong APK, stale result stay unknown/failed), WP-SC-VOICE-NEG.", None, None),
 "VAN-NX-022": (A, ["T-SURFACE-112", "T-VAN-CX-020-REC", "master:15.1#inherited"],
   "Inherited §15.1: escalation tiers degrade material effects while preserving status, text and controls; T-VAN-CX-020-REC reduces motion cost without removing semantics. A missed budget is a failing measurement by definition.", None, None),
 "VAN-NX-023": (A, ["T-VAN-CX-020-NEG", "T-VAN-CX-002-NEG", "T-VAN-LEAN-006-NEG", "T-VAN-CX-017-REC"],
   "T-VAN-CX-020-NEG rejects legacy UI leaking into new modules; T-VAN-CX-002-NEG rejects deleting a PR-only action; T-VAN-CX-017-REC reopens a unit when a missing capability is found.", None,
   "Recovery for a static admission check means reopening, which T-VAN-CX-017-REC provides."),
 "VAN-NX-024": (G, ["T-NX-024", "T-VAN-CX-019-NEG", "T-VAN-CX-019-REC"],
   "T-VAN-CX-019-NEG/REC (swapped revision, self-declared signature, reused device evidence) are bound to PRE-003 only. BQ-006/QA-005 re-verify at the release head but inherit no negative, so a stale or self-issued receipt at release time is untested.",
   "Owner addition: bind T-VAN-CX-019-NEG and T-VAN-CX-019-REC additionally to BQ-006 and QA-005, executed against the release head rather than inherited from the PRE-003 pass.", None),
 "VAN-NX-025": (G, ["T-NX-025", "T-BE-026-NEG", "T-BE-026-REC", "T-VAN-CX-019-NEG"],
   "The on-device acceptance unit QA-004 carries only T-VAN-CX-020. The Artemis negatives (disconnect, wrong APK, stale result must stay unknown/failed) are owned by BE-026, so the owner decision itself has no bound refusal case.",
   "Owner addition: bind T-BE-026-NEG and T-BE-026-REC additionally to QA-004; refine T-NX-025: an owner decision recorded against an APK digest other than the installed one, or against evidence from another build, is refused.", None),
 "VAN-NX-026": (G, ["T-NX-026"],
   "The identity requires the admission record to exist (39 REA ids and hashes, APK identities, static-only limits). Nothing tests refusal of a non-admitted record, a hash mismatch, or a static-only record cited as runtime evidence; MEMORY-family scenarios do not address research admission.",
   "NEG: a research record outside the admitted 39, a hash mismatch, or citing a static-only record as runtime/device evidence is refused by the REA gate. REC: a superseded record version invalidates dependent changes until re-admitted.", None),
 "VAN-NX-027": (A, ["T-SURFACE-041", "T-BE-009-NEG", "master:7.4.6#inherited", "master:18.2"],
   "Inherited §7.4 manual trading and §18.2 manual-trading rows: mandate absent → refused before preview; stop wider → refused; kill switch → entry refused while close/tighten work; double tap → one order; replayed biometric token refused. Note: T-NX-027 cites '§7.4', a number duplicated in the master (see AMBIGUITY).", None, None),
 "VAN-NX-030": (A, ["T-NX-030", "master:2.6"],
   "§2.6 (cited): native strings come from one catalogue built from the table and a lint rule rejects uncalibrated certainty wording in trading UI strings; that is the negative.", None,
   "Recovery does not apply: a static string catalogue has no runtime state to recover."),
 "VAN-NX-031": (A, ["T-BE-011-NEG", "master:7.4.6#inherited", "master:7.4.7#inherited", "master:18.2"],
   "Cited §7.4.6–§7.4.7 and §18.2: anti-martingale refusals at review, approval and submission; owner stop never widened on handover; take-back cancels unsent actions, reconciles in-flight ones under a new epoch and completes only after readback. T-BE-011-NEG restates them.", None, None),
 "VAN-NX-032": (A, ["T-SURFACE-074", "T-BE-014-NEG", "master:8.4#inherited"],
   "Inherited §8.4 (History comparison): fewer than 10 close analogues → EVIDENCE_THIN, MISSING marks kept; WP-SC-NEWS-NEG. T-NX-032 cites §8.4–§8.5, which are duplicated numbers (see AMBIGUITY).", None, None),
 "VAN-NX-033": (A, ["T-BE-017-NEG", "master:8.10.9#inherited"],
   "Cited §8.10.9 lists the bundle's negatives (early release value rejected, site lockup stands down without double-acting, spread above cap stands down, late entry refused, single or disagreeing sources); T-BE-017-NEG: SIGNED is not readiness; expiry disarms.", None, None),
 "VAN-NX-035": (A, ["T-SURFACE-085", "T-NX-035"],
   "The cited expectation is itself a refusal gate: candidates must pass deflated Sharpe, PBO and walk-forward before paper, so failing candidates are rejected; it learns from losers as well as winners.", None,
   "Recovery applies to the candidate pipeline's durable state and is carried by BE-022's generic T-BE-022-REC."),
 "VAN-NX-036": (A, ["T-BE-015-NEG", "master:8.2#inherited"],
   "Inherited §8.2: two prediction-market sources and markets below a liquidity floor are ignored; T-BE-015-NEG: missing marks stay missing and a thin sample cannot become calibrated probability; WP-SC-PREDICTION-NEG covers void/disputed resolution. T-NX-036 cites §8.2/§8.4, duplicated numbers (see AMBIGUITY).", None, None),
 "VAN-NX-038": (A, ["T-NX-038", "T-BE-014-NEG"],
   "The expectation is a gate (terms check and live probe per feed: a feed failing either is not added); WP-SC-NEWS-NEG covers an unavailable source.", None, None),
 "VAN-NX-041": (A, ["T-SURFACE-020", "T-BE-018-NEG", "T-BE-018-REC"],
   "500-cycle lifecycle test (leak/teardown negatives) plus WP-SC-CHART-NEG/REC renderer failure and reconnect gaps.", None, None),
 "VAN-NX-042": (A, ["T-NX-042", "T-BE-018-NEG"],
   "The expectation already names negatives the keyword screen missed: bridge fuzzing and a forbidden order call; renderer swap is the recovery path.", None, None),
 "VAN-NX-043": (A, ["T-SURFACE-022", "T-BE-018-NEG"],
   "Anchor round-trip, undo/redo and cross-device sync plus WP-SC-CHART-NEG workspace conflicts preserving precision.", None, None),
 "VAN-NX-048": (A, ["T-SURFACE-054", "T-BE-004-NEG", "T-BE-004-REC", "master:7.9.11#inherited"],
   "WP-SC-ACCOUNTS-NEG: observe-only access, KYC restriction, expired callback; §7.9.11 A1: link/OAuth attempts persist across app kill and a lost outcome is a visible retry/discard state.", None, None),
 "VAN-NX-049": (G, ["T-NX-049", "master:7.9.3#inherited", "master:7.9.10#inherited"],
   "T-NX-049 cites only §7.9.3, which states the rotation order (new secret → verify → swap → destroy). The failure case is in §7.9.10 ('rotation never leaves the account without valid credentials'), which only T-NX-051 cites, and only for F-033.",
   "Refine T-NX-049 to cite §7.9.10's rotation clause: a verification failure or crash mid-rotation keeps the old credential valid and records the attempt; a server/login change forces re-verification before trading.", None),
 "VAN-NX-050": (A, ["T-NX-050", "master:7.9.4#inherited"],
   "Cited §7.9.4: delete/disconnect blocked with open positions, working orders, in-flight funds, unknown outcomes or live leases, checked against fresh state; cancelling a deletion returns RELINK_REQUIRED and never revives credentials or a broker-closed account.", None, None),
 "VAN-NX-051": (A, ["T-NX-051", "T-BE-004-NEG", "master:7.9.10#inherited"],
   "Cited §7.9.10 F-033 regression: a withdrawal does not move drawdown tiers and a deposit does not mask a loss; WP-SC-ACCOUNTS-NEG: duplicate transfer and returned payment prevent false success.", None, None),
 "VAN-NX-052": (A, ["T-NX-052", "master:7.9.6#inherited", "master:7.9.7#inherited"],
   "Cited §7.9.6–§7.9.7: demo and live never sum; DEGRADED/AUTH_EXPIRED/BROKER_MAINTENANCE states, reconnection backs off and a lost connection with open positions raises Attention.", None, None),
 "VAN-NX-053": (A, ["T-VAN-CX-001-NEG", "T-VAN-CX-002-NEG", "T-VAN-CX-019-NEG", "T-VAN-CX-019-REC"],
   "PRE-002 owns T-VAN-CX-001-NEG (old plan, omitted producer rejected); signature negatives (self-declared signature_valid) and revoked-evidence recovery are T-VAN-CX-019-NEG/REC in the same PRE chain.", None, None),
 "VAN-NX-057": (A, ["T-SURFACE-055", "T-BE-004-NEG", "master:7.9.10#inherited"],
   "'REMOTE_CLOSED only on broker readback' is a no-false-closure negative; §7.9.10: OAuth cancel/timeout discard the attempt; investor-password MT5 accounts cannot send orders.", None, None),
 "VAN-NX-060": (A, ["T-NX-060", "master:15.1#inherited", "master:18.2", "T-BE-030-NEG"],
   "The requirement is itself a recovery requirement (process-death restore incl. pending provider and order references, inherited §15.1 device scope). §18.2: rotation with a popup open restores composition and anchor; WP-SC-MOBILE-NEG: low memory preserves state.", None, None),
 "VAN-NX-063": (A, ["T-SURFACE-004", "T-BE-030-NEG", "master:18.2"],
   "Expectation: sources cited, budget not exceeded, stale marked. §18.2: a model rewrite of a brief that adds a price is rejected and the template text shown.", None, None),
 "VAN-NX-066": (A, ["T-SURFACE-111", "T-BE-027-NEG", "T-BE-027-REC"],
   "Expectation: source deletion is not claimed as model unlearning; WP-SC-MEMORY-NEG/REC: stale index, derived cache and backups cannot silently revive erased material.", None, None),
 "VAN-NX-067": (G, ["T-NX-067", "T-BE-027-NEG"],
   "'Goal changes audited' is positive only, and WP-SC-MEMORY-NEG concerns erased material, not goal edits. No case covers an unauthorized edit, a stale revision, or a goal that widens data use beyond consent.",
   "NEG: a goal edit from a non-owner principal, against a stale goal revision, or widening data use beyond recorded consent is refused and audited. REC: concurrent edits resolve to one audited revision; restart preserves the last committed goal.", None),
}

AMBIGUITY_NOTE = ("The Rev1.18 master prefixes the whole-product contract (§1–§n) to the verbatim inherited specification, so "
                  "67 section numbers occur twice. Four identities cite such a number: T-NX-027 (§7.4), T-NX-032 (§8.4, §8.5), "
                  "T-NX-036 (§8.2, §8.4) and T-NX-037 (§8.3). Context shows the inherited section is meant in each case.")


def load():
    tests = {t["id"] for t in json.loads((PKG / "verification/EFFECTIVE_TEST_CONTRACTS_REV118.json").read_text())["tests"]}
    master = (PKG / MASTER).read_text().splitlines()
    heads = {}
    for i, line in enumerate(master, 1):
        m = re.match(r"^#{2,4}\s+(\d+(?:\.\d+)*)\.?\s", line)
        if m:
            heads.setdefault(m.group(1), []).append(i)
    flagged = [d["id"] for d in json.loads((ROOT / "docs/rebuild/rev118/pre002/challenge/DOSSIERS.json").read_text())["dossiers"]
               if "NO_NEGATIVE_OR_RECOVERY" in d["author_flags"]]
    return tests, heads, flagged


def build():
    tests, heads, flagged = load()
    problems = []
    if sorted(J) != sorted(flagged):
        problems.append(f"review covers {sorted(set(J) ^ set(flagged))} differently from the dossier flag set")
    rows = []
    for rid in flagged:
        if rid not in J:
            continue
        disp, refs, why, refine, na = J[rid]
        for ref in refs:
            if ref.startswith("master:"):
                num, _, which = ref[7:].partition("#")
                lines = heads.get(num, [])
                if not lines:
                    problems.append(f"{rid}: master section {num} not found")
                elif which == "inherited" and len(lines) < 2 and lines[0] < 1100:
                    problems.append(f"{rid}: §{num} has no inherited occurrence")
            elif ref not in tests:
                problems.append(f"{rid}: identity {ref} not in the effective registry")
        if disp == G and not refine:
            problems.append(f"{rid}: gap without a proposed refinement")
        rows.append({"id": rid, "disposition": disp, "references": refs, "reasoning": why,
                     "proposed_refinement": refine, "category_not_applicable": na, "state": STATE})
    counts = {A: sum(r["disposition"] == A for r in rows), G: sum(r["disposition"] == G for r in rows)}
    return {"schema": "van.rebuild.pre002.neg-rec-review/1", "state": STATE,
            "method": "Each flagged requirement read against its cited identity text, bound contexts' T-SURFACE identities, "
                      "owning units' WP domain NEG/REC scenarios (DOMAIN_SCENARIOS.json) and the cited master sections, with "
                      "duplicated section numbers resolved to the inherited specification where context requires.",
            "counts": counts, "citation_ambiguity": AMBIGUITY_NOTE, "reviews": rows}, problems


def main(argv):
    out, problems = build()
    if problems:
        print("\n".join(problems))
        return 1
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    if (argv[1] if len(argv) > 1 else "check") == "generate":
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text)
    drift = not OUT.is_file() or OUT.read_text() != text
    print(json.dumps({"counts": out["counts"], "drift": drift}))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
