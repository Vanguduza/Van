#!/usr/bin/env python3
"""Promote owner-approved proposed stack-lock layers into the admitted lock.

Rev 1.3 §366 blocks stack-lock mutation until the repository records the required
owner-approved adoption decision. This script performs the promotion once that
decision exists, and refuses otherwise — so the promotion is mechanical and
auditable rather than a hand edit.

It verifies, before writing:

* every layer's adoption decision is ``owner_signature_status: SIGNED``
* each signed decision carries an ``owner_decision_record`` with provenance
* no proposed layer is already admitted
* no proposed layer claims ``executes_live_orders`` or latency tier T0

Usage:
    python tools/architecture/promote_stack_lock_layers.py            # dry run
    python tools/architecture/promote_stack_lock_layers.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "trading" / "architecture" / "stack_lock.json"
PROPOSAL = ROOT / "trading" / "architecture" / "proposed" / "automation_browser_fabric_layers.json"

#: Keys the proposal carries for its own bookkeeping that must not leak into the lock.
_PROPOSAL_ONLY_KEYS = ("proposal_status",)


def _fail(message: str) -> int:
    print(f"REFUSED: {message}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the promotion")
    args = parser.parse_args()

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))

    admitted = {layer["layer"] for layer in lock["layers"]}
    refs = proposal.get("adoption_decision_refs", {})

    for layer in proposal["layers"]:
        name = layer["layer"]
        if name in admitted:
            return _fail(f"layer already admitted: {name}")
        if layer.get("executes_live_orders") is not False:
            return _fail(f"layer claims live order execution: {name}")
        if layer.get("latency_tier") == "T0":
            return _fail(f"layer claims T0: {name}")

        ref = refs.get(name)
        if not ref:
            return _fail(f"no adoption decision reference for {name}")
        decision_path = ROOT / ref
        if not decision_path.is_file():
            return _fail(f"adoption decision missing: {ref}")
        decision = decision_path.read_text(encoding="utf-8")
        if "owner_signature_status: SIGNED" not in decision:
            return _fail(f"adoption decision not owner-signed: {ref}")
        if "owner_decision_record:" not in decision or "provenance:" not in decision:
            return _fail(f"signed decision lacks provenance: {ref}")

    promoted = []
    for layer in proposal["layers"]:
        entry = {k: v for k, v in layer.items() if k not in _PROPOSAL_ONLY_KEYS}
        entry["adoption_decision_ref"] = refs[layer["layer"]]
        promoted.append(entry)

    print(f"verified {len(promoted)} layer(s) ready for promotion:")
    for entry in promoted:
        print(f"  {entry['layer']:24} tier={entry['latency_tier']}  licence={entry['licence_class']}")

    if not args.apply:
        print("\ndry run — re-run with --apply to write trading/architecture/stack_lock.json")
        return 0

    lock["layers"].extend(promoted)
    lock["revision"] = "5.2.0"
    lock["locked_at"] = "2026-09-18"
    notes = lock.setdefault("notes", [])
    notes.append(
        "5.2.0 admits the Automation & Browser Fabric layers (integration_automation, "
        "semantic_browser, deterministic_browser) under owner adoption decisions recorded "
        "2026-09-18. None executes live orders; none is in the T0 path. Payments are never "
        "automated on any of them."
    )
    LOCK.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    proposal["proposal_status"] = "PROMOTED"
    proposal["promoted_at"] = "2026-09-18"
    proposal["promoted_into_revision"] = "5.2.0"
    PROPOSAL.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")

    print(f"\npromoted into stack_lock.json revision {lock['revision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
