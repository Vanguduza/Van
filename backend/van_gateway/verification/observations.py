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

import json
from typing import Any

from van_gateway.command.authority import AuthoritySource, CommandAuthorityService
from van_gateway.models import PrincipalType
from van_gateway.storage.db import Store


async def standing_intent_disable_readback(store: Store, intent_id: str, command_id: str) -> dict[str, Any]:
    """Observe exact intent state and captured roots independently after execution."""
    intent = await store.fetchone("SELECT enabled FROM automation_standing_intents WHERE intent_id=?", (intent_id,))
    if intent is None:
        return {"intent_id": intent_id, "exists": False}
    roots = await store.fetchall(
        "SELECT authority_id,source_device_id,revoked_at_ms FROM standing_automation_authorities WHERE standing_intent_id=?",
        (intent_id,),
    )
    row = await store.fetchone("SELECT value FROM runtime_meta WHERE key=?", ("standing_disable_witness:" + command_id,))
    witness = json.loads(row["value"]) if row else {}
    captured = witness.get("authority_ids", [])
    by_id = {str(r["authority_id"]): r for r in roots}
    authority = await CommandAuthorityService(store).get(command_id)
    bound = bool(
        authority and authority.authority_source is AuthoritySource.OWNER_COMMAND
        and authority.principal_type is PrincipalType.OWNER_DEVICE
        and authority.typed_action_id == "automation.standing_intent.disable"
        and authority.typed_parameter_constraints.get("intent_id") == intent_id
        and witness.get("intent_id") == intent_id and witness.get("command_id") == command_id
        and any(r["source_device_id"] == authority.device_id for r in roots)
    )
    revoked = bool(captured and isinstance(captured, list) and all(
        isinstance(root, str) and root in by_id and by_id[root]["revoked_at_ms"] is not None
        for root in captured
    ))
    observed = {
        "intent_id": intent_id, "enabled": bool(intent["enabled"]),
        "active_authorities": sum(r["revoked_at_ms"] is None for r in roots),
        "captured_authorities_revoked": revoked, "owner_command_bound": bound,
    }
    if bound and revoked:
        observed["evidence_refs"] = [f"standing-intent://{intent_id}/disable/{command_id}"]
    return observed


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


async def trading_ticket_readback(trading: Any, ticket_id: str) -> dict[str, Any]:
    """Confirm only the owner-recorded broker receipt, never broker execution itself."""
    from van_gateway.command.resolver import canonical_positive_decimal

    if trading is None or not trading.available():
        raise FileNotFoundError("trading ledger unavailable")
    status = trading.status()
    ticket = next((item for item in trading.tickets() if item.get("ticket") == ticket_id), None)
    observed = {"ticket_id": ticket_id, "ticket_found": ticket is not None,
        "ledger_chain_ok": status.get("chain_ok") is True}
    if ticket is not None:
        observed.update(status=ticket.get("status"), contract_note_ref=ticket.get("contract_note_ref"))
        if ticket.get("status") == "CONFIRMED":
            observed.update(fill_price=canonical_positive_decimal(ticket.get("fill_price")),
                filled_qty=canonical_positive_decimal(ticket.get("filled_qty")))
            digest = ticket.get("confirmation_hash")
            if isinstance(digest, str) and len(digest) == 64 and observed["ledger_chain_ok"]:
                observed["evidence_ref"] = f"vati-event:{digest}"
    return observed


async def gmail_sent_readback(store: Store, google: Any, command_id: str, postconditions: dict[str, Any]) -> dict[str, Any]:
    """Correlations locate a provider object; only sealed owner intent and fresh raw MIME prove it."""
    from van_gateway.action.service import ActionRuntime
    from van_gateway.google.mail import content_digest, message_snapshot

    if google is None:
        raise ValueError("Google provider unavailable")
    authority = await CommandAuthorityService(store).get(command_id)
    params = {"draft_id": postconditions.get("draft_id"), "draft_content_sha256": postconditions.get("draft_content_sha256")}
    if (authority is None or authority.authority_source is not AuthoritySource.OWNER_COMMAND
        or authority.principal_type is not PrincipalType.OWNER_DEVICE or not authority.owner_approved
        or authority.typed_action_id != "google.gmail.send" or authority.typed_parameter_constraints != params):
        raise ValueError("Gmail send is not bound to sealed owner approval")
    rows = await store.fetchall("SELECT correlation_json,parameters_digest FROM action_executions "
        "WHERE command_id=? AND action_id='google.gmail.send' AND submitted_at_ms IS NOT NULL", (command_id,))
    message_ids = set()
    for row in rows:
        correlation = json.loads(row["correlation_json"])
        if row["parameters_digest"] != ActionRuntime.digest_parameters(params) or correlation.get("source_draft_id") != params["draft_id"]:
            raise ValueError("Gmail send correlation is not bound to approved parameters")
        message_id = correlation.get("message_id")
        if not isinstance(message_id, str) or not message_id or len(message_id) > 256:
            raise ValueError("Gmail sent message identity unavailable")
        message_ids.add(message_id)
    if len(message_ids) != 1:
        raise ValueError("Gmail sent message correlation is missing or ambiguous")
    message_id = next(iter(message_ids))
    message = await google.gmail_message_get(message_id)
    thread_id = message.get("threadId")
    if not isinstance(thread_id, str) or not thread_id:
        raise ValueError("Gmail sent thread identity unavailable")
    actual_digest = content_digest(message_snapshot(message.get("raw")), thread_id)
    observed = {"draft_id": params["draft_id"], "draft_content_sha256": actual_digest,
        "sent": message.get("id") == message_id and "SENT" in (message.get("labelIds") or []),
        "approved_content_matches": actual_digest == params["draft_content_sha256"],
        "owner_approved_command_bound": True, "message_id": message_id,
        "source_draft_cleanup": "NOT_ATTEMPTED", "source_draft_state": "UNOBSERVED",
        "evidence_ref": f"google://gmail/messages/{message_id}"}
    return observed


async def browser_evidence_readback(store: Store, mission_id: str) -> dict[str, Any]:
    """§34 — the artefacts the browser fabric stored, not what the worker reported."""
    rows = await store.fetchall(
        """
        SELECT e.evidence_id, e.kind
        FROM browser_evidence e
        JOIN mission_activities a ON a.executor_ref = e.task_id
        WHERE a.mission_id = ? AND a.executor = 'BROWSER_FABRIC'
          -- A router step record is a routing ledger entry and a postcondition verdict is a
          -- verifier's judgement; neither is a captured artefact, and a failed, refused or
          -- UNVERIFIABLE step must never read as "evidence captured".
          AND e.kind NOT IN ('interaction_router_step', 'postcondition_verification')
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


async def notebook_source_readback(
    knowledge: Any, notebook_id: str, source_names: list[str]
) -> dict[str, Any]:
    """§166 — the exact sources a mutation claims to have added or removed.

    P1-VERIFY-004. `notebook_enterprise_readback` answers a question about the *notebook*,
    and a source add or delete that failed leaves the notebook exactly as it was — so a
    contract binding only `notebook_exists` is satisfied by the failure. This reads each
    named source back individually, which the provider supports and which the delete path
    already did internally without the verifier being able to see it.

    Every source is reported in exactly one of `sources_present` or `sources_absent`, and a
    source the provider could not be asked about raises rather than landing in either: "I
    could not check" is not "it is gone", and that conflation is the whole defect.
    """
    notebook_id = str(notebook_id or "").strip()
    names = [str(name).strip() for name in (source_names or []) if str(name).strip()]
    if not notebook_id or not names:
        raise ValueError("source readback needs a notebook_id and at least one source name")

    present: list[str] = []
    absent: list[str] = []
    for name in names:
        try:
            await knowledge.notebook_enterprise_source_get(notebook_id, name)
        except Exception as exc:  # noqa: BLE001 - "gone" and "unreachable" are different
            if not _is_absent(exc):
                raise
            absent.append(name)
        else:
            present.append(name)

    return {
        "notebook_id": notebook_id,
        "source_names": sorted(names),
        "sources_present": sorted(present),
        "sources_absent": sorted(absent),
        # Evidence cites the sources actually observed, not the notebook. A
        # `provider-readback://notebook/x` reference on a source mutation would point an
        # auditor at the object that was not the subject of the claim.
        "evidence_refs": sorted(
            f"provider-readback://notebook/{notebook_id}/sources/{name.rsplit('/', 1)[-1]}"
            f"#{'present' if name in present else 'absent'}"
            for name in names
        ),
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
    "standing_intent_disable_readback",
    "automation_run_state_predicate",
    "browser_evidence_readback",
    "google_resource_readback",
    "notebook_enterprise_readback",
    "notebook_source_readback",
    "trading_halt_readback",
    "trading_ledger_readback",
]
