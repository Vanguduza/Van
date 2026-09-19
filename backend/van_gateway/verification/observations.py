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


async def trading_halt_readback(trading: Any) -> dict[str, Any]:
    """§§22, 421 — the VATI kill-switch ledger is the authority on whether trading stopped.

    `trading.halt` appends an OWNER_HALT kill-switch event and returns; nothing in that
    return proves the runner acted on it. This asks the hash-chained ledger what is true
    now, which is a different process from the one that wrote the event and the only party
    entitled to say. A ledger that cannot be read, or whose chain does not verify, raises
    or reports `chain_ok: False` rather than producing a pass.
    """
    status = trading.status()
    if not status.get("ledger_available"):
        raise ValueError("the VATI ledger is not available to read a halt back from")
    if status.get("chain_ok") is False:
        # A broken chain means the ledger cannot speak for anything, including this.
        raise ValueError("the VATI ledger chain does not verify")
    if status.get("ledger_stale"):
        # P0-TRADE-004 — a stale ledger is a copy somebody left behind, and reading a
        # halt out of it would confirm a stop that may never have reached the runner.
        raise ValueError(str(status.get("ledger_stale_reason") or "the VATI ledger is stale"))
    triggers = [str(t) for t in (status.get("kill_switch_triggers") or [])]
    active = bool(status.get("kill_switch_active"))
    head = str(status.get("head") or "")
    return {
        "kill_switch_active": active,
        "owner_halt_active": "OWNER_HALT" in triggers,
        "kill_switch_triggers": sorted(triggers),
        "evidence_refs": [f"ledger://kill-switch/{head}"] if active and head else [],
    }


async def notebook_enterprise_readback(knowledge: Any, notebook_id: str) -> dict[str, Any]:
    """§166 — ask the notebook provider what exists, not the executor what it did.

    Used for both directions: a create or a source-add claims the notebook is there, a
    delete claims it is gone, and one observation answers both because it reports what it
    found rather than whether it liked it. A provider that cannot be reached raises, which
    the caller turns into UNVERIFIABLE — never into a pass.
    """
    notebook_id = str(notebook_id or "").strip()
    if not notebook_id:
        raise ValueError("notebook readback needs a notebook_id to look for")
    try:
        found = await knowledge.notebook_enterprise_get(notebook_id)
    except Exception as exc:  # noqa: BLE001 - "gone" and "unreachable" are different answers
        if _is_absent(exc):
            return {
                "notebook_id": notebook_id,
                "notebook_exists": False,
                "evidence_refs": [f"provider-readback://notebook/{notebook_id}#absent"],
            }
        raise
    exists = bool(found)
    return {
        "notebook_id": notebook_id,
        "notebook_exists": exists,
        "source_count": len(found.get("sources") or []) if isinstance(found, dict) else 0,
        "evidence_refs": [f"provider-readback://notebook/{notebook_id}"] if exists else [],
    }


#: A provider that answers "no such notebook" has observed a deletion; one that cannot be
#: reached has observed nothing. Collapsing the two is how a failed delete reads as done.
#: Deliberately narrow. An unrecognised error raises, which becomes UNVERIFIABLE; a
#: marker matched too eagerly would read a failed delete as a completed one.
_ABSENT_MARKERS = ("not_found", "notfound", "404")


def _is_absent(exc: Exception) -> bool:
    text = f"{type(exc).__name__}:{exc}".casefold()
    return any(marker in text for marker in _ABSENT_MARKERS)


__all__ = [
    "automation_run_state_predicate",
    "browser_evidence_readback",
    "google_resource_readback",
    "notebook_enterprise_readback",
    "trading_halt_readback",
    "trading_ledger_readback",
]
