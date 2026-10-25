"""Declared calendar observations respect cutoffs, revision ownership and publication."""
from dataclasses import replace
from decimal import Decimal
from contextlib import contextmanager

import pytest
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

from test_rev51_calendar import _sched,_obs,SCHED_MS
from vati.calendar.recorder import CalendarRecorder,ReleaseStatus,ObservationConflict,PRODUCER
from vati.core.events import EventKind,make_event
from vati.core.ledger import Ledger


def test_future_observations_cannot_supply_an_actual_before_their_declared_availability():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    for source in ('a','b'):recorder.observe(_obs(scheduled.event_key,source,'150000',SCHED_MS+500))
    past=recorder.record(scheduled.event_key,now_ms=SCHED_MS+100)
    assert past.agreed_actual is None and past.observations==()
    assert recorder.verified_only(now_ms=SCHED_MS+100)==[]
    assert recorder.record(scheduled.event_key,now_ms=SCHED_MS+500).agreed_actual==Decimal('150000')


def test_future_revision_does_not_erase_the_original_agreement_at_an_earlier_cutoff():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    first=recorder.observe(_obs(scheduled.event_key,'a','150000',SCHED_MS+100))
    recorder.observe(_obs(scheduled.event_key,'b','150000',SCHED_MS+100))
    recorder.observe(replace(first,actual=Decimal('142000'),observed_ms=SCHED_MS+9000,
        revision_of=first.observation_id))
    past=recorder.record(scheduled.event_key,now_ms=SCHED_MS+200)
    assert past.status is ReleaseStatus.VERIFIED and past.agreed_actual==Decimal('150000')
    assert len(past.observations)==2


def test_revision_cannot_supersede_another_publishers_original_claim():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    first=recorder.observe(_obs(scheduled.event_key,'a','150000',SCHED_MS+100))
    other=recorder.observe(_obs(scheduled.event_key,'b','150000',SCHED_MS+100))
    with pytest.raises(ObservationConflict):
        recorder.observe(replace(other,actual=Decimal('142000'),observed_ms=SCHED_MS+9000,
            revision_of=first.observation_id))
    assert recorder.record(scheduled.event_key).agreed_actual==Decimal('150000')


@pytest.mark.parametrize('number',['NaN','Infinity','-Infinity'])
def test_nonfinite_actual_cannot_enter_a_calendar_record(number):
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    with pytest.raises(ValueError):recorder.observe(_obs(scheduled.event_key,'a',number,SCHED_MS+100))
    assert recorder.record(scheduled.event_key).observations==()


def test_equal_exact_values_with_different_decimal_scale_agree():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    recorder.observe(_obs(scheduled.event_key,'a','1.0',SCHED_MS+100))
    recorder.observe(_obs(scheduled.event_key,'b','1.00',SCHED_MS+100))
    result=recorder.record(scheduled.event_key)
    assert result.status is ReleaseStatus.VERIFIED and result.agreed_actual==Decimal('1')


def test_ledger_availability_is_the_actual_declared_observation_time(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
        observed=recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+3000))
        event=next(ledger.iter(EventKind.CALENDAR_RELEASE))
        assert event.received_time_ms==observed.observed_ms
        assert event.event_time_ms==observed.released_ms and ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('phase',['schedule','observe'])
def test_failed_ledger_publication_cannot_be_remembered_as_success(tmp_path,monkeypatch,phase):
    ledger=Ledger(tmp_path/'calendar.sqlite');recorder=CalendarRecorder(ledger=ledger)
    try:
        if phase=='observe':scheduled=_sched(recorder)
        write=ledger.append
        def fail(event):raise OSError('fixture publication unavailable before write')
        with monkeypatch.context() as patch:
            patch.setattr(ledger,'append',fail)
            with pytest.raises(OSError):
                if phase=='schedule':_sched(recorder)
                else:recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
        if phase=='schedule':_sched(recorder);assert ledger.count(EventKind.CALENDAR_SCHEDULE)==1
        else:
            recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
            assert ledger.count(EventKind.CALENDAR_RELEASE)==1
    finally:ledger.close()


def test_a_cold_recorder_does_not_publish_the_same_original_observation_twice(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        for _ in range(2):
            recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
            recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
        assert ledger.count(EventKind.CALENDAR_SCHEDULE)==1
        assert ledger.count(EventKind.CALENDAR_RELEASE)==1 and ledger.verify_chain()[0]
    finally:ledger.close()


def test_clock_defect_claims_remain_visible_but_cannot_verify_an_actual():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    for source in ('a','b'):recorder.observe(_obs(scheduled.event_key,source,'1',SCHED_MS-1))
    result=recorder.record(scheduled.event_key)
    assert len(result.observations)==2 and result.latency_ms==-1
    assert result.status is not ReleaseStatus.VERIFIED and result.agreed_actual is None


def test_forecast_only_observation_is_not_the_first_actual_release_latency():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    recorder.observe(replace(_obs(scheduled.event_key,'a','1',SCHED_MS-1),actual=None,forecast=Decimal('1')))
    assert recorder.record(scheduled.event_key).latency_ms is None


def test_malformed_actual_is_skipped_with_error_instead_of_silently_becoming_missing():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    n=recorder.ingest_observations([{'event_key':scheduled.event_key,'release':str(SCHED_MS),
        'observed':str(SCHED_MS+100),'source':'a','actual':'not-a-number'}])
    assert n==0 and len(recorder.skipped)==1


@pytest.mark.parametrize('phase',['schedule','observe'])
def test_actual_commit_lost_ack_reconciles_original_without_duplicate_publication(tmp_path,monkeypatch,phase):
    ledger=Ledger(tmp_path/'calendar.sqlite');recorder=CalendarRecorder(ledger=ledger)
    try:
        if phase=='observe':scheduled=_sched(recorder)
        atomic=ledger.atomic
        @contextmanager
        def commit_then_lose_ack():
            outer=not ledger._conn.in_transaction
            with atomic():yield ledger
            if outer:raise OSError('fixture ACK lost after actual SQL commit')
        with monkeypatch.context() as patch:
            patch.setattr(ledger,'atomic',commit_then_lose_ack)
            with pytest.raises(OSError,match='actual SQL commit'):
                if phase=='schedule':_sched(recorder)
                else:recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
        kind=EventKind.CALENDAR_SCHEDULE if phase=='schedule' else EventKind.CALENDAR_RELEASE
        original=next(ledger.iter(kind));head=ledger.head()
        if phase=='schedule':_sched(recorder)
        else:recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
        assert ledger.count(kind)==1 and ledger.head()==head
        assert next(ledger.iter(kind)).hash==original.hash and ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('phase',['schedule','observe'])
def test_missing_in_process_original_is_not_recreated_from_a_memory_success(tmp_path,phase):
    ledger=Ledger(tmp_path/'calendar.sqlite');recorder=CalendarRecorder(ledger=ledger)
    try:
        scheduled=_sched(recorder);observed=_obs(scheduled.event_key,'a','1',SCHED_MS+100)
        if phase=='observe':recorder.observe(observed)
        kind=EventKind.CALENDAR_SCHEDULE if phase=='schedule' else EventKind.CALENDAR_RELEASE
        ledger._conn.execute('DELETE FROM events WHERE kind=?',(kind.value,))
        with pytest.raises(ObservationConflict,match='missing'):
            if phase=='schedule':recorder.schedule(scheduled)
            else:recorder.observe(observed)
        assert ledger.count(kind)==0
    finally:ledger.close()


@pytest.mark.parametrize('target',['missing','old-branch','future-clock'])
def test_revision_must_bind_the_latest_prior_source_version(target):
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    first=recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
    second=recorder.observe(replace(first,actual=Decimal('2'),observed_ms=SCHED_MS+200,revision_of=first.observation_id))
    revised=replace(second,actual=Decimal('3'),observed_ms=SCHED_MS+300,revision_of=second.observation_id)
    if target=='missing':revised=replace(revised,revision_of='0'*32)
    elif target=='old-branch':revised=replace(revised,revision_of=first.observation_id)
    else:revised=replace(revised,observed_ms=SCHED_MS+199)
    with pytest.raises(ObservationConflict):recorder.observe(revised)
    assert recorder.record(scheduled.event_key).agreed_actual==Decimal('2')


def test_as_of_report_does_not_leak_future_observation_counts():
    recorder=CalendarRecorder();scheduled=_sched(recorder)
    recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+500))
    assert recorder.report(now_ms=SCHED_MS+100)['observations']==0
    body=recorder.record(scheduled.event_key).to_dict()
    assert body['provider_qualified'] is False and body['authority_effect']=='NONE'
    assert 'NOT_VERIFIED_PUBLISHER_INDEPENDENCE' in body['agreement_basis']


def test_cold_recovery_reads_original_sealed_records_without_another_publication(tmp_path):
    path=tmp_path/'calendar.sqlite';ledger=Ledger(path)
    recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
    for source in ('a','b'):recorder.observe(_obs(scheduled.event_key,source,'1',SCHED_MS+500))
    before=ledger.head();ledger.close();cold=Ledger(path)
    try:
        recovered=CalendarRecorder.from_ledger(cold)
        assert recovered.record(scheduled.event_key,now_ms=SCHED_MS+100).agreed_actual is None
        result=recovered.record(scheduled.event_key,now_ms=SCHED_MS+500)
        assert result.status is ReleaseStatus.VERIFIED and result.agreed_actual==Decimal('1')
        assert recovered.report()['recovered_from_ledger'] is True
        assert recovered.report()['legacy_envelope_availability_unqualified']==[]
        assert cold.count()==3 and cold.head()==before and cold.verify_chain()[0]
    finally:cold.close()


def test_legacy_envelope_clock_is_preserved_and_explicitly_unqualified_on_recovery(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
        observed=_obs(scheduled.event_key,'a','1',SCHED_MS+500)
        legacy=make_event(EventKind.CALENDAR_RELEASE,PRODUCER,{**observed.body(),'observation_id':observed.observation_id},
            event_time_ms=observed.released_ms,received_time_ms=observed.released_ms,correlation_id=observed.event_key)
        ledger.append(legacy);before=ledger.head()
        recovered=CalendarRecorder.from_ledger(ledger)
        assert recovered.report()['legacy_envelope_availability_unqualified']==[observed.observation_id]
        assert recovered.report(now_ms=SCHED_MS+100)['legacy_envelope_availability_unqualified']==[]
        assert recovered.record(scheduled.event_key,now_ms=SCHED_MS+100).agreed_actual is None
        assert next(ledger.iter(EventKind.CALENDAR_RELEASE)).received_time_ms==SCHED_MS
        recovered.observe(observed)
        assert ledger.count(EventKind.CALENDAR_RELEASE)==1 and ledger.head()==before
    finally:ledger.close()


def test_corrupted_journal_refuses_calendar_recovery_without_repairing_originals(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        recorder=CalendarRecorder(ledger=ledger);_sched(recorder)
        ledger._conn.execute("UPDATE events SET payload_json='{}'")
        with pytest.raises(ObservationConflict):CalendarRecorder.from_ledger(ledger)
        assert ledger.count()==1
    finally:ledger.close()


def test_recovery_capacity_refuses_a_partial_success_snapshot(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
        recorder.observe(_obs(scheduled.event_key,'a','1',SCHED_MS+100))
        with pytest.raises(ObservationConflict,match='capacity'):CalendarRecorder.from_ledger(ledger,max_events=1)
        assert ledger.count()==2 and ledger.verify_chain()[0]
    finally:ledger.close()


def ledger_factory(tmp_path,backend):
    if backend=='sqlite':return lambda:Ledger(tmp_path/'calendar-actors.sqlite')
    spec=os.environ.get('VATI_TEST_PG_DSN')
    if not spec or os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')!='1':
        pytest.skip('calendar PostgreSQL tests require explicitly isolated native fixture')
    from vati.core.ledger_pg import PostgresLedger
    name='calendar_'+uuid.uuid4().hex
    return lambda:PostgresLedger(spec,ledger_name=name)


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_concurrent_calendar_publishers_serialize_one_original_per_backend(tmp_path,backend):
    factory=ledger_factory(tmp_path,backend);initial=factory();initial.close()
    def publish(_):
        ledger=factory()
        try:
            recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
            original=recorder.observe(_obs(scheduled.event_key,'original-publisher','1',SCHED_MS+100))
            return original.observation_id
        finally:ledger.close()
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(publish,range(4)))
    cold=factory()
    try:
        assert len(set(ids))==1
        assert cold.count(EventKind.CALENDAR_SCHEDULE)==cold.count(EventKind.CALENDAR_RELEASE)==1
        recovered=CalendarRecorder.from_ledger(cold)
        assert recovered.records()[0].agreed_actual==Decimal('1') and cold.verify_chain()[0]
        assert recovered.records(now_ms=SCHED_MS+99)[0].agreed_actual is None
    finally:cold.close()


@pytest.mark.parametrize('backend',['sqlite','postgres'])
def test_actual_calendar_commit_reply_loss_is_recovered_from_original_backend(tmp_path,monkeypatch,backend):
    factory=ledger_factory(tmp_path,backend);ledger=factory()
    try:
        recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder)
        observed=_obs(scheduled.event_key,'original-publisher','1',SCHED_MS+100)
        atomic=ledger.atomic
        @contextmanager
        def commit_then_lose_reply():
            outer=ledger._atomic_depth==0 if backend=='postgres' else not ledger._conn.in_transaction
            with atomic():yield ledger
            if outer:raise OSError('fixture lost original committed calendar reply')
        with monkeypatch.context() as patch:
            patch.setattr(ledger,'atomic',commit_then_lose_reply)
            with pytest.raises(OSError,match='committed calendar reply'):recorder.observe(observed)
        head=ledger.head();recorder.observe(observed)
        assert ledger.count(EventKind.CALENDAR_RELEASE)==1 and ledger.head()==head
    finally:ledger.close()
    cold=factory()
    try:
        recovered=CalendarRecorder.from_ledger(cold)
        assert recovered.records()[0].agreed_actual==Decimal('1')
        event=next(cold.iter(EventKind.CALENDAR_RELEASE))
        assert event.received_time_ms==observed.observed_ms and cold.verify_chain()[0]
    finally:cold.close()


def test_sealed_but_malformed_legacy_record_returns_controlled_recovery_failure(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        payload={'event_key':'NFP:'+str(SCHED_MS),'name':'NFP','scheduled_ms':SCHED_MS,
                 'currencies':['USD'],'tier':1,'unit':''}  # required original forecast/previous keys absent
        event=make_event(EventKind.CALENDAR_SCHEDULE,PRODUCER,payload,event_time_ms=SCHED_MS,
            received_time_ms=SCHED_MS,correlation_id=payload['event_key'])
        ledger.append(event);head=ledger.head()
        with pytest.raises(ObservationConflict,match='format'):CalendarRecorder.from_ledger(ledger)
        assert ledger.head()==head and ledger.count()==1 and ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('cutoff',[True,-(2**63)-1,1.5,'1700000000000'])
def test_empty_calendar_cannot_accept_an_invalid_as_of_query(cutoff):
    with pytest.raises(ValueError):CalendarRecorder().records(now_ms=cutoff)


def test_cold_publisher_cannot_change_the_original_schedule_terms(tmp_path):
    ledger=Ledger(tmp_path/'calendar.sqlite')
    try:
        recorder=CalendarRecorder(ledger=ledger);scheduled=_sched(recorder);head=ledger.head()
        cold=CalendarRecorder(ledger=ledger)
        with pytest.raises(ObservationConflict):cold.schedule(replace(scheduled,forecast=Decimal('999')))
        assert cold.records()==[] and ledger.count()==1 and ledger.head()==head
    finally:ledger.close()


def test_unconfirmed_original_readback_cannot_advance_memory_success(tmp_path,monkeypatch):
    ledger=Ledger(tmp_path/'calendar.sqlite');recorder=CalendarRecorder(ledger=ledger)
    try:
        scheduled=_sched(recorder);observed=_obs(scheduled.event_key,'a','1',SCHED_MS+100);read=ledger.iter
        def unavailable_after_commit(kind=None,correlation_id=None):
            if kind is EventKind.CALENDAR_RELEASE and not ledger._conn.in_transaction:return iter(())
            return read(kind,correlation_id=correlation_id)
        with monkeypatch.context() as patch:
            patch.setattr(ledger,'iter',unavailable_after_commit)
            with pytest.raises(OSError,match='not confirmed'):recorder.observe(observed)
        assert recorder.record(scheduled.event_key).observations==()
        head=ledger.head();recorder.observe(observed)
        assert ledger.count(EventKind.CALENDAR_RELEASE)==1 and ledger.head()==head
        assert recorder.record(scheduled.event_key).agreed_actual==Decimal('1')
    finally:ledger.close()
