"""Original signed cancellation and uncertain effect recovery across SQL owners."""
import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_native_cancel_owner import setup_cancel
from vati.core.ledger import LedgerError
from vati.core.ledger_pg import PostgresLedger
from vati.execution import ExecutionRouter,ProtectionManager
from vati.execution.native_cancel import NativeCancelOwner
from vati.risk import KillSwitch


@pytest.mark.parametrize('lost_reply',[False,True])
def test_pg_signed_native_control_reopens_and_queries_original_without_another_cancel(pg_dsn,tmp_path,eurusd,lost_reply):
    ledger=PostgresLedger(pg_dsn,ledger_name='native-cancel')
    reopened=PostgresLedger(pg_dsn,ledger_name='native-cancel')
    foreign=PostgresLedger(pg_dsn,ledger_name='foreign-cancel')
    try:
        _,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd,ledger=ledger)
        adapter.transport.lose_reply=lost_reply
        result=owner.execute(intent,token)
        assert result['attempt_state']==('UNKNOWN' if lost_reply else 'WIRE_OBSERVED')
        other_router=ExecutionRouter(ledger=reopened,adapters={'ctrader':adapter},kill_switch=KillSwitch(),
            protection=ProtectionManager(),clock=lambda:clock['ms'])
        recovered=NativeCancelOwner(other_router,authority=authority.verifier)
        assert recovered.lookup('cancel-1')==result
        assert NativeCancelOwner(type('Router',(),{'ledger':foreign,'clock':lambda self:clock['ms']})(),
                                 authority=authority.verifier).lookup('cancel-1') is None
        clock['ms']+=100000
        assert recovered.execute(intent,None)==result
        reconciled=recovered.reconcile('cancel-1','pg-read-original',deadline_ms=clock['ms']+1000)
        assert reconciled['state']=='ORDER_OBSERVED' and reconciled['attempt_state']==result['attempt_state']
        assert len(adapter.transport.cancel_sends)==1 and foreign.count()==0 and ledger.verify_chain()[0]
        assert reconciled['position_flat'] is None and reconciled['cash_settled'] is False
    finally:foreign.close();reopened.close();ledger.close()


def test_pg_caller_writer_cannot_send_an_uncommitted_control(pg_dsn,tmp_path,eurusd):
    ledger=PostgresLedger(pg_dsn,ledger_name='staged-native-cancel')
    try:
        _,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd,ledger=ledger)
        count=ledger.count();calls=len(adapter.transport.calls)
        with ledger.atomic():
            with pytest.raises(LedgerError,match='committed_source_read_requires'):owner.execute(intent,token)
        assert ledger.count()==count and len(adapter.transport.calls)==calls and not adapter.transport.cancel_sends
    finally:ledger.close()


def test_pg_two_independent_control_writers_cannot_cancel_the_original_twice(pg_dsn,tmp_path,eurusd):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    ledger=PostgresLedger(pg_dsn,ledger_name='concurrent-cancel')
    try:
        _,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd,ledger=ledger)
        barrier=threading.Barrier(2)
        def execute():
            from vati.execution.native_cancel import NativeCancelError,NativeCancelUnknown
            from vati.execution.native_order_book import NativeOrderError
            connection=PostgresLedger(pg_dsn,ledger_name='concurrent-cancel')
            try:
                isolated=ExecutionRouter(ledger=connection,adapters={'ctrader':adapter},kill_switch=KillSwitch(),
                    protection=ProtectionManager(),clock=lambda:clock['ms'])
                controller=NativeCancelOwner(isolated,authority=authority.verifier)
                barrier.wait(timeout=10)
                try:return controller.execute(intent,token)
                except (NativeCancelError,NativeCancelUnknown,NativeOrderError) as error:
                    return {'conflict_type':type(error).__name__}
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:execute(),range(2)))
        assert any(r.get('state')=='WIRE_OBSERVED' for r in results)
        assert len(adapter.transport.cancel_sends)==1
        assert owner.lookup('cancel-1')['attempt_state']=='WIRE_OBSERVED'
        assert ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('lost_commit',[2,3])
def test_pg_request_or_result_commit_ack_loss_reconciles_original_without_resend(pg_dsn,tmp_path,eurusd,monkeypatch,lost_commit):
    from contextlib import contextmanager
    from vati.execution.native_cancel import NativeCancelUnknown
    ledger=PostgresLedger(pg_dsn,ledger_name='lost-ack-cancel')
    reopened=PostgresLedger(pg_dsn,ledger_name='lost-ack-cancel')
    try:
        _,adapter,router,owner,authority,clock,intent,token=setup_cancel(tmp_path,eurusd,ledger=ledger)
        atomic=ledger.atomic;outer_writes=[]
        @contextmanager
        def lost_ack():
            outer=ledger._conn.info.transaction_status==0
            with atomic():yield ledger
            if outer:
                outer_writes.append(1)
                if len(outer_writes)==lost_commit:raise OSError('fixture actual committed PG cancellation ACK lost')
        monkeypatch.setattr(ledger,'atomic',lost_ack)
        with pytest.raises(NativeCancelUnknown) as error:owner.execute(intent,token)
        assert error.value.request_id=='cancel-1'
        monkeypatch.setattr(ledger,'atomic',atomic)
        recovery_router=ExecutionRouter(ledger=reopened,adapters={'ctrader':adapter},kill_switch=KillSwitch(),
            protection=ProtectionManager(),clock=lambda:clock['ms'])
        recovered=NativeCancelOwner(recovery_router,authority=authority.verifier)
        expected='REQUESTED' if lost_commit==2 else 'WIRE_OBSERVED'
        result=recovered.lookup('cancel-1')
        assert result['attempt_state']==expected
        sends=len(adapter.transport.cancel_sends);count=ledger.count()
        assert sends==(0 if lost_commit==2 else 1)
        assert recovered.execute(intent,None)==result
        assert ledger.count()==count and len(adapter.transport.cancel_sends)==sends and ledger.verify_chain()[0]
    finally:reopened.close();ledger.close()
