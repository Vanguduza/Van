#!/usr/bin/env python3
"""Derive the VAN Next development plan from the blueprint, deterministically.

Reads the blueprint's own requirement catalogue (§16.1), Development Unit DAG (§16.2)
and the owner decision record's open questions, validates them, and emits the packet
order. Same inputs → byte-identical outputs.

The only inputs that are not read from the blueprint are the plan-level choices in
PLAN_CHOICES below (phase and lane per DU, and the §19.1 vertical slices). They are
stated here so the owner can approve or change them; everything else is derived.

Usage:
  python3 generate_plan.py            # validate and write the plan
  python3 generate_plan.py --check    # validate only; exit 1 on any finding
  python3 generate_plan.py --selftest # break each check on purpose; exit 1 if any check fails to catch it
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
BLUEPRINT = PACK / "VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_8_20261015.md"
DECISIONS = PACK / "VAN_NEXT_OWNER_DECISIONS_REV1.md"
OUT_MD = HERE / "VAN_NEXT_DEVELOPMENT_PLAN_REV1.md"
OUT_JSON = HERE / "VAN_NEXT_DEVELOPMENT_PLAN_REV1.json"

# ---------------------------------------------------------------- plan-level choices
# Phases follow blueprint §19.1. P2 builds one real vertical slice per domain (milestone
# M1); P3 completes every DU (milestone M2). Lanes follow §16.3 in its stated order.
PHASES = ["P0", "P1", "P2", "P3", "P4", "P5", "P6"]
LANES = ["Consolidation", "Foundation", "Orb/Floating", "Trading", "News", "Work Graph", "Continuity", "Qualification"]

PLAN_CHOICES = {
    "phase": {
        "DU-00": "P0", "DU-01": "P0",
        "DU-02": "P1", "DU-24": "P1", "DU-03": "P1", "DU-04": "P1",
        "DU-22": "P4", "DU-23": "P4", "DU-25": "P4", "DU-26": "P4",
        "DU-MR": "P5",
        # every other DU is a domain DU: M1 in P2 if it is in a slice closure, M2 in P3
    },
    "lane": {
        "DU-00": "Consolidation",
        "DU-01": "Foundation", "DU-02": "Foundation", "DU-24": "Foundation", "DU-03": "Foundation", "DU-04": "Foundation",
        "DU-05": "Orb/Floating", "DU-06": "Orb/Floating", "DU-07": "Orb/Floating",
        "DU-09": "Trading", "DU-10": "Trading", "DU-10b": "Trading", "DU-10c": "Trading", "DU-10d": "Trading",
        "DU-11": "Trading", "DU-12": "Trading", "DU-12a": "Trading", "DU-12b": "Trading", "DU-13": "Trading",
        "DU-28": "Trading", "DU-28b": "Trading", "DU-28c": "Trading", "DU-28d": "Trading", "DU-28e": "Trading",
        "DU-29": "Trading", "DU-29a": "Trading", "DU-29b": "Trading", "DU-29c": "Trading", "DU-30": "Trading",
        "DU-14a": "News", "DU-14b": "News", "DU-14c": "News", "DU-14d": "News", "DU-14e": "News", "DU-14f": "News",
        "DU-15": "Work Graph", "DU-16": "Work Graph", "DU-17": "Work Graph", "DU-18": "Work Graph",
        "DU-08": "Continuity", "DU-19": "Continuity", "DU-20": "Continuity", "DU-21": "Continuity",
        "DU-22": "Qualification", "DU-23": "Qualification", "DU-25": "Qualification", "DU-26": "Qualification", "DU-MR": "Qualification",
    },
    # Blueprint §19.1 P2: "one real flow per domain".
    "slices": {
        "S1 Home orb → Quick Hub → Attention": ["DU-05", "DU-06", "DU-08"],
        "S2 Trading Home → Chart → manual trade review → Position (demo account)": ["DU-09", "DU-10", "DU-28", "DU-11"],
        "S3 Work → Flow → Task": ["DU-15", "DU-16"],
        "S4 Intelligence → News → Instrument": ["DU-13", "DU-14d"],
        "S5 Floating VAN → Voice / Work": ["DU-07", "DU-21"],
    },
    # Research that is complete as research; its amendments enter through DU-10's contract.
    "complete": {"DU-27": "REA studies done (Rev 1.5–1.6, OD-15/16/17); amendments are inputs to the DU-10 contract, not a packet."},
}

# --------------------------------------------------------------------------- parsing
DU_RE = re.compile(r"DU-(\d+|MR)([a-z])?((?:/[a-z])*)")


def expand_du(text: str) -> list[str]:
    """'DU-14a/b, DU-14d' → ['DU-14a', 'DU-14b', 'DU-14d']."""
    out: list[str] = []
    for num, suf, more in DU_RE.findall(text):
        out.append(f"DU-{num}{suf}")
        for extra in [m for m in more.split("/") if m]:
            out.append(f"DU-{num}{extra}")
    return out


def section(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def parse_dag(bp: str):
    block = section(bp, "### 16.2 Development Unit dependency DAG", "### 16.3")
    mer = block[block.index("```mermaid"): block.index("```", block.index("```mermaid") + 3)]
    labels: dict[str, str] = {}
    for key, label in re.findall(r"\b([A-Z]{1,3})\[([^\]]+)\]", mer):
        labels.setdefault(key, label)
    solid, dotted = [], []
    for line in mer.splitlines():
        line = line.strip()
        m = re.match(r"^([A-Z]{1,3})(?:\[[^\]]+\])?\s*(-->|-\..*?\.->)\s*([A-Z]{1,3})", line)
        if not m:
            continue
        (solid if m.group(2) == "-->" else dotted).append((m.group(1), m.group(3)))
    nodes: dict[str, dict] = {}
    for key, label in labels.items():
        ids = expand_du(label)
        if not ids:
            raise SystemExit(f"DAG node without a DU id: {label}")
        du = ids[0]
        title = re.sub(r"^DU-\S+\s*", "", label).strip()
        nodes[key] = {"du": du, "title": title}
    edges = sorted({(nodes[a]["du"], nodes[b]["du"]) for a, b in solid})
    dotted_edges = sorted({(nodes[a]["du"], nodes[b]["du"]) for a, b in dotted})
    dus = {n["du"]: n["title"] for n in nodes.values()}
    return dus, edges, dotted_edges


def parse_requirements(bp: str) -> dict[str, dict]:
    block = section(bp, "### 16.1 Atomic requirement catalogue", "### 16.2")
    reqs = {}
    for row in block.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("VAN-NX-"):
            reqs[cells[0]] = {"behaviour": cells[1], "dus": expand_du(cells[2]), "acceptance": cells[3]}
    return reqs


def parse_open_questions(dec: str) -> dict[str, dict]:
    block = dec[dec.index("## Open owner decisions"):]
    oqs = {}
    for row in block.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 3 and re.match(r"OQ-\d+", cells[0]):
            when = cells[2]
            oqs[cells[0]] = {
                "question": cells[1],
                "needed_before": when,
                "dus": expand_du(when),
                # "live use" / "per path" gate promotion to live, not the start of the packet
                "blocks": "exit" if re.search(r"\bexit\b", when, re.I)
                else "live" if re.search(r"live use|per path|promotion", when + cells[1], re.I) else "start",
            }
    return oqs


# ------------------------------------------------------------------------ validation
def validate(dus, edges, reqs, oqs, choices) -> list[str]:
    f: list[str] = []
    known = set(dus)
    # 1. acyclic
    indeg = {d: 0 for d in known}
    for a, b in edges:
        indeg[b] += 1
    q = sorted(d for d, k in indeg.items() if k == 0)
    seen = 0
    adj: dict[str, list[str]] = {d: [] for d in known}
    for a, b in edges:
        adj[a].append(b)
    while q:
        d = q.pop()
        seen += 1
        for n in adj[d]:
            indeg[n] -= 1
            if indeg[n] == 0:
                q.append(n)
    if seen != len(known):
        f.append(f"CYCLE: {sorted(d for d, k in indeg.items() if k > 0)}")
    # 2. every requirement maps to DAG DUs
    for rid, r in sorted(reqs.items()):
        if not r["dus"]:
            f.append(f"REQ_NO_DU: {rid}")
        for d in r["dus"]:
            if d not in known:
                f.append(f"REQ_DU_NOT_IN_DAG: {rid} → {d}")
    # 3. every open question maps to DAG DUs
    for oid, o in sorted(oqs.items()):
        if not o["dus"]:
            f.append(f"OQ_NO_DU: {oid}")
        for d in o["dus"]:
            if d not in known:
                f.append(f"OQ_DU_NOT_IN_DAG: {oid} → {d}")
    # 4. every DU has a lane; phase map only names known DUs
    for d in sorted(known):
        if d not in choices["lane"] and d not in choices["complete"]:
            f.append(f"DU_NO_LANE: {d}")
    for d in choices["phase"]:
        if d not in known:
            f.append(f"PHASE_UNKNOWN_DU: {d}")
    for s, members in choices["slices"].items():
        for d in members:
            if d not in known:
                f.append(f"SLICE_UNKNOWN_DU: {s} → {d}")
    # 5. no DU depends on a DU in a later phase
    def ph(d):  # domain DUs sit in P2/P3; treat as P2 for the ordering check
        return PHASES.index(choices["phase"].get(d, "P2"))
    for a, b in edges:
        if a in choices["complete"] or b in choices["complete"]:
            continue
        if ph(a) > ph(b):
            f.append(f"PHASE_INVERSION: {b} ({choices['phase'].get(b, 'P2/P3')}) depends on {a} ({choices['phase'].get(a, 'P2/P3')})")
    # 6. DUs that carry no requirement (reported, not fatal — listed in the plan)
    return f


def unrequired(dus, reqs, choices):
    covered = {d for r in reqs.values() for d in r["dus"]}
    return sorted(d for d in dus if d not in covered and d not in choices["complete"])


# --------------------------------------------------------------------------- ordering
def natural(d: str):
    m = re.match(r"DU-(\d+)([a-z]?)", d)
    return (int(m.group(1)), m.group(2)) if m else (999, d)


def order(dus, edges, choices):
    deps: dict[str, set[str]] = {d: set() for d in dus}
    for a, b in edges:
        deps[b].add(a)
    complete = set(choices["complete"])
    for d in deps:
        deps[d] -= complete
    # longest-path level
    level: dict[str, int] = {}

    def lv(d):
        if d not in level:
            level[d] = 0 if not deps[d] else 1 + max(lv(x) for x in deps[d])
        return level[d]

    for d in dus:
        lv(d)
    lane_rank = {d: LANES.index(choices["lane"][d]) for d in dus if d in choices["lane"]}

    def key(d):
        return (level[d], lane_rank.get(d, 99), natural(d))

    fixed = choices["phase"]
    domain = sorted((d for d in dus if d not in fixed and d not in complete), key=natural)
    slice_members = {d for ms in choices["slices"].values() for d in ms}

    def ancestors(d, acc):
        for x in deps[d]:
            if x not in acc:
                acc.add(x)
                ancestors(x, acc)
        return acc

    p2 = set()
    for d in slice_members:
        p2 |= {d} | {a for a in ancestors(d, set()) if a in domain}

    def kahn(subset, done_before):
        """Topological order of `subset`; a node is ready when every dependency inside
        `subset` has been emitted (dependencies outside it belong to earlier phases)."""
        members, done, out = set(subset), set(), []
        while len(out) < len(members):
            ready = sorted((d for d in members - done if all(x in done or x not in members for x in deps[d])), key=key)
            if not ready:
                raise SystemExit(f"cannot order: {sorted(members - done)}")
            out.append(ready[0])
            done.add(ready[0])
        return out

    seq: list[dict] = []
    done: set[str] = set()
    for phase in ["P0", "P1"]:
        for d in kahn([x for x in dus if fixed.get(x) == phase], done):
            seq.append({"du": d, "phase": phase, "milestone": "FULL"})
            done.add(d)
    for d in kahn(sorted(p2), done):
        seq.append({"du": d, "phase": "P2", "milestone": "M1"})
    p2_done = set(p2)
    for d in kahn(domain, done):
        seq.append({"du": d, "phase": "P3", "milestone": "M2" if d in p2_done else "FULL"})
    done |= set(domain)
    for d in kahn([x for x in dus if fixed.get(x) == "P4"], done):
        seq.append({"du": d, "phase": "P4", "milestone": "FULL"})
        done.add(d)
    seq.append({"du": "DU-MR", "phase": "P5", "milestone": "ROLLOUT"})
    seq.append({"du": "DU-MR", "phase": "P6", "milestone": "RETIREMENT"})
    for i, s in enumerate(seq, 1):
        s["packet"] = f"PKT-{i:03d}"
        s["level"] = level.get(s["du"], 0)
    return seq, deps, level


# ---------------------------------------------------------------------------- render
MILESTONE_TEXT = {
    "FULL": "Whole DU to its requirement acceptance.",
    "M1": "Only what its §19.1 slice (or a dependent slice) needs, end to end on real permitted data; scope fixed in the packet contract.",
    "M2": "Remainder of the DU to full requirement acceptance (its M1 already exited).",
    "ROLLOUT": "§19.1 P5: signed APK under the admitted identity, feature flags, recovery on the owner's S24, tested rollback build.",
    "RETIREMENT": "§19.1 P6: remove old frontend only after full parity and readback, in its own reviewable branch with negative tests.",
}


def render(dus, edges, dotted, reqs, oqs, choices, seq, deps, findings, unreq, src_hash):
    by_du_reqs: dict[str, list[str]] = {}
    for rid, r in reqs.items():
        for d in r["dus"]:
            by_du_reqs.setdefault(d, []).append(rid)
    by_du_oqs: dict[str, list[str]] = {}
    for oid, o in oqs.items():
        for d in o["dus"]:
            by_du_oqs.setdefault(d, []).append(oid)
    first_packet: dict[str, str] = {}
    last_packet: dict[str, str] = {}
    for s in seq:
        first_packet.setdefault(s["du"], s["packet"])
        last_packet[s["du"]] = s["packet"]

    def dep_packets(s):
        out = set()
        for d in sorted(deps.get(s["du"], ()), key=natural):
            # M1 needs the dependency's first packet; M2/FULL needs its last packet before this one
            target = first_packet[d] if s["milestone"] == "M1" else last_packet[d]
            if target < s["packet"]:
                out.add(target)
            else:
                out.add(first_packet[d])
        if s["milestone"] == "M2":
            out.add(first_packet[s["du"]])
        if s["phase"] == "P6":
            out.add(first_packet["DU-MR"])
        return sorted(out)

    L = []
    w = L.append
    w("# VAN Next — Deterministic Development Plan, Rev 1")
    w("")
    w("**Status:** `DRAFT / AWAITING_OWNER_APPROVAL`. No packet starts until the owner approves this plan.")
    w(f"**Derived from:** `{BLUEPRINT.name}` §16.1, §16.2, §19.1 and `{DECISIONS.name}` (open questions), source SHA-256 `{src_hash}`.")
    w("**Generator:** `plan/generate_plan.py`. Re-running it on the same inputs gives byte-identical output; `--check` validates, `--selftest` proves each check catches a deliberately broken input.")
    w("")
    w("## 1. Rules")
    w("")
    w("1. **One packet at a time, in sequence order.** A packet starts only when its entry gate holds; the next packet starts only when the current one has exited. Parallel work is allowed only when the owner assigns another worker, and then only to packets of the same wave (§6) whose dependencies have exited.")
    w("2. **Entry gate (every packet):** all dependency packets exited; the packet's acceptance contract written and owner-approved (fields of blueprint §16.4, including exact source SHA, files, negative cases, acceptance commands, rollback); every open question that blocks its start resolved.")
    w("3. **Exit gate (every packet):** the contract's acceptance commands pass on a recorded commit; each new gate is broken deliberately and seen to fail before it is trusted; the parity checker (from PKT-001 onward) shows no `FEATURE_LOSS`; independent review recorded; artifact state at least `REPOSITORY_PROVEN` (§17.1). Device, live and owner-acceptance states are reached in P4–P5 and are never claimed earlier.")
    w("4. **No code outside a packet.** Work not in an open packet is not done. A discovery that changes scope stops the packet and goes to the owner as a blueprint amendment; the plan is regenerated.")
    w("5. **Order key** (deterministic): phase (§19.1) → dependency depth in the §16.2 DAG → lane order of §16.3 → DU number. P2 builds the five §19.1 vertical slices as milestone M1 of each DU in a slice and of every DU those slices depend on; P3 completes each DU (M2), then the remaining DUs in full.")
    w("6. **Owner-only steps** are listed per packet and are never assumed: signatures, open-question answers, `OWNER_RETIRE` dispositions, live promotion.")
    w("")
    w("## 2. Validation of the blueprint inputs")
    w("")
    w(f"- Development Units in the DAG: {len(dus)}; solid dependency edges: {len(edges)}; non-blocking (dotted) edges: {len(dotted)}.")
    w(f"- Requirements parsed: {len(reqs)}; open questions parsed: {len(oqs)}.")
    if findings:
        w(f"- **Findings ({len(findings)}) — the plan is not valid until these are fixed:**")
        for x in findings:
            w(f"  - `{x}`")
    else:
        w("- Findings: none. The DAG is acyclic; every requirement and every open question maps to a DU in the DAG; every DU has a lane; no DU depends on a later phase.")
    w(f"- DUs with no requirement row (kept, flagged for the freeze list): {', '.join(unreq) if unreq else 'none'}.")
    for d, why in choices["complete"].items():
        w(f"- {d} is not a packet: {why}")
    w("")
    w("## 3. Plan-level choices awaiting owner approval")
    w("")
    w("These are the only inputs not read from the blueprint.")
    w("")
    w("| DU | Phase | Lane |")
    w("|---|---|---|")
    for d in sorted(dus, key=natural):
        if d in choices["complete"]:
            continue
        w(f"| {d} | {choices['phase'].get(d, 'P2 (M1, if in a slice closure) / P3')} | {choices['lane'][d]} |")
    w("")
    w("| Vertical slice (§19.1 P2) | DUs |")
    w("|---|---|")
    for s, m in choices["slices"].items():
        w(f"| {s} | {', '.join(m)} |")
    w("")
    w("## 4. Packet sequence")
    w("")
    w("| Packet | DU | Title | Phase | Milestone | Lane | Depends on | Requirements | Owner decisions (start / live / exit) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for s in seq:
        d = s["du"]
        title = dus.get(d, "Controlled migration/retirement")
        def pick(kind):
            return ", ".join(o for o in by_du_oqs.get(d, []) if oqs[o]["blocks"] == kind) or "—"
        oq = f"{pick('start')} / {pick('live')}" + (f" / exit: {pick('exit')}" if pick("exit") != "—" else "")
        w(f"| {s['packet']} | {d} | {title} | {s['phase']} | {s['milestone']} | {choices['lane'].get(d, '')} | {', '.join(dep_packets(s)) or '—'} | {', '.join(sorted(by_du_reqs.get(d, []))) or '—'} | {oq} |")
    w("")
    w("## 5. Milestones")
    w("")
    for k, v in MILESTONE_TEXT.items():
        w(f"- **{k}:** {v}")
    w("")
    w("## 6. Waves (what may run in parallel if the owner adds workers)")
    w("")
    w("Within a phase, packets at the same DAG depth do not depend on each other.")
    w("")
    w("| Phase | Depth | Packets |")
    w("|---|---|---|")
    waves: dict[tuple, list[str]] = {}
    for s in seq:
        waves.setdefault((s["phase"], s["level"]), []).append(f"{s['packet']} ({s['du']})")
    for (p, lvl), items in waves.items():
        w(f"| {p} | {lvl} | {', '.join(items)} |")
    w("")
    w("## 7. Exit evidence by requirement")
    w("")
    w("A DU's last packet exits only with every listed requirement's key acceptance (blueprint §16.1).")
    w("")
    w("| Requirement | DU | Key acceptance |")
    w("|---|---|---|")
    for rid in sorted(reqs, key=lambda r: int(r.split("-")[-1])):
        r = reqs[rid]
        w(f"| {rid} | {', '.join(r['dus'])} | {r['acceptance']} |")
    w("")
    return "\n".join(L) + "\n"


def build(bp_text: str, dec_text: str, choices=PLAN_CHOICES):
    dus, edges, dotted = parse_dag(bp_text)
    reqs = parse_requirements(bp_text)
    oqs = parse_open_questions(dec_text)
    findings = validate(dus, edges, reqs, oqs, choices)
    return dus, edges, dotted, reqs, oqs, findings


def selftest() -> int:
    bp, dec = BLUEPRINT.read_text(), DECISIONS.read_text()
    base = build(bp, dec)[-1]
    if base:
        print("baseline has findings; fix them before the self-test:", base)
        return 1
    cases = {
        "cycle": (bp.replace("  A[DU-00 Consolidation", "  J --> A\n  A[DU-00 Consolidation", 1), dec, PLAN_CHOICES, "CYCLE"),
        "requirement to unknown DU": (bp.replace("| VAN-NX-044 | Replay sandbox | DU-10c |", "| VAN-NX-044 | Replay sandbox | DU-99 |", 1), dec, PLAN_CHOICES, "REQ_DU_NOT_IN_DAG"),
        "open question to unknown DU": (bp, dec.replace("| DU-29 |", "| DU-98 |", 1), PLAN_CHOICES, "OQ_DU_NOT_IN_DAG"),
        "DU without lane": (bp, dec, {**PLAN_CHOICES, "lane": {k: v for k, v in PLAN_CHOICES["lane"].items() if k != "DU-16"}}, "DU_NO_LANE"),
        "phase inversion": (bp, dec, {**PLAN_CHOICES, "phase": {**PLAN_CHOICES["phase"], "DU-01": "P4"}}, "PHASE_INVERSION"),
    }
    bad = 0
    for name, (b, d, ch, expect) in cases.items():
        assert b != bp or d != dec or ch is not PLAN_CHOICES, f"self-test case '{name}' did not change its input"
        got = build(b, d, ch)[-1]
        ok = any(x.startswith(expect) for x in got)
        print(f"{'caught' if ok else 'MISSED'}: {name} → {[x for x in got if x.startswith(expect)][:1] or got[:1]}")
        bad += 0 if ok else 1
    return 1 if bad else 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    bp, dec = BLUEPRINT.read_text(), DECISIONS.read_text()
    dus, edges, dotted, reqs, oqs, findings = build(bp, dec)
    for x in findings:
        print("FINDING", x)
    if "--check" in argv:
        return 1 if findings else 0
    seq, deps, level = order(dus, edges, PLAN_CHOICES)
    src_hash = hashlib.sha256((bp + "\n" + dec).encode()).hexdigest()[:16]
    md = render(dus, edges, dotted, reqs, oqs, PLAN_CHOICES, seq, deps, findings, unrequired(dus, reqs, PLAN_CHOICES), src_hash)
    OUT_MD.write_text(md)
    OUT_JSON.write_text(json.dumps({"source_sha256_16": src_hash, "findings": findings, "packets": seq}, indent=1) + "\n")
    print(f"{len(seq)} packets, {len(findings)} findings → {OUT_MD.name}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
