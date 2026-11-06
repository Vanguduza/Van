#!/usr/bin/env python3
"""Derive the VAN Next development plan from the blueprint, deterministically.

Reads the blueprint's own requirement catalogue (§16.1), Development Unit DAG (§16.2)
and the owner decision record's open questions, validates them, and emits the packet
order. Same inputs → byte-identical outputs.

The only inputs that are not read from the blueprint are the plan-level choices in
PLAN_CHOICES below (phase and lane per DU, and the §19.1 vertical slices). They are
stated here so the owner can approve or change them; everything else is derived.

Rev 1.9b (OD-33, OD-34): the requirement IDs and their text, and the 78 legacy
surfaces with their 349 owner actions, are locked in REQUIREMENT_LOCK_REV1_9B.json,
whose SHA-256 is pinned in the owner decision record. A requirement or surface
obligation that is removed, changed, added without locking or duplicated is a
finding, so regenerating the plan cannot quietly drop one.

Usage:
  python3 generate_plan.py            # validate and write the plan
  python3 generate_plan.py --check    # validate only; exit 1 on any finding
  python3 generate_plan.py --selftest # break each check on purpose; exit 1 if any check fails to catch it
  python3 generate_plan.py --write-requirement-lock
      # rewrite the lock from the current inputs and print its hash; refuses to drop a
      # locked requirement unless the lock's "superseded" section names the owner decision.
      # The new hash takes effect only when it is pinned in the owner decision record.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
BLUEPRINT = PACK / "VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9B_20261016.md"
DECISIONS = PACK / "VAN_NEXT_OWNER_DECISIONS_REV1.md"
SURFACES = PACK / "VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.json"
REQ_LOCK = HERE / "REQUIREMENT_LOCK_REV1_9B.json"
OUT_MD = HERE / "VAN_NEXT_DEVELOPMENT_PLAN_REV1.md"
OUT_JSON = HERE / "VAN_NEXT_DEVELOPMENT_PLAN_REV1.json"
OUT_PROV = HERE / "PLAN_INPUT_PROVENANCE.json"
GENERATOR = Path(__file__).resolve()
# Units every build unit must reach (blueprint Rev 1.9, AUD-01).
QUALIFICATION = ["DU-25", "DU-26", "DU-MR"]
# The predevelopment F15 gate (Rev 1.9a, V19-A02) and the read-only units allowed before it.
F15_GATE = "DU-31"
READ_ONLY_BEFORE_F15 = {"DU-00a", "DU-01", "DU-31"}
# The unit that builds and qualifies the parity checker (Rev 1.9b, NXA-04). Every other
# code-bearing unit depends on it, so no packet's exit gate needs a checker that does not exist yet.
PARITY_UNIT = "DU-00b"

# ---------------------------------------------------------------- plan-level choices
# Phases follow blueprint §19.1. P2 builds one real vertical slice per domain (milestone
# M1); P3 completes every DU (milestone M2). Lanes follow §16.3 in its stated order.
PHASES = ["P0", "P1", "P2", "P3", "P4", "P5", "P6"]
LANES = ["Consolidation", "Foundation", "Orb/Floating", "Trading", "News", "Work Graph", "Continuity", "Qualification"]

PLAN_CHOICES = {
    "phase": {
        "DU-00a": "P0", "DU-01": "P0", "DU-31": "P0", "DU-00b": "P0",
        "DU-02": "P1", "DU-24": "P1", "DU-03": "P1", "DU-04": "P1",
        "DU-22": "P4", "DU-23": "P4", "DU-25": "P4", "DU-26": "P4",
        "DU-MR": "P5",
        # every other DU is a domain DU: M1 in P2 if it is in a slice closure, M2 in P3
    },
    "lane": {
        "DU-00a": "Consolidation", "DU-31": "Consolidation", "DU-00b": "Consolidation",
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
    "complete": {"DU-27": "REA research (static) done under OD-15/16/17. Its admission record is VAN-NX-026, carried by DU-01; its findings are inputs to the DU-10 and DU-29 contracts."},
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
    for key, label in re.findall(r"\b([A-Z][A-Z0-9]{0,2})\[([^\]]+)\]", mer):
        labels.setdefault(key, label)
    solid, dotted = [], []
    for line in mer.splitlines():
        line = line.strip()
        m = re.match(r"^([A-Z][A-Z0-9]{0,2})(?:\[[^\]]+\])?\s*(-->|-\..*?\.->)\s*([A-Z][A-Z0-9]{0,2})", line)
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


def dag_duplicates(bp: str) -> list[str]:
    """A node key with two labels, or one DU behind two node keys (parse_dag keeps only one)."""
    block = section(bp, "### 16.2 Development Unit dependency DAG", "### 16.3")
    mer = block[block.index("```mermaid"): block.index("```", block.index("```mermaid") + 3)]
    labels: dict[str, set[str]] = {}
    for key, label in re.findall(r"\b([A-Z][A-Z0-9]{0,2})\[([^\]]+)\]", mer):
        labels.setdefault(key, set()).add(label)
    out = [f"DAG_DUPLICATE: node {k} has {len(v)} labels" for k, v in sorted(labels.items()) if len(v) > 1]
    keys_of: dict[str, set[str]] = {}
    for k, v in labels.items():
        for label in v:
            ids = expand_du(label)
            if ids:
                keys_of.setdefault(ids[0], set()).add(k)
    out += [f"DAG_DUPLICATE: {d} is defined by nodes {sorted(ks)}" for d, ks in sorted(keys_of.items()) if len(ks) > 1]
    return out


def requirement_rows(bp: str) -> list[list[str]]:
    block = section(bp, "### 16.1 Atomic requirement catalogue", "### 16.2")
    rows = []
    for row in block.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if cells and cells[0].startswith("VAN-NX-"):
            rows.append(cells)
    return rows


def row_digest(cells: list[str]) -> str:
    return hashlib.sha256(" | ".join(cells).encode()).hexdigest()


def parse_requirements(bp: str) -> dict[str, dict]:
    reqs = {}
    for cells in requirement_rows(bp):
        if len(cells) == 4:
            m = re.search(r"Needs:\s*([^|]*)", cells[3])
            reqs[cells[0]] = {"behaviour": cells[1], "dus": expand_du(cells[2]), "acceptance": cells[3],
                              "needs": expand_du(m.group(1)) if m else [], "digest": row_digest(cells)}
    return reqs


def duplicate_findings(bp: str, dec: str) -> list[str]:
    """Rev 1.9b (NXA-03): dictionaries keep only the last of two rows, so collisions are counted on the raw rows."""
    out = dag_duplicates(bp)
    ids = [c[0] for c in requirement_rows(bp)]
    out += [f"REQ_DUPLICATE: {r} appears {ids.count(r)} times" for r in sorted({x for x in ids if ids.count(x) > 1})]
    out += [f"REQ_MALFORMED: {c[0]} row has {len(c)} cells, expected 4" for c in requirement_rows(bp) if len(c) != 4]
    oq = re.findall(r"^\|\s*(OQ-\d+)\s*\|", dec[dec.index("## Open owner decisions"):], re.M)
    out += [f"OQ_DUPLICATE: {o} appears {oq.count(o)} times" for o in sorted({x for x in oq if oq.count(x) > 1})]
    return out


# ------------------------------------------------------------------- requirement lock
def surface_obligations(matrix_bytes: bytes) -> dict[str, str]:
    """78 legacy surfaces → digest of their owner actions (349 in Rev 1.2)."""
    recs = json.loads(matrix_bytes)["records"]
    out: dict[str, str] = {}
    for i, r in enumerate(recs):
        key = r["id"] if r["id"] not in out else f"{r['id']}#DUPLICATE@{i}"
        out[key] = hashlib.sha256(json.dumps(sorted(r["actions"])).encode()).hexdigest()
    return out


def pinned_lock_hash(dec: str) -> str | None:
    m = re.search(r"^\|\s*REQUIREMENT_LOCK\s*\|[^|]*\|\s*`?([0-9a-f]{64})`?\s*\|", dec, re.M)
    return m.group(1) if m else None


def lock_findings(reqs: dict, lock_bytes: bytes, dec: str, matrix_bytes: bytes) -> list[str]:
    f: list[str] = []
    pin, actual = pinned_lock_hash(dec), hashlib.sha256(lock_bytes).hexdigest()
    if pin is None:
        f.append("LOCK_NOT_PINNED: no REQUIREMENT_LOCK hash in the owner decision record")
    elif pin != actual:
        f.append(f"LOCK_CHANGED_WITHOUT_APPROVAL: pinned {pin[:12]}, actual {actual[:12]}")
    lock = json.loads(lock_bytes)
    locked, superseded = lock["requirements"], lock.get("superseded", {})
    for rid in sorted(set(locked) - set(reqs)):
        f.append(f"REQ_REMOVED: {rid} is locked but missing from §16.1")
    for rid in sorted(set(reqs) - set(locked)):
        f.append(f"REQ_SUPERSEDED_STILL_PRESENT: {rid}" if rid in superseded else f"REQ_NOT_LOCKED: {rid} is not in the requirement lock")
    for rid in sorted(set(reqs) & set(locked)):
        if reqs[rid]["digest"] != locked[rid]:
            f.append(f"REQ_CHANGED: {rid} text differs from the locked row")
    surf, lsurf = surface_obligations(matrix_bytes), lock["surface_obligations"]
    for sid in sorted(set(lsurf) - set(surf)):
        f.append(f"SURFACE_REMOVED: {sid}")
    for sid in sorted(set(surf) - set(lsurf)):
        f.append(f"SURFACE_DUPLICATE: {sid}" if "#DUPLICATE@" in sid else f"SURFACE_NOT_LOCKED: {sid}")
    for sid in sorted(set(surf) & set(lsurf)):
        if surf[sid] != lsurf[sid]:
            f.append(f"SURFACE_OBLIGATIONS_CHANGED: {sid}")
    return f


def make_lock(bp: str, matrix_bytes: bytes, previous: dict | None) -> tuple[dict, list[str]]:
    reqs = parse_requirements(bp)
    superseded = (previous or {}).get("superseded", {})
    refused = [r for r in (previous or {}).get("requirements", {}) if r not in reqs and r not in superseded]
    lock = {
        "schema": "van-next-requirement-lock/1.0",
        "revision": "Rev 1.9b (16 October 2026)",
        "status": "PREPARED_PENDING_OWNER_SIGNATURE",
        "authority": "OD-33. Pinned by SHA-256 in VAN_NEXT_OWNER_DECISIONS_REV1.md, section 'Locked contracts'.",
        "row_digest": "sha256(' | '.join(stripped §16.1 cells))",
        "surface_digest": "sha256(json.dumps(sorted(record.actions)))",
        "requirements": {r: reqs[r]["digest"] for r in sorted(reqs, key=lambda x: int(x.split("-")[-1]))},
        "superseded": superseded,
        "surface_obligations": surface_obligations(matrix_bytes),
    }
    return lock, refused


_DISK = object()


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
def validate(dus, edges, reqs, oqs, choices, lock=_DISK) -> list[str]:
    """lock: (lock bytes, decision-record text, surface-matrix bytes); the files on disk by default."""
    f: list[str] = []
    if lock is _DISK:
        lock = (REQ_LOCK.read_bytes(), DECISIONS.read_text(), SURFACES.read_bytes())
    if lock is not None:
        f += lock_findings(reqs, *lock)
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
    # 6. every build unit reaches integrated verification, device acceptance and rollout (AUD-01)
    deps_of: dict[str, set[str]] = {d: set() for d in known}
    for a, b in edges:
        deps_of[b].add(a)
    def ancestors(d):
        acc, todo = set(), [d]
        while todo:
            for x in deps_of.get(todo.pop(), ()):
                if x not in acc:
                    acc.add(x)
                    todo.append(x)
        return acc
    for q in QUALIFICATION:
        if q not in known:
            f.append(f"QUAL_UNIT_MISSING: {q}")
            continue
        anc = ancestors(q)
        downstream = {d for d in known if q in ancestors(d)}
        for d in sorted(known - anc - downstream - {q} - set(choices["complete"]) - set(QUALIFICATION)):
            f.append(f"QUAL_UNREACHED: {d} has no dependency path to {q}")
    # 7. no code-bearing unit runs before the predevelopment F15 gate (V19-A02)
    if F15_GATE in known:
        for d in sorted(known - READ_ONLY_BEFORE_F15 - set(choices["complete"])):
            if F15_GATE not in ancestors(d):
                f.append(f"CODE_BEFORE_F15: {d} does not depend on {F15_GATE}")
    else:
        f.append(f"F15_GATE_MISSING: {F15_GATE}")
    # 8. every unit a requirement needs is built upstream of (or is) the requirement's unit (V19-A03)
    for rid, r in sorted(reqs.items()):
        for owner in r["dus"]:
            if owner not in known:
                continue
            up = ancestors(owner) | {owner}
            for need in r.get("needs", []):
                if need not in known:
                    f.append(f"REQ_NEEDS_UNKNOWN: {rid} needs {need}")
                elif need not in up:
                    f.append(f"REQ_NEEDS_NOT_UPSTREAM: {rid} on {owner} needs {need}, which is not upstream")
    # 9. the parity checker exists before every packet whose exit gate needs it (NXA-04)
    if PARITY_UNIT in known:
        for d in sorted(known - READ_ONLY_BEFORE_F15 - {PARITY_UNIT} - set(choices["complete"])):
            if PARITY_UNIT not in ancestors(d):
                f.append(f"PARITY_BEFORE_CHECKER: {d} does not depend on {PARITY_UNIT}, which builds the parity checker")
    else:
        f.append(f"PARITY_UNIT_MISSING: {PARITY_UNIT}")
    # DUs that carry no requirement are reported, not fatal (listed in the plan)
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


def render(dus, edges, dotted, reqs, oqs, choices, seq, deps, findings, unreq, prov):
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
    w(f"**Derived from:** `{BLUEPRINT.name}` §16.1, §16.2, §19.1 and `{DECISIONS.name}` (open questions).")
    w("")
    w("| Input | SHA-256 (full file bytes) |")
    w("|---|---|")
    for k in ("blueprint", "owner_decisions", "generator", "requirement_lock", "surface_matrix"):
        w(f"| `{prov[k]['path']}` | `{prov[k]['sha256']}` |")
    w("")
    w(f"Aggregate input digest `{prov['aggregate_input_sha256']}` = SHA-256 of the blueprint bytes, one newline byte, then the decision-record, generator, requirement-lock and surface-matrix bytes. `PLAN_INPUT_PROVENANCE.json` records these values and the hashes of the generated plan.")
    w("")
    w("**Generator:** `plan/generate_plan.py`. Re-running it on the same inputs gives byte-identical output. `--check` validates the inputs **and** fails if this file is stale; `--selftest` proves each check catches a deliberately broken input.")
    w("")
    w("## 1. Rules")
    w("")
    w("1. **One packet at a time, in sequence order.** A packet starts only when its entry gate holds; the next packet starts only when the current one has exited. Parallel work is allowed only when the owner assigns another worker, and then only to packets of the same wave (§6) whose dependencies have exited.")
    w("2. **Entry gate (every packet):** for every code-bearing packet (any unit other than DU-00a, DU-01 and DU-31), a current independent F15 `FORENSIC_BUILD_READY` certificate from DU-31 and a passing deterministic predevelopment gate (PRD-DDP-R2 §19); all dependency packets exited; the packet's acceptance contract written and owner-approved (fields of blueprint §16.4, including exact source SHA, files, negative cases, acceptance commands, rollback); every open question that blocks its start resolved.")
    pp = first_packet[PARITY_UNIT]
    before = [x["packet"] for x in seq if x["packet"] < pp]
    after = next((x["packet"] for x in seq if x["packet"] > pp), None)
    w("3. **Exit gate (every packet):** the contract's acceptance commands pass on a recorded commit; each new gate is broken deliberately and seen to fail before it is trusted; feature preservation holds as in rule 3a; independent review recorded; artifact state at least `REPOSITORY_PROVEN` (§17.1). Device, live and owner-acceptance states are reached in P4–P5 and are never claimed earlier.")
    w(f"3a. **Feature preservation, in two stages** (Rev 1.9b, NXA-04). The parity checker is built by {pp} ({PARITY_UNIT}), so it cannot gate earlier packets. "
      f"**{'–'.join([before[0], before[-1]]) if len(before) > 1 else ''.join(before)} (read-only):** the *preservation-inventory gate* — no source file changes; the frozen heads still resolve to the recorded SHAs; `generate_plan.py --check` passes, so the owner-pinned requirement lock and the 78 legacy surfaces with their owner actions are intact; after DU-00a exits, its Feature Ledger changes only through recorded rows, each with a reason. "
      f"**{pp}:** exits only with the parity checker qualified — an induced omission fails it — and no `FEATURE_LOSS` on consolidated `main`. "
      f"**{after} onward:** every packet's exit requires the parity checker to show no `FEATURE_LOSS`. Validator rule `PARITY_BEFORE_CHECKER` keeps every code-bearing unit downstream of {PARITY_UNIT}.")
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
        w("- Findings: none. The DAG is acyclic; every requirement and every open question maps to a DU in the DAG; every DU has a lane; no DU depends on a later phase; every build unit has a dependency path to DU-25, DU-26 and DU-MR; no code-bearing unit runs before the F15 gate DU-31; every unit a requirement needs is built upstream of it; every code-bearing unit is downstream of the parity checker; no DAG node, requirement or open question is duplicated; the requirement IDs and text and the 78 legacy surfaces' owner actions match the owner-pinned requirement lock.")
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
    w("## 7. Open questions by packet")
    w("")
    w("Generated from the decision record, so packet numbers here are always current. Freeze lists cite this section instead of copying packet numbers.")
    w("")
    w("| Question | Gate | Packets |")
    w("|---|---|---|")
    for oid in sorted(oqs, key=lambda o: int(o.split("-")[1])):
        pk = [f"{s['packet']} ({s['du']} {s['milestone']})" for s in seq if s["du"] in oqs[oid]["dus"]]
        w(f"| {oid} | {oqs[oid]['blocks']} | {', '.join(pk) or '—'} |")
    w("")
    w("## 8. Exit evidence by requirement")
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


def provenance(bp_bytes: bytes, dec_bytes: bytes, gen_bytes: bytes, lock_bytes: bytes, matrix_bytes: bytes) -> dict:
    h = lambda b: hashlib.sha256(b).hexdigest()
    return {
        "blueprint": {"path": f"docs/design/van-next/{BLUEPRINT.name}", "sha256": h(bp_bytes)},
        "owner_decisions": {"path": f"docs/design/van-next/{DECISIONS.name}", "sha256": h(dec_bytes)},
        "generator": {"path": "docs/design/van-next/plan/generate_plan.py", "sha256": h(gen_bytes)},
        "requirement_lock": {"path": f"docs/design/van-next/plan/{REQ_LOCK.name}", "sha256": h(lock_bytes)},
        "surface_matrix": {"path": f"docs/design/van-next/{SURFACES.name}", "sha256": h(matrix_bytes)},
        "aggregate_input_sha256": h(bp_bytes + b"\n" + dec_bytes + gen_bytes + lock_bytes + matrix_bytes),
        "aggregate_algorithm": "sha256(blueprint_bytes + b'\\n' + decisions_bytes + generator_bytes + requirement_lock_bytes + surface_matrix_bytes)",
    }


def produce(bp_bytes: bytes, dec_bytes: bytes, gen_bytes: bytes, lock_bytes: bytes | None = None, matrix_bytes: bytes | None = None):
    lock_bytes = REQ_LOCK.read_bytes() if lock_bytes is None else lock_bytes
    matrix_bytes = SURFACES.read_bytes() if matrix_bytes is None else matrix_bytes
    bp, dec = bp_bytes.decode(), dec_bytes.decode()
    dus, edges, dotted, reqs, oqs, findings = build(bp, dec, lock_bytes=lock_bytes, matrix_bytes=matrix_bytes)
    seq, deps, level = order(dus, edges, PLAN_CHOICES)
    prov = provenance(bp_bytes, dec_bytes, gen_bytes, lock_bytes, matrix_bytes)
    md = render(dus, edges, dotted, reqs, oqs, PLAN_CHOICES, seq, deps, findings, unrequired(dus, reqs, PLAN_CHOICES), prov)
    js = json.dumps({"provenance": prov, "findings": findings, "packets": seq}, indent=1) + "\n"
    return md, js, prov, findings, seq


def stale(expected_md: str, on_disk_md: str) -> list[str]:
    return [] if expected_md == on_disk_md else ["STALE_PLAN: the committed plan does not match its current inputs; regenerate it"]


def build(bp_text: str, dec_text: str, choices=PLAN_CHOICES, lock_bytes: bytes | None = None, matrix_bytes: bytes | None = None):
    dus, edges, dotted = parse_dag(bp_text)
    reqs = parse_requirements(bp_text)
    oqs = parse_open_questions(dec_text)
    lock = (REQ_LOCK.read_bytes() if lock_bytes is None else lock_bytes, dec_text,
            SURFACES.read_bytes() if matrix_bytes is None else matrix_bytes)
    findings = duplicate_findings(bp_text, dec_text) + validate(dus, edges, reqs, oqs, choices, lock)
    return dus, edges, dotted, reqs, oqs, findings


def selftest() -> int:
    bp, dec = BLUEPRINT.read_text(), DECISIONS.read_text()
    base = build(bp, dec)[-1]
    if base:
        print("baseline has findings; fix them before the self-test:", base)
        return 1
    lock_bytes, matrix = REQ_LOCK.read_bytes(), json.loads(SURFACES.read_bytes())

    def row(text, rid):
        return next(l + "\n" for l in text.splitlines() if l.startswith(f"| {rid} |"))

    def drop_row(text, rid):
        return text.replace(row(text, rid), "", 1)

    def matrix_with(fn):
        m = json.loads(json.dumps(matrix))
        fn(m["records"])
        return json.dumps(m).encode()

    cases = {
        "cycle": (bp.replace("  A0[DU-00a Read-only inventory", "  J --> A0\n  A0[DU-00a Read-only inventory", 1), dec, PLAN_CHOICES, "CYCLE"),
        "requirement to unknown DU": (bp.replace("| VAN-NX-044 | Replay sandbox | DU-10c |", "| VAN-NX-044 | Replay sandbox | DU-99 |", 1), dec, PLAN_CHOICES, "REQ_DU_NOT_IN_DAG"),
        "open question to unknown DU": (bp, dec.replace("| DU-29 |", "| DU-98 |", 1), PLAN_CHOICES, "OQ_DU_NOT_IN_DAG"),
        "DU without lane": (bp, dec, {**PLAN_CHOICES, "lane": {k: v for k, v in PLAN_CHOICES["lane"].items() if k != "DU-16"}}, "DU_NO_LANE"),
        "phase inversion": (bp, dec, {**PLAN_CHOICES, "phase": {**PLAN_CHOICES["phase"], "DU-01": "P4"}}, "PHASE_INVERSION"),
        "feature unit cut off from qualification": (bp.replace("  K --> Z\n", "", 1), dec, PLAN_CHOICES, "QUAL_UNREACHED"),
        "code-bearing work before the F15 gate": (bp.replace("  A --> C[DU-02 Visual golden authority + labels]", "  B --> C[DU-02 Visual golden authority + labels]", 1), dec, PLAN_CHOICES, "CODE_BEFORE_F15"),
        "requirement producer not upstream": (bp.replace("  N --> JD\n", "", 1), dec, PLAN_CHOICES, "REQ_NEEDS_NOT_UPSTREAM"),
        # Rev 1.9b (NXA-02): Product Truth cannot be dropped, changed or added outside the owner-pinned lock
        "money requirement deleted (VAN-NX-055)": (drop_row(bp, "VAN-NX-055"), dec, PLAN_CHOICES, "REQ_REMOVED"),
        "visual requirement deleted (VAN-NX-004)": (drop_row(bp, "VAN-NX-004"), dec, PLAN_CHOICES, "REQ_REMOVED"),
        "requirement text changed": (bp.replace(row(bp, "VAN-NX-055"), row(bp, "VAN-NX-055").replace("Deposits", "Deposits only"), 1), dec, PLAN_CHOICES, "REQ_CHANGED"),
        "requirement added without locking": (bp.replace(row(bp, "VAN-NX-055"), row(bp, "VAN-NX-055") + "| VAN-NX-099 | Unlocked extra | DU-29c | Anything |\n", 1), dec, PLAN_CHOICES, "REQ_NOT_LOCKED"),
        "lock edited without re-approval": (bp, dec, PLAN_CHOICES, "LOCK_CHANGED_WITHOUT_APPROVAL", lock_bytes.replace(b'"VAN-NX-055"', b'"VAN-NX-055-X"', 1), None),
        "lock not pinned": (bp, re.sub(r"^\| REQUIREMENT_LOCK .*\n", "", dec, flags=re.M), PLAN_CHOICES, "LOCK_NOT_PINNED"),
        "legacy surface removed": (bp, dec, PLAN_CHOICES, "SURFACE_REMOVED", None, matrix_with(lambda r: r.pop(0))),
        "legacy owner action dropped": (bp, dec, PLAN_CHOICES, "SURFACE_OBLIGATIONS_CHANGED", None, matrix_with(lambda r: r[0]["actions"].pop())),
        # Rev 1.9b (NXA-03): collisions are findings, not silent overwrites
        "requirement duplicated with contradictory text": (bp.replace(row(bp, "VAN-NX-055"), row(bp, "VAN-NX-055") + row(bp, "VAN-NX-055").replace("Deposits", "No deposits"), 1), dec, PLAN_CHOICES, "REQ_DUPLICATE"),
        "open question duplicated": (bp, dec.replace("| OQ-16 |", "| OQ-15 |", 1), PLAN_CHOICES, "OQ_DUPLICATE"),
        "DAG node with two labels": (bp.replace("  N --> JD\n", "  N --> JD\n  N[DU-13 Another title]\n", 1), dec, PLAN_CHOICES, "DAG_DUPLICATE"),
        "legacy surface duplicated": (bp, dec, PLAN_CHOICES, "SURFACE_DUPLICATE", None, matrix_with(lambda r: r.append(dict(r[0])))),
        # Rev 1.9b (NXA-04): no code-bearing unit may sit outside the parity checker's reach
        "code-bearing unit not downstream of the parity checker": (bp.replace("  A --> C[DU-02 Visual golden authority + labels]", "  FG --> C[DU-02 Visual golden authority + labels]", 1), dec, PLAN_CHOICES, "PARITY_BEFORE_CHECKER"),
    }
    bad = 0
    for name, case in cases.items():
        b, d, ch, expect = case[:4]
        lb, mb = (case[4], case[5]) if len(case) > 4 else (None, None)
        assert b != bp or d != dec or ch is not PLAN_CHOICES or lb or mb, f"self-test case '{name}' did not change its input"
        got = build(b, d, ch, lock_bytes=lb, matrix_bytes=mb)[-1]
        ok = any(x.startswith(expect) for x in got)
        print(f"{'caught' if ok else 'MISSED'}: {name} → {[x for x in got if x.startswith(expect)][:1] or got[:1]}")
        bad += 0 if ok else 1
    # staleness: a plan produced from the real inputs must be flagged stale against altered inputs
    gen = GENERATOR.read_bytes()
    real_md = produce(BLUEPRINT.read_bytes(), DECISIONS.read_bytes(), gen)[0]
    altered_md = produce(BLUEPRINT.read_bytes(), DECISIONS.read_bytes() + b"\n", gen)[0]
    got = stale(altered_md, real_md)
    print(f"{'caught' if got else 'MISSED'}: stale plan → {got[:1]}")
    bad += 0 if got else 1
    # the auditor's path: a caller that drops a requirement from the parsed set and calls validate() directly
    dus, edges, _, reqs, oqs, _ = build(bp, dec)
    got = [x for x in validate(dus, edges, {k: v for k, v in reqs.items() if k != "VAN-NX-055"}, oqs, PLAN_CHOICES) if x.startswith("REQ_REMOVED")]
    print(f"{'caught' if got else 'MISSED'}: requirement dropped before a direct validate() call → {got[:1]}")
    bad += 0 if got else 1
    return 1 if bad else 0


def write_lock() -> int:
    previous = json.loads(REQ_LOCK.read_text()) if REQ_LOCK.exists() else None
    lock, refused = make_lock(BLUEPRINT.read_text(), SURFACES.read_bytes(), previous)
    if refused:
        print("REFUSED: these locked requirements are missing and not superseded by an owner decision:", ", ".join(refused))
        return 1
    body = (json.dumps(lock, indent=1) + "\n").encode()
    REQ_LOCK.write_bytes(body)
    print(f"{len(lock['requirements'])} requirements, {len(lock['surface_obligations'])} surfaces locked → {REQ_LOCK.name}")
    print(f"sha256 {hashlib.sha256(body).hexdigest()}  (takes effect only when pinned in {DECISIONS.name})")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--write-requirement-lock" in argv:
        return write_lock()
    md, js, prov, findings, seq = produce(BLUEPRINT.read_bytes(), DECISIONS.read_bytes(), GENERATOR.read_bytes())
    if "--check" in argv:
        findings = findings + stale(md, OUT_MD.read_text() if OUT_MD.exists() else "")
        for x in findings:
            print("FINDING", x)
        print(f"{len(findings)} findings")
        return 1 if findings else 0
    for x in findings:
        print("FINDING", x)
    OUT_MD.write_text(md)
    OUT_JSON.write_text(js)
    h = lambda b: hashlib.sha256(b).hexdigest()
    OUT_PROV.write_text(json.dumps({**prov, "generated_plan_md_sha256": h(md.encode()), "generated_plan_json_sha256": h(js.encode()),
                                    "packet_count": len(seq), "du_count": len({x["du"] for x in seq}),
                                    "all_build_units_reach_qualification": not any(x.startswith("QUAL_") for x in findings),
                                    "independent_f0_f15_certificate": "NOT_ISSUED"}, indent=1) + "\n")
    print(f"{len(seq)} packets, {len(findings)} findings → {OUT_MD.name}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
