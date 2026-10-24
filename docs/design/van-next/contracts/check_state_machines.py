#!/usr/bin/env python3
"""Model-check the VAN Next state machines (blueprint Rev 1.9, Amendment C; Rev 1.9b).

Rules, each proven by --selftest to fail when deliberately broken:
  R0 no duplicate machine IDs, states or (from, to) transitions (Rev 1.9b, NXA-03)
  R1 every state is reachable from the initial state
  R2 every non-terminal state has an outgoing transition (no dead ends)
  R3 every transition into a receipt state names the receipt it requires
  R4 every obligation transition (audit findings and owner decisions) is present
  R5 no forbidden transition is present
  R6 an unknown outcome never leads straight back to a sending state, and every
     exit from it requires a readback (no automatic resend)
  R7 every declared terminal / receipt / send state exists in the machine
  R8 the model's transition relation equals the approved transition list
     (VAN_TRANSITION_GUARDS_REV1_9B.json): no unlisted transition, no changed
     guard set, no listed transition missing (Rev 1.9b, NXA-01)
  R9 every proof a transition requires is a typed proof in that list (NXA-01)
  R10 every success state is reachable only through its mandatory waypoints
     (approval, submission, readback); held here, so it holds even if the
     approved list itself is edited (NXA-01)
  R11 the approved list's SHA-256 equals the hash pinned in the owner decision
     record (OD-32)

Obligations, forbidden transitions and waypoints live here, not in the JSON,
so editing a machine cannot quietly remove them.

Usage:
  python3 check_state_machines.py [machines.json]   # default: VAN_STATE_MACHINES_REV1_9.json
  python3 check_state_machines.py --selftest
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "VAN_STATE_MACHINES_REV1_9.json"
GUARDS = HERE / "VAN_TRANSITION_GUARDS_REV1_9B.json"
DECISIONS = HERE.parent / "VAN_NEXT_OWNER_DECISIONS_REV1.md"

OBLIGATIONS = {  # machine -> [(from, to, source)]
    "VAN-SM-ACCOUNT_LIFECYCLE": [
        ("UNLINK_REQUESTED", "RELINK_REQUIRED", "AUD-03/AUD-10 cancel deletion"),
        ("RESTRICTED", "REAUTH_PENDING", "AUD-03 recover from restriction"),
        ("REAUTH_PENDING", "LINKED_READ_ONLY", "AUD-03 recover after re-verification"),
        ("REMOTE_CLOSURE_PENDING", "REMOTE_CLOSURE_REFUSED", "AUD-03 refused closure"),
        ("REMOTE_CLOSURE_PENDING", "CLOSURE_OUTCOME_UNKNOWN", "AUD-03 unknown closure"),
        ("UNLINK_REQUESTED", "UNLINK_BLOCKED", "OD-25 exposure blocks unlink"),
    ],
    "VAN-SM-FUND_DEPOSIT": [
        ("SETTLED", "REVERSED", "AUD-03 compensating reversal"),
        ("SENT", "OUTCOME_UNKNOWN", "§7.9.12 timeout"),
        ("PENDING_SETTLEMENT", "SETTLED", "§7.9.12 settlement"),
    ],
    "VAN-SM-FUND_WITHDRAWAL": [
        ("PROVIDER_PENDING", "FAILED", "AUD-03 withdrawal FAILED"),
        ("PAID", "REVERSED", "AUD-03 compensating reversal"),
        ("QUOTED", "REFUSED_MARGIN", "AUD-05 under-margin refusal"),
        ("AUTHORIZED", "REFUSED_MARGIN", "AUD-05 recheck at submission"),
        ("SUBMITTED", "OUTCOME_UNKNOWN", "§7.9.12 timeout"),
    ],
    "VAN-SM-FUND_TRANSFER": [
        ("DEBIT_CONFIRMED", "SETTLED", "§7.9.12 both legs read back"),
        ("DEBIT_CONFIRMED", "INVESTIGATION_REQUIRED", "credit missing"),
    ],
    "VAN-SM-TRADE_ORDER": [
        ("CANCEL_PENDING", "PARTIAL", "AUD-03 cancel/fill race"),
        ("CANCEL_PENDING", "FILLED", "AUD-03 cancel/fill race"),
        ("CANCEL_PENDING", "OUTCOME_UNKNOWN", "AUD-03 lost cancel response"),
        ("CANCEL_PENDING", "CANCELLED", "cancel confirmed"),
        ("BROKER_PENDING", "REJECTED", "AUD-03"),
        ("BROKER_PENDING", "EXPIRED", "AUD-03"),
        ("BROKER_PENDING", "OUTCOME_UNKNOWN", "AUD-03"),
        ("MODIFY_PENDING", "PLACED", "AUD-03 modify confirmed or rejected"),
        ("PARTIAL", "CANCEL_PENDING", "AUD-03"),
    ],
    "VAN-SM-NEWS_ARMED_TICKET": [
        ("ARMED", "USED", "AUD-04 one use"),
        ("ARMED", "VOIDED", "AUD-04 void on policy/feed/quote change"),
        ("ARMED", "EXPIRED", "AUD-04 window"),
    ],
}

FORBIDDEN = {  # machine -> [(from, to, why)]
    "VAN-SM-ACCOUNT_LIFECYCLE": [
        ("RELINK_REQUIRED", "LINKED_READ_ONLY", "AUD-10 cancelled deletion must re-authenticate"),
        ("RELINK_REQUIRED", "ACTIVE_ELIGIBLE", "AUD-10 cancelled deletion must re-authenticate"),
        ("UNLINKED_LOCAL", "REMOTE_CLOSED", "local unlink is never remote closure"),
        ("UNLINK_REQUESTED", "REMOTE_CLOSED", "local unlink is never remote closure"),
    ],
    "VAN-SM-NEWS_ARMED_TICKET": [
        ("USED", "ARMED", "AUD-04 nonce is single use"),
        ("EXPIRED", "ARMED", "AUD-04 no revival"),
        ("VOIDED", "ARMED", "AUD-04 no revival"),
    ],
}

# machine -> {success state: states every path from the initial state must pass through}
WAYPOINTS = {
    "VAN-SM-ACCOUNT_LIFECYCLE": {
        "ACTIVE_ELIGIBLE": ["AUTH_PENDING", "LINKED_READ_ONLY"],
        "REMOTE_CLOSED": ["AUTH_PENDING"],
    },
    "VAN-SM-FUND_DEPOSIT": {
        "SETTLED": ["QUOTED", "AWAITING_OWNER", "AUTHORIZED", "PROVIDER_PENDING", "PENDING_SETTLEMENT"],
    },
    "VAN-SM-FUND_WITHDRAWAL": {
        "PAID": ["BENEFICIARY_VERIFIED", "QUOTED", "AWAITING_A4", "AUTHORIZED", "SUBMITTED", "PROVIDER_PENDING"],
    },
    "VAN-SM-FUND_TRANSFER": {
        "SETTLED": ["QUOTED", "AWAITING_A4", "AUTHORIZED", "SUBMITTED", "DEBIT_CONFIRMED"],
    },
    "VAN-SM-TRADE_ORDER": {
        s: ["RISK_REVIEW", "OWNER_REVIEW", "AUTHORIZED", "BROKER_PENDING"] for s in ("PLACED", "PARTIAL", "FILLED")
    },
    "VAN-SM-NEWS_ARMED_TICKET": {
        "USED": ["SIGNED", "ARMED"],
    },
}

REQUIRED_MACHINES = set(OBLIGATIONS)


def guards_of(t: dict) -> frozenset:
    return frozenset(x for x in t.get("requires", "").split("+") if x)


def pinned_guard_hash(decisions_text: str) -> str | None:
    m = re.search(r"^\|\s*TRANSITION_GUARDS\s*\|[^|]*\|\s*`?([0-9a-f]{64})`?\s*\|", decisions_text, re.M)
    return m.group(1) if m else None


def load_guards(guards_bytes: bytes | None = None, decisions_text: str | None = None) -> tuple[dict, list[str]]:
    """The approved transition list and any R11 finding about its pin."""
    gb = GUARDS.read_bytes() if guards_bytes is None else guards_bytes
    dt = (DECISIONS.read_text() if DECISIONS.exists() else "") if decisions_text is None else decisions_text
    out = []
    pin = pinned_guard_hash(dt)
    actual = hashlib.sha256(gb).hexdigest()
    if pin is None:
        out.append(f"{GUARDS.name}: R11 no TRANSITION_GUARDS hash pinned in the owner decision record")
    elif pin != actual:
        out.append(f"{GUARDS.name}: R11 approved list changed without re-approval (pinned {pin[:12]}, actual {actual[:12]})")
    return json.loads(gb), out


def check_guard_list(g: dict) -> list[str]:
    out = []
    for mid, rows in sorted(g.get("machines", {}).items()):
        ids, pairs = set(), set()
        for r in rows:
            if r["id"] in ids:
                out.append(f"{mid}: R0 duplicate approved transition ID {r['id']}")
            if (r["from"], r["to"]) in pairs:
                out.append(f"{mid}: R0 duplicate approved transition {r['from']}->{r['to']}")
            ids.add(r["id"])
            pairs.add((r["from"], r["to"]))
            for p in r["guards"]:
                if p not in g.get("proof_types", {}):
                    out.append(f"{mid}: R9 approved transition {r['id']} names untyped proof '{p}'")
    return out


def reachable_avoiding(init: str, trans: list, avoid: str) -> set:
    seen = set() if init == avoid else {init}
    todo = list(seen)
    while todo:
        x = todo.pop()
        for a, b in trans:
            if a == x and b != avoid and b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def check(doc: dict, guards: dict | None = None, guard_findings: list[str] | None = None) -> list[str]:
    """guards=None loads the approved list from disk and checks its pin (R11)."""
    out: list[str] = []
    if guards is None:
        guards, pin_findings = load_guards()
        out += pin_findings
    out += guard_findings or []
    out += check_guard_list(guards)
    approved = {mid: {(r["from"], r["to"]): (r["id"], frozenset(r["guards"])) for r in rows}
                for mid, rows in guards.get("machines", {}).items()}
    proof_types = set(guards.get("proof_types", {}))
    # R0 duplicates
    ids = [m["id"] for m in doc.get("machines", [])]
    for mid in sorted({x for x in ids if ids.count(x) > 1}):
        out.append(f"{mid}: R0 duplicate machine ID ({ids.count(mid)} definitions)")
    for m in doc.get("machines", []):
        st = m["states"]
        for s_ in sorted({x for x in st if st.count(x) > 1}):
            out.append(f"{m['id']}: R0 duplicate state {s_}")
        pairs = [(t["from"], t["to"]) for t in m["transitions"]]
        for a, b in sorted({p for p in pairs if pairs.count(p) > 1}):
            out.append(f"{m['id']}: R0 duplicate transition {a}->{b} ({pairs.count((a, b))} definitions)")
    machines = {m["id"]: m for m in doc.get("machines", [])}
    for mid in sorted(REQUIRED_MACHINES - set(machines)):
        out.append(f"{mid}: MISSING_MACHINE")
    for mid, m in sorted(machines.items()):
        states = set(m["states"])
        trans = [(t["from"], t["to"]) for t in m["transitions"]]
        tmap = {(t["from"], t["to"]): t for t in m["transitions"]}
        terminal = set(m.get("terminal", []))
        receipts = set(m.get("receipt_states", []))
        send = set(m.get("send_states", []))
        unknown = m.get("unknown_state")
        unknowns = unknown if isinstance(unknown, list) else ([unknown] if unknown else [])
        # R7
        for label, group in (("terminal", terminal), ("receipt", receipts), ("send", send)):
            for s in sorted(group - states):
                out.append(f"{mid}: R7 {label} state {s} not in states")
        if m["initial"] not in states:
            out.append(f"{mid}: R7 initial {m['initial']} not in states")
        for a, b in trans:
            if a not in states or b not in states:
                out.append(f"{mid}: R7 transition {a}->{b} uses an undeclared state")
        # R1
        seen, todo = {m["initial"]}, [m["initial"]]
        while todo:
            x = todo.pop()
            for a, b in trans:
                if a == x and b not in seen:
                    seen.add(b)
                    todo.append(b)
        for s in sorted(states - seen):
            out.append(f"{mid}: R1 unreachable state {s}")
        # R2
        for s in sorted(states - terminal):
            if not any(a == s for a, _ in trans):
                out.append(f"{mid}: R2 dead end {s} (non-terminal, no exit)")
        # R3
        for (a, b), t in sorted(tmap.items()):
            if b in receipts and not t.get("requires"):
                out.append(f"{mid}: R3 {a}->{b} enters receipt state without a required receipt")
        # R4
        for a, b, why in OBLIGATIONS.get(mid, []):
            if (a, b) not in tmap:
                out.append(f"{mid}: R4 missing obligation {a}->{b} ({why})")
        # R5
        for a, b, why in FORBIDDEN.get(mid, []):
            if (a, b) in tmap:
                out.append(f"{mid}: R5 forbidden {a}->{b} ({why})")
        # R6
        for s in sorted(set(unknowns) - states):
            out.append(f"{mid}: R7 unknown state {s} not in states")
        for (a, b), t in sorted(tmap.items()):
            if a not in unknowns:
                continue
            if b in send:
                out.append(f"{mid}: R6 {a}->{b} resends")
            if not t.get("requires"):
                out.append(f"{mid}: R6 {a}->{b} leaves unknown without a readback")
        # R8 / R9: the transition relation equals the approved list, with typed proofs
        allowed = approved.get(mid)
        if allowed is None:
            out.append(f"{mid}: R8 machine has no approved transition list")
            allowed = {}
        for t in m["transitions"]:
            a, b, g = t["from"], t["to"], guards_of(t)
            for p in sorted(g - proof_types):
                out.append(f"{mid}: R9 {a}->{b} requires untyped proof '{p}'")
            if (a, b) not in allowed:
                out.append(f"{mid}: R8 unapproved transition {a}->{b}")
            elif g != allowed[(a, b)][1]:
                out.append(f"{mid}: R8 {a}->{b} guard set {sorted(g)} differs from approved "
                           f"{allowed[(a, b)][0]} {sorted(allowed[(a, b)][1])}")
        for (a, b), (tid, _) in sorted(allowed.items()):
            if (a, b) not in tmap:
                out.append(f"{mid}: R8 approved transition {tid} {a}->{b} missing from the model")
        # R10 mandatory waypoints
        for target, ways in sorted(WAYPOINTS.get(mid, {}).items()):
            for w_ in ways:
                if target in reachable_avoiding(m["initial"], trans, w_):
                    out.append(f"{mid}: R10 {target} reachable without passing {w_}")
    for mid in sorted(set(approved) - set(machines)):
        out.append(f"{mid}: R8 approved list names a machine absent from the model")
    return out


def selftest(path: Path) -> int:
    base = json.loads(path.read_text())
    if check(base):
        print("baseline has findings; fix them before the self-test")
        return 1

    def mutate(fn):
        d = copy.deepcopy(base)
        fn({m["id"]: m for m in d["machines"]})
        return d

    def drop(mid, a, b):
        return lambda ms: ms[mid]["transitions"].remove(next(t for t in ms[mid]["transitions"] if (t["from"], t["to"]) == (a, b)))

    def strip_requires(mid, a, b):
        def f(ms):
            next(t for t in ms[mid]["transitions"] if (t["from"], t["to"]) == (a, b)).pop("requires", None)
        return f

    def add(mid, a, b, req):
        return mutate(lambda ms: ms[mid]["transitions"].append({"from": a, "to": b, "requires": req}))

    def set_requires(mid, a, b, req):
        def f(ms):
            next(t for t in ms[mid]["transitions"] if (t["from"], t["to"]) == (a, b))["requires"] = req
        return f

    gbytes = GUARDS.read_bytes()
    approved = json.loads(gbytes)

    def guards_plus(mid, a, b, g):
        d = copy.deepcopy(approved)
        d["machines"][mid].append({"id": "X-T99", "from": a, "to": b, "guards": g})
        return d

    dup_doc = copy.deepcopy(base)
    dup_doc["machines"].append(copy.deepcopy(dup_doc["machines"][0]))

    # (rule, model, approved list or None for the file on disk, extra pin findings)
    cases = {
        "R1 unreachable state": ("R1", mutate(lambda ms: ms["VAN-SM-TRADE_ORDER"]["states"].append("ORPHAN")), None, None),
        "R2 dead end": ("R2", mutate(lambda ms: (ms["VAN-SM-FUND_DEPOSIT"]["states"].append("LIMBO"),
                                                ms["VAN-SM-FUND_DEPOSIT"]["transitions"].append({"from": "DRAFT", "to": "LIMBO"}))), None, None),
        "R3 receipt without proof": ("R3", mutate(strip_requires("VAN-SM-FUND_WITHDRAWAL", "PROVIDER_PENDING", "PAID")), None, None),
        "R4 missing cancel/fill race": ("R4", mutate(drop("VAN-SM-TRADE_ORDER", "CANCEL_PENDING", "FILLED")), None, None),
        "R5 cancelled deletion skips re-auth": ("R5", mutate(lambda ms: ms["VAN-SM-ACCOUNT_LIFECYCLE"]["transitions"].append(
            {"from": "RELINK_REQUIRED", "to": "LINKED_READ_ONLY", "requires": "broker_readback"})), None, None),
        "R6 unknown outcome resends": ("R6", mutate(lambda ms: ms["VAN-SM-FUND_WITHDRAWAL"]["transitions"].append(
            {"from": "OUTCOME_UNKNOWN", "to": "SUBMITTED", "requires": "reconciliation_readback"})), None, None),
        "R6 second unknown state leaves without readback": ("R6", mutate(lambda ms: ms["VAN-SM-ACCOUNT_LIFECYCLE"]["transitions"].append(
            {"from": "CLOSURE_OUTCOME_UNKNOWN", "to": "LINKED_READ_ONLY_X"}) or ms["VAN-SM-ACCOUNT_LIFECYCLE"]["states"].append("LINKED_READ_ONLY_X")
            or ms["VAN-SM-ACCOUNT_LIFECYCLE"]["terminal"].append("LINKED_READ_ONLY_X")), None, None),
        "R7 undeclared receipt state": ("R7", mutate(lambda ms: ms["VAN-SM-FUND_DEPOSIT"]["receipt_states"].append("GHOST")), None, None),
        # Rev 1.9b (NXA-01): the four shortcuts, each carrying a real, typed proof label
        "R8 shortcut deposit DRAFT->SETTLED": ("R8", add("VAN-SM-FUND_DEPOSIT", "DRAFT", "SETTLED", "broker_balance_readback"), None, None),
        "R8 shortcut withdrawal DRAFT->PAID": ("R8", add("VAN-SM-FUND_WITHDRAWAL", "DRAFT", "PAID", "provider_settlement_receipt"), None, None),
        "R8 shortcut order DRAFT->FILLED": ("R8", add("VAN-SM-TRADE_ORDER", "DRAFT", "FILLED", "broker_fill"), None, None),
        "R8 shortcut news DRAFT_UNAPPROVED->USED": ("R8", add("VAN-SM-NEWS_ARMED_TICKET", "DRAFT_UNAPPROVED", "USED",
                                                             "two_source_agreement+mandate_and_risk_gate+unused_nonce"), None, None),
        "R8 weakened guard on PAID": ("R8", mutate(set_requires("VAN-SM-FUND_WITHDRAWAL", "PROVIDER_PENDING", "PAID", "broker_readback")), None, None),
        "R8 approved transition removed": ("R8", mutate(drop("VAN-SM-FUND_DEPOSIT", "DRAFT", "CANCELLED")), None, None),
        "R9 untyped proof string": ("R9", mutate(set_requires("VAN-SM-FUND_WITHDRAWAL", "PROVIDER_PENDING", "PAID", "arbitrary_nonempty_string")), None, None),
        # even with the approved list edited (and re-pinned), the waypoints still refuse every shortcut
        "R10 deposit shortcut with edited approved list": ("R10", add("VAN-SM-FUND_DEPOSIT", "DRAFT", "SETTLED", "broker_balance_readback"),
                                                           guards_plus("VAN-SM-FUND_DEPOSIT", "DRAFT", "SETTLED", ["broker_balance_readback"]), []),
        "R10 withdrawal shortcut with edited approved list": ("R10", add("VAN-SM-FUND_WITHDRAWAL", "DRAFT", "PAID", "provider_settlement_receipt"),
                                                              guards_plus("VAN-SM-FUND_WITHDRAWAL", "DRAFT", "PAID", ["provider_settlement_receipt"]), []),
        "R10 order shortcut with edited approved list": ("R10", add("VAN-SM-TRADE_ORDER", "DRAFT", "FILLED", "broker_fill"),
                                                         guards_plus("VAN-SM-TRADE_ORDER", "DRAFT", "FILLED", ["broker_fill"]), []),
        "R10 news shortcut with edited approved list": ("R10", add("VAN-SM-NEWS_ARMED_TICKET", "DRAFT_UNAPPROVED", "USED", "unused_nonce"),
                                                        guards_plus("VAN-SM-NEWS_ARMED_TICKET", "DRAFT_UNAPPROVED", "USED", ["unused_nonce"]), []),
        "R11 approved list edited without re-approval": ("R11", base, None,
            load_guards(json.dumps(guards_plus("VAN-SM-FUND_DEPOSIT", "DRAFT", "SETTLED", ["broker_balance_readback"])).encode())[1]),
        # Rev 1.9b (NXA-03): collisions
        "R0 duplicate machine ID": ("R0", dup_doc, None, None),
        "R0 duplicate state": ("R0", mutate(lambda ms: ms["VAN-SM-TRADE_ORDER"]["states"].append("FILLED")), None, None),
        "R0 duplicate transition with a different proof": ("R0", add("VAN-SM-FUND_WITHDRAWAL", "PROVIDER_PENDING", "PAID", "broker_readback"), None, None),
        "R0 duplicate approved transition": ("R0", base, guards_plus("VAN-SM-FUND_DEPOSIT", "DRAFT", "CANCELLED", []), []),
    }
    bad = 0
    for name, (rule, doc, guards, pin) in cases.items():
        got = [x for x in (check(doc) if guards is None and pin is None
                           else check(doc, guards if guards is not None else approved, pin)) if f": {rule} " in x]
        print(f"{'caught' if got else 'MISSED'}: {name} -> {got[:1]}")
        bad += 0 if got else 1
    return 1 if bad else 0


def main(argv):
    if "--selftest" in argv:
        return selftest(DEFAULT)
    path = Path(next((a for a in argv if not a.startswith("--")), DEFAULT))
    doc = json.loads(path.read_text())
    if "machines" in doc and doc["machines"] and "allowed_transitions" in doc["machines"][0]:
        # Rev 2 pack format: adapt (no terminal/receipt metadata exists there)
        doc = {"machines": [{"id": m["id"].replace("VNX-SM-", "VAN-SM-"), "states": m["states"], "initial": m["states"][0],
                             "transitions": [{"from": t["from"], "to": t["to"]} for t in m["allowed_transitions"]],
                             "terminal": [], "receipt_states": [], "send_states": []} for m in doc["machines"]]}
    findings = check(doc)
    for x in findings:
        print(x)
    print(f"{len(findings)} findings in {path.name}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
