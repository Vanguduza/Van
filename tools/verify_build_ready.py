#!/usr/bin/env python3
"""Rev 5.1 mechanical verifier (TRD-REV51 / G0).

Green certifies **specification closure only**. It does not certify
implementation correctness, runtime behaviour, or live eligibility. That
distinction is the whole point of the check: a repository can be internally
consistent about what it promised and still have no right to trade.

What closure means here:

* every packet named in the execution pack index exists in the registry, with
  the same id, DU id, title and hook;
* every packet names a module and at least one test that exist on disk;
* every gate in the implementation order either carries packets or is declared
  structural with a reason;
* every invariant a packet cites is a real invariant, and no invariant is
  decorative (each one is cited by at least one packet);
* the two sole-authority invariants hold as *static* facts about the tree:
  one order-sending boundary, one live numeric sizer;
* the pack has not quietly promoted itself to live.

Exit 0 = closed. Exit 1 = open, with every failure named.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "trading" / "rev51" / "packets.json"
PACK = ROOT / "docs" / "trading" / "rev51" / "REV51_EXECUTION_PACK_MASTER.md"

#: INV-EXEC-001. The venue adapter's order-sending call, and the only module
#: permitted to make it. A second caller is a second broker-submit path.
SUBMIT_CALL = re.compile(r"\badapter\.submit\s*\(|\b[a-z_]*adapter[a-z_]*\.submit\s*\(")
SUBMIT_BOUNDARY = "trading/vati/execution/router.py"

#: INV-AUTH-001. Only the Risk Authority may construct a RiskDecision carrying
#: an approved size. Anything else producing one is a second live sizer.
DECISION_CTOR = re.compile(r"\bRiskDecision\s*\(")
DECISION_BOUNDARY = "trading/vati/risk/authority.py"

#: Modules that legitimately mention these symbols without being an authority:
#: serialisation, the router's own verification of a sealed decision, and tests.
DECISION_READERS = {
    "trading/vati/risk/serde.py",
    "trading/vati/execution/router.py",
}

PACK_ROW = re.compile(
    r"^- `(?P<packet_id>TRD-REV51-\d{3})` / `(?P<du_id>DU-TRD-\d{3})` — \*\*(?P<title>[^*]+)\*\* — (?P<hook>.+)$"
)


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, ok: bool, detail: str) -> bool:
        self.checks += 1
        if not ok:
            self.failures.append(detail)
        return ok


def _unwrap_hook(raw: str) -> str:
    """The pack index wraps hooks in backticks, sometimes unbalanced. Compare
    the text, not the markup."""
    return raw.replace("`", "").strip()


def load_registry() -> dict:
    if not REGISTRY.exists():
        raise SystemExit(f"FAIL registry missing: {REGISTRY.relative_to(ROOT)}")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def pack_index() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not PACK.exists():
        return rows
    for line in PACK.read_text(encoding="utf-8").splitlines():
        m = PACK_ROW.match(line.strip())
        if m:
            rows[m.group("packet_id")] = {
                "du_id": m.group("du_id"),
                "title": m.group("title").strip(),
                "hook": _unwrap_hook(m.group("hook")),
            }
    return rows


def check_registry_shape(reg: dict, r: Report) -> None:
    for field in ("schema_version", "revision", "baseline_commit", "invariants",
                  "gate_order", "packets", "cognition_mode", "live_advisory", "live_status"):
        r.check(field in reg, f"registry is missing required field {field!r}")
    r.check(reg.get("revision") == "5.1", f"registry revision is {reg.get('revision')!r}, expected '5.1'")
    ids = [p["packet_id"] for p in reg.get("packets", [])]
    r.check(len(ids) == len(set(ids)), "registry contains duplicate packet ids")


def check_pack_join(reg: dict, r: Report) -> None:
    """The registry is a claim about the pack. Every claim must join back."""
    index = pack_index()
    r.check(bool(index), "execution pack index could not be parsed (no packet rows found)")
    by_id = {p["packet_id"]: p for p in reg["packets"]}
    for pid, row in index.items():
        p = by_id.get(pid)
        if not r.check(p is not None, f"{pid} is in the pack index but not in the registry"):
            continue
        r.check(p["du_id"] == row["du_id"], f"{pid} du_id {p['du_id']!r} != pack {row['du_id']!r}")
        r.check(p["title"] == row["title"], f"{pid} title {p['title']!r} != pack {row['title']!r}")
        hook = _unwrap_hook(p["hook"])
        r.check(hook == row["hook"], f"{pid} hook {hook!r} != pack {row['hook']!r}")
    for pid in by_id:
        r.check(pid in index, f"{pid} is in the registry but not in the pack index")


def check_gates(reg: dict, r: Report) -> None:
    order = reg["gate_order"]
    structural = reg.get("structural_gates", {})
    used = {p["gate"] for p in reg["packets"]}
    for gate in order:
        if gate in used:
            continue
        r.check(gate in structural,
                f"gate {gate} carries no packet and is not declared structural")
        if gate in structural:
            r.check(bool(str(structural[gate]).strip()),
                    f"structural gate {gate} has an empty reason")
    for p in reg["packets"]:
        r.check(p["gate"] in order, f"{p['packet_id']} names gate {p['gate']!r}, which is not in gate_order")


def check_artifacts(reg: dict, r: Report) -> None:
    for p in reg["packets"]:
        mod = ROOT / p["module"]
        r.check(mod.exists(), f"{p['packet_id']} module does not exist: {p['module']}")
        r.check(bool(p["tests"]), f"{p['packet_id']} names no test")
        for t in p["tests"]:
            r.check((ROOT / t).exists(), f"{p['packet_id']} test does not exist: {t}")


def check_invariants(reg: dict, r: Report) -> None:
    declared = set(reg["invariants"])
    cited: set[str] = set()
    for p in reg["packets"]:
        r.check(bool(p["invariants"]), f"{p['packet_id']} cites no invariant")
        for inv in p["invariants"]:
            r.check(inv in declared, f"{p['packet_id']} cites unknown invariant {inv}")
            cited.add(inv)
    for inv in sorted(declared - cited):
        r.check(False, f"invariant {inv} is declared but cited by no packet")


def check_live_posture(reg: dict, r: Report) -> None:
    """INV-LIVE-001. The first pass is offline evolution plus shadow live."""
    r.check(reg.get("live_advisory") == "DISABLED",
            f"live_advisory is {reg.get('live_advisory')!r}; INV-LIVE-001 requires DISABLED")
    r.check(reg.get("live_status") == "NOT_CLAIMED",
            f"live_status is {reg.get('live_status')!r}; INV-EVID-001 forbids a self-asserted live claim")
    r.check(reg.get("cognition_mode") == "OFFLINE_EVOLUTION+SHADOW_LIVE",
            f"cognition_mode is {reg.get('cognition_mode')!r}; INV-LIVE-001 fixes the first pass")


def _python_sources() -> list[Path]:
    out: list[Path] = []
    for base in ("trading/vati", "backend/app"):
        d = ROOT / base
        if d.exists():
            out.extend(sorted(d.rglob("*.py")))
    return out


def check_sole_boundaries(r: Report) -> None:
    """INV-AUTH-001 and INV-EXEC-001, as static facts rather than intentions."""
    submit_callers: list[str] = []
    decision_makers: list[str] = []
    for f in _python_sources():
        rel = f.relative_to(ROOT).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        if SUBMIT_CALL.search(text) and rel != SUBMIT_BOUNDARY:
            submit_callers.append(rel)
        if DECISION_CTOR.search(text) and rel != DECISION_BOUNDARY and rel not in DECISION_READERS:
            decision_makers.append(rel)
    r.check(not submit_callers,
            "INV-EXEC-001: broker submit reached outside the ExecutionRouter: " + ", ".join(submit_callers))
    r.check(not decision_makers,
            "INV-AUTH-001: RiskDecision constructed outside the RiskAuthority: " + ", ".join(decision_makers))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="verify_build_ready")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    a = ap.parse_args(argv)

    reg = load_registry()
    r = Report()
    check_registry_shape(reg, r)
    check_pack_join(reg, r)
    check_gates(reg, r)
    check_artifacts(reg, r)
    check_invariants(reg, r)
    check_live_posture(reg, r)
    check_sole_boundaries(r)

    ok = not r.failures
    result = {
        "specification_closure": "CLOSED" if ok else "OPEN",
        "certifies": "specification closure only; not implementation, runtime or live eligibility",
        "packets": len(reg["packets"]),
        "checks": r.checks,
        "failures": r.failures,
        "live_status": reg.get("live_status"),
    }
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Rev {reg['revision']} specification closure: {result['specification_closure']}")
        print(f"  packets {result['packets']}   checks {r.checks}   failures {len(r.failures)}")
        for f in r.failures:
            print(f"  FAIL {f}")
        print("  green certifies specification closure only, not implementation/runtime/live eligibility")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
