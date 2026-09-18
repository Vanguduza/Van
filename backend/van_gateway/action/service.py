from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from van_gateway.action.models import (
    ActionDefinition,
    ActionExecution,
    ActionReceipt,
    ExecutionStatus,
    VerificationObservation,
    VerifierType,
)
from van_gateway.models import ActionClass, PrincipalType
from van_gateway.storage.db import Store


class ActionPolicyError(ValueError):
    pass


class ActionRuntime:
    """Deterministic action registry + execution/verification ledger.

    It does not plan. Hermes may propose action IDs and parameters; this service
    revalidates canonical class/principal/idempotency/verifier rules before any
    adapter is permitted to execute.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def digest_parameters(parameters: dict[str, Any]) -> str:
        data = json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    async def register(self, definition: ActionDefinition) -> ActionDefinition:
        if definition.action_class == ActionClass.A5 and definition.enabled:
            definition = definition.model_copy(update={"enabled": False})
        await self.store.execute(
            """
            INSERT INTO action_definitions(
              action_id, action_class, mutates_state, allowed_principals_json, verifier_type,
              no_stale_replay, max_age_seconds, parameter_schema_json, enabled, updated_at_unix_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_id) DO UPDATE SET
              action_class=excluded.action_class,
              mutates_state=excluded.mutates_state,
              allowed_principals_json=excluded.allowed_principals_json,
              verifier_type=excluded.verifier_type,
              no_stale_replay=excluded.no_stale_replay,
              max_age_seconds=excluded.max_age_seconds,
              parameter_schema_json=excluded.parameter_schema_json,
              enabled=excluded.enabled,
              updated_at_unix_ms=excluded.updated_at_unix_ms
            """,
            (
                definition.action_id, definition.action_class.value,
                1 if definition.mutates_state else 0,
                Store.dumps(sorted(p.value for p in definition.allowed_principals)),
                definition.verifier_type.value,
                1 if definition.no_stale_replay else 0,
                definition.max_age_seconds,
                Store.dumps(definition.parameter_schema),
                1 if definition.enabled else 0,
                int(time.time() * 1000),
            ),
        )
        return definition

    async def get_definition(self, action_id: str) -> ActionDefinition | None:
        row = await self.store.fetchone("SELECT * FROM action_definitions WHERE action_id = ?", (action_id,))
        if row is None:
            return None
        return ActionDefinition(
            action_id=str(row["action_id"]),
            action_class=ActionClass(str(row["action_class"])),
            mutates_state=bool(row["mutates_state"]),
            allowed_principals={PrincipalType(value) for value in json.loads(row["allowed_principals_json"])},
            verifier_type=VerifierType(str(row["verifier_type"])),
            no_stale_replay=bool(row["no_stale_replay"]),
            max_age_seconds=int(row["max_age_seconds"]) if row["max_age_seconds"] is not None else None,
            parameter_schema=json.loads(row["parameter_schema_json"]),
            enabled=bool(row["enabled"]),
        )

    async def begin(
        self,
        *,
        execution_id: str,
        command_id: str,
        turn_id: str | None,
        action_id: str,
        principal_type: PrincipalType,
        requested_by: str,
        idempotency_key: str,
        parameters: dict[str, Any],
        snapshot_id: str | None,
        owner_approved: bool,
        command_age_seconds: int = 0,
    ) -> ActionExecution:
        definition = await self.get_definition(action_id)
        if definition is None:
            raise ActionPolicyError("unknown_action")
        if definition.action_class == ActionClass.A5 or not definition.enabled:
            return await self._persist_execution(ActionExecution(
                execution_id=execution_id, command_id=command_id, turn_id=turn_id,
                action_id=action_id, action_class=definition.action_class,
                principal_type=principal_type, requested_by=requested_by,
                status=ExecutionStatus.DENIED, idempotency_key=idempotency_key,
                snapshot_id=snapshot_id, parameters_digest=self.digest_parameters(parameters),
                error_code="A5_OR_DISABLED",
            ))
        if principal_type not in definition.allowed_principals:
            raise ActionPolicyError("principal_not_allowed")
        if definition.action_class == ActionClass.A4 and not owner_approved:
            return await self._persist_execution(ActionExecution(
                execution_id=execution_id, command_id=command_id, turn_id=turn_id,
                action_id=action_id, action_class=definition.action_class,
                principal_type=principal_type, requested_by=requested_by,
                status=ExecutionStatus.AUTHORIZATION_REQUIRED, idempotency_key=idempotency_key,
                snapshot_id=snapshot_id, parameters_digest=self.digest_parameters(parameters),
                error_code="OWNER_APPROVAL_REQUIRED",
            ))
        no_replay_window = definition.max_age_seconds if definition.max_age_seconds is not None else 5
        if definition.no_stale_replay and command_age_seconds > no_replay_window:
            return await self._persist_execution(ActionExecution(
                execution_id=execution_id, command_id=command_id, turn_id=turn_id,
                action_id=action_id, action_class=definition.action_class,
                principal_type=principal_type, requested_by=requested_by,
                status=ExecutionStatus.EXPIRED, idempotency_key=idempotency_key,
                snapshot_id=snapshot_id, parameters_digest=self.digest_parameters(parameters),
                error_code="NO_STALE_REPLAY",
            ))
        if definition.max_age_seconds is not None and command_age_seconds > definition.max_age_seconds:
            return await self._persist_execution(ActionExecution(
                execution_id=execution_id, command_id=command_id, turn_id=turn_id,
                action_id=action_id, action_class=definition.action_class,
                principal_type=principal_type, requested_by=requested_by,
                status=ExecutionStatus.EXPIRED, idempotency_key=idempotency_key,
                snapshot_id=snapshot_id, parameters_digest=self.digest_parameters(parameters),
                error_code="ACTION_EXPIRED",
            ))
        existing = await self.store.fetchone("SELECT * FROM action_executions WHERE idempotency_key = ?", (idempotency_key,))
        if existing is not None:
            if str(existing["parameters_digest"]) != self.digest_parameters(parameters) or str(existing["action_id"]) != action_id:
                raise ActionPolicyError("idempotency_conflict")
            return self._row_to_execution(existing)
        return await self._persist_execution(ActionExecution(
            execution_id=execution_id, command_id=command_id, turn_id=turn_id,
            action_id=action_id, action_class=definition.action_class,
            principal_type=principal_type, requested_by=requested_by,
            status=ExecutionStatus.AUTHORIZED, idempotency_key=idempotency_key,
            snapshot_id=snapshot_id, parameters_digest=self.digest_parameters(parameters),
        ))

    async def mark_executing(self, execution_id: str) -> ActionExecution:
        current = await self.get_execution(execution_id)
        if current is None:
            raise ActionPolicyError("unknown_execution")
        if current.terminal:
            return current
        if current.status not in {ExecutionStatus.AUTHORIZED, ExecutionStatus.RETRYABLE_FAILURE}:
            raise ActionPolicyError("execution_not_authorized")
        now = int(time.time() * 1000)
        await self.store.execute(
            "UPDATE action_executions SET status=?, updated_at_unix_ms=? WHERE execution_id=?",
            (ExecutionStatus.EXECUTING.value, now, execution_id),
        )
        result = await self.get_execution(execution_id)
        assert result is not None
        return result

    async def mark_verifying(self, execution_id: str) -> ActionExecution:
        current = await self.get_execution(execution_id)
        if current is None:
            raise ActionPolicyError("unknown_execution")
        if current.terminal:
            return current
        if current.status != ExecutionStatus.SUBMITTED:
            raise ActionPolicyError("execution_not_submitted")
        now = int(time.time() * 1000)
        await self.store.execute(
            "UPDATE action_executions SET status=?, updated_at_unix_ms=? WHERE execution_id=?",
            (ExecutionStatus.VERIFYING.value, now, execution_id),
        )
        result = await self.get_execution(execution_id)
        assert result is not None
        return result

    async def mark_submitted(self, execution_id: str, *, correlation: dict[str, Any], evidence_pointer: str | None = None) -> ActionExecution:
        current = await self.get_execution(execution_id)
        if current is None:
            raise ActionPolicyError("unknown_execution")
        if current.terminal:
            return current
        now = int(time.time() * 1000)
        await self.store.execute(
            "UPDATE action_executions SET status=?, submitted_at_ms=?, correlation_json=?, evidence_pointer=?, updated_at_unix_ms=? WHERE execution_id=?",
            (ExecutionStatus.SUBMITTED.value, now, Store.dumps(correlation), evidence_pointer, now, execution_id),
        )
        result = await self.get_execution(execution_id)
        assert result is not None
        return result

    async def verify(self, observation: VerificationObservation) -> ActionReceipt:
        execution = await self.get_execution(observation.execution_id)
        if execution is None:
            raise ActionPolicyError("unknown_execution")
        definition = await self.get_definition(execution.action_id)
        if definition is None:
            raise ActionPolicyError("unknown_action")

        if definition.verifier_type == VerifierType.NONE:
            status = ExecutionStatus.UNVERIFIABLE
        elif not observation.success:
            status = ExecutionStatus.PARTIAL_SUCCESS if observation.partial else ExecutionStatus.VERIFICATION_FAILED
        elif execution.correlation:
            for key, expected in execution.correlation.items():
                if observation.correlation.get(key) != expected:
                    status = ExecutionStatus.VERIFICATION_FAILED
                    break
            else:
                status = ExecutionStatus.VERIFIED_SUCCESS
        else:
            status = ExecutionStatus.UNVERIFIABLE if definition.mutates_state else ExecutionStatus.VERIFIED_SUCCESS

        now = int(time.time() * 1000)
        evidence_pointer = observation.evidence_pointer or execution.evidence_pointer
        await self.store.execute(
            "UPDATE action_executions SET status=?, verified_at_ms=?, evidence_pointer=?, updated_at_unix_ms=? WHERE execution_id=?",
            (status.value, now, evidence_pointer, now, execution.execution_id),
        )
        receipt = ActionReceipt(
            receipt_id=str(uuid.uuid4()), execution_id=execution.execution_id,
            status=status, verifier_type=definition.verifier_type,
            correlation=observation.correlation,
            observed_postcondition=observation.observed_postcondition,
            evidence_pointer=evidence_pointer, created_at_ms=now,
        )
        await self.store.execute(
            "INSERT INTO action_receipts(receipt_id, execution_id, status, verifier_type, correlation_json, observed_postcondition_json, evidence_pointer, created_at_unix_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (receipt.receipt_id, receipt.execution_id, receipt.status.value, receipt.verifier_type.value,
             Store.dumps(receipt.correlation), Store.dumps(receipt.observed_postcondition), receipt.evidence_pointer, receipt.created_at_ms),
        )
        return receipt

    async def fail_execution(
        self,
        execution_id: str,
        *,
        status: ExecutionStatus,
        error_code: str,
        evidence_pointer: str | None = None,
    ) -> ActionExecution:
        allowed = {
            ExecutionStatus.PRECONDITION_FAILED,
            ExecutionStatus.EXECUTION_FAILED,
            ExecutionStatus.VERIFICATION_FAILED,
            ExecutionStatus.RETRYABLE_FAILURE,
            ExecutionStatus.PARTIAL_SUCCESS,
            ExecutionStatus.CONTEXT_INSUFFICIENT,
            ExecutionStatus.CONFLICTED_STATE,
        }
        if status not in allowed:
            raise ActionPolicyError("invalid_failure_status")
        current = await self.get_execution(execution_id)
        if current is None:
            raise ActionPolicyError("unknown_execution")
        if current.terminal:
            return current
        now = int(time.time() * 1000)
        await self.store.execute(
            "UPDATE action_executions SET status=?, error_code=?, evidence_pointer=COALESCE(?,evidence_pointer), updated_at_unix_ms=? WHERE execution_id=?",
            (status.value, error_code, evidence_pointer, now, execution_id),
        )
        result = await self.get_execution(execution_id)
        assert result is not None
        return result

    async def get_execution(self, execution_id: str) -> ActionExecution | None:
        row = await self.store.fetchone("SELECT * FROM action_executions WHERE execution_id = ?", (execution_id,))
        return self._row_to_execution(row) if row is not None else None

    async def revoke_privileged_for_device(self, requested_by: str) -> int:
        now = int(time.time() * 1000)
        async with self.store.connection() as db:
            cur = await db.execute(
                """
                UPDATE action_executions
                SET status=?, error_code='DEVICE_OR_GRANT_REVOKED', updated_at_unix_ms=?
                WHERE requested_by=? AND action_class IN ('A2','A3','A4')
                  AND status NOT IN ('VERIFIED_SUCCESS','DENIED','EXPIRED','REVOKED','VERIFICATION_FAILED','UNVERIFIABLE')
                """,
                (ExecutionStatus.REVOKED.value, now, requested_by),
            )
            await db.commit()
            return int(cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0)

    async def _persist_execution(self, execution: ActionExecution) -> ActionExecution:
        now = int(time.time() * 1000)
        await self.store.execute(
            """
            INSERT INTO action_executions(
              execution_id, command_id, turn_id, action_id, action_class, principal_type,
              requested_by, status, idempotency_key, snapshot_id, parameters_digest,
              submitted_at_ms, verified_at_ms, correlation_json, evidence_pointer, error_code,
              updated_at_unix_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(execution_id) DO UPDATE SET
              status=excluded.status, error_code=excluded.error_code, updated_at_unix_ms=excluded.updated_at_unix_ms
            """,
            (execution.execution_id, execution.command_id, execution.turn_id, execution.action_id,
             execution.action_class.value, execution.principal_type.value, execution.requested_by,
             execution.status.value, execution.idempotency_key, execution.snapshot_id,
             execution.parameters_digest, execution.submitted_at_ms, execution.verified_at_ms,
             Store.dumps(execution.correlation), execution.evidence_pointer, execution.error_code, now),
        )
        return execution

    @staticmethod
    def _row_to_execution(row: Any) -> ActionExecution:
        return ActionExecution(
            execution_id=str(row["execution_id"]), command_id=str(row["command_id"]),
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            action_id=str(row["action_id"]), action_class=ActionClass(str(row["action_class"])),
            principal_type=PrincipalType(str(row["principal_type"])), requested_by=str(row["requested_by"]),
            status=ExecutionStatus(str(row["status"])), idempotency_key=str(row["idempotency_key"]),
            snapshot_id=str(row["snapshot_id"]) if row["snapshot_id"] is not None else None,
            parameters_digest=str(row["parameters_digest"]),
            submitted_at_ms=int(row["submitted_at_ms"]) if row["submitted_at_ms"] is not None else None,
            verified_at_ms=int(row["verified_at_ms"]) if row["verified_at_ms"] is not None else None,
            correlation=json.loads(row["correlation_json"] or "{}"),
            evidence_pointer=str(row["evidence_pointer"]) if row["evidence_pointer"] is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
        )