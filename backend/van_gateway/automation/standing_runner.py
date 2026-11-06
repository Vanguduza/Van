"""Canonical gateway producer for schedule and external-event standing runs.

n8n has no timers that can bypass this producer. Each firing claims a durable
trigger, seals a new snapshot, derives ordinary authority, then dispatches once.
"""
from __future__ import annotations

import datetime
import json
import time
from typing import Any

from van_gateway.automation.canonical import new_id, digest
from van_gateway.automation.models import WorkflowIR, WorkflowLifecycle
from van_gateway.automation.runtime_bindings import RuntimeBindingStore
from van_gateway.command.standing import StandingAuthorityError
from van_gateway.context.service import OwnerContextService
from van_gateway.models import PrincipalType


def _cron_values(field: str, minimum: int, maximum: int) -> set[int]:
    result = set()
    for chunk in field.split(","):
        base, separator, increment = chunk.partition("/")
        step = int(increment) if separator else 1
        if step < 1:
            raise ValueError("invalid step")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            left, right = base.split("-", 1)
            start, end = int(left), int(right)
        else:
            start = end = int(base)
            if separator:
                end = maximum
        if not minimum <= start <= end <= maximum:
            raise ValueError("invalid range")
        result.update(range(start, end + 1, step))
    return result


def cron_due(cron: str, now_ms: int) -> bool:
    fields = cron.split()
    if len(fields) != 5:
        raise StandingAuthorityError("STANDING_CRON_INVALID")
    try:
        minute, hour, day, month, weekday = [_cron_values(value, *bounds) for value, bounds in zip(fields,
            ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7)))]
    except (ValueError, TypeError) as exc:
        raise StandingAuthorityError("STANDING_CRON_INVALID") from exc
    date = datetime.datetime.fromtimestamp(now_ms / 1000, datetime.timezone.utc)
    dow = (date.weekday() + 1) % 7
    day_match, weekday_match = date.day in day, dow in weekday or (dow == 0 and 7 in weekday)
    calendar_match = (day_match or weekday_match) if fields[2] != "*" and fields[4] != "*" else day_match and weekday_match
    return date.minute in minute and date.hour in hour and date.month in month and calendar_match


class StandingRunProducer:
    def __init__(self, store, *, standing, registry, dispatcher):
        self.store, self.standing, self.registry, self.dispatcher = store, standing, registry, dispatcher
        self.context = OwnerContextService(store)
        self.bindings = RuntimeBindingStore(store)

    async def ensure(self) -> None:
        await self.store.execute("""CREATE TABLE IF NOT EXISTS automation_standing_firings(
            authority_id TEXT NOT NULL, trigger_key TEXT NOT NULL, state TEXT NOT NULL,
            run_id TEXT, error_code TEXT, created_at_ms INTEGER NOT NULL, completed_at_ms INTEGER,
            PRIMARY KEY(authority_id,trigger_key))""")

    async def run(self, authority_id: str, *, inputs: dict[str, Any], trigger_key: str, now_ms: int | None = None):
        now = int(time.time() * 1000) if now_ms is None else now_ms
        if self.dispatcher is None or not self.dispatcher.enabled:
            raise StandingAuthorityError("AUTOMATION_DISPATCH_UNCONFIGURED")
        source = await self.standing.get(authority_id)
        if source is None:
            raise StandingAuthorityError("STANDING_AUTHORITY_NOT_FOUND")
        intent = await self.store.fetchone("SELECT trigger_json FROM automation_standing_intents WHERE intent_id=?", (source.standing_intent_id,))
        if intent is None:
            raise StandingAuthorityError("STANDING_INTENT_NOT_FOUND")
        trigger = json.loads(intent["trigger_json"])
        kind = str(trigger.get("kind", "")).upper()
        constraints = source.parameter_constraints
        fixed = {key: rule["const"] for key, rule in constraints.items() if isinstance(rule, dict) and "const" in rule}
        if kind == "SCHEDULE":
            if (trigger.get("timezone", "UTC") != "UTC" or not cron_due(str(trigger.get("cron", "")), now)
                    or trigger_key != f"schedule:{now // 60000}"):
                raise StandingAuthorityError("STANDING_TRIGGER_NOT_DUE")
            if len(fixed) != len(constraints) or inputs != fixed:
                raise StandingAuthorityError("STANDING_TRIGGER_PARAMETERS_UNBOUND")
        elif kind in {"EVENT", "WEBHOOK"}:
            event_id = trigger_key.removeprefix("event:") if trigger_key.startswith("event:") else ""
            event = await self.store.fetchone("SELECT * FROM automation_external_events WHERE event_id=?", (event_id,))
            if (event is None or event["source_system"] != trigger.get("source_system")
                    or event["event_type"] != trigger.get("event_type")
                    or (trigger.get("source_account_alias") and event["source_account_alias"] != trigger["source_account_alias"])
                    or not max(source.issued_at_ms, now - 300000) <= int(event["received_at_ms"]) <= now):
                raise StandingAuthorityError("STANDING_EVENT_TRIGGER_MISMATCH")
            expected = {**fixed, "event": {"event_id": event["event_id"], "payload": json.loads(event["payload_json"]),
                                           "source_trust": event["source_trust"], "payload_digest": event["payload_digest"]}}
            if inputs != expected or any(key != "event" and key not in fixed for key in constraints):
                raise StandingAuthorityError("STANDING_TRIGGER_PARAMETERS_UNBOUND")
        else:
            raise StandingAuthorityError("STANDING_TRIGGER_UNSUPPORTED")
        # validate_for_run also checks the current source device and intent.
        await self.standing.validate_for_run(source, trigger=trigger, artifact_id=source.artifact_id,
                                            workflow_version=source.workflow_version, parameters=inputs, now_ms=now)
        binding = await self.bindings.get(source.artifact_id)
        capability = await self.registry.get_capability(source.capability_id)
        artifact = await self.registry.get_artifact(source.artifact_id)
        if (binding is None or binding["binding_state"] != "DEPLOYED" or binding["readiness_errors"]
                or capability is None or artifact is None
                or artifact.capability_id != capability.capability_id or artifact.version != source.workflow_version
                or artifact.lifecycle_state not in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}
                or capability.lifecycle_state not in {WorkflowLifecycle.ADMITTED, WorkflowLifecycle.HOT}
                or binding["n8n_workflow_id"] != artifact.n8n_workflow_id
                or digest(binding["semantic_graph"]) != artifact.compiled_semantic_digest
                or RuntimeBindingStore.compute_full_digest(binding["runtime_graph"], binding["dependencies"]) != artifact.compiled_full_digest):
            raise StandingAuthorityError("STANDING_WORKFLOW_RUNTIME_UNAVAILABLE")
        ir = WorkflowIR.model_validate(binding["ir"])
        if digest(ir.semantic_payload()) != artifact.workflow_ir_digest or ir.action_class != capability.action_class:
            raise StandingAuthorityError("STANDING_WORKFLOW_SCOPE_MISMATCH")
        effects = {effect.value for step in ir.steps for effect in step.effects}
        domains = {step.external_domain for step in ir.steps if step.external_domain}
        if not effects <= set(source.allowed_effects) or not domains <= set(source.allowed_domains):
            raise StandingAuthorityError("STANDING_WORKFLOW_SCOPE_MISMATCH")
        if capability.required_context:
            raise StandingAuthorityError("STANDING_CONTEXT_REQUIREMENT_UNSUPPORTED")
        await self.ensure()
        async with self.store.connection() as db:
            cursor = await db.execute("INSERT OR IGNORE INTO automation_standing_firings(authority_id,trigger_key,state,created_at_ms) VALUES (?,?,'IN_PROGRESS',?)",
                                      (authority_id, trigger_key, now))
            await db.commit()
            if cursor.rowcount != 1:
                raise StandingAuthorityError("STANDING_TRIGGER_ALREADY_CLAIMED")
        try:
            run_id = new_id("run")
            command_id = f"automation:{run_id}"
            snapshot = await self.context.compile_snapshot(command_id, [], now_ms=now)
            derived = await self.standing.derive_run_authority(source, run_id=run_id, trigger=trigger,
                artifact_id=source.artifact_id, workflow_version=source.workflow_version, parameters=inputs,
                run_snapshot_id=snapshot.snapshot_id, run_context_digest=snapshot.digest,
                operation_action_class=capability.action_class, typed_action_id=f"automation.workflow.{source.capability_id}", now_ms=now)
            result = await self.dispatcher.dispatch(capability_id=source.capability_id,
                action_id=f"automation.workflow.{source.capability_id}", command_id=derived.command_id,
                principal_type=PrincipalType.AUTOMATION, requested_by=derived.authority.requested_by,
                snapshot_id=snapshot.snapshot_id, inputs=inputs, standing_authority_id=authority_id, now_ms=now)
        except Exception as exc:
            await self.store.execute("UPDATE automation_standing_firings SET state='FAILED',error_code=?,completed_at_ms=? WHERE authority_id=? AND trigger_key=?",
                                     (type(exc).__name__, now, authority_id, trigger_key))
            raise
        await self.store.execute("UPDATE automation_standing_firings SET state='COMPLETED',run_id=?,completed_at_ms=? WHERE authority_id=? AND trigger_key=?",
                                 (result.run_id, now, authority_id, trigger_key))
        return result

    async def sweep_due(self, *, now_ms: int | None = None) -> dict[str, int]:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self.ensure()
        if self.dispatcher is None or not self.dispatcher.enabled:
            return {"started": 0, "refused": 0}
        rows = await self.store.fetchall("""SELECT a.authority_id,a.parameter_constraints_json,a.issued_at_ms,i.trigger_json
            FROM standing_automation_authorities a JOIN automation_standing_intents i ON i.intent_id=a.standing_intent_id
            WHERE a.revoked_at_ms IS NULL AND i.enabled=1""")
        started = refused = 0
        for row in rows:
            try:
                trigger = json.loads(row["trigger_json"])
                constraints = json.loads(row["parameter_constraints_json"])
                kind = str(trigger.get("kind", "")).upper()
                if kind == "SCHEDULE":
                    if trigger.get("timezone", "UTC") != "UTC" or not cron_due(str(trigger.get("cron", "")), now):
                        continue
                    if any(not isinstance(rule, dict) or "const" not in rule for rule in constraints.values()):
                        raise StandingAuthorityError("STANDING_TRIGGER_PARAMETERS_UNBOUND")
                    inputs = {key: rule["const"] for key, rule in constraints.items()}
                    firings = [(f"schedule:{now // 60000}", inputs)]
                elif kind in {"EVENT", "WEBHOOK"}:
                    if not isinstance(trigger.get("source_system"), str) or not isinstance(trigger.get("event_type"), str):
                        raise StandingAuthorityError("STANDING_EVENT_SELECTOR_UNBOUND")
                    events = await self.store.fetchall("""SELECT * FROM automation_external_events
                        WHERE source_system=? AND event_type=? AND received_at_ms>=? AND received_at_ms<=?
                        ORDER BY received_at_ms,event_id LIMIT 100""",
                        (trigger["source_system"], trigger["event_type"], max(int(row["issued_at_ms"]), now - 300000), now))
                    firings = []
                    for event in events:
                        if trigger.get("source_account_alias") and trigger["source_account_alias"] != event["source_account_alias"]:
                            continue
                        inputs = {key: rule["const"] for key, rule in constraints.items() if isinstance(rule, dict) and "const" in rule}
                        inputs["event"] = {"event_id": event["event_id"], "payload": json.loads(event["payload_json"]),
                                           "source_trust": event["source_trust"], "payload_digest": event["payload_digest"]}
                        firings.append((f"event:{event['event_id']}", inputs))
                else:
                    continue
                for key, inputs in firings:
                    try:
                        await self.run(row["authority_id"], inputs=inputs, trigger_key=key, now_ms=now)
                        started += 1
                    except StandingAuthorityError as exc:
                        if str(exc) != "STANDING_TRIGGER_ALREADY_CLAIMED":
                            refused += 1
            except StandingAuthorityError as exc:
                if str(exc) != "STANDING_TRIGGER_ALREADY_CLAIMED":
                    refused += 1
            except Exception:
                # One provider outage cannot prevent other independently scoped
                # scheduled work from being checked. The durable firing keeps
                # the explicit failure; it is never retried as a new effect.
                refused += 1
        return {"started": started, "refused": refused}
