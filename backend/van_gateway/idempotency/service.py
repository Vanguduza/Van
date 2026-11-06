from __future__ import annotations

import hashlib
import json
import time
from enum import Enum
from typing import Any

from van_gateway.storage.db import Store
from van_gateway.models import CommandResult
from van_gateway.mission.models import AuthorityEnvelope


class IdempotencyStatus(str, Enum):
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


class IdempotencyConflict(Exception):
    pass


class IdempotencyReceiptCorrupt(IdempotencyConflict):
    pass


class IdempotencyInFlight(Exception):
    pass


#: P0-OPS-011 — how long a claim may be held before it is treated as abandoned.
#:
#: An IN_FLIGHT claim had no lease at all. A gateway that died between claiming a key and
#: completing it left the row IN_FLIGHT forever, and every later retry raised "still in
#: flight". The idempotency key is part of the signed request, so the owner could not work
#: around it by changing it: that command became permanently unrepeatable and the only cure
#: was editing the database.
#:
#: Chosen against the execution deadline rather than against how long a request takes. A
#: command handed to Hermes carries a deadline measured in minutes, and a claim released
#: before that deadline would let a second attempt run beside the first. Fifteen minutes is
#: comfortably past it, and the cost of waiting is a retry that is refused for a while
#: rather than one that duplicates work.
STALE_CLAIM_SECONDS = 15 * 60


class IdempotencyService:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def request_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def begin(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Start idempotent work.

        Returns prior response if same key+hash completed.
        Raises conflict if same key different hash.
        Raises in-flight if ambiguous reuse while running.
        """
        req_hash = self.request_hash(payload)
        now = int(time.time())

        # The claim must be atomic. The previous implementation did a SELECT on one
        # connection and an INSERT on another with no transaction, so two concurrent
        # identical signed commands could both observe no row and both proceed to execute
        # (finding P1-SEC-005). auth/service.py already used BEGIN IMMEDIATE for exactly
        # this reason; the pattern was known and simply not applied here.
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cur = await db.execute(
                    "SELECT idempotency_key, request_hash, status, response_json, "
                    "updated_at_unix FROM idempotency WHERE idempotency_key = ?",
                    (key,),
                )
                row = await cur.fetchone()
                if row is None:
                    await db.execute(
                        "INSERT INTO idempotency(idempotency_key, request_hash, status, "
                        "response_json, created_at_unix, updated_at_unix, claim_count) "
                        "VALUES (?, ?, ?, NULL, ?, ?, 1)",
                        (key, req_hash, IdempotencyStatus.IN_FLIGHT.value, now, now),
                    )
                    await db.commit()
                    return None
                # Materialise before the transaction closes.
                row = dict(row)

                # P0-OPS-011 — recover a claim whose holder is gone. Inside the same
                # BEGIN IMMEDIATE as the read, because two retries arriving together must
                # not both conclude the claim is theirs; that is the defect P1-SEC-005
                # closed, and releasing a claim would reopen it if done outside.
                #
                # Only an IN_FLIGHT claim with a matching hash is recoverable. COMPLETED
                # and CONFLICT are answers, not claims, and a different hash under the same
                # key is the conflict this table exists to detect.
                if (
                    row["status"] == IdempotencyStatus.IN_FLIGHT.value
                    and row["request_hash"] == req_hash
                    and now - int(row["updated_at_unix"]) >= STALE_CLAIM_SECONDS
                ):
                    await db.execute(
                        "UPDATE idempotency SET updated_at_unix = ?, "
                        "claim_count = claim_count + 1 WHERE idempotency_key = ?",
                        (now, key),
                    )
                    await db.commit()
                    # The caller now re-executes. That is safe because the work it would
                    # repeat is itself idempotent at the layer that matters:
                    # `CommandMissionLink.existing_for_command` returns the mission already
                    # opened for this command rather than opening a second one. Retaking a
                    # claim is not a promise that nothing happened; it is a statement that
                    # whoever held it is not coming back.
                    return None
                if (
                    row["status"] == IdempotencyStatus.FAILED.value
                    and row["request_hash"] == req_hash
                ):
                    await db.execute(
                        "UPDATE idempotency SET status = ?, response_json = NULL, "
                        "updated_at_unix = ?, claim_count = claim_count + 1 "
                        "WHERE idempotency_key = ?",
                        (IdempotencyStatus.IN_FLIGHT.value, now, key),
                    )
                    await db.commit()
                    return None
            except BaseException:
                await db.rollback()
                raise
            await db.commit()

        if row["request_hash"] != req_hash:
            # A conflicting attempt must not overwrite the original command's receipt
            # or release its in-flight claim.
            raise IdempotencyConflict("Same idempotency key with different request")
        if row["status"] == IdempotencyStatus.COMPLETED.value:
            return json.loads(row["response_json"]) if row["response_json"] else {}
        if row["status"] == IdempotencyStatus.IN_FLIGHT.value:
            raise IdempotencyInFlight("Idempotency key still in flight")
        if row["status"] == IdempotencyStatus.CONFLICT.value:
            raise IdempotencyConflict("Idempotency key previously conflicted")
        raise IdempotencyConflict("Unknown idempotency claim state")

    async def complete(self, key: str, response: dict[str, Any]) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE idempotency SET status = ?, response_json = ?, updated_at_unix = ? WHERE idempotency_key = ?",
            (IdempotencyStatus.COMPLETED.value, Store.dumps(response), now, key),
        )

    async def fail(self, key: str, response: dict[str, Any]) -> None:
        now = int(time.time())
        await self.store.execute(
            "UPDATE idempotency SET status = ?, response_json = ?, updated_at_unix = ? WHERE idempotency_key = ?",
            (IdempotencyStatus.FAILED.value, Store.dumps(response), now, key),
        )

    @staticmethod
    def _original_response(row, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Decode history, never reinterpret corrupt or foreign data as authority."""
        if row['request_hash'] != IdempotencyService.request_hash(payload):
            raise IdempotencyConflict('Original request digest differs')
        try:
            response = json.loads(row['response_json'])
            if (not isinstance(response, dict) or response.get('command_id') != payload.get('command_id')
                    or response.get('idempotency_key') != key):
                raise ValueError('Original response identity differs')
            return response
        except (ValueError, TypeError) as exc:
            raise IdempotencyReceiptCorrupt('Original command receipt is unresolved or corrupt') from exc

    @staticmethod
    def evidence_object(raw: Any, label: str) -> dict[str, Any]:
        """Decode an owned evidence object without treating JSON scalars as proof."""
        try:
            value = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise IdempotencyReceiptCorrupt(label + ' is malformed') from exc
        if not isinstance(value, dict):
            raise IdempotencyReceiptCorrupt(label + ' is not an object')
        return value

    @staticmethod
    def evidence_identity(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value:
            raise IdempotencyReceiptCorrupt(label + ' identity is missing or malformed')
        return value

    @staticmethod
    def local_result(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise IdempotencyReceiptCorrupt('Original local result is not an object')
        for name in ('execution_id', 'action_id', 'verification_state'):
            IdempotencyService.evidence_identity(value.get(name), name)
        if not isinstance(value.get('summary'), str):
            raise IdempotencyReceiptCorrupt('Original local result summary is malformed')
        if value.get('evidence_ref') is not None:
            IdempotencyService.evidence_identity(value['evidence_ref'], 'local evidence')
        if 'mission_pending' in value and not isinstance(value['mission_pending'], bool):
            raise IdempotencyReceiptCorrupt('Original local pending fact is malformed')
        if value.get('parent_reconciliation') is not None and not isinstance(value['parent_reconciliation'], dict):
            raise IdempotencyReceiptCorrupt('Original local reconciliation is malformed')
        return value

    @staticmethod
    async def _run_bound_to(db, run_id: str, mission_id: str) -> bool:
        # Read the existing MissionService.for_hermes_run owner mapping under
        # this writer, including its unambiguous legacy mission-event fallback.
        row = await (await db.execute('SELECT mission_id FROM hermes_run_bindings WHERE hermes_run_id=?', (run_id,))).fetchone()
        if row is not None:
            return row['mission_id'] == mission_id
        rows = await (await db.execute("SELECT DISTINCT mission_id FROM mission_events WHERE evidence_ref=? AND event_type='mission.started' LIMIT 2",
            ('hermes-run:' + run_id,))).fetchall()
        return len(rows) == 1 and rows[0]['mission_id'] == mission_id

    async def _checked_original(self, db, row, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._original_response(row, key, payload)
        try:
            CommandResult.model_validate(response)
        except ValueError as exc:
            raise IdempotencyReceiptCorrupt('Original result domain shape is malformed') from exc
        for field in ('mission_id', 'hermes_run_id', 'execution_id', 'context_snapshot_id', 'evidence_id'):
            if response.get(field) is not None:
                self.evidence_identity(response[field], field)
        if response.get('status') != 'accepted':
            return response
        try:
            raw = await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                ('command_authority:' + str(payload['command_id']),))).fetchone()
            sealed = self.evidence_object(raw['value'] if raw else None, 'Original authority')
            from van_gateway.command.authority import CommandAuthorityRecord
            from van_gateway.command.resolver import CommandResolution
            CommandAuthorityRecord.model_validate(sealed)
            metadata = sealed.get('dispatch_metadata', {})
            if 'typed_resolution' in metadata:
                if not isinstance(metadata['typed_resolution'], dict):
                    raise ValueError('Original resolution is not an object')
                CommandResolution.model_validate(metadata['typed_resolution'])
            if 'canonical_context' in metadata:
                context = metadata['canonical_context']
                if (not isinstance(context, dict) or context.get('snapshot_id') != sealed['snapshot_id']
                    or context.get('digest') != sealed['context_digest']):
                    raise ValueError('Original context subject differs')
            self.evidence_identity(sealed.get('snapshot_id'), 'snapshot')
            if (sealed.get('command_id') != payload['command_id']
                or sealed.get('requested_by') != payload.get('requested_by')
                or sealed.get('principal_type') != payload.get('principal_type')
                or sealed.get('request_hash') != self.request_hash(payload)
                or sealed.get('device_id') != payload.get('device_id')
                or sealed.get('snapshot_id') != response.get('context_snapshot_id')):
                raise ValueError('Original context differs')
            if response.get('mission_id'):
                mission = await (await db.execute('SELECT * FROM missions WHERE mission_id=?', (response['mission_id'],))).fetchone()
                envelope = self.evidence_object(mission['authority_envelope_json'] if mission else None, 'Original mission authority')
                AuthorityEnvelope.model_validate(envelope)
                if (mission is None or envelope.get('source_command_id') != payload['command_id']
                    or mission['owner_principal_id'] != 'device:' + str(payload['device_id'])):
                    raise ValueError('Original mission differs')
            if response.get('hermes_run_id'):
                receipt = await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                    ('command_run_receipt:' + str(payload['command_id']),))).fetchone()
                observed = self.evidence_object(receipt['value'] if receipt else None, 'Original run receipt')
                self.evidence_identity(observed.get('id'), 'run')
                if (observed['id'] != response['hermes_run_id']
                    or (response.get('mission_id') and not await self._run_bound_to(db, response['hermes_run_id'], response['mission_id']))):
                    raise ValueError('Original run differs')
            if response.get('execution_id'):
                execution = await (await db.execute('SELECT * FROM action_executions WHERE execution_id=?', (response['execution_id'],))).fetchone()
                local = self.local_result(response.get('local_execution'))
                if local['execution_id'] != response['execution_id']:
                    raise ValueError('Original local result execution differs')
                receipt = await (await db.execute('SELECT receipt_id FROM action_receipts WHERE execution_id=? AND status=?',
                    (response['execution_id'], local.get('verification_state')))).fetchone()
                if (execution is None or execution['command_id'] != payload['command_id']
                    or execution['idempotency_key'] != key or execution['snapshot_id'] != sealed['snapshot_id']
                    or execution['requested_by'] != sealed['requested_by']
                    or execution['action_id'] != local.get('action_id')
                    or execution['action_id'] != sealed.get('typed_action_id') or receipt is None):
                    raise ValueError('Original execution differs')
                audit = await (await db.execute("SELECT after_json FROM audit WHERE id=? AND command_id=? AND device_id=? AND result='accepted' AND model_delegate='gateway:local'",
                    (response.get('evidence_id'), payload['command_id'], payload['device_id']))).fetchone()
                audit_result = self.evidence_object(audit['after_json'] if audit else None, 'Original audit')
                audited_local = self.local_result(audit_result.get('local_execution'))
                if audited_local != local:
                    raise ValueError('Original local result evidence differs')
            return response
        except (ValueError, TypeError, KeyError) as exc:
            raise IdempotencyReceiptCorrupt('Original result owner could not be verified') from exc

    async def read_original(self, key: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        async with self.store.connection() as db:
            await db.execute('BEGIN')
            try:
                row = await (await db.execute('SELECT * FROM idempotency WHERE idempotency_key=?', (key,))).fetchone()
                if row is None or row['request_hash'] != self.request_hash(payload):
                    raise IdempotencyConflict('Original claim is absent or differs')
                response = await self._checked_original(db, row, key, payload) if row['status'] == IdempotencyStatus.COMPLETED.value else None
                await db.rollback()
                return response
            except BaseException:
                await db.rollback()
                raise

    async def publish_original(self, key: str, payload: dict[str, Any], response: dict[str, Any],
                               *, failed: bool = False) -> dict[str, Any]:
        """Publish this command's answer under its existing writer, preserving history.

        A stale claimant may still be alive. Its late failure/UNKNOWN must not replace
        a completed original result. Legacy generic complete/fail callers retain their
        established contract; the command orchestrator explicitly uses this boundary.
        """
        digest = self.request_hash(payload)
        if response.get('command_id') != payload.get('command_id') or response.get('idempotency_key') != key:
            raise IdempotencyConflict('Result does not name the original request')
        async with self.store.connection() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                row = await (await db.execute('SELECT * FROM idempotency WHERE idempotency_key=?', (key,))).fetchone()
                if row is None or row['request_hash'] != digest:
                    raise IdempotencyConflict('Original claim is absent or differs')
                if row['status'] == IdempotencyStatus.COMPLETED.value:
                    prior = await self._checked_original(db, row, key, payload)
                    # UNKNOWN is an observation, not proof that no effect exists. A
                    # subsequently observed original run can resolve it only through
                    # the existing durable run + mission + sealed-context owners.
                    promote = False
                    if prior.get('status') in {'in_flight', 'outcome_unknown'} and response.get('status') == 'accepted':
                        run = await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                            ('command_run_receipt:' + str(payload['command_id']),))).fetchone()
                        authority = await (await db.execute('SELECT value FROM runtime_meta WHERE key=?',
                            ('command_authority:' + str(payload['command_id']),))).fetchone()
                        mission = await (await db.execute('SELECT mission_id FROM missions WHERE '
                            "json_extract(authority_envelope_json, '$.source_command_id')=?", (payload['command_id'],))).fetchone()
                        try:
                            sealed = self.evidence_object(authority['value'] if authority else None, 'Original authority')
                            observed = self.evidence_object(run['value'] if run else None, 'Original run receipt')
                            promote = (not failed and isinstance(observed.get('id'), str) and bool(observed['id'])
                                and observed['id'] == response.get('hermes_run_id')
                                and sealed.get('request_hash') == digest
                                and sealed.get('snapshot_id') == response.get('context_snapshot_id')
                                and mission is not None and mission['mission_id'] == response.get('mission_id')
                                and await self._run_bound_to(db, observed['id'], mission['mission_id']))
                        except (IdempotencyReceiptCorrupt, ValueError, TypeError):
                            promote = False
                    if (not promote and prior.get('status') in {'in_flight', 'outcome_unknown'}
                        and response.get('status') == 'accepted' and response.get('execution_id') and not failed):
                        try:
                            await self._checked_original(db, {'request_hash': digest,
                                'response_json': Store.dumps(response)}, key, payload)
                            promote = True
                        except IdempotencyReceiptCorrupt:
                            pass
                    if not promote:
                        await db.rollback()
                        return prior
                await db.execute('UPDATE idempotency SET status=?,response_json=?,updated_at_unix=? WHERE idempotency_key=?',
                    (IdempotencyStatus.FAILED.value if failed else IdempotencyStatus.COMPLETED.value,
                     Store.dumps(response), int(time.time()), key))
                await db.commit()
                return response
            except BaseException:
                await db.rollback()
                raise
