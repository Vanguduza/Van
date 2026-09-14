from __future__ import annotations

import time
from typing import Any

from van_gateway.audit.service import AuditService
from van_gateway.auth.service import AuthError, AuthService
from van_gateway.degraded.registry import DegradedRegistry
from van_gateway.hermes.bridge import HermesBridge, HermesBridgeError
from van_gateway.idempotency.service import IdempotencyConflict, IdempotencyInFlight, IdempotencyService
from van_gateway.models import ActionClass, CommandRequest, CommandResult, ContentTrust, DegradedCode
from van_gateway.projects.router import ProjectRouter


INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "send secrets",
    "disable audit",
    "disable approvals",
)


class CommandOrchestrator:
    def __init__(
        self,
        *,
        auth: AuthService,
        idempotency: IdempotencyService,
        hermes: HermesBridge,
        projects: ProjectRouter,
        audit: AuditService,
        degraded: DegradedRegistry,
        owner_intent_max_age_seconds: int,
    ) -> None:
        self.auth = auth
        self.idempotency = idempotency
        self.hermes = hermes
        self.projects = projects
        self.audit = audit
        self.degraded = degraded
        self.owner_intent_max_age_seconds = owner_intent_max_age_seconds

    async def handle(self, req: CommandRequest) -> CommandResult:
        payload = req.model_dump()
        try:
            prior = await self.idempotency.begin(req.idempotency_key, payload)
            if prior is not None:
                return CommandResult(**prior)
        except IdempotencyConflict:
            result = CommandResult(
                status="conflict",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Idempotency key reused with different request",
            )
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result
        except IdempotencyInFlight:
            return CommandResult(
                status="in_flight",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Command already in flight",
            )

        try:
            await self.auth.require_device(req.device_id)
            canonical = AuthService.canonical_command(
                req.command_id,
                req.idempotency_key,
                req.device_id,
                req.issued_at_unix,
                req.text,
                req.action_class.value,
                req.project_id,
            )
            self.auth.verify_signature(req.device_id, canonical, req.signature)
        except AuthError as exc:
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message=exc.message,
            )
            await self.audit.record(result="denied", command_id=req.command_id, device_id=req.device_id, failure_reason=exc.code)
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result

        now = int(time.time())
        if now - req.issued_at_unix > self.owner_intent_max_age_seconds:
            result = CommandResult(
                status="expired",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Owner intent expired; refusing stale offline replay",
            )
            await self.audit.record(result="expired", command_id=req.command_id, device_id=req.device_id, failure_reason="stale_intent")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        if req.action_class == ActionClass.A5:
            result = CommandResult(
                status="denied",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="A5 prohibited action",
            )
            await self.audit.record(result="denied", command_id=req.command_id, device_id=req.device_id, failure_reason="A5")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        if req.action_class == ActionClass.A4 and not req.approval_token:
            result = CommandResult(
                status="approval_required",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="A4 destructive action requires explicit owner approval",
                requires_approval=True,
            )
            await self.audit.record(result="approval_required", command_id=req.command_id, device_id=req.device_id, approval="missing")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result

        # Untrusted context cannot become authority
        if req.context_trust == ContentTrust.UNTRUSTED:
            lowered = req.text.lower()
            if any(m in lowered for m in INJECTION_MARKERS):
                result = CommandResult(
                    status="rejected_untrusted",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="Untrusted content attempted instruction override; treated as data only and rejected for mutation",
                )
                await self.audit.record(result="rejected_untrusted", command_id=req.command_id, device_id=req.device_id, failure_reason="injection")
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result

        before: dict[str, Any] = {}
        if req.project_id and req.action_class in (ActionClass.A3, ActionClass.A4):
            truth = await self.projects.load_truth(req.project_id)
            if not truth.get("ok"):
                code = truth.get("degraded", DegradedCode.STALE_PROJECT_TRUTH.value)
                self.degraded.set(DegradedCode(code), True)
                result = CommandResult(
                    status="degraded",
                    command_id=req.command_id,
                    idempotency_key=req.idempotency_key,
                    message="Project Truth missing or stale; refusing mutation",
                    degraded=[code],
                )
                await self.audit.record(
                    result="degraded",
                    command_id=req.command_id,
                    device_id=req.device_id,
                    project_id=req.project_id,
                    failure_reason="truth_gate",
                    before=truth,
                )
                await self.idempotency.complete(req.idempotency_key, result.model_dump())
                return result
            before = {"truth_sha": truth.get("truth_sha"), "repo_sha": truth.get("repo_sha")}

        health = await self.hermes.health()
        if not health.get("ok"):
            self.degraded.set(DegradedCode.HERMES_OFFLINE, True)
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message="Hermes offline; command not executed",
                degraded=[DegradedCode.HERMES_OFFLINE.value],
            )
            await self.audit.record(result="degraded", command_id=req.command_id, device_id=req.device_id, failure_reason="hermes_offline")
            await self.idempotency.complete(req.idempotency_key, result.model_dump())
            return result
        self.degraded.set(DegradedCode.HERMES_OFFLINE, False)

        try:
            run = await self.hermes.create_run(
                req.text,
                metadata={
                    "command_id": req.command_id,
                    "device_id": req.device_id,
                    "project_id": req.project_id,
                    "action_class": req.action_class.value,
                    "context_trust": req.context_trust.value,
                },
            )
        except HermesBridgeError as exc:
            self.degraded.set(DegradedCode.HERMES_OFFLINE, True)
            result = CommandResult(
                status="degraded",
                command_id=req.command_id,
                idempotency_key=req.idempotency_key,
                message=exc.message,
                degraded=[DegradedCode.HERMES_OFFLINE.value],
            )
            await self.audit.record(result="degraded", command_id=req.command_id, device_id=req.device_id, failure_reason=exc.code)
            await self.idempotency.fail(req.idempotency_key, result.model_dump())
            return result

        evidence_id = await self.audit.record(
            result="accepted",
            command_id=req.command_id,
            device_id=req.device_id,
            project_id=req.project_id,
            capability=req.action_class.value,
            approval=req.approval_token or "not_required",
            model_delegate="hermes:van",
            before=before,
            after={"hermes_run": run},
            evidence_pointer=run.get("id"),
        )
        result = CommandResult(
            status="accepted",
            command_id=req.command_id,
            idempotency_key=req.idempotency_key,
            message="Accepted and routed to Hermes profile van",
            hermes_run_id=run.get("id"),
            evidence_id=evidence_id,
        )
        await self.idempotency.complete(req.idempotency_key, result.model_dump())
        return result
