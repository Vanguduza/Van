"""An expired signature may certify refusal only, never extend native authority."""
from dataclasses import replace
from contextlib import closing

import pytest

from test_runtime_recovery_protocol import owner_proof, NOW
from test_runtime_recovery_journal import recovery_ledger
from vati.app.runtime_control_journal import RuntimeControlJournal, RuntimeControlConflict
from vati.app.runtime_control_protocol import RuntimeControlError
from vati.core import Ledger, EventKind


@pytest.mark.asyncio
async def test_expired_first_delivery_is_durable_refusal_and_never_reopened(tmp_path, owner_proof, recovery_ledger):
    intent, proof, keys = await owner_proof(); path = tmp_path/'native.sqlite'
    with closing(recovery_ledger(path)) as ledger:
        journal = RuntimeControlJournal(ledger, clock=lambda:proof.expires_at_unix+1)
        state = journal.enqueue(intent, proof, keys)
        assert state.phase == 'REFUSED' and state.result['reason_code'] == 'APPROVAL_EXPIRED'
        assert state.result['effect_refs'] == [] and state.result['entry_authority_granted'] is False
        assert state.result['remaining_kill'] is None and state.result['state_ref'] is None
        assert journal.pending_account(intent.account_alias) == ()
        ref = state.event_ref
    with closing(recovery_ledger(path)) as ledger:
        # Clock rollback and re-registration cannot reopen the original refusal.
        state = RuntimeControlJournal(ledger, clock=lambda:NOW).enqueue(intent, proof, keys)
        assert state.phase == 'REFUSED' and state.event_ref == ref
        assert ledger.count(EventKind.KILL_SWITCH) == ledger.count(EventKind.ORDER_COMMAND) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['signature','intent','expiry','key'])
async def test_expired_invalid_proof_cannot_create_a_native_refusal_record(tmp_path, owner_proof, change, recovery_ledger):
    intent, proof, keys = await owner_proof()
    if change == 'signature': proof = replace(proof, signature_b64='AAAA')
    elif change == 'intent': intent = replace(intent, state_ref='b'*64)
    elif change == 'expiry': proof = replace(proof, expires_at_unix=proof.expires_at_unix+1)
    else: keys = {}
    with closing(recovery_ledger(tmp_path/'native.sqlite')) as ledger:
        with pytest.raises(RuntimeControlError):
            RuntimeControlJournal(ledger, clock=lambda:proof.expires_at_unix+1).enqueue(intent, proof, keys)
        assert ledger.count() == 0


@pytest.mark.asyncio
async def test_pending_original_wins_over_expiry_without_being_reclassified_no_effect(tmp_path, owner_proof, recovery_ledger):
    intent, proof, keys = await owner_proof()
    with closing(recovery_ledger(tmp_path/'native.sqlite')) as ledger:
        original = RuntimeControlJournal(ledger, clock=lambda:NOW).enqueue(intent, proof, keys)
        later = RuntimeControlJournal(ledger, clock=lambda:proof.expires_at_unix+1000).enqueue(intent, proof, {})
        assert later.phase == 'REQUESTED' and later.event_ref == original.event_ref
        with pytest.raises(RuntimeControlConflict):
            RuntimeControlJournal(ledger).enqueue(replace(intent, state_ref='b'*64), proof, keys)


@pytest.mark.asyncio
async def test_nonexpired_but_not_yet_valid_original_cannot_be_reclassified_as_expired(tmp_path, owner_proof, recovery_ledger):
    intent, proof, keys = await owner_proof()
    with closing(recovery_ledger(tmp_path/'native.sqlite')) as ledger:
        with pytest.raises(RuntimeControlError):
            RuntimeControlJournal(ledger, clock=lambda:NOW-61).enqueue(intent,proof,keys)
        assert ledger.count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('defect',['applied','claims_state','claims_effect','claims_entry','accepted_before_expiry'])
async def test_expired_refusal_history_rejects_invented_effects_or_current_state(tmp_path, owner_proof, defect):
    from copy import deepcopy
    from vati.core import make_event
    from vati.app.runtime_control_journal import RuntimeControlStoreError,EXPIRED_SCHEMA,PRODUCER
    intent, proof, keys = await owner_proof()
    with closing(Ledger(tmp_path/'template.sqlite')) as ledger:
        state = RuntimeControlJournal(ledger,clock=lambda:proof.expires_at_unix+1).enqueue(intent,proof,keys)
        payload = deepcopy(next(iter(ledger.iter())).payload)
    if defect=='applied': payload['phase']='APPLIED';payload['result']['reason_code']='APPLIED'
    elif defect=='claims_state': payload['result']['state_ref']=intent.state_ref;payload['result']['remaining_kill']=[]
    elif defect=='claims_effect': payload['result']['effect_refs']=['b'*64]
    elif defect=='claims_entry': payload['result']['entry_authority_granted']=True
    else: payload['accepted_at_unix']=proof.expires_at_unix-1
    stamp=payload['accepted_at_unix']*1000
    with closing(Ledger(tmp_path/'tampered.sqlite')) as ledger:
        ledger.append(make_event(EventKind.SESSION,PRODUCER,payload,event_time_ms=stamp,
            received_time_ms=stamp,correlation_id=proof.operation_id))
        assert ledger.verify_chain()[0]  # Semantics, not just a broken hash, must reject it.
        with pytest.raises(RuntimeControlStoreError):
            RuntimeControlJournal(ledger).status(proof.operation_id,intent.device_id)


@pytest.mark.asyncio
async def test_two_native_connections_at_expiry_choose_one_original_admission(tmp_path, owner_proof, recovery_ledger):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    intent, proof, keys = await owner_proof(); path = tmp_path/'native-race.sqlite'
    recovery_ledger(path).close()
    barrier = Barrier(2)
    def attempt(stamp):
        with closing(recovery_ledger(path)) as ledger:
            barrier.wait(timeout=5)
            return RuntimeControlJournal(ledger,clock=lambda:stamp).enqueue(intent,proof,keys)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(attempt,stamp) for stamp in (NOW,proof.expires_at_unix+1)]
        states = [f.result(timeout=15) for f in tasks]
    assert states[0].event_ref == states[1].event_ref
    assert states[0].phase == states[1].phase and states[0].phase in {'REQUESTED','REFUSED'}
    with closing(recovery_ledger(path)) as ledger:
        assert len([e for e in ledger.iter(EventKind.SESSION) if e.producer=='vati-runtime-recovery-control']) == 1
        assert ledger.count(EventKind.KILL_SWITCH) == ledger.count(EventKind.ORDER_COMMAND) == 0
        assert ledger.verify_chain()[0]
