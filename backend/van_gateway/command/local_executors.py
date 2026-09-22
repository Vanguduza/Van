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
from typing import Any, Protocol

from van_gateway.command.context_requirements import OWNER_SUBJECT
from van_gateway.context.authoring import ContextAuthoringError, OwnerFactAuthor
from van_gateway.context.models import ContextRequirement
from van_gateway.context.service import OwnerContextService
from van_gateway.models import ReminderCreate
from van_gateway.reminders.service import ReminderService
from van_gateway.reminders.timeparse import TimeParseError, parse_due_expression


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


#: action_id -> executor factory. A factory rather than a shared instance because an
#: executor may be given per-call state one day; today each is stateless and the factory is
#: just its class.
LOCAL_EXECUTORS: dict[str, type[LocalActionExecutor]] = {
    "memory.remember": MemoryRememberExecutor,
    "memory.decision.record": MemoryDecisionRecordExecutor,
    "reminder.create": ReminderCreateExecutor,
    "trading.halt": TradingHaltExecutor,
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
]
