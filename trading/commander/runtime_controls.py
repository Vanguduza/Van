"""Private gateway-only transport for original owner runtime recoveries."""
import json
from pathlib import Path
import time

from fastapi import HTTPException

from vati.app.runtime_control_journal import RuntimeControlJournal, RuntimeControlConflict
from vati.app.runtime_control_protocol import RecoveryIntent, RecoveryProof, RuntimeControlError
from vati.authority import load_owner_keys
from vati.core import open_ledger
from vati.core.canonical import canonical_hash

RUNTIME_COMMANDS = ('runtime_recovery_review', 'runtime_recovery_request', 'runtime_recovery_operation')
RUNTIME_TOOL_SCHEMAS = {
    name: {'description': description, 'properties': {}} for name, description in (
        ('runtime_recovery_review', 'Current single-session recovery state; never an entry grant.'),
        ('runtime_recovery_request', 'Queue an exact device-signed owner recovery for the fenced runtime.'),
        ('runtime_recovery_operation', 'Read the original recovery outcome for its owning device.'))}


def build_runtime_control_handlers(settings):
    def review(args):
        matches = []
        for path in Path(settings.heartbeat_dir).glob('*.json'):
            try:
                hb = json.loads(path.read_text())
                value = hb.get('runtime_recovery', {})
                state = value.get('state', {})
                if (state.get('account_alias') != args.get('account_alias')
                    or state.get('session_id') != args.get('session_id')):
                    continue
                now = int(time.time() * 1000)
                if (type(value.get('observed_ms')) is not int or not 0 <= now-value['observed_ms'] <= 30000
                    or value.get('state_ref') != canonical_hash(state)):
                    continue
                matches.append(value)
            except (OSError, ValueError, TypeError):
                continue
        if len(matches) != 1:
            raise HTTPException(409, 'a unique fresh native recovery review is unavailable')
        return matches[0]

    def request(args):
        led = open_ledger(settings.ledger)
        try:
            intent = RecoveryIntent.from_mapping(args.get('intent'))
            proof = RecoveryProof.from_mapping(args.get('proof'))
            return RuntimeControlJournal(led).enqueue(intent, proof, load_owner_keys(settings.owner_authority_keys)).public()
        except RuntimeControlConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeControlError as exc:
            raise HTTPException(403, str(exc)) from exc
        finally:
            led.close()

    def operation(args):
        led = open_ledger(settings.ledger)
        try:
            state = RuntimeControlJournal(led).status(args.get('operation_id'), args.get('device_id'))
            if state is None:
                raise HTTPException(404, 'unknown original recovery operation')
            return state.public()
        finally:
            led.close()
    return dict(zip(RUNTIME_COMMANDS, (review, request, operation)))
