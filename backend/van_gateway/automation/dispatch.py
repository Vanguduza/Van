"""Rev 1.3 §§159, 223, 422-423 — automation dispatch through the existing Action Runtime.

§223 is emphatic: *"Do not create an automation-specific parallel authorization
ledger."* So this dispatcher owns no authority of its own. It sequences:

    ActionRuntime.begin → mint run grant → n8n → mark_submitted → verify → ActionRuntime.verify

Authority arrives from one of exactly two places (§160):

* an owner-triggered flow, where a live ``CommandAuthorityRecord`` already exists
  (§422); or
* a scheduled/event flow, where ``StandingAutomationAuthorityService`` has derived
  one from an owner-authorized standing intent (§423).

Either way ``authorize_action()`` remains the final check, and an n8n success is
never by itself an owner success.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from van_gateway.action.models import ActionExecution, ExecutionStatus, VerifierType
from van_gateway.action.service import ActionPolicyError, ActionRuntime
from van_gateway.action.models import VerificationObservation
from van_gateway.automation.canonical import digest, new_id
from van_gateway.automation.external_runtime import RuntimeState
from van_gateway.automation.grants import GrantKind, MintedGrant, RunGrantService
from van_gateway.automation.models import AutomationWorkflowArtifact, RunStatus, WorkflowLifecycle
from van_gateway.automation.n8n_client import N8nClientError, N8nManagementClient
from van_gateway.automation.deadletter import DeadLetterService
from van_gateway.automation.registry import AutomationRegistry
from van_gateway.automation.telemetry import CacheState, RunTiming, TelemetryService
from van_gateway.automation.workflow_health import (
    FailureClass,
    HealthStatus,
    WorkflowHealthService,
)
from van_gateway.automation.verifier import (
    PostconditionSpec,
    VerificationOutcome,
    WorkflowVerifier,
)
from van_gateway.command.authority import CommandAuthorityService
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store


class DispatchError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class DispatchResult(BaseModel):
    run_id: str
    capability_id: str
    artifact_id: str
    status: RunStatus
    execution: ActionExecution | None = None
    verification_outcome: VerificationOutcome | None = None
    evidence_pointer: str | None = None
    error_code: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def owner_success(self) -> bool:
        """Only an independently verified run counts as success for the owner."""
        return self.status is RunStatus.VERIFIED_SUCCESS


class AutomationDispatcher:
    def __init__(
        self,
        store: Store,
        *,
        actions: ActionRuntime,
        authority: CommandAuthorityService,
        registry: AutomationRegistry,
        grants: RunGrantService,
        client: N8nManagementClient,
        verifier: WorkflowVerifier | None = None,
        health: WorkflowHealthService | None = None,
        telemetry: TelemetryService | None = None,
        dead_letter: DeadLetterService | None = None,
        enabled: bool = False,
    ) -> None:
        self.store = store
        self.actions = actions
        self.authority = authority
        self.registry = registry
        self.grants = grants
        self.client = client
        self.verifier = verifier or WorkflowVerifier()
        self.health = health or WorkflowHealthService(store)
        self.telemetry = telemetry or TelemetryService(store)
        self.dead_letter = dead_letter or DeadLetterService(store)
        self.enabled = enabled

    async def dispatch(
        self,
        *,
        capability_id: str,
        action_id: str,
        command_id: str,
        principal_type: PrincipalType,
        requested_by: str,
        snapshot_id: str,
        inputs: dict[str, Any],
        turn_id: str | None = None,
        owner_approved: bool = False,
        command_age_seconds: int = 0,
        postcondition: PostconditionSpec | None = None,
        standing_authority_id: str | None = None,
        now_ms: int | None = None,
    ) -> DispatchResult:
        if not self.enabled:
            raise DispatchError("AUTOMATION_FABRIC_DISABLED")

        now = int(time.time() * 1000) if now_ms is None else now_ms
        run_id = new_id("run")

        artifact = await self.registry.admitted_artifact(capability_id)
        if artifact is None:
            # §36 — nothing executes before admission, on any path.
            raise DispatchError("CAPABILITY_NOT_ADMITTED", capability_id)
        capability = await self.registry.get_capability(capability_id)
        if capability is None:
            raise DispatchError("CAPABILITY_UNKNOWN", capability_id)

        input_digest = digest(inputs)
        await self._record_run(
            run_id=run_id, capability_id=capability_id, artifact=artifact, command_id=command_id,
            turn_id=turn_id, action_class=capability.action_class, input_digest=input_digest,
            status=RunStatus.PENDING, now=now,
        )

        # 1. Authority. The Action Runtime re-derives every canonical rule; this
        #    dispatcher never decides whether something is permitted.
        definition = await self.actions.get_definition(action_id)
        if definition is None:
            raise DispatchError("UNKNOWN_ACTION", action_id)
        try:
            record, age = await self.authority.authorize_action(
                command_id=command_id, action=definition, principal_type=principal_type,
                requested_by=requested_by, snapshot_id=snapshot_id, turn_id=turn_id,
            )
            execution = await self.actions.begin(
                execution_id=f"exec_{run_id}", command_id=command_id, turn_id=record.turn_id,
                action_id=action_id, principal_type=record.principal_type,
                requested_by=record.requested_by, idempotency_key=f"{run_id}:{input_digest}",
                parameters=inputs, snapshot_id=record.snapshot_id,
                owner_approved=record.owner_approved or owner_approved,
                command_age_seconds=command_age_seconds or age,
            )
        except (ActionPolicyError, ValueError) as exc:
            await self._fail(run_id, "AUTHORITY_DENIED", now)
            raise DispatchError("AUTHORITY_DENIED", str(exc)) from exc

        if execution.status is not ExecutionStatus.AUTHORIZED:
            # AUTHORIZATION_REQUIRED, EXPIRED, DENIED — all terminal here.
            await self._fail(run_id, execution.error_code or execution.status.value, now)
            return DispatchResult(
                run_id=run_id, capability_id=capability_id, artifact_id=artifact.artifact_id,
                status=RunStatus.FAILED, execution=execution, error_code=execution.error_code,
            )

        # 2. Worker-scope grant. Never owner authority (§160).
        grant = await self._mint_grant(
            run_id=run_id, command_id=command_id, capability=capability, artifact=artifact,
            snapshot_id=snapshot_id, input_digest=input_digest,
            standing_authority_id=standing_authority_id, now=now,
        )

        # 3. Execute. An engine failure is a failure; an engine success is not
        #    yet an owner success.
        try:
            engine_result = await self._invoke(artifact, inputs, grant)
        except (N8nClientError, DispatchError) as exc:
            code = getattr(exc, "code", "AUTOMATION_FABRIC_UNAVAILABLE")
            await self._fail(run_id, code, now)
            await self.grants.revoke_run(run_id, now_ms=now)
            await self._record_failure(
                run_id=run_id, capability_id=capability_id, artifact=artifact,
                failure_class=classify_failure(code), error_code=code, now=now,
                started=now,
            )
            return DispatchResult(
                run_id=run_id, capability_id=capability_id, artifact_id=artifact.artifact_id,
                status=RunStatus.FAILED, execution=execution, error_code=code,
            )

        correlation = {"n8n_execution_id": str(engine_result.get("executionId", ""))}
        execution = await self.actions.mark_submitted(execution.execution_id, correlation=correlation)
        await self._update_run(run_id, status=RunStatus.SUBMITTED, now=now,
                               n8n_execution_id=correlation["n8n_execution_id"])

        # 4. Independent verification (§80).
        verification = await self.verifier.verify(
            spec=postcondition,
            verifier_type=VerifierType(capability.verifier_type)
            if capability.verifier_type in VerifierType.__members__.values()
            or capability.verifier_type in {v.value for v in VerifierType}
            else VerifierType.NONE,
            engine_reported_success=bool(engine_result.get("success", False)),
            context={"run_id": run_id, "inputs": inputs, "engine": engine_result},
        )
        receipt = await self.actions.verify(
            VerificationObservation(
                execution_id=execution.execution_id,
                success=verification.outcome is VerificationOutcome.VERIFIED,
                correlation=verification.correlation or correlation,
                observed_postcondition=verification.observed,
                evidence_pointer=verification.evidence_pointer,
                partial=verification.outcome is VerificationOutcome.PARTIAL,
            )
        )
        status = {
            VerificationOutcome.VERIFIED: RunStatus.VERIFIED_SUCCESS,
            VerificationOutcome.PARTIAL: RunStatus.PARTIAL_SUCCESS,
            VerificationOutcome.UNVERIFIABLE: RunStatus.UNVERIFIABLE,
            VerificationOutcome.FAILED: RunStatus.FAILED,
        }[verification.outcome]
        await self._update_run(
            run_id, status=status, now=now, evidence_pointer=receipt.evidence_pointer,
            verifier_status=receipt.status.value,
        )

        # §§76-77, 101 — the run's outcome is the fabric's health signal, and the
        # ladder rung it took is what makes the HOT hit rate measurable.
        completed = int(time.time() * 1000) if now_ms is None else now_ms
        duration = max(0, completed - now)
        if status is RunStatus.FAILED:
            await self._record_failure(
                run_id=run_id, capability_id=capability_id, artifact=artifact,
                failure_class=FailureClass.VERIFICATION,
                error_code=verification.detail or "VERIFICATION_FAILED",
                now=completed, started=now,
            )
        else:
            await self.health.record_success(
                capability_id=capability_id, workflow_version=artifact.version,
                duration_ms=duration,
                verified=status is RunStatus.VERIFIED_SUCCESS, now_ms=completed,
            )
        await self.telemetry.record_run(
            RunTiming(
                run_id=run_id, cache_state=CacheState.HOT, capability_id=capability_id,
                workflow_version=artifact.version, execution_time_ms=duration,
                failure_count=1 if status is RunStatus.FAILED else 0,
            ),
            now_ms=completed,
        )
        return DispatchResult(
            run_id=run_id, capability_id=capability_id, artifact_id=artifact.artifact_id,
            status=status, execution=await self.actions.get_execution(execution.execution_id),
            verification_outcome=verification.outcome, evidence_pointer=receipt.evidence_pointer,
            detail={"verifier_detail": verification.detail} if verification.detail else {},
        )

    # ----------------------------------------------------------------- pieces

    async def _mint_grant(
        self, *, run_id: str, command_id: str, capability: Any,
        artifact: AutomationWorkflowArtifact, snapshot_id: str, input_digest: str,
        standing_authority_id: str | None, now: int,
    ) -> MintedGrant:
        kind = (
            GrantKind.SINGLE_USE_MUTATION if capability.mutates_state else GrantKind.BOUNDED_READ_SESSION
        )
        return await self.grants.mint(
            run_id=run_id, command_id=command_id, capability_id=capability.capability_id,
            artifact_id=artifact.artifact_id, artifact_version=artifact.version,
            context_snapshot_id=snapshot_id, input_digest=input_digest,
            action_class_ceiling=capability.action_class,
            allowed_gateway_operations=sorted(set(capability.required_context) | {"emit_event", "seal_evidence"}),
            allowed_external_domains=[], grant_kind=kind,
            max_uses=1 if capability.mutates_state else 16,
            standing_authority_id=standing_authority_id, now_ms=now,
        )

    async def _invoke(
        self, artifact: AutomationWorkflowArtifact, inputs: dict[str, Any], grant: MintedGrant
    ) -> dict[str, Any]:
        """§159 — gateway-adapter invocation carrying the run envelope.

        The grant token travels in the body rather than as a bearer header: n8n
        holds no general-purpose VAN credential, only this one run-scoped grant.
        """
        if artifact.n8n_workflow_id is None:
            raise DispatchError("ARTIFACT_NOT_DEPLOYED", artifact.artifact_id)
        status = await self.client.status()
        if status.state is not RuntimeState.READY:
            # §369 — an unproven runtime cannot execute owner work.
            raise DispatchError("AUTOMATION_FABRIC_UNAVAILABLE", status.state.value)
        response = await self.client.run_workflow(
            artifact.n8n_workflow_id,
            {
                "run_id": grant.grant.run_id,
                "capability_id": grant.grant.capability_id,
                "artifact_version": grant.grant.artifact_version,
                "command_id": grant.grant.command_id,
                "context_snapshot_id": grant.grant.context_snapshot_id,
                "input": inputs,
                "issued_at_ms": grant.grant.issued_at_ms,
                "expires_at_ms": grant.grant.expires_at_ms,
                "capability_grant": grant.token,
            },
        )
        return response

    async def _record_run(
        self, *, run_id: str, capability_id: str, artifact: AutomationWorkflowArtifact,
        command_id: str, turn_id: str | None, action_class: ActionClass, input_digest: str,
        status: RunStatus, now: int,
    ) -> None:
        await self.store.execute(
            """
            INSERT INTO automation_runs(
              run_id, capability_id, artifact_id, command_id, turn_id, execution_id,
              n8n_execution_id, status, action_class, input_digest, output_digest,
              evidence_pointer, verifier_status, error_code, started_at_ms, submitted_at_ms,
              verified_at_ms, completed_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?)
            """,
            (
                run_id, capability_id, artifact.artifact_id, command_id, turn_id,
                f"exec_{run_id}", status.value, action_class.value, input_digest, now, now,
            ),
        )

    async def _update_run(
        self, run_id: str, *, status: RunStatus, now: int, evidence_pointer: str | None = None,
        verifier_status: str | None = None, n8n_execution_id: str | None = None,
    ) -> None:
        await self.store.execute(
            "UPDATE automation_runs SET status = ?, evidence_pointer = COALESCE(?, evidence_pointer), "
            "verifier_status = COALESCE(?, verifier_status), "
            "n8n_execution_id = COALESCE(?, n8n_execution_id), "
            "submitted_at_ms = COALESCE(submitted_at_ms, ?), updated_at_ms = ? WHERE run_id = ?",
            (status.value, evidence_pointer, verifier_status, n8n_execution_id, now, now, run_id),
        )

    async def _record_failure(
        self,
        *,
        run_id: str,
        capability_id: str,
        artifact: AutomationWorkflowArtifact,
        failure_class: FailureClass,
        error_code: str,
        now: int,
        started: int,
    ) -> None:
        """One place where a failed run becomes health, telemetry and — if the
        workflow has run out of road — a dead letter (§246).

        The dead letter is written only once the workflow is REPAIR_REQUIRED or
        QUARANTINED. Before that the failure is a health signal; after it, retry
        has demonstrably stopped helping, and continuing to retry is the exact
        thing §246 forbids.
        """
        health = await self.health.record_failure(
            capability_id=capability_id, workflow_version=artifact.version,
            failure_class=failure_class, duration_ms=max(0, now - started), now_ms=now,
        )
        await self.telemetry.record_run(
            RunTiming(
                run_id=run_id, cache_state=CacheState.HOT, capability_id=capability_id,
                workflow_version=artifact.version, execution_time_ms=max(0, now - started),
                failure_count=1,
            ),
            now_ms=now,
        )
        if health.status in (HealthStatus.REPAIR_REQUIRED, HealthStatus.QUARANTINED):
            await self.dead_letter.record(
                run_id=run_id, capability_id=capability_id, failure_class=failure_class,
                attempt_count=health.consecutive_failures, last_error_code=error_code,
                evidence_refs=[f"artifact://{artifact.artifact_id}"],
                detail={"workflow_version": artifact.version, "health": health.status.value},
                now_ms=now,
            )

    async def _fail(self, run_id: str, error_code: str, now: int) -> None:
        await self.store.execute(
            "UPDATE automation_runs SET status = ?, error_code = ?, completed_at_ms = ?, "
            "updated_at_ms = ? WHERE run_id = ?",
            (RunStatus.FAILED.value, error_code, now, now, run_id),
        )


#: Error codes the fabric already produces, mapped onto §77's failure classes.
#: Anything unrecognised is UNKNOWN rather than TRANSIENT: guessing "transient"
#: would silently exempt a real fault from ever degrading the workflow.
_FAILURE_CLASSES = {
    "AUTOMATION_FABRIC_UNAVAILABLE": FailureClass.TRANSIENT,
    "N8N_TIMEOUT": FailureClass.TRANSIENT,
    "N8N_UNREACHABLE": FailureClass.TRANSIENT,
    "N8N_VERSION_MISMATCH": FailureClass.CONNECTOR,
    "N8N_NOT_READY": FailureClass.CONNECTOR,
    "CREDENTIAL_UNRESOLVED": FailureClass.CREDENTIAL,
    "CREDENTIAL_REJECTED": FailureClass.CREDENTIAL,
    "SCHEMA_MISMATCH": FailureClass.SCHEMA,
    "GRANT_REPLAYED": FailureClass.SECURITY,
    "AUTHORITY_DENIED": FailureClass.SECURITY,
}


def classify_failure(error_code: str | None) -> FailureClass:
    return _FAILURE_CLASSES.get((error_code or "").strip().upper(), FailureClass.UNKNOWN)


__all__ = [
    "AutomationDispatcher",
    "DispatchError",
    "DispatchResult",
    "classify_failure",
]
