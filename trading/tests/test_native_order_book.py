"""Real original command -> native protocol read -> durable result -> risk owner."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from test_ctrader_order_details import native_reply
from test_native_entry_volume import dispatched
from vati.core import EventKind, Ledger
from vati.core.ledger import LedgerError
from vati.execution.native_order_book import NativeOrderBook, NativeOrderError, NativeOrderUnknown
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.physical_pending import PhysicalPendingRisk, project_pending_risk


def setup_order(tmp_path, eurusd, *, ledger=None, receipt_changes=None):
    ledger, adapter, margin, clock, command, binding = dispatched(tmp_path, eurusd,
        ledger=ledger, receipt_changes=receipt_changes)
    context = NativeAccountRiskContext(**margin.lookup_entry(command.command_hash, binding['source_ref'])
                                       ['observation']['native_account_context'])
    response = native_reply(); response['order']['orderId'] = 2
    for deal in response['deal']:
        deal['orderId'] = 2; deal['positionId'] = 3
    adapter.transport.order_reply = response
    original = adapter.transport.call
    def call(name, body):
        if name == 'ProtoOAOrderDetailsReq':
            adapter.transport.calls.append((name, deepcopy(body)))
            return 'ProtoOAOrderDetailsRes', deepcopy(adapter.transport.order_reply)
        return original(name, body)
    adapter.transport.call = call
    book = NativeOrderBook(ledger, clock=lambda: clock['ms'])
    return ledger, adapter, book, clock, command, binding, context


def capture(parts, request_id='query-1'):
    ledger, adapter, book, clock, command, binding, _ = parts
    return book.capture(adapter, request_id, command.command_hash, binding['source_ref'], 2,
                        deadline_ms=clock['ms']+1000)


def test_actual_native_read_reopens_original_durable_result_without_requery(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, _ = parts
    reopened = None
    try:
        receipt = capture(parts); count = ledger.count(); calls = len(adapter.transport.calls)
        assert receipt['state'] == 'ORIGINAL_NATIVE_ORDER_STORED'
        assert receipt['settlement_qualified'] is receipt['execution_authority'] is False
        clock['ms'] += 90*86400*1000
        reopened = Ledger(ledger.path)
        recovered = NativeOrderBook(reopened, clock=lambda: clock['ms'])
        result = recovered.lookup('query-1')
        assert result['receipt'] == receipt
        assert result['observation']['facts']['recorded_gross_deal_volume'] == 500000
        assert recovered.capture(adapter, 'query-1', command.command_hash, binding['source_ref'], 2,
                                 deadline_ms=1) == receipt
        result['observation']['response']['deal'][0]['filledVolume'] = 0
        assert recovered.lookup('query-1')['observation']['facts']['recorded_gross_deal_volume'] == 500000
        assert ledger.count() == count and len(adapter.transport.calls) == calls
        assert ledger.verify_chain()[0]
    finally:
        if reopened is not None: reopened.close()
        ledger.close()


def test_confirmed_fills_contradict_no_effect_in_actual_pending_owner(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd, receipt_changes={'status': 'REJECTED', 'filled_qty': D(0), 'average_fill': None})
    ledger, adapter, book, clock, command, _, context = parts
    try:
        runtime = PhysicalPendingRisk(ledger, context, now_ms=clock['ms'])
        assert runtime.refresh((), now_ms=clock['ms']) == ()
        capture(parts)
        with pytest.raises(ValueError, match='native order'):
            runtime.refresh((), now_ms=clock['ms'])
        output, issue = project_pending_risk(SimpleNamespace(), ledger, context, (),
                                            now_ms=clock['ms'], contracts={})
        assert output == () and issue.startswith('NATIVE_PENDING_RISK_UNAVAILABLE:')
        result = book.for_command(command.command_hash, available_at_ms=clock['ms'])
        assert result['recorded_gross_deal_volume'] == 500000
        assert result['remaining_entry_allowance'] is result['position_flat'] is None
    finally: ledger.close()


def test_cancelled_native_order_does_not_release_original_pending_quantity(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, _, book, clock, command, _, context = parts
    try:
        capture(parts)
        pending = PhysicalPendingRisk(ledger, context, now_ms=clock['ms']).refresh((), now_ms=clock['ms'])
        assert len(pending) == 1 and pending[0].quantity == command.quantity
        assert pending[0].execution_authority is False
    finally: ledger.close()


@pytest.mark.parametrize('defect', ['foreign-order', 'foreign-command', 'foreign-source', 'foreign-adapter', 'bad-key'])
def test_unbound_request_never_reaches_provider(tmp_path, eurusd, defect):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, _ = parts
    before = len(adapter.transport.calls); count = ledger.count()
    request = ['query-1', command.command_hash, binding['source_ref'], 2]
    if defect == 'foreign-order': request[3] = 71
    elif defect == 'foreign-command': request[1] = 'f'*64
    elif defect == 'foreign-source': request[2] = 'f'*64
    elif defect == 'foreign-adapter': adapter.account_alias = 'foreign'
    else: request[0] = '../query'
    try:
        with pytest.raises((NativeOrderError, ValueError)):
            book.capture(adapter, *request, deadline_ms=clock['ms']+1000)
        assert len(adapter.transport.calls) == before and ledger.count() == count
    finally: ledger.close()


def test_actual_commit_ack_loss_recovers_original_without_querying_or_duplication(tmp_path, eurusd, monkeypatch):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, _ = parts
    atomic = ledger.atomic
    @contextmanager
    def lost_ack():
        outer = not ledger._conn.in_transaction
        with atomic(): yield ledger
        if outer: raise OSError('fixture actual committed ACK loss')
    try:
        monkeypatch.setattr(ledger, 'atomic', lost_ack)
        with pytest.raises(NativeOrderUnknown) as error: capture(parts)
        assert error.value.request_id == 'query-1'
        monkeypatch.setattr(ledger, 'atomic', atomic)
        count = ledger.count(); calls = len(adapter.transport.calls)
        assert capture(parts) == book.lookup('query-1')['receipt']
        assert ledger.count() == count and len(adapter.transport.calls) == calls
    finally: ledger.close()


def test_queued_storage_expiry_is_not_a_durable_success(tmp_path, eurusd, monkeypatch):
    parts = setup_order(tmp_path, eurusd); ledger, _, book, clock, _, _, _ = parts
    atomic = ledger.atomic; count = ledger.count()
    @contextmanager
    def delayed():
        with atomic():
            clock['ms'] += 1000
            yield ledger
    try:
        monkeypatch.setattr(ledger, 'atomic', delayed)
        with pytest.raises(NativeOrderError, match='EXPIRED'): capture(parts)
        assert ledger.count() == count and book.lookup('query-1') is None
    finally: ledger.close()


def test_staged_caller_transaction_never_issues_native_read(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, _, _, _, _, _ = parts
    count = ledger.count(); calls = len(adapter.transport.calls)
    try:
        with ledger.atomic():
            with pytest.raises(LedgerError, match='committed_source_read_requires'): capture(parts)
        assert ledger.count() == count and len(adapter.transport.calls) == calls
    finally: ledger.close()


def test_future_publication_is_not_current_evidence_and_later_missing_rows_do_not_erase_fills(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, _, _ = parts
    before = clock['ms']; clock['ms'] += 1
    try:
        receipt = capture(parts)
        assert book.for_command(command.command_hash, available_at_ms=before)['original_record_refs'] == []
        clock['ms'] += 1
        adapter.transport.order_reply['deal'] = []
        adapter.transport.order_reply['order'].pop('executedVolume')
        capture(parts, 'query-2')
        facts = book.for_command(command.command_hash, available_at_ms=clock['ms'])
        assert facts['recorded_gross_deal_volume'] == 500000
        assert facts['original_record_refs'][0] == receipt['record_ref']
        assert len(facts['original_record_refs']) == 2 and facts['execution_authority'] is False
    finally: ledger.close()


def test_later_conflicting_deal_is_retained_and_blocks_current_pending_use(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, _, context = parts
    try:
        capture(parts); clock['ms'] += 1
        adapter.transport.order_reply['deal'][0]['filledVolume'] = 0
        capture(parts, 'query-2')
        facts = book.for_command(command.command_hash, available_at_ms=clock['ms'])
        assert 'NATIVE_ORDER_DEAL_CORRECTION_UNRECONCILED' in facts['issues']
        assert facts['recorded_gross_deal_volume'] == 500000
        with pytest.raises(ValueError, match='native order'):
            PhysicalPendingRisk(ledger, context, now_ms=clock['ms'])
    finally: ledger.close()


def test_actual_router_read_then_replay_works_without_adapter_or_new_grant(tmp_path, eurusd):
    from vati.execution import ExecutionRouter, ProtectionManager
    from vati.risk import KillSwitch
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, _ = parts
    try:
        router = ExecutionRouter(ledger=ledger, adapters={'ctrader': adapter}, kill_switch=KillSwitch(),
                                 protection=ProtectionManager(), clock=lambda: clock['ms'])
        first = router.observe_native_order('router-query', command.command_hash, binding['source_ref'], 2,
                                            deadline_ms=clock['ms']+1000)
        count = ledger.count(); calls = len(adapter.transport.calls)
        router.adapters.clear(); clock['ms'] += 999999
        assert router.observe_native_order('router-query', command.command_hash, binding['source_ref'], 2,
                                           deadline_ms=1) == first
        assert ledger.count() == count and len(adapter.transport.calls) == calls
        assert ledger.count(EventKind.ORDER_COMMAND) == ledger.count(EventKind.EXECUTION_RECEIPT) == 1
    finally: ledger.close()


def test_failed_independent_readback_retains_original_request_for_recovery(tmp_path, eurusd, monkeypatch):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, _, _, _, _ = parts
    original = book.lookup; seen = []
    def unavailable(request_id):
        seen.append(request_id)
        if len(seen) == 3: raise OSError('fixture committed readback unavailable')
        return original(request_id)
    try:
        monkeypatch.setattr(book, 'lookup', unavailable)
        with pytest.raises(NativeOrderUnknown) as error: capture(parts)
        assert error.value.request_id == 'query-1'
        monkeypatch.setattr(book, 'lookup', original)
        count = ledger.count(); calls = len(adapter.transport.calls)
        assert capture(parts) == original('query-1')['receipt']
        assert ledger.count() == count and len(adapter.transport.calls) == calls
    finally: ledger.close()


def test_same_request_cannot_retarget_another_original_native_order(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, _ = parts
    try:
        first = capture(parts); calls = len(adapter.transport.calls); count = ledger.count()
        with pytest.raises(NativeOrderError, match='CONFLICT'):
            book.capture(adapter, 'query-1', command.command_hash, binding['source_ref'], 71,
                         deadline_ms=clock['ms']+1000)
        assert book.lookup('query-1')['receipt'] == first
        assert ledger.count() == count and len(adapter.transport.calls) == calls
    finally: ledger.close()


@pytest.mark.parametrize('defect', ['overfill', 'closing', 'unknown-status', 'total-conflict'])
def test_unreconciled_native_facts_are_stored_and_block_actual_pending_use(tmp_path, eurusd, defect):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, _, context = parts
    raw = adapter.transport.order_reply
    if defect == 'overfill':
        raw['deal'][0]['volume'] = raw['deal'][0]['filledVolume'] = 2000000
        raw['order']['executedVolume'] = 2300000
    elif defect == 'closing': raw['order']['closingOrder'] = True
    elif defect == 'unknown-status': raw['order']['orderStatus'] = 999
    else: raw['order']['executedVolume'] = 300000
    try:
        receipt = capture(parts)
        assert book.lookup('query-1')['receipt'] == receipt
        assert book.for_command(command.command_hash, available_at_ms=clock['ms'])['issues']
        with pytest.raises(ValueError, match='native order'):
            PhysicalPendingRisk(ledger, context, now_ms=clock['ms'])
        assert ledger.count(EventKind.EXECUTION_RECEIPT) == 1 and ledger.verify_chain()[0]
    finally: ledger.close()


def test_empty_native_snapshot_does_not_complete_no_effect_or_release_allowance(tmp_path, eurusd):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, _, context = parts
    adapter.transport.order_reply['deal'] = []
    adapter.transport.order_reply['order']['executedVolume'] = 0
    try:
        capture(parts)
        facts = book.for_command(command.command_hash, available_at_ms=clock['ms'])
        assert facts['recorded_gross_deal_volume'] == 0 and facts['remaining_entry_allowance'] is None
        pending = PhysicalPendingRisk(ledger, context, now_ms=clock['ms']).refresh((), now_ms=clock['ms'])
        assert len(pending) == 1 and pending[0].quantity == command.quantity
    finally: ledger.close()


def test_actual_two_sqlite_connections_publish_one_original_result(tmp_path, eurusd):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from vati.execution.ctrader.orders import NativeOrderObservation
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, context = parts
    observation = adapter.order_details(2, context=context, deadline_ms=clock['ms']+1000).body()
    barrier = threading.Barrier(2)
    def write():
        owned = Ledger(ledger.path)
        try:
            other = NativeOrderBook(owned, clock=lambda: clock['ms']); barrier.wait(timeout=10)
            return other.record('same-query', command.command_hash, binding['source_ref'],
                                NativeOrderObservation.from_body(observation))
        finally: owned.close()
    try:
        before = ledger.count()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: write(), range(2)))
        assert results[0] == results[1] == book.lookup('same-query')['receipt']
        assert ledger.count() == before+1 and ledger.verify_chain()[0]
    finally: ledger.close()


@pytest.mark.parametrize('limit,value', [('max_records', 1), ('max_bytes', 100), ('max_events', 1)])
def test_capacity_refusal_has_no_partial_publication(tmp_path, eurusd, limit, value):
    parts = setup_order(tmp_path, eurusd); ledger, adapter, book, clock, command, binding, context = parts
    try:
        if limit == 'max_records': capture(parts)
        count = ledger.count()
        limited = NativeOrderBook(ledger, clock=lambda: clock['ms'], **{limit: value})
        observation = adapter.order_details(2, context=context, deadline_ms=clock['ms']+1000)
        with pytest.raises(NativeOrderError, match='CAPACITY'):
            limited.record('next-query', command.command_hash, binding['source_ref'], observation)
        assert ledger.count() == count and ledger.verify_chain()[0]
    finally: ledger.close()
