"""Actual PostgreSQL control owners retain original command budgets."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

import pytest

from conftest import NOW
from test_postgres_ledger_isolation import pg_dsn
from test_pretrade_durable_command_budget import durable_controls
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.execution import RouterError
from vati.execution.router import EntryDispatchUnknown
from vati.execution.style_selector import ExecutionStyleSelector


def test_actual_postgres_reopen_retains_the_original_account_window(pg_dsn,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='command-window')
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        receipt=send(1);assert receipt.status=='FILLED'
        adapter.close(receipt.broker_position_id,None,now_ms=NOW*1000,reason='source-test-close')
    finally:
        ledger.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='command-window')
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        with pytest.raises(RouterError,match='ORDER_RATE_LIMIT'):
            send(2)
        assert send(2,now=NOW*1000+60_001).status=='FILLED'
        assert len(adapter.positions())==1 and ledger.count(EventKind.ORDER_COMMAND)==2
        assert ledger.verify_chain()[0]
    finally:
        ledger.close()


def test_two_preexisting_postgres_control_owners_share_one_remaining_command_slot(pg_dsn,eurusd):
    check=PostgresLedger(pg_dsn,ledger_name='command-race')
    ready=threading.Barrier(2)
    class SimultaneousStyle(ExecutionStyleSelector):
        def select(self,**kwargs):
            style=super().select(**kwargs)
            ready.wait(5)  # Both original pre-trade checks passed.
            return style
    def execute(index):
        ledger=PostgresLedger(pg_dsn,ledger_name='command-race')
        try:
            _,adapter,_,router,send=durable_controls(ledger,eurusd,max_orders=1)
            router.style_selector=SimultaneousStyle()
            try:
                status=send(index).status
            except RouterError as error:
                status=str(error)
            return status,len(adapter.positions())
        finally:
            ledger.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(execute,index) for index in (1,2)]
            results=[job.result(timeout=15) for job in jobs]
        assert sum(status=='FILLED' for status,_ in results)==1
        assert sum('ORDER_RATE_LIMIT' in status for status,_ in results)==1
        assert sum(count for _,count in results)==1
        assert check.count(EventKind.ORDER_COMMAND)==check.count(EventKind.EXECUTION_RECEIPT)==1
        assert check.verify_chain()[0]
    finally:
        check.close()


def test_original_admission_with_lost_commit_ack_cannot_reset_the_postgres_window(pg_dsn,eurusd,monkeypatch):
    ledger=PostgresLedger(pg_dsn,ledger_name='command-unknown')
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        atomic=ledger.atomic
        @contextmanager
        def lose_original_ack():
            outer=ledger._atomic_depth==0
            before=ledger.count(EventKind.ORDER_COMMAND) if outer else None
            with atomic():yield ledger
            if outer and before==0 and ledger.count(EventKind.ORDER_COMMAND)==1:
                raise OSError('source fixture original command commit ACK lost')
        monkeypatch.setattr(ledger,'atomic',lose_original_ack)
        with pytest.raises(EntryDispatchUnknown):send(1)
        assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==1
        monkeypatch.setattr(ledger,'atomic',atomic)
    finally:
        ledger.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='command-unknown')
    try:
        _,adapter,_,_,send=durable_controls(ledger,eurusd,max_orders=1)
        with pytest.raises(RouterError,match='ORDER_RATE_LIMIT'):
            send(2)
        assert not adapter.positions() and ledger.count(EventKind.ORDER_COMMAND)==1
        assert ledger.count(EventKind.EXECUTION_RECEIPT)==0 and ledger.verify_chain()[0]
    finally:
        ledger.close()
