"""Gateway-executed typed actions: owner-device commands the gateway answers itself.

GAP-F-001, GAP-F-002, GAP-F-005 — `memory.remember`, `memory.decision.record`,
`reminder.create` and `trading.halt` all name state the gateway already owns: the owner
fact store, the reminders table, the VATI kill-switch ledger. Before this module, a typed
resolution for any of them was still dispatched to Hermes, which has no tool for any of the
four (`hermes/mcp/owner_runtime_stdio.mjs` exposes none of them). `trading.halt` reached
biometric approval and then stalled at RUNNING forever; `memory.remember` and
`reminder.create` had no resolver pattern at all, so the routes behind them
(`POST /v1/context/facts`, `POST /v1/reminders`) were production-complete with no owner-side
producer.

An executor here does three things and nothing else: it performs the one write it is named
for, it independently re-reads the store to confirm the write is actually there — not trusts
the write call's own return value — and it reports a human summary plus the postcondition
`orchestrator.py` hands to `ActionRuntime.verify`. A failure is always a named
`LocalExecutionError`, never a bare exception the owner sees as a crash, and never a partial
write reported as success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Protocol

from van_gateway.command.authority import AuthoritySource, CommandAuthorityService
from van_gateway.command.context_requirements import OWNER_SUBJECT
from van_gateway.context.authoring import ContextAuthoringError, OwnerFactAuthor
from van_gateway.context.models import ContextRequirement
from van_gateway.context.service import OwnerContextService
from van_gateway.context.memory_erasure import MemoryErasureDenied, erase_memory, memory_erasure_readback, selected_stores
from van_gateway.models import ActionClass, PrincipalType, ReminderCreate
from van_gateway.reminders.service import ReminderService
from van_gateway.reminders.timeparse import TimeParseError, parse_due_expression
from van_gateway.storage.db import Store
from van_gateway.verification.observations import standing_intent_disable_readback
from van_gateway.proactive.owner_control import (DomainCeilingDenied, ceiling_parameters,
    domain_ceiling_readback, set_owner_domain_ceiling)


class LocalExecutionError(Exception):
    """A gateway-executed typed action refused or could not complete, for a named reason.

    `code` is a stable, machine-readable failure reason (surfaced on `CommandResult` via
    `local_execution` and in the mission's `final_outcome`); `message` is what the owner is
    told. Raising this — rather than letting a bare exception surface, or returning a
    result that only looks like success — is what keeps a failed local action from ever
    being reported as accepted work.

    `status` is the wire status `orchestrator.py` puts on the `CommandResult`: "denied" for
    an owner/authority/parameter refusal (a missing required field, a missing or invalid
    `owner_halt_authority_ref`, a write policy refusal) — something the owner did or did not
    supply that they can fix — and "degraded" for an infrastructure fault (a service not
    wired on this gateway, a store that would not read back what it just wrote, a ledger it
    could not reach) — something wrong with VAN, not with what the owner asked. Defaulted to
    "denied" because most named failures here are refusals, not faults.
    """

    def __init__(self, code: str, message: str, *, status: str = "denied") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class LocalExecutionResult:
    """What an executor reports back, once its own independent re-read has confirmed it."""

    summary: str
    evidence_ref: str | None
    observed_postcondition: dict[str, Any] = field(default_factory=dict)
    mission_pending: bool = False


@dataclass
class LocalExecutionContext:
    """Exactly what a local executor needs, assembled by the orchestrator.

    Executors receive this rather than the orchestrator itself, so each one's dependencies
    are visible at a glance and a new executor cannot reach for a service the registry did
    not grant it.
    """

    store: Any
    context: OwnerContextService
    owner_fact_author: OwnerFactAuthor | None
    reminders: ReminderService | None
    trading: Any | None
    device_id: str
    command_id: str
    mission_id: str
    parameters: dict[str, Any]
    #: Unsigned request context. `owner_halt_authority_ref` rides here because it is its
    #: own separately-signed ECDSA credential — self-authenticating, so it does not need to
    #: be inside the owner's command signature the way a typed action's sealed parameters
    #: do.
    client_context: dict[str, Any]
    now_ms: int
    browser_preparation: Any | None = None
    browser_plans: Any | None = None
    browser_artifacts: Any | None = None
    automation: Any | None = None
    execution_id: str | None = None


class LocalActionExecutor(Protocol):
    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult: ...


def _require(ctx: LocalExecutionContext, name: str) -> str:
    value = ctx.parameters.get(name)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise LocalExecutionError(f"{name}_missing", f"'{name}' is required and was not sealed")
    return text


class MemoryRememberExecutor:
    """GAP-F-001 — "remember ..." writes a CANONICAL_OWNER fact.

    `OwnerFactAuthor.state` is the one writer entitled to CANONICAL_OWNER (context/authoring.py).
    After it returns, this re-reads the fact through `OwnerContextService.current_candidates`
    — a second, independent query — before calling the write a success, which is the
    STATE_PREDICATE check `action/registry.py` declares for this action.
    """

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        if ctx.owner_fact_author is None:
            raise LocalExecutionError(
                "owner_fact_author_unavailable", "owner memory is not wired on this gateway",
                status="degraded",
            )
        subject = str(ctx.parameters.get("subject") or OWNER_SUBJECT).strip() or OWNER_SUBJECT
        predicate = _require(ctx, "predicate")
        raw_value = ctx.parameters.get("value")
        value = str(raw_value).strip() if raw_value is not None else ""
        if not value:
            raise LocalExecutionError("value_missing", "'value' is required and was not sealed")
        scope = str(ctx.parameters.get("scope") or "global").strip() or "global"
        try:
            record = await ctx.owner_fact_author.state(
                device_id=ctx.device_id, subject=subject, predicate=predicate,
                value=value, scope=scope, now_ms=ctx.now_ms,
            )
        except ContextAuthoringError as exc:
            raise LocalExecutionError("owner_fact_write_refused", str(exc)) from exc
        confirmed = await ctx.context.current_candidates(
            ContextRequirement(subject=subject, predicate=predicate, scope=scope), now_ms=ctx.now_ms,
        )
        if not any(fact.fact_id == record.fact_id for fact in confirmed):
            raise LocalExecutionError(
                "owner_fact_not_readable", "the fact was written but could not be read back",
                status="degraded",
            )
        predicate_readable = predicate.replace("_", " ")
        who = "your" if subject == OWNER_SUBJECT else f"{subject}'s"
        return LocalExecutionResult(
            summary=f"Remembered: {who} {predicate_readable} is {value}.",
            evidence_ref=f"owner-fact:{record.fact_id}",
            observed_postcondition={
                "subject": subject, "predicate": predicate, "scope": scope, "fact_id": record.fact_id,
            },
        )


class MemoryDecisionRecordExecutor:
    """GAP-F-001 — "record decision: ..." / "we decided ..." write a CANONICAL_OWNER decision.

    Same writer and the same independent re-read as `MemoryRememberExecutor`; only the
    fixed subject/predicate/scope differ, so every decision lands where a later "what did
    we decide" question can find it.
    """

    SUBJECT = OWNER_SUBJECT
    PREDICATE = "decision"
    SCOPE = "decisions"

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        if ctx.owner_fact_author is None:
            raise LocalExecutionError(
                "owner_fact_author_unavailable", "owner memory is not wired on this gateway",
                status="degraded",
            )
        decision = _require(ctx, "decision")
        try:
            record = await ctx.owner_fact_author.state(
                device_id=ctx.device_id, subject=self.SUBJECT, predicate=self.PREDICATE,
                value=decision, scope=self.SCOPE, now_ms=ctx.now_ms,
            )
        except ContextAuthoringError as exc:
            raise LocalExecutionError("owner_fact_write_refused", str(exc)) from exc
        confirmed = await ctx.context.current_candidates(
            ContextRequirement(subject=self.SUBJECT, predicate=self.PREDICATE, scope=self.SCOPE),
            now_ms=ctx.now_ms,
        )
        if not any(fact.fact_id == record.fact_id for fact in confirmed):
            raise LocalExecutionError(
                "owner_fact_not_readable", "the decision was written but could not be read back",
                status="degraded",
            )
        return LocalExecutionResult(
            summary=f"Decision recorded: {decision}.",
            evidence_ref=f"owner-fact:{record.fact_id}",
            observed_postcondition={
                "subject": self.SUBJECT, "predicate": self.PREDICATE, "scope": self.SCOPE,
                "fact_id": record.fact_id,
            },
        )


class ReminderCreateExecutor:
    """GAP-F-002 — "remind me ..." creates a reminder the sweep will actually fire.

    The due expression was already validated by the resolver (`resolver.py` refuses to
    resolve one `reminders.timeparse.parse_due_expression` cannot parse), so a
    `TimeParseError` here would mean the resolver and this executor disagreed — reported as
    a failure rather than guessed at. After `ReminderService.create`, `list_open` is an
    independent re-read confirming the row exists before this reports success.
    """

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        if ctx.reminders is None:
            raise LocalExecutionError(
                "reminders_unavailable", "reminders are not wired on this gateway", status="degraded",
            )
        text = _require(ctx, "text")
        due_expression = _require(ctx, "due_expression")
        try:
            due_at_unix = parse_due_expression(due_expression)
        except TimeParseError as exc:
            raise LocalExecutionError("due_expression_unparseable", str(exc)) from exc
        idempotency_key = f"reminder:{ctx.command_id}"
        created = await ctx.reminders.create(
            ReminderCreate(text=text, due_at_unix=due_at_unix, idempotency_key=idempotency_key)
        )
        open_reminders = await ctx.reminders.list_open()
        if not any(row["id"] == created["id"] for row in open_reminders):
            raise LocalExecutionError(
                "reminder_not_readable", "the reminder was created but could not be read back",
                status="degraded",
            )
        when = datetime.fromtimestamp(due_at_unix, tz=timezone.utc).strftime("%H:%M UTC on %Y-%m-%d")
        return LocalExecutionResult(
            summary=f"Reminder set for {when}: {text}.",
            evidence_ref=f"reminder:{created['id']}",
            observed_postcondition={
                "reminder_id": created["id"], "due_at_unix": due_at_unix, "status": "OPEN",
            },
        )


class TradingHaltExecutor:
    """GAP-F-005 — the one A4 action the gateway executes itself rather than dispatching.

    `trading.halt` used to reach biometric approval and then go to Hermes, which has no
    trading tool at all, so the mission stalled at RUNNING forever and the owner had no
    working kill switch. `TradingService.halt` is already on the gateway
    (`trading/service.py`); this is the caller it never had.

    Halting live trading needs its own authority, not a reuse of the command's own
    signature, so the Android app supplies a second, separately-signed credential — an
    OwnerAuthority ECDSA token bound to act `"owner-halt"` and subject
    `"van-trading-core"` — alongside the biometric approval proof. It rides in
    `client_context["owner_halt_authority_ref"]` because it is self-authenticating (its own
    signature is checked by `TradingService`), not because it is trusted on arrival.
    Missing it is a deterministic, named failure: never a halt attempted on partial
    authority.
    """

    PARAMETER_NAME = "owner_halt_authority_ref"

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        if ctx.trading is None:
            raise LocalExecutionError(
                "trading_service_unavailable", "trading is not wired on this gateway", status="degraded",
            )
        owner_halt_authority_ref = str(ctx.client_context.get(self.PARAMETER_NAME) or "").strip()
        if not owner_halt_authority_ref:
            raise LocalExecutionError(
                "owner_halt_authority_missing",
                "trading.halt requires an owner_halt_authority_ref alongside the approval proof",
            )
        reason = str(ctx.parameters.get("reason") or "owner command via VAN").strip() or "owner command via VAN"
        try:
            outcome = ctx.trading.halt(
                owner_signature_ref=owner_halt_authority_ref, reason=reason, now_ms=ctx.now_ms,
            )
        except FileNotFoundError as exc:
            raise LocalExecutionError("trading_ledger_unavailable", str(exc), status="degraded") from exc
        except PermissionError as exc:
            # TradingAuthorityError and TradingControlError are both PermissionError —
            # an invalid, expired, wrong-act or already-used authority token.
            raise LocalExecutionError("owner_halt_authority_invalid", str(exc)) from exc
        return LocalExecutionResult(
            summary="Trading halted; OWNER_HALT recorded in the ledger.",
            evidence_ref=f"vati-event:{outcome.get('event_hash')}",
            observed_postcondition={
                "trigger": outcome.get("trigger"),
                "event_hash": outcome.get("event_hash"),
                "chain_hash": outcome.get("chain_hash"),
            },
        )


class TradingTicketConfirmExecutor:
    """Record an exact broker confirmation under separate trading and biometric authority."""

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        from van_gateway.verification.observations import trading_ticket_readback

        if ctx.trading is None:
            raise LocalExecutionError("trading_service_unavailable", "Trading is unavailable", status="degraded")
        authority = ctx.client_context.get("owner_ticket_authority_ref")
        if not isinstance(authority, str) or not authority.strip():
            raise LocalExecutionError("owner_ticket_authority_missing", "A separately signed ticket-confirm authority is required")
        parameters = {name: _require(ctx, name) for name in ("ticket_id", "fill_price", "filled_qty", "contract_note_ref")}
        try:
            ctx.trading.confirm_ticket(parameters["ticket_id"], owner_signature_ref=authority,
                fill_price=parameters["fill_price"], filled_qty=parameters["filled_qty"],
                contract_note_ref=parameters["contract_note_ref"], now_ms=ctx.now_ms)
        except FileNotFoundError as exc:
            raise LocalExecutionError("trading_ledger_unavailable", str(exc), status="degraded") from exc
        except PermissionError as exc:
            raise LocalExecutionError("owner_ticket_authority_or_state_invalid", str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise LocalExecutionError("trading_ticket_confirmation_invalid", str(exc)) from exc
        try:
            observed = await trading_ticket_readback(ctx.trading, parameters["ticket_id"])
        except Exception as exc:
            raise LocalExecutionError("trading_ticket_readback_unavailable", "Confirmation recorded; ledger readback unavailable", status="degraded") from exc
        if not observed.get("evidence_ref") or observed.get("status") != "CONFIRMED" or any(observed.get(k) != v for k, v in parameters.items()):
            raise LocalExecutionError("trading_ticket_readback_mismatch", "Confirmation recorded; exact ledger result could not be verified", status="degraded")
        return LocalExecutionResult(summary="Broker confirmation recorded in the owner ticket ledger.",
            evidence_ref=observed["evidence_ref"], observed_postcondition=observed)


class StandingIntentDisableExecutor:
    """Disable the exact owner-sealed intent and revoke only its authority roots."""

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        intent_id = _require(ctx, "intent_id")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,256}", intent_id):
            raise LocalExecutionError("standing_intent_id_invalid", "The standing intent identifier is invalid")
        authority = await CommandAuthorityService(ctx.store).get(ctx.command_id)
        if not authority or (
            authority.authority_source is not AuthoritySource.OWNER_COMMAND
            or authority.principal_type is not PrincipalType.OWNER_DEVICE
            or authority.device_id != ctx.device_id
            or authority.effective_action_class not in {ActionClass.A3, ActionClass.A4, ActionClass.A5}
            or (authority.expires_at_unix is not None and ctx.now_ms // 1000 >= authority.expires_at_unix)
            or authority.typed_action_id != "automation.standing_intent.disable"
            or authority.typed_parameter_constraints.get("intent_id") != intent_id
        ):
            raise LocalExecutionError("standing_disable_owner_authority_required", "A signed owner command for this intent is required")
        async with ctx.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            device = await (await db.execute(
                "SELECT revoked_at_unix FROM devices WHERE device_id=?", (ctx.device_id,),
            )).fetchone()
            if device is None or device["revoked_at_unix"] is not None:
                raise LocalExecutionError("standing_disable_device_revoked", "The owner device is no longer authorized")
            intent = await (await db.execute(
                "SELECT enabled FROM automation_standing_intents WHERE intent_id=?", (intent_id,),
            )).fetchone()
            if intent is None:
                raise LocalExecutionError("standing_intent_not_found", "The standing intent was not found")
            roots = await (await db.execute(
                "SELECT authority_id,source_device_id FROM standing_automation_authorities WHERE standing_intent_id=?",
                (intent_id,),
            )).fetchall()
            if not any(r["source_device_id"] == ctx.device_id for r in roots):
                raise LocalExecutionError("standing_intent_not_owned_by_device", "This device did not authorize the standing intent")
            # Capture actual roots before changing them. The separate observer reads
            # both this bounded witness and fresh authoritative rows after commit.
            witness = {
                "intent_id": intent_id, "command_id": ctx.command_id,
                "authority_ids": sorted(str(r["authority_id"]) for r in roots),
                "observed_before_write_ms": ctx.now_ms,
            }
            await db.execute(
                "UPDATE automation_standing_intents SET enabled=0,updated_at_ms=? WHERE intent_id=?",
                (ctx.now_ms, intent_id),
            )
            await db.execute(
                "UPDATE standing_automation_authorities SET revoked_at_ms=? "
                "WHERE standing_intent_id=? AND revoked_at_ms IS NULL", (ctx.now_ms, intent_id),
            )
            await db.execute(
                "INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
                ("standing_disable_witness:" + ctx.command_id, Store.dumps(witness), ctx.now_ms),
            )
            await db.commit()
        observed = await standing_intent_disable_readback(ctx.store, intent_id, ctx.command_id)
        if not (observed.get("enabled") is False and observed.get("active_authorities") == 0
                and observed.get("captured_authorities_revoked") is True and observed.get("owner_command_bound") is True):
            raise LocalExecutionError("standing_disable_not_verified", "The disabled state could not be confirmed", status="degraded")
        return LocalExecutionResult(
            summary="Standing work disabled and its authority revoked.",
            evidence_ref=observed["evidence_refs"][0], observed_postcondition=observed,
        )


class MemoryEraseExecutor:
    """Irreversible owner-memory deletion requires the existing bound A4 proof."""

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        store_id = _require(ctx, "store")
        record_fields={k:ctx.parameters[k] for k in ["record_id","expected_sha256"] if k in ctx.parameters}
        if record_fields:
            from van_gateway.understanding.records import record_parameters
            try:
                if ctx.parameters != record_parameters(store_id,record_fields["record_id"],record_fields["expected_sha256"]):
                    raise ValueError("record_erasure_scope_mismatch")
            except (ValueError,KeyError) as exc:
                raise LocalExecutionError("record_erasure_scope_invalid","The exact selected record revision is required") from exc
        try:
            stores = selected_stores(store_id)
        except ValueError as exc:
            raise LocalExecutionError("memory_store_not_allowlisted", "This store is outside owner-memory erasure") from exc
        authority = await CommandAuthorityService(ctx.store).get(ctx.command_id)
        if not authority or (
            authority.authority_source is not AuthoritySource.OWNER_COMMAND
            or authority.principal_type is not PrincipalType.OWNER_DEVICE
            or authority.device_id != ctx.device_id or not authority.owner_approved
            or authority.effective_action_class not in {ActionClass.A4, ActionClass.A5}
            or authority.typed_action_id != "memory.erase"
            or authority.typed_parameter_constraints.get("store") != store_id
            or authority.typed_parameter_constraints.get("stores") != [entry.table for entry in stores]
            or any(authority.typed_parameter_constraints.get(k)!=v for k,v in record_fields.items())
            or ctx.parameters.get("stores") != [entry.table for entry in stores]
            or authority.expires_at_unix is None or ctx.now_ms // 1000 >= authority.expires_at_unix
        ):
            raise LocalExecutionError("memory_erasure_approved_command_required", "A fresh bound owner approval for this erasure is required")
        device = await ctx.store.fetchone("SELECT revoked_at_unix FROM devices WHERE device_id=?", (ctx.device_id,))
        if device is None or device["revoked_at_unix"] is not None:
            raise LocalExecutionError("memory_erasure_device_revoked", "The owner device is no longer authorized")
        try:
            await erase_memory(ctx.store, store_id, ctx.command_id, device_id=ctx.device_id,**record_fields)
            observed = await memory_erasure_readback(ctx.store, store_id, ctx.command_id,**record_fields)
        except MemoryErasureDenied as exc:
            raise LocalExecutionError(str(exc), "The current device approval no longer authorizes this erasure") from exc
        except Exception as exc:
            raise LocalExecutionError("memory_erasure_failed", "The memory erasure could not be completed", status="degraded") from exc
        if not (observed["scope_empty"] and observed["captured_ids_absent"] and observed["owner_approved_command_bound"]
                and observed["context_cache_invalidated"]):
            raise LocalExecutionError("memory_erasure_not_verified", "The erased state could not be confirmed", status="degraded")
        total = sum(observed["removed_counts"].values())
        return LocalExecutionResult(
            summary=f"Removed {total} owner-derived memory records. Audit history and missions are retained.",
            evidence_ref=observed["evidence_refs"][0], observed_postcondition=observed,
        )


class DomainAutonomyCeilingExecutor:
    """Only a fresh, exact owner A4 command can set this bounded trust ceiling."""

    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        try:
            parameters = ceiling_parameters(ctx.parameters)
            await set_owner_domain_ceiling(ctx.store, parameters, ctx.command_id, device_id=ctx.device_id)
        except DomainCeilingDenied as exc:
            raise LocalExecutionError(str(exc), "The current approved owner command does not authorize this domain ceiling") from exc
        except ValueError as exc:
            raise LocalExecutionError(str(exc), "Choose a registered domain and a level from S0 through S4") from exc
        try:
            observed = await domain_ceiling_readback(ctx.store, parameters, ctx.command_id)
        except Exception as exc:
            raise LocalExecutionError("domain_ceiling_readback_unavailable", "Ceiling may have changed; target readback is unavailable", status="degraded") from exc
        if not observed.get("evidence_refs"):
            raise LocalExecutionError("domain_ceiling_not_verified", "The exact owner ceiling could not be confirmed", status="degraded")
        return LocalExecutionResult(
            summary=f"Owner autonomy ceiling for {parameters['domain']} set to {parameters['level']}. Native approvals, policies and evidence limits still apply.",
            evidence_ref=observed["evidence_refs"][0], observed_postcondition=observed,
        )


#: action_id -> executor factory; each executor receives only per-call context.
class OwnerPermissionGrantExecutor:
    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        from van_gateway.capability.owner_permissions import grant_owner_permission, permission_readback, OwnerPermissionDenied
        try:
            await grant_owner_permission(ctx.store,ctx.parameters,ctx.command_id,device_id=ctx.device_id)
            observed=await permission_readback(ctx.store,ctx.parameters,ctx.command_id)
        except OwnerPermissionDenied as exc:
            raise LocalExecutionError(str(exc),"The exact current owner approval does not authorize this permission grant") from exc
        if not observed.get("evidence_refs"):
            raise LocalExecutionError("permission_grant_unconfirmed","The permission grant could not be confirmed",status="degraded")
        return LocalExecutionResult(summary="Exact owner permission recorded. Native command, provider and approval gates remain required.",
            evidence_ref=observed["evidence_refs"][0],observed_postcondition=observed)


class BrowserFileProviderExecutor:
    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        from van_gateway.action.service import ActionRuntime
        from van_gateway.browser.artifact_provider import ArtifactProviderError
        if ctx.browser_artifacts is None or not ctx.execution_id:
            raise LocalExecutionError("browser_artifact_runtime_unconfigured", "File provider admission is unavailable", status="degraded")
        execution = await ActionRuntime(ctx.store).get_execution(ctx.execution_id)
        if execution is None:
            raise LocalExecutionError("browser_artifact_execution_unknown", "File submission execution is unavailable")
        try:
            await ctx.browser_artifacts.submit(execution, ctx.parameters)
            observed = await ctx.browser_artifacts.verify(execution, ctx.parameters)
        except ArtifactProviderError as exc:
            raise LocalExecutionError(str(exc), "File submission could not be independently confirmed. Inspect its receipt before issuing a new approval.", status="degraded") from exc
        if observed.get("success") is not True or not observed.get("evidence_pointer"):
            raise LocalExecutionError("browser_artifact_unverified", "File submission is unverified", status="degraded")
        return LocalExecutionResult(summary="File submission persisted and independently checked. Its contents remain untrusted evidence.",
            evidence_ref=observed["evidence_pointer"], observed_postcondition=observed)


class BrowserPlanExecutor:
    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        if ctx.browser_plans is None or not ctx.execution_id:
            raise LocalExecutionError("browser_plan_native_runtime_unconfigured", "Browser plan runtime is not configured", status="degraded")
        from van_gateway.action.service import ActionRuntime
        from van_gateway.browser.action_plans import PlanError
        execution = await ActionRuntime(ctx.store).get_execution(ctx.execution_id)
        if execution is None:
            raise LocalExecutionError("browser_plan_execution_unknown", "Browser plan execution is unavailable")
        try:
            await ctx.browser_plans.execute(execution, ctx.parameters)
            observed = await ctx.browser_plans.verify(execution, ctx.parameters)
        except PlanError as exc:
            raise LocalExecutionError(str(exc), "Browser plan could not be completed under the current exact approval", status="degraded") from exc
        if observed.get("success") is not True or not observed.get("evidence_pointer"):
            raise LocalExecutionError("browser_plan_postcondition_not_verified", "Browser plan effects could not be independently confirmed; inspect the plan before any new command", status="degraded")
        return LocalExecutionResult(summary="Browser plan completed and independently checked.",
            evidence_ref=observed["evidence_pointer"], observed_postcondition=observed)


class BrowserTaskPrepareExecutor:
    async def execute(self, ctx: LocalExecutionContext) -> LocalExecutionResult:
        from van_gateway.action.service import ActionRuntime
        from van_gateway.browser.action_plans import PlanError
        if ctx.browser_preparation is None or not ctx.execution_id:
            raise LocalExecutionError("browser_preparation_native_runtime_unconfigured", "Native browser preparation is unavailable", status="degraded")
        execution = await ActionRuntime(ctx.store).get_execution(ctx.execution_id)
        try:
            await ctx.browser_preparation.prepare(execution, ctx.parameters, ctx.mission_id)
            observed = await ctx.browser_preparation.readback(execution, ctx.parameters, ctx.mission_id)
        except PlanError as exc:
            raise LocalExecutionError(str(exc), "Browser task preparation could not be confirmed under the current owner command", status="degraded") from exc
        if observed.get("success") is not True or not observed.get("evidence_pointer"):
            raise LocalExecutionError("browser_preparation_not_verified", "Browser task preparation is unverified",status="degraded")
        return LocalExecutionResult(summary="Browser task prepared. Review an exact action plan before starting effects.",
            evidence_ref=observed["evidence_pointer"], observed_postcondition=observed, mission_pending=True)


LOCAL_EXECUTORS: dict[str, type[LocalActionExecutor]] = {
    "browser.file.provider.submit": BrowserFileProviderExecutor,
    "browser.task.prepare": BrowserTaskPrepareExecutor,
    "browser.plan.execute": BrowserPlanExecutor,
    "owner.permission.grant": OwnerPermissionGrantExecutor,
    "owner.autonomy.ceiling.set": DomainAutonomyCeilingExecutor,
    "memory.erase": MemoryEraseExecutor,
    "automation.standing_intent.disable": StandingIntentDisableExecutor,
    "memory.remember": MemoryRememberExecutor,
    "memory.decision.record": MemoryDecisionRecordExecutor,
    "reminder.create": ReminderCreateExecutor,
    "trading.halt": TradingHaltExecutor,
    "trading.ticket.confirm": TradingTicketConfirmExecutor,
}


__all__ = [
    "LOCAL_EXECUTORS",
    "LocalActionExecutor",
    "LocalExecutionContext",
    "LocalExecutionError",
    "LocalExecutionResult",
    "MemoryDecisionRecordExecutor",
    "MemoryRememberExecutor",
    "ReminderCreateExecutor",
    "TradingHaltExecutor",
    "StandingIntentDisableExecutor",
    "MemoryEraseExecutor",
    "DomainAutonomyCeilingExecutor",
]
