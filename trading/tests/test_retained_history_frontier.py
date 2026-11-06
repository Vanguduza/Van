import pytest
from contextlib import closing
from vati.core.ledger import LedgerError
from vati.funding.retained_history import MovementFrontier


def add(frontier, identity, value, ref):
    frontier.observe({'native_id': identity, 'delta': value}, ref, 1, 2)


def test_later_lower_ids_and_duplicates_retain_first_original():
    frontier = MovementFrontier(0, 2)
    for identity in (9, 7, 5, 3, 1, 5, 3, 1):
        add(frontier, identity, str(identity), 'first' if identity in (9, 7, 5, 3, 1) else 'later')
    page, more = frontier.page()
    assert [r['movement']['native_id'] for r in page] == [1, 3]
    assert more and all(r['original_statement_ref'] == 'first' for r in page)


def test_selected_contradiction_survives_many_later_candidates():
    frontier = MovementFrontier(0, 2)
    for identity in (10, 9, 8, 7, 6, 5, 4, 3, 2, 1):
        add(frontier, identity, str(identity), 'original')
    add(frontier, 2, 'changed', 'contradiction')
    for identity in range(11, 50):
        add(frontier, identity, str(identity), 'later')
    with pytest.raises(LedgerError, match='funding_original_history_conflict'):
        frontier.page()


def test_evicted_contradiction_does_not_claim_global_consistency():
    frontier = MovementFrontier(0, 1)
    add(frontier, 9, 'old', 'a'); add(frontier, 9, 'changed', 'b')
    add(frontier, 2, '2', 'c'); add(frontier, 1, '1', 'd')
    page, more = frontier.page()
    assert [r['movement']['native_id'] for r in page] == [1] and more


def test_verified_scan_budgets_rows_and_stops_at_fixed_original_anchor(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import VerifiedLedgerScan
    with closing(Ledger(tmp_path / 'scan.sqlite')) as ledger:
        for i in range(3):
            ledger.append(make_event(EventKind.SESSION, 'scan', {'statement': {'movements': list(range(i * 5, i * 5 + 5))}},
                event_time_ms=i, received_time_ms=i, correlation_id='scan'))
        anchor = ledger.read_page(0, 3)[-1]
        ledger.append(make_event(EventKind.SESSION, 'scan', {'statement': {'movements': [999]}},
            event_time_ms=4, received_time_ms=4, correlation_id='scan'))
        scan = VerifiedLedgerScan(anchor[0], anchor[3]); seen = []
        while not scan.finished:
            result = scan.advance(ledger, lambda event: True,
                lambda event, row: seen.append(row), event_budget=1, row_budget=2)
            assert result['events'] <= 1 and result['rows'] <= 2
        assert seen == list(range(15)) and scan.seq == anchor[0]


def test_verified_scan_rejects_wrong_anchor(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import VerifiedLedgerScan
    with closing(Ledger(tmp_path / 'scan.sqlite')) as ledger:
        ledger.append(make_event(EventKind.SESSION, 'scan', {'statement': {'movements': []}},
            event_time_ms=0, received_time_ms=0, correlation_id='scan'))
        scan = VerifiedLedgerScan(ledger.read_page(0, 1)[0][0], '0' * 64)
        with pytest.raises(LedgerError, match='retained_original_anchor_changed'):
            scan.advance(ledger, lambda event: True, lambda event, row: None, event_budget=1, row_budget=1)


def test_job_owner_capacity_expiry_shutdown_and_revocation():
    from vati.funding.retained_history import RetainedHistoryError, RetainedHistoryJobs
    now = [10]
    manager = RetainedHistoryJobs(clock=lambda: now[0], ttl_seconds=5)
    guard = lambda: None
    first = manager.start('a', ('anchor',), [], guard)
    manager.start('a', ('anchor',), [], guard)
    with pytest.raises(RetainedHistoryError, match='CAPACITY'):
        manager.start('a', ('anchor',), [], guard)
    with pytest.raises(RetainedHistoryError, match='OWNER_CHANGED'):
        manager.advance(first, 'b', ('anchor',), guard, lambda job: job.append(1))
    assert manager.advance(first, 'a', ('anchor',), guard, lambda job: len(job)) == 0
    calls = []
    def revoked_after():
        calls.append(1)
        if len(calls) == 2:
            raise PermissionError('revoked')
    with pytest.raises(PermissionError):
        manager.advance(first, 'a', ('anchor',), revoked_after, lambda job: job.append(2))
    with pytest.raises(RetainedHistoryError, match='RESTART_REQUIRED'):
        manager.advance(first, 'a', ('anchor',), guard, lambda job: job)
    now[0] += 6
    new = manager.start('a', ('anchor',), [], guard)
    manager.close()
    with pytest.raises(RetainedHistoryError, match='RESTART_REQUIRED'):
        manager.advance(new, 'a', ('anchor',), guard, lambda job: job)


def test_failed_row_callback_cannot_resume_and_replay(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import VerifiedLedgerScan
    with closing(Ledger(tmp_path / 'scan.sqlite')) as ledger:
        ledger.append(make_event(EventKind.SESSION, 'scan', {'statement': {'movements': [1]}},
            event_time_ms=0, received_time_ms=0, correlation_id='scan'))
        anchor = ledger.read_page(0, 1)[0]
        scan = VerifiedLedgerScan(anchor[0], anchor[3]); seen = []
        def partial_then_fail(event, row):
            seen.append(row)
            raise ValueError('failed after mutation')
        with pytest.raises(ValueError):
            scan.advance(ledger, lambda event: True, partial_then_fail, event_budget=1, row_budget=1)
        with pytest.raises(LedgerError, match='retained_scan_restart_required'):
            scan.advance(ledger, lambda event: True, lambda event, row: seen.append(row), event_budget=1, row_budget=1)
        assert seen == [1]


def test_job_copies_binding_and_state_and_shutdown_invalidates_active_step():
    import threading
    from vati.funding.retained_history import RetainedHistoryError, RetainedHistoryJobs
    manager = RetainedHistoryJobs(); binding = ['anchor']; original_job = []
    token = manager.start('owner', binding, original_job, lambda: None)
    binding.append('changed'); original_job.append('untrusted')
    with pytest.raises(RetainedHistoryError, match='OWNER_CHANGED'):
        manager.advance(token, 'owner', binding, lambda: None, lambda job: job)
    assert manager.advance(token, 'owner', ['anchor'], lambda: None, lambda job: job) == []
    entered = threading.Event(); release = threading.Event(); outcomes = []
    def slow(job):
        entered.set(); assert release.wait(2); return 'must not escape'
    def run():
        try: outcomes.append(manager.advance(token, 'owner', ['anchor'], lambda: None, slow))
        except RetainedHistoryError as error: outcomes.append(str(error))
    thread = threading.Thread(target=run); thread.start()
    assert entered.wait(2)
    shutdown=threading.Thread(target=manager.close);shutdown.start()
    with manager._condition:
        assert manager._condition.wait_for(lambda:manager._closed,timeout=2)
    release.set();thread.join(2);shutdown.join(2)
    assert not thread.is_alive() and not shutdown.is_alive() and outcomes == ['RETAINED_HISTORY_RESTART_REQUIRED']


def test_scan_charges_budget_even_when_rows_are_discarded(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import VerifiedLedgerScan
    with closing(Ledger(tmp_path / 'scan.sqlite')) as ledger:
        ledger.append(make_event(EventKind.SESSION, 'scan', {'statement': {'movements': list(range(7))}},
            event_time_ms=0, received_time_ms=0, correlation_id='scan'))
        anchor = ledger.read_page(0, 1)[0]
        scan = VerifiedLedgerScan(anchor[0], anchor[3]); selected = []
        first = scan.advance(ledger, lambda event: True,
            lambda event, row: selected.append(row) if row == 6 else None, event_budget=1, row_budget=2)
        assert first == {'events': 1, 'rows': 2, 'finished': False} and selected == []
        while not scan.finished:
            result = scan.advance(ledger, lambda event: True,
                lambda event, row: selected.append(row) if row == 6 else None, event_budget=1, row_budget=2)
            assert result['rows'] <= 2
        assert selected == [6]


def test_global_validation_scans_all_ids_across_multiple_batches(tmp_path):
    from dataclasses import replace
    from trading.tests.test_funding_journal import statement
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import GlobalMovementValidation
    with closing(Ledger(tmp_path / 'scan.sqlite')) as ledger:
        original = statement(); book = FundingBook(ledger, clock=lambda: 5000)
        for identities in ((8, 7, 6, 5), (4, 3, 2, 1)):
            book.record_statement(replace(original, movements=tuple(
                replace(original.movements[0], native_id=i) for i in identities)))
        anchor = ledger.read_page(0, 2)[-1]
        validation = GlobalMovementValidation(anchor[0], anchor[3], broker='CTRADER', scope_hash=original.scope_hash, batch_limit=2)
        calls = 0
        while not validation.finished:
            result = validation.advance(ledger, event_budget=1, row_budget=2)
            assert result['events'] <= 1 and result['rows'] <= 2
            calls += 1
            assert calls < 100
        assert calls > 10 and validation.after_native_id == 6


def test_global_validation_finds_contradiction_for_later_batch(tmp_path):
    from dataclasses import replace
    from decimal import Decimal
    from trading.tests.test_funding_journal import statement
    from vati.core.events import make_event
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import GlobalMovementValidation
    with closing(Ledger(tmp_path / 'scan.sqlite')) as ledger:
        original = statement(); book = FundingBook(ledger, clock=lambda: 5000)
        first = replace(original, movements=tuple(replace(original.movements[0], native_id=i) for i in (1, 2, 3)))
        book.record_statement(first)
        altered = replace(original, movements=(replace(original.movements[0], native_id=3, delta=Decimal('5')),))
        event = make_event(book.kind, book.producer, {'schema': book.schema, 'scope_hash': original.scope_hash,
            'content_key': book._key(altered), 'state': 'OBSERVED', 'statement': altered.body(),
            'conflicting_original_refs': {}, 'execution_authority': False},
            event_time_ms=altered.to_ms, received_time_ms=5000, correlation_id=book.correlation_prefix + original.scope_hash)
        ledger.append(event)
        anchor = ledger.read_page(0, 2)[-1]
        validation = GlobalMovementValidation(anchor[0], anchor[3], broker='CTRADER', scope_hash=original.scope_hash, batch_limit=1)
        with pytest.raises(LedgerError, match='funding_original_history_conflict'):
            for _ in range(30):
                validation.advance(ledger, event_budget=1, row_budget=2)
        assert not validation.finished and validation.failed


def test_mt5_global_validation_uses_original_native_owner(tmp_path):
    from dataclasses import replace
    from trading.tests.test_mt5_funding_contract import frame, cash
    from vati.core.ledger import Ledger
    from vati.funding.mt5 import Mt5CashFact
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import GlobalMovementValidation
    with closing(Ledger(tmp_path / 'mt5.sqlite')) as ledger:
        original = replace(frame(), movements=tuple(Mt5CashFact.from_body(cash(native_id=i)) for i in (3, 2, 1)))
        Mt5FundingBook(ledger, clock=lambda: 11000).record_statement(original)
        anchor = ledger.read_page(0, 1)[0]
        validation = GlobalMovementValidation(anchor[0], anchor[3], broker='MT5', scope_hash=original.scope_hash, batch_limit=1)
        for _ in range(20):
            result = validation.advance(ledger, event_budget=1, row_budget=1)
            assert result['events'] <= 1 and result['rows'] <= 1
            if validation.finished: break
        assert validation.finished and validation.after_native_id == 2


def test_original_boundary_discovery_is_budgeted_and_fixed_before_later_activity(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import OriginalBoundaryScan
    with closing(Ledger(tmp_path / 'boundary.sqlite')) as ledger:
        for n in range(4):
            ledger.append(make_event(EventKind.SESSION, 'scan', {'n': n}, event_time_ms=n, received_time_ms=n))
        boundary = make_event(EventKind.ACCOUNT_OPERATION, 'fixture', {'phase': 'IN_FLIGHT', 'previous_ref': ''},
            event_time_ms=4, received_time_ms=4, correlation_id='original_operation')
        ledger.append(boundary)
        anchor = ledger.read_page(0, 5)[-1]
        ledger.append(make_event(EventKind.SESSION, 'scan', {'n': 99}, event_time_ms=5, received_time_ms=5))
        scan = OriginalBoundaryScan('original_operation', boundary.hash)
        calls = 0
        while not scan.finished:
            result = scan.advance(ledger, event_budget=2); calls += 1
            assert result['events'] <= 2
        assert calls == 3 and (scan.seq, scan.chain) == (anchor[0], anchor[3])


def test_original_boundary_rejects_foreign_operation(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import OriginalBoundaryScan
    with closing(Ledger(tmp_path / 'boundary.sqlite')) as ledger:
        event = make_event(EventKind.ACCOUNT_OPERATION, 'fixture', {'phase': 'IN_FLIGHT', 'previous_ref': ''},
            event_time_ms=1, received_time_ms=1, correlation_id='foreign')
        ledger.append(event); scan = OriginalBoundaryScan('original_operation', event.hash)
        with pytest.raises(LedgerError, match='retained_original_boundary_invalid'):
            scan.advance(ledger, event_budget=1)
        assert scan.failed and not scan.finished


def test_trusted_job_resumes_with_fresh_ledger_per_advance(tmp_path):
    from dataclasses import replace
    from trading.tests.test_funding_journal import statement
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import GlobalMovementValidation, RetainedHistoryJobs
    path = tmp_path / 'reopened.sqlite'; original = statement()
    with closing(Ledger(path)) as ledger:
        frame = replace(original, movements=tuple(replace(original.movements[0], native_id=i) for i in (4, 3, 2, 1)))
        FundingBook(ledger, clock=lambda: 5000).record_statement(frame)
        anchor = ledger.read_page(0, 1)[0]
    manager = RetainedHistoryJobs(); binding = ('original', original.scope_hash, anchor[0], anchor[3])
    token = manager.start('original-device', binding,
        GlobalMovementValidation(anchor[0], anchor[3], broker='CTRADER', scope_hash=original.scope_hash, batch_limit=1), lambda: None)
    for calls in range(30):
        with closing(Ledger(path)) as current:
            result = manager.advance(token, 'original-device', binding, lambda: None,
                lambda job: job.advance(current, event_budget=1, row_budget=1))
        if result['finished']: break
    assert result['finished'] and calls > 4
    manager.close()


def test_original_reference_requires_complete_anchored_chain_and_preserves_ordinal(tmp_path):
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import OriginalReferenceScan
    with closing(Ledger(tmp_path / 'references.sqlite')) as ledger:
        events = [make_event(EventKind.SESSION, 'fixture', {'n': n}, event_time_ms=n, received_time_ms=n) for n in range(4)]
        for event in events: ledger.append(event)
        rows = ledger.read_page(0, 4); scan = OriginalReferenceScan(rows[-1][0], rows[-1][3], events[1].hash)
        scan.advance(ledger, event_budget=2)
        with pytest.raises(LedgerError, match='retained_original_reference_unproven'):
            scan.result()
        while not scan.finished:
            assert scan.advance(ledger, event_budget=1)['events'] <= 1
        assert scan.result() == (rows[1][0], events[1], rows[1][3])
        absent = OriginalReferenceScan(rows[-1][0], rows[-1][3], '0' * 64)
        while not absent.finished: absent.advance(ledger, event_budget=2)
        assert absent.result() is None


def test_original_snapshot_discovery_proves_actual_native_statement_and_cutoff(tmp_path):
    from trading.tests.test_retained_funding_history import original
    from vati.funding.retained_history import OriginalSnapshotDiscovery
    ledger, raw, snapshot, args = original(tmp_path, count=3)
    try:
        anchor = ledger.read_page(0, 256)[-1]
        scan = OriginalSnapshotDiscovery(anchor[0], anchor[3], args['lifecycle']['alias'], args['profile'])
        calls = 0
        while not scan.finished:
            result = scan.advance(ledger, event_budget=1)
            assert result['events'] <= 1
            calls += 1; assert calls < 30
        value = scan.result()
        assert value['snapshot_ref'] == snapshot.hash and value['scope_hash'] == raw.scope_hash
        assert value['statement_ref'] == snapshot.payload['funding_observation']['statement']['statement_ref']
        assert value['query_ref'] is None and calls > 3
        statement = ledger.event_at(value['statement_seq'])
        assert statement[1].hash == value['statement_ref'] and statement[3] == value['statement_chain']
    finally:
        ledger.close()


def test_original_mt5_snapshot_requires_exact_original_query_and_statement(tmp_path):
    from dataclasses import replace
    from trading.tests.test_mt5_funding_contract import frame, cash
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5 import Mt5CashFact
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import OriginalSnapshotDiscovery
    with closing(Ledger(tmp_path / 'mt5-snapshot.sqlite')) as ledger:
        original = replace(frame(), movements=(Mt5CashFact.from_body(cash()),))
        query, receipt = Mt5FundingBook(ledger, clock=lambda: 11000).capture(original)
        snapshot = make_event(EventKind.ACCOUNT_SNAPSHOT, 'vati-service', {'account_alias':'native',
            'native_account_mark':original.mark_body(),'funding_observation':{'query_ref':query,
            'statement':receipt,'scope_hash':original.scope_hash}}, event_time_ms=11000, received_time_ms=11000)
        ledger.append(snapshot)
        boundary = make_event(EventKind.SESSION,'fixture',{'boundary':True},event_time_ms=1,received_time_ms=1)
        ledger.append(boundary); anchor = ledger.read_page(0,256)[-1]
        profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        scan = OriginalSnapshotDiscovery(anchor[0],anchor[3],'native',profile)
        for _ in range(40):
            result=scan.advance(ledger,event_budget=2)
            assert result['events']<=2
            if scan.finished: break
        assert scan.finished and scan.result()['query_ref']==query and scan.result()['statement_ref']==receipt['statement_ref']


def test_original_movement_pages_exclude_later_activity_and_use_keyset(tmp_path):
    from dataclasses import replace
    from trading.tests.test_funding_journal import statement
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import OriginalMovementPage
    with closing(Ledger(tmp_path / 'page.sqlite')) as ledger:
        original=statement();book=FundingBook(ledger,clock=lambda:5000)
        frame=replace(original,movements=tuple(replace(original.movements[0],native_id=i) for i in (5,4,3,2,1)))
        book.record_statement(frame);anchor=ledger.read_page(0,1)[0]
        later=replace(original,movements=(replace(original.movements[0],native_id=99),),observed_at_ms=6000)
        FundingBook(ledger,clock=lambda:6000).record_statement(later)
        pages=[];after=0
        while True:
            job=OriginalMovementPage(anchor[0],anchor[3],broker='CTRADER',scope_hash=original.scope_hash,after_native_id=after,limit=2)
            while not job.finished:
                step=job.advance(ledger,event_budget=1,row_budget=2)
                assert step['events']<=1 and step['rows']<=2
            rows,more=job.result();pages.extend(r['movement']['native_id'] for r in rows)
            if not more:break
            after=rows[-1]['movement']['native_id']
        assert pages==[1,2,3,4,5] and 99 not in pages


def test_original_coverage_and_conflicts_reachable_in_bounded_pages(tmp_path):
    from dataclasses import replace
    from decimal import Decimal
    from trading.tests.test_funding_journal import statement
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import OriginalMetadataPage
    with closing(Ledger(tmp_path / 'metadata.sqlite')) as ledger:
        original=statement();book=FundingBook(ledger,clock=lambda:5000)
        first=replace(original,movements=tuple(replace(original.movements[0],native_id=i) for i in (1,2,3,4)))
        original_receipt=book.record_statement(first)
        changed=replace(first,movements=tuple(replace(row,delta=Decimal('5')) for row in first.movements))
        conflict_receipt=book.record_statement(changed)
        assert conflict_receipt['state']=='CONFLICT'
        anchor=ledger.read_page(0,2)[-1]
        all_rows={}
        for collection in ('COVERAGE','CONFLICT'):
            after=(0,0);output=[]
            while True:
                job=OriginalMetadataPage(anchor[0],anchor[3],broker='CTRADER',scope_hash=original.scope_hash,
                    collection=collection,after=after,limit=2)
                while not job.finished:
                    progress=job.advance(ledger,event_budget=1,row_budget=1)
                    assert progress['events']<=1 and progress['rows']<=1
                page,more,after=job.result();output.extend(page)
                if not more:break
            all_rows[collection]=output
        assert len(all_rows['COVERAGE'])==1 and all_rows['COVERAGE'][0]['statement_ref']==original_receipt['statement_ref']
        conflicts=all_rows['CONFLICT']; references=[r for r in conflicts if r['kind']=='CONFLICT_REFERENCE']
        assert [r['statement_ref'] for r in conflicts if r['kind']=='CONFLICT_EVENT']==[conflict_receipt['statement_ref']]
        assert {row['native_id'] for row in references}=={'1','2','3','4'}
        assert all(row['original_ref']==original_receipt['statement_ref'] and row['statement_ref']==conflict_receipt['statement_ref']
            for row in references)
        quarantined=[r for r in conflicts if r['kind']=='CONFLICT_MOVEMENT']
        assert {r['movement']['native_id'] for r in quarantined}=={1,2,3,4}
        assert all(r['lineage']=='QUARANTINED_NOT_OBSERVED' and r['execution_authority'] is False for r in quarantined)


def test_conflict_event_with_no_reference_entries_is_still_reachable(tmp_path):
    from trading.tests.test_funding_journal import statement
    from vati.core.events import make_event
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import OriginalMetadataPage
    with closing(Ledger(tmp_path / 'empty-conflict.sqlite')) as ledger:
        source=statement();book=FundingBook(ledger,clock=lambda:5000)
        event=make_event(book.kind,book.producer,{'schema':book.schema,'scope_hash':source.scope_hash,
            'content_key':book._key(source),'state':'CONFLICT','statement':source.body(),
            'conflicting_original_refs':{},'execution_authority':False},event_time_ms=source.to_ms,
            received_time_ms=5000,correlation_id=book.correlation_prefix+source.scope_hash)
        ledger.append(event);anchor=ledger.read_page(0,1)[0]
        job=OriginalMetadataPage(anchor[0],anchor[3],broker='CTRADER',scope_hash=source.scope_hash,
            collection='CONFLICT',after=(0,0),limit=1)
        while not job.finished:job.advance(ledger,event_budget=1,row_budget=1)
        rows,more,_=job.result()
        assert rows[0]['kind']=='CONFLICT_EVENT' and rows[0]['statement_ref']==event.hash and more


def test_retained_read_job_advances_all_collections_under_original_boundary(tmp_path):
    from dataclasses import replace
    from decimal import Decimal
    from trading.tests.test_retained_funding_history import original
    from trading.tests.test_native_balance_reconciliation import mark
    from trading.tests.test_funding_owner_reports import snapshot
    from vati.core.events import EventKind, make_event
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    ledger, raw, _, args=original(tmp_path,count=4); path=tmp_path/'original.sqlite'
    changed=replace(raw,movements=tuple(replace(row,delta=Decimal('5')) for row in raw.movements))
    receipt=FundingBook(ledger,clock=lambda:5000).record_statement(changed)
    assert receipt['state']=='CONFLICT'
    snapshot(ledger,funding_observation={'state':'CONFLICT','scope_hash':raw.scope_hash,'native_mark':mark(3000).body(),'statement':receipt})
    boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},
        event_time_ms=1,received_time_ms=1,correlation_id=args['lifecycle']['operation_id'])
    ledger.append(boundary)
    later=replace(raw,movements=(replace(raw.movements[0],native_id=999),),observed_at_ms=6000)
    FundingBook(ledger,clock=lambda:6000).record_statement(later);ledger.close()
    results={}
    for collection,after in [('MOVEMENTS',0),('COVERAGE',(0,0)),('CONFLICT',(0,0))]:
        rows=[]
        while True:
            job=RetainedHistoryReadJob(operation_id=args['lifecycle']['operation_id'],cutoff_ref=boundary.hash,
                alias=args['lifecycle']['alias'],profile=args['profile'],collection=collection,after=after,limit=2)
            for _ in range(500):
                with closing(Ledger(path)) as current:
                    step=job.advance(current,event_budget=2,row_budget=2)
                    assert step['events']<=2 and step['rows']<=2
                if job.finished:break
            assert job.finished
            page=job.result();assert page['state']=='CONFLICT' and page['movement_count'] is None
            rows.extend(page['rows']);after=page['bookmark']
            if not page['more']:break
        results[collection]=rows
    assert [r['movement']['native_id'] for r in results['MOVEMENTS']]==[1,2,3,4]
    assert len(results['COVERAGE'])==1
    assert len([r for r in results['CONFLICT'] if r['kind']=='CONFLICT_REFERENCE'])==4
    assert len([r for r in results['CONFLICT'] if r['kind']=='CONFLICT_EVENT'])==1
    assert len([r for r in results['CONFLICT'] if r['kind']=='CONFLICT_MOVEMENT'])==4


def test_funding_scope_rejects_wrong_kind_before_original_anchor(tmp_path):
    from trading.tests.test_funding_journal import statement
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import GlobalMovementValidation
    with closing(Ledger(tmp_path/'foreign-kind.sqlite')) as ledger:
        source=statement();book=FundingBook(ledger,clock=lambda:5000);receipt=book.record_statement(source)
        foreign=make_event(EventKind.SESSION,'fixture',{'wrong':True},event_time_ms=5001,received_time_ms=5001,
            correlation_id=book.correlation_prefix+source.scope_hash)
        ledger.append(foreign);anchor=ledger.read_page(0,2)[-1]
        with pytest.raises(LedgerError):book.observations(source.scope_hash,as_of=foreign.hash)
        job=GlobalMovementValidation(anchor[0],anchor[3],broker='CTRADER',scope_hash=source.scope_hash)
        with pytest.raises(LedgerError,match='funding_observation_journal_invalid'):
            while not job.finished:job.advance(ledger,event_budget=1,row_budget=1)
        assert job.failed and not job.finished


def test_original_reference_replay_keeps_first_publication(tmp_path):
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.retained_history import OriginalReferenceScan
    with closing(Ledger(tmp_path/'replay.sqlite')) as ledger:
        event=make_event(EventKind.SESSION,'fixture',{'same':True},event_time_ms=1,received_time_ms=1)
        ledger.append(event);ledger.append(event);rows=ledger.read_page(0,2)
        scan=OriginalReferenceScan(rows[-1][0],rows[-1][3],event.hash)
        while not scan.finished:scan.advance(ledger,event_budget=1)
        assert scan.result()==(rows[0][0],event,rows[0][3])


def test_expired_inflight_jobs_stay_counted_and_shutdown_drains():
    import threading
    from vati.funding.retained_history import RetainedHistoryError,RetainedHistoryJobs
    now=[0];manager=RetainedHistoryJobs(clock=lambda:now[0],ttl_seconds=5);guard=lambda:None
    first=manager.start('device','binding',[],guard);manager.start('device','binding',[],guard)
    entered=threading.Event();release=threading.Event();closed=threading.Event();outcomes=[]
    def step(job):entered.set();assert release.wait(2);return 'private'
    def run():
        try:outcomes.append(manager.advance(first,'device','binding',guard,step))
        except RetainedHistoryError as error:outcomes.append(str(error))
    worker=threading.Thread(target=run);worker.start();assert entered.wait(2)
    now[0]=6
    manager.start('device','binding',[],guard)
    with pytest.raises(RetainedHistoryError,match='CAPACITY'):manager.start('device','binding',[],guard)
    def shutdown():manager.close();closed.set()
    stopper=threading.Thread(target=shutdown);stopper.start()
    with manager._condition:assert manager._condition.wait_for(lambda:manager._closed,timeout=2)
    assert not closed.is_set()
    release.set();worker.join(2);stopper.join(2)
    assert closed.is_set() and not worker.is_alive() and outcomes==['RETAINED_HISTORY_RESTART_REQUIRED']


def test_snapshot_rejects_statement_from_foreign_correlation(tmp_path):
    from trading.tests.test_funding_journal import statement
    from trading.tests.test_native_balance_reconciliation import mark
    from trading.tests.test_funding_owner_reports import snapshot,profile
    from vati.core.events import make_event,EventKind
    from vati.core.ledger import Ledger
    from vati.funding.journal import FundingBook
    from vati.funding.retained_history import OriginalSnapshotDiscovery
    with closing(Ledger(tmp_path/'foreign-statement.sqlite')) as ledger:
        source=statement();book=FundingBook(ledger,clock=lambda:5000);book.record_statement(source)
        real=ledger.read_page(0,1)[0][1]
        foreign=make_event(real.kind,real.producer,real.payload,event_time_ms=real.event_time_ms,
            received_time_ms=real.received_time_ms,correlation_id='other-scope')
        ledger.append(foreign)
        snapshot(ledger,funding_observation={'scope_hash':source.scope_hash,'native_mark':mark(3000).body(),
            'statement':{'statement_ref':foreign.hash}})
        ledger.append(make_event(EventKind.SESSION,'fixture',{'boundary':True},event_time_ms=1,received_time_ms=1))
        anchor=ledger.read_page(0,256)[-1];job=OriginalSnapshotDiscovery(anchor[0],anchor[3],'ctrader_primary',profile(server=''))
        with pytest.raises(LedgerError,match='retained_original_statement_unavailable'):
            while not job.finished:job.advance(ledger,event_budget=2)


def test_mt5_snapshot_rejects_malformed_earlier_same_scope_query(tmp_path):
    from copy import deepcopy
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import OriginalSnapshotDiscovery
    with closing(Ledger(tmp_path/'mt5-query.sqlite')) as ledger:
        original=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(original)
        query_event=next(e for _,e,_,_ in ledger.read_page(0,2) if e.hash==query)
        bad=deepcopy(query_event.payload);bad['source_ref']='0'*64
        ledger.append(make_event(query_event.kind,query_event.producer,bad,event_time_ms=query_event.event_time_ms,
            received_time_ms=query_event.received_time_ms,correlation_id=query_event.correlation_id))
        snap=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','native_account_mark':original.mark_body(),
            'funding_observation':{'scope_hash':original.scope_hash,'query_ref':query,'statement':receipt}},
            event_time_ms=11000,received_time_ms=11000);ledger.append(snap)
        ledger.append(make_event(EventKind.SESSION,'fixture',{'boundary':True},event_time_ms=1,received_time_ms=1))
        anchor=ledger.read_page(0,256)[-1];profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=OriginalSnapshotDiscovery(anchor[0],anchor[3],'native',profile)
        with pytest.raises(LedgerError,match='mt5_native_query_source_invalid'):
            for _ in range(100):
                job.advance(ledger,event_budget=2)
                if job.finished:break
        assert job.failed and not job.finished


def test_mt5_snapshot_rejects_query_from_foreign_correlation(tmp_path):
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import OriginalSnapshotDiscovery
    with closing(Ledger(tmp_path/'mt5-foreign.sqlite')) as ledger:
        original=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(original)
        q=next(e for _,e,_,_ in ledger.read_page(0,2) if e.hash==query)
        foreign=make_event(q.kind,q.producer,q.payload,event_time_ms=q.event_time_ms,received_time_ms=q.received_time_ms,correlation_id='foreign-query')
        ledger.append(foreign)
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','native_account_mark':original.mark_body(),
            'funding_observation':{'scope_hash':original.scope_hash,'query_ref':foreign.hash,'statement':receipt}},event_time_ms=11000,received_time_ms=11000))
        ledger.append(make_event(EventKind.SESSION,'fixture',{'boundary':True},event_time_ms=1,received_time_ms=1))
        anchor=ledger.read_page(0,256)[-1];profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=OriginalSnapshotDiscovery(anchor[0],anchor[3],'native',profile)
        with pytest.raises(LedgerError,match='retained_original_query_unavailable'):
            for _ in range(100):
                job.advance(ledger,event_budget=2)
                if job.finished:break
        assert job.failed and not job.finished


def test_later_missing_lineage_returns_only_verified_prefix_with_reconciliation(tmp_path):
    from trading.tests.test_retained_funding_history import original
    from trading.tests.test_native_balance_reconciliation import mark
    from trading.tests.test_funding_owner_reports import snapshot
    from vati.core.events import EventKind,make_event
    from vati.funding.retained_history import RetainedHistoryReadJob
    ledger,raw,first,args=original(tmp_path,count=3)
    try:
        snapshot(ledger,funding_observation={'state':'OBSERVED','scope_hash':raw.scope_hash,
            'native_mark':mark(3000).body(),'statement':{'statement_ref':'f'*64}})
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},
            event_time_ms=1,received_time_ms=1,correlation_id=args['lifecycle']['operation_id']);ledger.append(boundary)
        job=RetainedHistoryReadJob(operation_id=args['lifecycle']['operation_id'],cutoff_ref=boundary.hash,
            alias=args['lifecycle']['alias'],profile=args['profile'],collection='MOVEMENTS',after=0,limit=10)
        for _ in range(100):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result()
        assert result['state']=='RECONCILIATION_REQUIRED' and result['reason']=='ORIGINAL_LATER_LINEAGE_UNAVAILABLE'
        assert result['original_prefix_state']=='OBSERVED' and result['movement_count'] is None
        assert result['source']['snapshot_ref']==first.hash
        assert [row['movement']['native_id'] for row in result['rows']]==[1,2,3]
    finally:ledger.close()


def test_mt5_snapshot_validates_all_same_scope_original_prefix_statements(tmp_path):
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import OriginalSnapshotDiscovery
    with closing(Ledger(tmp_path/'mt5-original-prefix.sqlite')) as ledger:
        original=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(original)
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','native_account_mark':original.mark_body(),
            'funding_observation':{'scope_hash':original.scope_hash,'query_ref':query,'statement':receipt}},event_time_ms=11000,received_time_ms=11000))
        ledger.append(make_event(EventKind.SESSION,'fixture',{'wrong':True},event_time_ms=11001,received_time_ms=11001,
            correlation_id='funding-mt5:'+original.scope_hash))
        ledger.append(make_event(EventKind.SESSION,'fixture',{'boundary':True},event_time_ms=1,received_time_ms=1))
        anchor=ledger.read_page(0,256)[-1];profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=OriginalSnapshotDiscovery(anchor[0],anchor[3],'native',profile)
        with pytest.raises(LedgerError,match='funding_observation_journal_invalid'):
            for _ in range(100):
                job.advance(ledger,event_budget=2)
                if job.finished:break
        assert job.failed and not job.finished


def test_later_unattributed_snapshot_preserves_known_prefix_with_reconciliation(tmp_path):
    from trading.tests.test_retained_funding_history import original
    from vati.core.events import EventKind,make_event
    from vati.funding.retained_history import RetainedHistoryReadJob
    ledger,raw,first,args=original(tmp_path,count=3)
    try:
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':args['lifecycle']['alias'],
            'funding_observation':{'scope_hash':raw.scope_hash,'statement':{'statement_ref':'f'*64}}},event_time_ms=4000,received_time_ms=4000))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,
            correlation_id=args['lifecycle']['operation_id']);ledger.append(boundary)
        job=RetainedHistoryReadJob(operation_id=args['lifecycle']['operation_id'],cutoff_ref=boundary.hash,
            alias=args['lifecycle']['alias'],profile=args['profile'],collection='MOVEMENTS',after=0,limit=10)
        for _ in range(100):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result()
        assert result['state']=='RECONCILIATION_REQUIRED' and result['source']['snapshot_ref']==first.hash
        assert result['original_prefix_state']=='OBSERVED' and [r['movement']['native_id'] for r in result['rows']]==[1,2,3]
    finally:ledger.close()


def test_later_mt5_query_missing_statement_preserves_known_prefix(tmp_path):
    from copy import deepcopy
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    with closing(Ledger(tmp_path/'later-missing-query.sqlite')) as ledger:
        source=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(source)
        snap=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','native_account_mark':source.mark_body(),
            'funding_observation':{'scope_hash':source.scope_hash,'query_ref':query,'statement':receipt}},event_time_ms=11000,received_time_ms=11000)
        ledger.append(snap)
        q=next(e for _,e,_,_ in ledger.read_page(0,2) if e.hash==query)
        bad=deepcopy(q.payload);bad['cash_statement_ref']='f'*64
        ledger.append(make_event(q.kind,q.producer,bad,event_time_ms=q.event_time_ms,received_time_ms=q.received_time_ms,correlation_id=q.correlation_id))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id='original_operation')
        ledger.append(boundary);profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=RetainedHistoryReadJob(operation_id='original_operation',cutoff_ref=boundary.hash,alias='native',profile=profile,
            collection='MOVEMENTS',after=0,limit=10)
        actual=[0];original_read=ledger.read_page
        def counted(*args,**kwargs):
            rows=original_read(*args,**kwargs);actual[0]+=len(rows);return rows
        ledger.read_page=counted
        for _ in range(150):
            before=actual[0];step=job.advance(ledger,event_budget=2,row_budget=2)
            assert actual[0]-before==step['events']<=2
            if job.finished:break
        result=job.result()
        assert result['state']=='RECONCILIATION_REQUIRED' and result['reason']=='ORIGINAL_LATER_LINEAGE_UNAVAILABLE'
        assert result['source']['snapshot_ref']==snap.hash and result['original_prefix_state']=='OBSERVED'


@pytest.mark.parametrize('fault',['missing_then_new_snapshot','statement_published_after_query'])
def test_later_mt5_query_lineage_gap_never_promotes_newer_snapshot(tmp_path,fault):
    from copy import deepcopy
    from dataclasses import replace
    from trading.tests.test_mt5_funding_contract import frame,cash
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5 import Mt5CashFact
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    with closing(Ledger(tmp_path/'later-gap.sqlite')) as ledger:
        source=frame();book=Mt5FundingBook(ledger,clock=lambda:11000);query,receipt=book.capture(source)
        payload={'account_alias':'native','native_account_mark':source.mark_body(),
            'funding_observation':{'scope_hash':source.scope_hash,'query_ref':query,'statement':receipt}}
        first=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11000,received_time_ms=11000);ledger.append(first)
        q=next(e for _,e,_,_ in ledger.read_page(0,2) if e.hash==query);bad=deepcopy(q.payload)
        late=None
        if fault=='statement_published_after_query':
            altered=replace(source,movements=(Mt5CashFact.from_body(cash(native_id=7)),))
            late=make_event(book.kind,book.producer,{'schema':book.schema,'scope_hash':source.scope_hash,'content_key':book._key(altered),
                'state':'OBSERVED','statement':altered.body(),'conflicting_original_refs':{},'execution_authority':False},
                event_time_ms=altered.to_ms,received_time_ms=11000,correlation_id=book.correlation_prefix+source.scope_hash)
            bad['cash_statement_ref']=late.hash
        else:bad['cash_statement_ref']='f'*64
        ledger.append(make_event(q.kind,q.producer,bad,event_time_ms=q.event_time_ms,received_time_ms=q.received_time_ms,correlation_id=q.correlation_id))
        if late is not None:ledger.append(late)
        else:ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11001,received_time_ms=11001))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id='original_operation');ledger.append(boundary)
        profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=RetainedHistoryReadJob(operation_id='original_operation',cutoff_ref=boundary.hash,alias='native',profile=profile,collection='MOVEMENTS',after=0,limit=10)
        for _ in range(200):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result()
        assert result['state']=='RECONCILIATION_REQUIRED' and result['source']['snapshot_ref']==first.hash
        assert result['reason']=='ORIGINAL_LATER_LINEAGE_UNAVAILABLE' and result['movement_count'] is None


def test_mt5_lineage_gap_before_any_valid_snapshot_stays_unobserved(tmp_path):
    from copy import deepcopy
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    with closing(Ledger(tmp_path/'no-prefix.sqlite')) as ledger:
        source=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(source)
        q=next(e for _,e,_,_ in ledger.read_page(0,2) if e.hash==query);bad=deepcopy(q.payload);bad['cash_statement_ref']='f'*64
        ledger.append(make_event(q.kind,q.producer,bad,event_time_ms=q.event_time_ms,received_time_ms=q.received_time_ms,correlation_id=q.correlation_id))
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','native_account_mark':source.mark_body(),
            'funding_observation':{'scope_hash':source.scope_hash,'query_ref':query,'statement':receipt}},event_time_ms=11000,received_time_ms=11000))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id='original_operation');ledger.append(boundary)
        profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=RetainedHistoryReadJob(operation_id='original_operation',cutoff_ref=boundary.hash,alias='native',profile=profile,collection='MOVEMENTS',after=0,limit=10)
        for _ in range(200):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        assert job.result()=={'state':'UNOBSERVED','reason':'ORIGINAL_LINEAGE_REQUIRES_RECONCILIATION'}


@pytest.mark.parametrize('fault',['malformed_observation','malformed_ctrader_mark','malformed_statement','missing_statement'])
def test_unattributable_ctrader_snapshot_blocks_promotion_of_later_snapshot(tmp_path,fault):
    from trading.tests.test_retained_funding_history import original
    from vati.core.events import EventKind,make_event
    from vati.funding.retained_history import RetainedHistoryReadJob
    ledger,raw,first,args=original(tmp_path,count=3)
    try:
        payload={'account_alias':args['lifecycle']['alias'],'funding_observation':'malformed'}
        if fault=='malformed_ctrader_mark':
            payload['funding_observation']={'scope_hash':raw.scope_hash,'statement':{'statement_ref':'f'*64}}
            payload['native_account_mark']={'schema':'native-account-mark/1'}
        if fault in {'malformed_statement','missing_statement'}:
            payload=dict(first.payload);payload['funding_observation']=dict(first.payload['funding_observation'])
            if fault=='malformed_statement':payload['funding_observation']['statement']='malformed'
            else:del payload['funding_observation']['statement']
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=4000,received_time_ms=4000))
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',first.payload,event_time_ms=4001,received_time_ms=4001))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id=args['lifecycle']['operation_id']);ledger.append(boundary)
        job=RetainedHistoryReadJob(operation_id=args['lifecycle']['operation_id'],cutoff_ref=boundary.hash,alias=args['lifecycle']['alias'],profile=args['profile'],collection='MOVEMENTS',after=0,limit=10)
        for _ in range(150):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result()
        assert result['state']=='RECONCILIATION_REQUIRED' and result['source']['snapshot_ref']==first.hash
        assert result['original_prefix_state']=='OBSERVED' and result['movement_count'] is None
    finally:ledger.close()


def test_incomplete_mt5_identity_is_unattributable_not_foreign(tmp_path):
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    with closing(Ledger(tmp_path/'missing-mt5-identity.sqlite')) as ledger:
        source=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(source)
        payload={'account_alias':'native','native_account_mark':source.mark_body(),'funding_observation':{'scope_hash':source.scope_hash,'query_ref':query,'statement':receipt}}
        first=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11000,received_time_ms=11000);ledger.append(first)
        bad=dict(payload);bad['native_account_mark']=dict(source.mark_body());del bad['native_account_mark']['login']
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',bad,event_time_ms=11001,received_time_ms=11001))
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11002,received_time_ms=11002))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id='original_operation');ledger.append(boundary)
        profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=RetainedHistoryReadJob(operation_id='original_operation',cutoff_ref=boundary.hash,alias='native',profile=profile,collection='MOVEMENTS',after=0,limit=10)
        for _ in range(200):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result();assert result['state']=='RECONCILIATION_REQUIRED' and result['source']['snapshot_ref']==first.hash
        assert result['original_prefix_state']=='OBSERVED' and result['movement_count'] is None


def test_foreign_looking_incomplete_mark_does_not_hide_lineage_gap(tmp_path):
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.canonical import canonical_hash
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    with closing(Ledger(tmp_path/'foreign-incomplete.sqlite')) as ledger:
        source=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(source)
        payload={'account_alias':'native','native_account_mark':source.mark_body(),'funding_observation':{'scope_hash':source.scope_hash,'query_ref':query,'statement':receipt}}
        first=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11000,received_time_ms=11000);ledger.append(first)
        foreign={'schema':'mt5-account-mark/1','account_alias':'native','login':999,'server':'Broker-Demo','currency':'USD','demo':True}
        foreign['scope_hash']=canonical_hash({'provider':'MT5','login':999,'server':'Broker-Demo','currency':'USD','demo':True})
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'native','native_account_mark':foreign,
            'funding_observation':{'scope_hash':foreign['scope_hash'],'query_ref':'f'*64,'statement':{'statement_ref':'e'*64}}},event_time_ms=11001,received_time_ms=11001))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id='original_operation');ledger.append(boundary)
        profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=RetainedHistoryReadJob(operation_id='original_operation',cutoff_ref=boundary.hash,alias='native',profile=profile,collection='MOVEMENTS',after=0,limit=10)
        for _ in range(200):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result();assert result['state']=='RECONCILIATION_REQUIRED' and result['source']['snapshot_ref']==first.hash
        assert result['movement_count'] is None


def test_blocked_admissions_count_capacity_survive_expiry_and_drain_on_shutdown():
    import threading
    from vati.funding.retained_history import RetainedHistoryError,RetainedHistoryJobs
    now=[0];manager=RetainedHistoryJobs(clock=lambda:now[0],ttl_seconds=5)
    entered=threading.Event();release=threading.Event();closed=threading.Event();outcomes=[]
    def guard():entered.set();assert release.wait(3)
    def admit():
        try:manager.start('device','binding',[],guard)
        except RetainedHistoryError as error:outcomes.append(str(error))
    first=threading.Thread(target=admit);first.start();assert entered.wait(2)
    now[0]=10
    manager.start('device','other',[],lambda:None)
    with pytest.raises(RetainedHistoryError,match='CAPACITY'):manager.start('device','third',[],lambda:None)
    stopper=threading.Thread(target=lambda:(manager.close(),closed.set()));stopper.start()
    with manager._condition:assert manager._condition.wait_for(lambda:manager._closed,timeout=2)
    assert not closed.is_set()
    with pytest.raises(RetainedHistoryError,match='RESTART_REQUIRED'):manager.start('other','x',[],lambda:None)
    release.set();first.join(3);stopper.join(3)
    assert not first.is_alive() and not stopper.is_alive() and closed.is_set()
    assert outcomes==['RETAINED_HISTORY_RESTART_REQUIRED'] and not manager._jobs


@pytest.mark.parametrize('fault',['missing','malformed'])
def test_unproven_mt5_statement_preserves_prefix(tmp_path,fault):
    from trading.tests.test_mt5_funding_contract import frame
    from vati.core.events import EventKind,make_event
    from vati.core.ledger import Ledger
    from vati.funding.mt5_journal import Mt5FundingBook
    from vati.funding.retained_history import RetainedHistoryReadJob
    with closing(Ledger(tmp_path/'missing-mt5-statement.sqlite')) as ledger:
        source=frame();query,receipt=Mt5FundingBook(ledger,clock=lambda:11000).capture(source)
        payload={'account_alias':'native','native_account_mark':source.mark_body(),'funding_observation':{'scope_hash':source.scope_hash,'query_ref':query,'statement':receipt}}
        first=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11000,received_time_ms=11000);ledger.append(first)
        bad=dict(payload);bad['funding_observation']=dict(payload['funding_observation'])
        if fault=='missing':del bad['funding_observation']['statement']
        else:bad['funding_observation']['statement']=None
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',bad,event_time_ms=11001,received_time_ms=11001))
        ledger.append(make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',payload,event_time_ms=11002,received_time_ms=11002))
        boundary=make_event(EventKind.ACCOUNT_OPERATION,'fixture',{'phase':'IN_FLIGHT','previous_ref':''},event_time_ms=1,received_time_ms=1,correlation_id='original_operation');ledger.append(boundary)
        profile={'alias':'native','broker':'MT5','login':'12345678','server':'Broker-Demo','currency':'USD','demo':True}
        job=RetainedHistoryReadJob(operation_id='original_operation',cutoff_ref=boundary.hash,alias='native',profile=profile,collection='MOVEMENTS',after=0,limit=10)
        for _ in range(200):
            job.advance(ledger,event_budget=2,row_budget=2)
            if job.finished:break
        result=job.result();assert result['state']=='RECONCILIATION_REQUIRED' and result['source']['snapshot_ref']==first.hash
        assert result['movement_count'] is None
