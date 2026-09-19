"""The independent observations the gateway can actually make.

Two verification systems exist in VAN and the audit found both defective in the same way.
`VerifierRegistry` (mission core) was constructed only in tests; `WorkflowVerifier`
(automation) was constructed in production with an empty observer map, so every automation
run came back UNVERIFIABLE and `owner_success` could never be true. Findings P0-VERIFY-001,
P1-AUTO-001 and the verifier half of P2-COH-002.

Unifying the two record shapes would be a large refactor for little gain: each subsystem
persists its own, and neither shape is wrong. What was genuinely duplicated — and worth
having exactly once — is the *observations*. So they live here, written once, and each
system wraps them in its own adapter. Adding a way to observe the world is now one change
rather than two.

The bar for adding one is fixed and is the reason this file is short: an observation must
reach a system that is independent of whoever did the work. Asking n8n whether its own
workflow succeeded, or asking Hermes whether its run worked, is forwarding a claim. Where
no independent source exists, nothing is registered, the honest fallback answers
UNVERIFIABLE, and the owner is told VAN could not confirm it. That is a supported outcome,
not a hole to be filled with something optimistic.
"""

from __future__ import annotations

from typing import Any

from van_gateway.storage.db import Store


async def trading_ledger_readback(trading: Any, trade_intent_id: str) -> dict[str, Any]:
    """§22 — the VATI ledger is the authority on whether a trade happened."""
    detail = trading.trade_detail(trade_intent_id)
    if not detail:
        return {"trade_intent_id": trade_intent_id, "trade_found": False}
    return {
        "trade_intent_id": trade_intent_id,
        "trade_found": True,
        "status": detail.get("status"),
        "filled_qty": detail.get("filled_qty"),
        "fill_price": detail.get("fill_price"),
        "evidence_refs": [f"ledger://trade/{trade_intent_id}"],
    }


async def browser_evidence_readback(store: Store, mission_id: str) -> dict[str, Any]:
    """§34 — the artefacts the browser fabric stored, not what the worker reported."""
    rows = await store.fetchall(
        """
        SELECT e.evidence_id, e.kind
        FROM browser_evidence e
        JOIN mission_activities a ON a.executor_ref = e.task_id
        WHERE a.mission_id = ? AND a.executor = 'BROWSER_FABRIC'
        ORDER BY e.created_at_ms
        """,
        (mission_id,),
    )
    if not rows:
        return {"evidence_captured": False}
    return {
        "evidence_captured": True,
        "evidence_count": len(rows),
        "kinds": sorted({str(r["kind"]) for r in rows}),
        "evidence_refs": [f"browser-evidence://{r['evidence_id']}" for r in rows],
    }


async def google_resource_readback(google: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """§166 — read the resource back from the provider that was asked to create it.

    Independent of n8n: the workflow asked Google to do something, and this asks Google
    what is there now. A provider that cannot be reached raises, and the caller turns that
    into UNVERIFIABLE — never into a pass.
    """
    surface = str(spec.get("surface") or "").strip().lower()
    query = str(spec.get("query") or "").strip()
    if not surface or not query:
        raise ValueError("readback needs a surface and a query to look for")

    if surface == "gmail":
        found = await google.gmail_search(query)
        refs = [f"provider-readback://gmail/{m.get('id')}" for m in found if m.get("id")]
    elif surface == "drive":
        found = await google.drive_search(query)
        refs = [f"provider-readback://drive/{m.get('id')}" for m in found if m.get("id")]
    else:
        raise ValueError(f"no independent readback for surface {surface!r}")

    return {"exists": bool(found), "match_count": len(found), "evidence_refs": refs,
            "evidence_pointer": refs[0] if refs else None}


async def automation_run_state_predicate(store: Store, run_id: str) -> dict[str, Any]:
    """The gateway's own durable record of a run, which n8n does not write.

    This is admissible for STATE_PREDICATE because the row is written by the gateway's
    dispatch path from what it independently observed, not by the engine reporting on
    itself. It is weak evidence and typed as such: it proves the gateway saw a terminal
    submission, not that the world changed.
    """
    row = await store.fetchone(
        "SELECT run_id, status, evidence_pointer, output_digest, completed_at_ms "
        "FROM automation_runs WHERE run_id = ?",
        (run_id,),
    )
    if row is None:
        return {"exists": False}
    return {
        "exists": True,
        "run_id": str(row["run_id"]),
        "status": str(row["status"]),
        "output_digest": row["output_digest"],
        "completed_at_ms": row["completed_at_ms"],
        "evidence_pointer": row["evidence_pointer"],
        "evidence_refs": [f"automation-run://{row['run_id']}"] if row["evidence_pointer"] else [],
    }


__all__ = [
    "automation_run_state_predicate",
    "browser_evidence_readback",
    "google_resource_readback",
    "trading_ledger_readback",
]
