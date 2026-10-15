#!/usr/bin/env python3
"""Model-check the VAN Next state machines (blueprint Rev 1.9, Amendment C).

Rules, each proven by --selftest to fail when deliberately broken:
  R1 every state is reachable from the initial state
  R2 every non-terminal state has an outgoing transition (no dead ends)
  R3 every transition into a receipt state names the receipt it requires
  R4 every obligation transition (audit findings and owner decisions) is present
  R5 no forbidden transition is present
  R6 an unknown outcome never leads straight back to a sending state, and every
     exit from it requires a readback (no automatic resend)
  R7 every declared terminal / receipt / send state exists in the machine

Obligations live here, not in the JSON, so editing a machine cannot quietly
remove them.

Usage:
  python3 check_state_machines.py [machines.json]   # default: VAN_STATE_MACHINES_REV1_9.json
  python3 check_state_machines.py --selftest
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "VAN_STATE_MACHINES_REV1_9.json"

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

REQUIRED_MACHINES = set(OBLIGATIONS)


def check(doc: dict) -> list[str]:
    out: list[str] = []
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

    cases = {
        "R1 unreachable state": ("R1", mutate(lambda ms: ms["VAN-SM-TRADE_ORDER"]["states"].append("ORPHAN"))),
        "R2 dead end": ("R2", mutate(lambda ms: (ms["VAN-SM-FUND_DEPOSIT"]["states"].append("LIMBO"),
                                                ms["VAN-SM-FUND_DEPOSIT"]["transitions"].append({"from": "DRAFT", "to": "LIMBO"})))),
        "R3 receipt without proof": ("R3", mutate(strip_requires("VAN-SM-FUND_WITHDRAWAL", "PROVIDER_PENDING", "PAID"))),
        "R4 missing cancel/fill race": ("R4", mutate(drop("VAN-SM-TRADE_ORDER", "CANCEL_PENDING", "FILLED"))),
        "R5 cancelled deletion skips re-auth": ("R5", mutate(lambda ms: ms["VAN-SM-ACCOUNT_LIFECYCLE"]["transitions"].append(
            {"from": "RELINK_REQUIRED", "to": "LINKED_READ_ONLY", "requires": "broker_readback"}))),
        "R6 unknown outcome resends": ("R6", mutate(lambda ms: ms["VAN-SM-FUND_WITHDRAWAL"]["transitions"].append(
            {"from": "OUTCOME_UNKNOWN", "to": "SUBMITTED", "requires": "reconciliation_readback"}))),
        "R6 second unknown state leaves without readback": ("R6", mutate(lambda ms: ms["VAN-SM-ACCOUNT_LIFECYCLE"]["transitions"].append(
            {"from": "CLOSURE_OUTCOME_UNKNOWN", "to": "LINKED_READ_ONLY_X"}) or ms["VAN-SM-ACCOUNT_LIFECYCLE"]["states"].append("LINKED_READ_ONLY_X")
            or ms["VAN-SM-ACCOUNT_LIFECYCLE"]["terminal"].append("LINKED_READ_ONLY_X"))),
        "R7 undeclared receipt state": ("R7", mutate(lambda ms: ms["VAN-SM-FUND_DEPOSIT"]["receipt_states"].append("GHOST"))),
    }
    bad = 0
    for name, (rule, doc) in cases.items():
        got = [x for x in check(doc) if f": {rule} " in x]
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
