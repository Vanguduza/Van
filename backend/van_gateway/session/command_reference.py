"""Side-effect-free lookup of an original signed HTTP command during session recovery."""
from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError

from van_gateway.auth.service import AuthError
from van_gateway.idempotency.service import IdempotencyService
from van_gateway.models import CommandRequest, CommandResult
from van_gateway.orchestrator import CommandOrchestrator


async def read_original_commands(*, store, auth, sessions, device_id: str,
                                 van_session_id: str, pending_command_ids: list[str],
                                 references: list[dict], read_owned_result=None, missions=None, actions=None) -> tuple[dict[str, str], dict[str, dict]]:
    # A client profile label is correlation data, never server authority. The session,
    # current authenticated device and original signature establish the actual scope.
    session = await sessions.get(van_session_id)
    states: dict[str, str] = {}
    receipts: dict[str, dict] = {}
    seen: set[str] = set()
    for ref in references[:50]:
        identity = ref['command_id']
        if identity not in pending_command_ids[:50]:
            continue
        states[identity] = 'ORIGINAL_UNRESOLVED'
        if identity in seen:
            continue
        seen.add(identity)
        if (session is None or session.device_id != device_id
                or ref['device_id'] != device_id):
            continue
        original_session = (await sessions.get(ref['van_session_id'])
                            if ref['van_session_id'] != 'unbound' else None)
        if ref['van_session_id'] != 'unbound' and (original_session is None or original_session.device_id != device_id):
            continue
        try:
            original = CommandRequest(**ref['command_request'])
            if (not original.idempotency_key or original.device_id != device_id
                    or original.command_id != identity):
                continue
            await auth.require_device(device_id)
            canonical = CommandOrchestrator.original_command_canonical(original)
            auth.verify_signature(device_id, canonical, original.signature)
        except (ValidationError, AuthError, TypeError, ValueError):
            continue
        # A committed outer envelope, when present, must describe this exact original.
        # An absent outer row is legitimate for a lost direct-HTTP answer, but is never
        # itself evidence that the command was not submitted.
        outer = await store.fetchone(
            'SELECT command_id,idempotency_key,kind,payload_digest FROM van_session_messages '
            'WHERE van_session_id=? AND message_id=?',
            (ref['van_session_id'], ref['message_id']),
        )
        if outer is not None:
            try:
                if (outer['command_id'] != identity
                        or outer['idempotency_key'] != ref['idempotency_key']
                        or outer['kind'] != 'command.submit'
                        or outer['payload_digest'] != hashlib.sha256(json.dumps(
                            ref['command_request'], sort_keys=True, separators=(',', ':'),
                            ).encode()).hexdigest()):
                    continue
            except (ValidationError, TypeError, ValueError):
                continue
        row = await store.fetchone(
            'SELECT request_hash,status,response_json FROM idempotency WHERE idempotency_key=?',
            (original.idempotency_key,),
        )
        if row is None or row['request_hash'] != IdempotencyService.request_hash(original.model_dump()):
            continue
        if row['status'] == 'IN_FLIGHT':
            states[identity] = 'RESULT_PENDING'
            continue
        if row['status'] != 'COMPLETED':
            continue
        try:
            result = CommandResult(**json.loads(row['response_json']))
        except (ValidationError, TypeError, ValueError):
            continue
        if (result.command_id != original.command_id or result.idempotency_key != original.idempotency_key
                or result.status in {'degraded', 'in_flight'}):
            continue
        owned = None
        if read_owned_result is not None:
            try:
                owned = await read_owned_result(original.command_id, device_id)
            except Exception as exc:
                # The existing owner read refuses missing/foreign history. Do not
                # turn unavailable readback into a successful transfer.
                from fastapi import HTTPException
                if not isinstance(exc, HTTPException) or exc.status_code != 404:
                    continue
        if result.mission_id is not None:
            if (owned is None or owned.get('command_id') != original.command_id
                    or owned.get('mission_id') != result.mission_id
                    or (result.correlation_id is not None and owned.get('correlation_id') != result.correlation_id)):
                continue
            if result.hermes_run_id:
                try:
                    bound = await missions.for_hermes_run(result.hermes_run_id) if missions is not None else None
                except Exception:
                    continue
                if bound is None or bound.mission_id != result.mission_id:
                    continue
            if result.execution_id:
                execution = await actions.get_execution(result.execution_id) if actions is not None else None
                if (execution is None or execution.command_id != original.command_id
                        or execution.idempotency_key != original.idempotency_key):
                    continue
            history_owner = 'command_mission'
        elif (result.status in {'denied', 'expired', 'rejected_untrusted', 'conflict'}
              and result.hermes_run_id is None and result.execution_id is None and not result.local_execution):
            # This exact durable idempotency receipt owns the original refusal;
            # there is no native-work transfer inferred from its status.
            history_owner = 'idempotency_refusal'
            owned = None
        else:
            continue
        public_fields = ('status', 'command_id', 'idempotency_key', 'mission_id',
                         'hermes_run_id', 'execution_id', 'correlation_id',
                         'verification_state', 'evidence_id', 'context_snapshot_id')
        owner_fields = ('command_id', 'correlation_id', 'mission_id', 'mission_state',
                        'owner_status', 'verification_state', 'finished', 'deadline_ms', 'updated_at_ms')
        raw = result.model_dump(mode='json')
        receipts[identity] = {
            'reference': {key: ref[key] for key in ('van_session_id', 'message_id',
                'idempotency_key', 'command_id', 'device_id', 'profile_id')},
            'request_hash': row['request_hash'], 'history_owner': history_owner,
            'result': {key: raw[key] for key in public_fields if key in raw},
            'owner_result': {key: owned.get(key) for key in owner_fields} if owned else None,
        }
        # This means request/result LOOKUP completed, never native-effect success.
        # Authority-bearing approvals, signatures and payloads are not returned.
        states[identity] = 'ORIGINAL_COMPLETED'
    return states, receipts
