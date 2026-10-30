"""Actual router transport requires an independently committed unique command."""
from dataclasses import replace
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
import threading

import pytest

from conftest import NOW, intent, mandate_dict, snapshot
from vati.core import EventKind, Ledger
from vati.execution import ExecutionRouter, PaperAdapter, ProtectionManager, RouterError
from vati.risk import Decision, KillSwitch, RiskAuthority, StrategyState, TradingMandate
from vati.execution.router import EntryDispatchUnknown


def approved_entry(contract):
    mandate = TradingMandate.from_mapping(mandate_dict(venue='paper', mode='DEMO_TRADER'))
    trade = intent(venue='paper', strategy_state=StrategyState.DEMO)
    decision = RiskAuthority(mandate).evaluate_safe(trade, snapshot(replace(contract, venue='paper')))
    assert decision.decision in {Decision.APPROVED, Decision.REDUCED}
    return mandate, trade, decision


def sender(ledger, adapter):
    return ExecutionRouter(ledger=ledger, adapters={'paper': adapter},
        kill_switch=KillSwitch(), protection=ProtectionManager())


def test_preexisting_independent_routers_cannot_dispatch_the_same_original_twice(tmp_path, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    path = tmp_path/'entry.sqlite'
    first, second = Ledger(path), Ledger(path)
    left, right = PaperAdapter(), PaperAdapter()
    try:
        a, b = sender(first, left), sender(second, right)
        a.execute(trade, decision, mandate, now_ms=NOW*1000)
        try:
            b.execute(trade, decision, mandate, now_ms=NOW*1000+1)
        except RouterError:
            pass
        assert first.count(EventKind.ORDER_COMMAND) == 1
        assert len(left.positions())+len(right.positions()) == 1
        assert first.verify_chain()[0]
    finally:
        second.close()
        first.close()


def test_ambient_transaction_cannot_send_before_its_command_is_committed(eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    ledger, adapter = Ledger(), PaperAdapter()
    try:
        router = sender(ledger, adapter)
        with ledger.atomic():
            try:
                router.execute(trade, decision, mandate, now_ms=NOW*1000)
            except RouterError:
                pass
            assert not adapter.positions(), 'native effect escaped an uncommitted caller transaction'
        assert ledger.count(EventKind.ORDER_COMMAND) == 0
    finally:
        ledger.close()


def test_transport_reads_its_original_command_from_an_independent_connection(tmp_path, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    path = tmp_path/'entry.sqlite'
    ledger = Ledger(path)
    observed = []
    class Observer(PaperAdapter):
        def submit(self, command, *, now_ms):
            assert not ledger._conn.in_transaction
            other = Ledger(path)
            try:
                rows = list(other.iter(EventKind.ORDER_COMMAND))
                assert len(rows) == 1 and rows[0].payload['command_hash'] == command.command_hash
                assert rows[0].event_time_ms == now_ms and other.verify_chain()[0]
                observed.append(rows[0].hash)
            finally:
                other.close()
            return super().submit(command, now_ms=now_ms)
    try:
        adapter = Observer()
        assert sender(ledger, adapter).execute(trade, decision, mandate, now_ms=NOW*1000).status == 'FILLED'
        assert len(observed) == len(adapter.positions()) == 1
    finally:
        ledger.close()


def test_concurrent_routers_with_the_same_key_have_one_durable_send(tmp_path, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    path = tmp_path/'race.sqlite'
    Ledger(path).close()
    ready = threading.Barrier(2)
    class Synchronized(PaperAdapter):
        def heartbeat(self, *, now_ms):
            ready.wait(5)  # Both early in-memory duplicate checks have passed.
            return super().heartbeat(now_ms=now_ms)
    def execute():
        ledger, adapter = Ledger(path), Synchronized()
        try:
            router = sender(ledger, adapter)
            try:
                status = router.execute(trade, decision, mandate, now_ms=NOW*1000).status
            except RouterError as error:
                status = str(error)
            return status, len(adapter.positions())
        finally:
            ledger.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(execute) for _ in range(2)]
        results = [job.result(timeout=15) for job in jobs]
    check = Ledger(path)
    try:
        assert sum(count for _, count in results) == 1
        assert sum(status == 'FILLED' for status, _ in results) == 1
        assert sum('duplicate idempotency' in status for status, _ in results) == 1
        assert check.count(EventKind.ORDER_COMMAND) == check.count(EventKind.EXECUTION_RECEIPT) == 1
        assert check.verify_chain()[0]
    finally:
        check.close()


@pytest.mark.parametrize('fault', ['before-append', 'commit-ack-lost', 'readback-unavailable'])
def test_uncertain_publication_never_authorizes_transport(tmp_path, eurusd, monkeypatch, fault):
    mandate, trade, decision = approved_entry(eurusd)
    path = tmp_path/'unknown.sqlite'
    ledger, adapter = Ledger(path), PaperAdapter()
    router = sender(ledger, adapter)
    append, atomic, snapshot_reader = ledger.append, ledger.atomic, ledger.read_snapshot
    if fault == 'before-append':
        def refuse(event):
            if event.kind is EventKind.ORDER_COMMAND:
                raise OSError('source fixture command storage refused')
            return append(event)
        monkeypatch.setattr(ledger, 'append', refuse)
    elif fault == 'commit-ack-lost':
        @contextmanager
        def lose_ack():
            outer = not ledger._conn.in_transaction
            with atomic():
                yield ledger
            if outer:
                raise OSError('source fixture commit ACK lost')
        monkeypatch.setattr(ledger, 'atomic', lose_ack)
    else:
        @contextmanager
        def no_readback():
            raise OSError('source fixture original readback unavailable')
            yield
        monkeypatch.setattr(ledger, 'read_snapshot', no_readback)
    try:
        with pytest.raises(EntryDispatchUnknown) as failure:
            router.execute(trade, decision, mandate, now_ms=NOW*1000)
        assert failure.value.idempotency_key == trade.idempotency_key
        assert not adapter.positions() and ledger.count(EventKind.EXECUTION_RECEIPT) == 0
        check = Ledger(path)
        try:
            assert check.count(EventKind.ORDER_COMMAND) == (0 if fault == 'before-append' else 1)
            assert check.verify_chain()[0]
        finally:
            check.close()
        monkeypatch.setattr(ledger, 'append', append)
        monkeypatch.setattr(ledger, 'atomic', atomic)
        monkeypatch.setattr(ledger, 'read_snapshot', snapshot_reader)
        cold = sender(ledger, PaperAdapter())
        if fault == 'before-append':
            # Independent readback proved no command; no transport was attempted.
            assert cold.execute(trade, decision, mandate, now_ms=NOW*1000+1).status == 'FILLED'
        else:
            with pytest.raises(RouterError, match='duplicate idempotency'):
                cold.execute(trade, decision, mandate, now_ms=NOW*1000+1)
    finally:
        ledger.close()


@pytest.mark.parametrize('boundary', ['writer', 'readback'])
@pytest.mark.parametrize('fact', ['expiry', 'lease', 'kill', 'clock'])
def test_mutable_dispatch_facts_are_rechecked_after_storage_boundaries(tmp_path, eurusd, monkeypatch, boundary, fact):
    from vati.risk import KillSwitchTrigger
    mandate, trade, decision = approved_entry(eurusd)
    ledger, adapter = Ledger(tmp_path/'boundary.sqlite'), PaperAdapter()
    router = sender(ledger, adapter)
    clock = {'now': NOW*1000, 'lease': True}
    router.clock = lambda: clock['now']
    router.lease_fence = lambda epoch: clock['lease']
    def change():
        if fact == 'expiry':
            clock['now'] = mandate.expires_at_unix*1000
        elif fact == 'lease':
            clock['lease'] = False
        elif fact == 'kill':
            router.kill.trip(KillSwitchTrigger.RECONCILIATION_FAILURE, NOW*1000)
        else:
            clock['now'] = None
    original = ledger.atomic if boundary == 'writer' else ledger.read_snapshot
    changed = []
    @contextmanager
    def after_acquisition():
        with original():
            if boundary == 'writer' and not changed:
                changed.append(True)
                change()
            yield ledger
        if boundary == 'readback' and not changed:
            changed.append(True)
            change()
    monkeypatch.setattr(ledger, 'atomic' if boundary == 'writer' else 'read_snapshot', after_acquisition)
    try:
        if boundary == 'writer':
            with pytest.raises(RouterError):
                router.execute(trade, decision, mandate, now_ms=NOW*1000)
            assert ledger.count(EventKind.ORDER_COMMAND) == ledger.count(EventKind.EXECUTION_RECEIPT) == 0
        else:
            receipt = router.execute(trade, decision, mandate, now_ms=NOW*1000)
            assert receipt.status == 'REJECTED' and receipt.filled_qty == 0
            event = next(ledger.iter(EventKind.EXECUTION_RECEIPT))
            command = next(ledger.iter(EventKind.ORDER_COMMAND))
            assert event.payload['entry_command_ref'] == command.hash
            assert event.payload['native_dispatch_attempted'] is False
            assert event.payload['dispatch_state'] == 'NOT_DISPATCHED'
            assert ledger.count(EventKind.ORDER_COMMAND) == ledger.count(EventKind.EXECUTION_RECEIPT) == 1
        assert changed == [True] and not adapter.positions() and ledger.verify_chain()[0]
    finally:
        ledger.close()


def test_readonly_caller_snapshot_cannot_own_native_publication(eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    ledger, adapter = Ledger(), PaperAdapter()
    try:
        router = sender(ledger, adapter)
        with ledger.read_snapshot():
            with pytest.raises(RouterError, match='committed writer'):
                router.execute(trade, decision, mandate, now_ms=NOW*1000)
        assert ledger.count() == 0 and not adapter.positions()
    finally:
        ledger.close()


def test_real_process_death_after_commit_does_not_allow_a_replacement_send(tmp_path, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    path = tmp_path/'process-crash.sqlite'
    Ledger(path).close()
    def child():
        ledger, adapter = Ledger(path), PaperAdapter()
        router = sender(ledger, adapter)
        publish = router._commit_entry_command
        def stop_after_commit(*args, **kwargs):
            publish(*args, **kwargs)
            os._exit(71)
        router._commit_entry_command = stop_after_commit
        router.execute(trade, decision, mandate, now_ms=NOW*1000)
        os._exit(72)
    process = multiprocessing.get_context('fork').Process(target=child)
    process.start()
    try:
        process.join(10)
        assert not process.is_alive() and process.exitcode == 71
        ledger, adapter = Ledger(path), PaperAdapter()
        try:
            assert ledger.count(EventKind.ORDER_COMMAND) == 1
            assert ledger.count(EventKind.EXECUTION_RECEIPT) == 0 and ledger.verify_chain()[0]
            with pytest.raises(RouterError, match='duplicate idempotency'):
                sender(ledger, adapter).execute(trade, decision, mandate, now_ms=NOW*1000+1)
            assert not adapter.positions()
        finally:
            ledger.close()
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        assert not process.is_alive()
        process.close()
