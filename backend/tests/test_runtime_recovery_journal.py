"""Durable exact operation readback and atomic local recovery evidence."""
from dataclasses import replace

import pytest

from test_runtime_recovery_protocol import owner_proof,NOW
from vati.app.runtime_control_journal import RuntimeControlJournal,RuntimeControlConflict,RuntimeControlStoreError
from vati.core import Ledger,EventKind,make_event


@pytest.fixture(params=["sqlite","postgres"])
def recovery_ledger(tmp_path, request):
    import os, uuid
    if request.param=="postgres":
        spec=os.environ.get("VATI_TEST_PG_DSN")
        if not spec or os.environ.get("VATI_TEST_PG_ISOLATED_FIXTURE")!="1":
            pytest.skip("requires explicitly isolated native PostgreSQL fixture")
        from vati.core import PostgresLedger
        scope="runtime-recovery-"+uuid.uuid4().hex
        return lambda path: PostgresLedger(spec,ledger_name=scope)
    return Ledger


def outcome(phase='APPLIED',refs=()):
    return {'reason_code':phase,'effect_refs':list(refs),'entry_authority_granted':False,
        'remaining_kill':[],'state_ref':'c'*64}


def effect(ledger,state):
    event=make_event(EventKind.KILL_SWITCH,'vati-cycle',{'trigger':'OWNER_HALT','cleared':True,
        'account_alias':state.intent.account_alias,'owner_signature_ref':state.authority_ref},
        event_time_ms=NOW*1000,received_time_ms=NOW*1000,correlation_id=state.intent.session_id)
    ledger.append(event);return event.hash


@pytest.mark.asyncio
async def test_exact_original_recovery_read_survives_restart_and_expiry(tmp_path,owner_proof,recovery_ledger):
    intent,proof,keys=await owner_proof();path=tmp_path/'recovery.sqlite'
    ledger=recovery_ledger(path);journal=RuntimeControlJournal(ledger,clock=lambda:NOW)
    try:
        request=journal.enqueue(intent,proof,keys)
        assert request.phase=='REQUESTED' and len(journal.pending(intent.session_id))==1
        with ledger.atomic():
            ref=effect(ledger,request);done=journal.finish(request,'APPLIED',outcome(refs=[ref]))
        assert done.phase=='APPLIED' and len(journal.pending(intent.session_id))==0
    finally:ledger.close()
    ledger=recovery_ledger(path);journal=RuntimeControlJournal(ledger,clock=lambda:NOW+1000)
    try:
        assert journal.enqueue(intent,proof,{}).event_ref==done.event_ref
        assert journal.status(proof.operation_id,intent.device_id).public()['phase']=='APPLIED'
        assert journal.status(proof.operation_id,'other-device') is None
        assert len(list(ledger.iter(EventKind.KILL_SWITCH)))==1
    finally:ledger.close()


@pytest.mark.asyncio
async def test_control_does_not_become_applied_without_actual_owned_effect_evidence(tmp_path,owner_proof,recovery_ledger):
    intent,proof,keys=await owner_proof();ledger=recovery_ledger(tmp_path/'recovery.sqlite');journal=RuntimeControlJournal(ledger,clock=lambda:NOW)
    try:
        request=journal.enqueue(intent,proof,keys)
        for refs in [[],['b'*64]]:
            with pytest.raises(RuntimeControlStoreError):journal.finish(request,'APPLIED',outcome(refs=refs))
        assert journal.status(proof.operation_id,intent.device_id).phase=='REQUESTED'
    finally:ledger.close()


@pytest.mark.asyncio
async def test_recovery_and_its_domain_effect_roll_back_together(tmp_path,owner_proof,recovery_ledger):
    intent,proof,keys=await owner_proof();ledger=recovery_ledger(tmp_path/'recovery.sqlite');journal=RuntimeControlJournal(ledger,clock=lambda:NOW)
    try:
        request=journal.enqueue(intent,proof,keys)
        with pytest.raises(OSError,match='before outer commit'):
            with ledger.atomic():
                ref=effect(ledger,request);journal.finish(request,'APPLIED',outcome(refs=[ref]))
                raise OSError('fixture before outer commit')
        assert journal.status(proof.operation_id,intent.device_id).phase=='REQUESTED'
        assert list(ledger.iter(EventKind.KILL_SWITCH))==[]
        with ledger.atomic():
            ref=effect(ledger,request);done=journal.finish(request,'APPLIED',outcome(refs=[ref]))
        assert done.phase=='APPLIED' and len(list(ledger.iter(EventKind.KILL_SWITCH)))==1
    finally:ledger.close()


@pytest.mark.asyncio
async def test_original_control_cannot_change_actor_args_or_outcome(tmp_path,owner_proof,recovery_ledger):
    intent,proof,keys=await owner_proof();ledger=recovery_ledger(tmp_path/'recovery.sqlite');journal=RuntimeControlJournal(ledger,clock=lambda:NOW)
    try:
        request=journal.enqueue(intent,proof,keys)
        with pytest.raises(RuntimeControlConflict):journal.enqueue(replace(intent,session_id='another-runtime'),proof,keys)
        denied=journal.finish(request,'REFUSED',outcome('STATE_CHANGED'))
        assert denied.phase=='REFUSED'
        assert journal.finish(request,'REFUSED',outcome('STATE_CHANGED')).event_ref==denied.event_ref
        with pytest.raises(RuntimeControlConflict):journal.finish(request,'REFUSED',outcome('PRECONDITION_UNMET'))
        assert journal.enqueue(intent,proof,keys).phase=='REFUSED'
    finally:ledger.close()


@pytest.mark.asyncio
async def test_independent_native_connections_claim_the_same_original_only_once(tmp_path,owner_proof,recovery_ledger):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    intent,proof,keys=await owner_proof();path=tmp_path/'parallel.sqlite'
    # Initialize the shared schema before both independent connections compete.
    recovery_ledger(path).close()
    barrier=Barrier(2)
    def enqueue():
        led=recovery_ledger(path)
        try:
            barrier.wait(timeout=5)
            return RuntimeControlJournal(led,clock=lambda:NOW).enqueue(intent,proof,keys).event_ref
        finally:led.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks=[pool.submit(enqueue) for _ in range(2)]
        refs=[task.result(timeout=10) for task in tasks]
    assert refs[0]==refs[1]
    ledger=recovery_ledger(path)
    try:
        assert len([e for e in ledger.iter(EventKind.SESSION) if e.producer=='vati-runtime-recovery-control'])==1
        assert ledger.verify_chain()[0]
    finally:ledger.close()
