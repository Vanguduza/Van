"""Actual PostgreSQL writer waits, SDK handoff and original publication recovery."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import time

import pytest

from conftest import NOW, intent, mandate_dict, snapshot
from test_postgres_ledger_isolation import pg_dsn
from test_entry_dispatch_commit_fence import approved_entry, sender
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.execution import ExecutionRouter, PaperAdapter, ProtectionManager, RouterError
from vati.execution.router import EntryDispatchUnknown
from vati.execution.risk_refresh import CurrentRiskFacts
from vati.risk import Decision, KillSwitch, RiskAuthority, TradingMandate


def test_preexisting_postgres_routers_share_the_original_idempotency_fence(pg_dsn, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    first = PostgresLedger(pg_dsn, ledger_name='entry-original')
    second = PostgresLedger(pg_dsn, ledger_name='entry-original')
    left, right = PaperAdapter(), PaperAdapter()
    try:
        a, b = sender(first, left), sender(second, right)
        assert a.execute(trade, decision, mandate, now_ms=NOW*1000).status == 'FILLED'
        with pytest.raises(RouterError, match='duplicate idempotency'):
            b.execute(trade, decision, mandate, now_ms=NOW*1000+1)
        assert first.count(EventKind.ORDER_COMMAND) == first.count(EventKind.EXECUTION_RECEIPT) == 1
        assert len(left.positions()) == 1 and not right.positions() and first.verify_chain()[0]
    finally:
        second.close()
        first.close()


def test_concurrent_postgres_routers_publish_and_send_the_original_once(pg_dsn, eurusd):
    mandate, trade, decision = approved_entry(eurusd)
    check = PostgresLedger(pg_dsn, ledger_name='entry-race')
    barrier = threading.Barrier(2)
    class ConcurrentPaper(PaperAdapter):
        def heartbeat(self, *, now_ms):
            barrier.wait(5)
            return super().heartbeat(now_ms=now_ms)
    def execute():
        ledger, adapter = PostgresLedger(pg_dsn, ledger_name='entry-race'), ConcurrentPaper()
        try:
            router = sender(ledger, adapter)
            try:
                status = router.execute(trade, decision, mandate, now_ms=NOW*1000).status
            except RouterError as error:
                status = str(error)
            return status, len(adapter.positions())
        finally:
            ledger.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(execute) for _ in range(2)]
            results = [job.result(timeout=15) for job in jobs]
        assert sum(count for _, count in results) == 1
        assert sum(status == 'FILLED' for status, _ in results) == 1
        assert sum('duplicate idempotency' in status for status, _ in results) == 1
        assert check.count(EventKind.ORDER_COMMAND) == check.count(EventKind.EXECUTION_RECEIPT) == 1
        assert check.verify_chain()[0]
    finally:
        check.close()


def test_grant_expiry_during_actual_postgres_writer_wait_cannot_send(pg_dsn, eurusd):
    import psycopg
    mandate, trade, decision = approved_entry(eurusd)
    blocker = PostgresLedger(pg_dsn, ledger_name='entry-wait')
    clock = {'now': NOW*1000}
    backend_pid = []
    ready = threading.Event()
    def execute():
        ledger, adapter = PostgresLedger(pg_dsn, ledger_name='entry-wait'), PaperAdapter()
        try:
            router = sender(ledger, adapter)
            router.clock = lambda: clock['now']
            backend_pid.append(ledger._conn.info.backend_pid)
            ready.set()
            try:
                router.execute(trade, decision, mandate, now_ms=NOW*1000)
            except RouterError as error:
                return str(error), len(adapter.positions())
            return 'SENT', len(adapter.positions())
        finally:
            ledger.close()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with blocker.atomic():
                job = pool.submit(execute)
                assert ready.wait(5)
                waiting = False
                with psycopg.connect(pg_dsn, autocommit=True) as observer:
                    until = time.monotonic()+5
                    while time.monotonic() < until:
                        row = observer.execute('SELECT wait_event_type,query FROM pg_stat_activity WHERE pid=%s',
                            (backend_pid[0],)).fetchone()
                        if row and row[0] == 'Lock' and 'FOR UPDATE' in row[1]:
                            waiting = True
                            break
                        time.sleep(.01)
                assert waiting, 'source fixture never reached the actual PostgreSQL entry writer lock'
                clock['now'] = mandate.expires_at_unix*1000
            message, positions = job.result(timeout=15)
        assert 'mandate' in message and positions == 0
        assert blocker.count(EventKind.ORDER_COMMAND) == blocker.count(EventKind.EXECUTION_RECEIPT) == 0
    finally:
        blocker.close()


def native_sender(ledger, tmp_path, eurusd):
    from test_mt5_worker_funding import connection
    from test_native_risk_history_inputs import record
    from vati.funding.mt5_runtime import capture_cached_mt5
    from vati.risk.account_context import context_for_account
    sdk, worker, adapter, clock = connection(tmp_path)
    clock['ms'] = NOW*1000
    grant = mandate_dict(venue='mt5', account_alias='native')
    mandate = TradingMandate.from_mapping(grant)
    authority = RiskAuthority(mandate)
    trade = intent(venue='mt5', account_alias='native')
    account = adapter.sync_account()
    captured = capture_cached_mt5(ledger, account, now_ms=clock['ms'])
    context = context_for_account(ledger, adapter, account, now_ms=clock['ms'], mt5_capture=captured)
    facts = snapshot(replace(eurusd, venue='mt5'), account_alias='native', native_account_context=context)
    original = record(ledger, facts, request=trade, grant=grant)
    decision = authority.evaluate_safe(trade, facts)
    assert decision.decision in {Decision.APPROVED, Decision.REDUCED}
    assert original.payload['decision']['decision_hash'] == decision.decision_hash
    router = ExecutionRouter(ledger=ledger, adapters={'mt5': adapter}, kill_switch=KillSwitch(),
        protection=ProtectionManager(), clock=lambda: clock['ms'], current_risk_authority=authority,
        current_risk_facts_provider=lambda *args, **kwargs: CurrentRiskFacts(facts, clock['ms']))
    return sdk, adapter, clock, mandate, trade, decision, router


@pytest.mark.parametrize('fault', ['none', 'commit-ack-lost', 'readback-unavailable'])
def test_actual_signed_native_sdk_handoff_requires_committed_postgres_command(pg_dsn, tmp_path, eurusd, monkeypatch, fault):
    ledger = PostgresLedger(pg_dsn, ledger_name='native-entry')
    try:
        sdk, adapter, clock, mandate, trade, decision, router = native_sender(ledger, tmp_path, eurusd)
        atomic, read_snapshot = ledger.atomic, ledger.read_snapshot
        @contextmanager
        def uncertain_commit():
            outer = ledger._atomic_depth == 0
            before = ledger.count(EventKind.ORDER_COMMAND) if outer else None
            with atomic():
                yield ledger
            if outer and before == 0 and ledger.count(EventKind.ORDER_COMMAND) == 1:
                raise OSError('source fixture original native command commit ACK lost')
        @contextmanager
        def failed_readback():
            if ledger.count(EventKind.ORDER_COMMAND):
                raise OSError('source fixture original native command readback unavailable')
            with read_snapshot():
                yield ledger
        if fault == 'commit-ack-lost':
            monkeypatch.setattr(ledger, 'atomic', uncertain_commit)
        elif fault == 'readback-unavailable':
            monkeypatch.setattr(ledger, 'read_snapshot', failed_readback)
        if fault == 'none':
            send = sdk.order_send
            observed = []
            def native_effect(body):
                independent = PostgresLedger(pg_dsn, ledger_name='native-entry')
                try:
                    rows = list(independent.iter(EventKind.ORDER_COMMAND))
                    assert len(rows) == 1 and independent.verify_chain()[0]
                    assert ledger._conn.info.transaction_status == 0
                    observed.append(rows[0].payload['command_hash'])
                finally:
                    independent.close()
                return send(body)
            sdk.order_send = native_effect
            assert router.execute(trade, decision, mandate, now_ms=clock['ms'], entry_type='MARKET').status == 'FILLED'
            assert len(sdk.sent) == len(observed) == 1
        else:
            with pytest.raises(EntryDispatchUnknown):
                router.execute(trade, decision, mandate, now_ms=clock['ms'], entry_type='MARKET')
            assert not sdk.sent and ledger.count(EventKind.EXECUTION_RECEIPT) == 0
        monkeypatch.setattr(ledger, 'atomic', atomic)
        monkeypatch.setattr(ledger, 'read_snapshot', read_snapshot)
        assert ledger.count(EventKind.ORDER_COMMAND) == 1 and ledger.verify_chain()[0]
        with pytest.raises(RouterError, match='duplicate idempotency'):
            sender(ledger, PaperAdapter()).execute(trade, decision, mandate, now_ms=clock['ms'])
    finally:
        ledger.close()
