"""Original PostgreSQL cursor isolation and restart-safe baseline readback."""
from dataclasses import replace

import pytest

from conftest import NOW, snapshot, intent
from test_postgres_ledger_isolation import pg_dsn, event
from test_mt5_funding_runtime import setup
from test_native_risk_history_index import other_context
from test_native_risk_history_inputs import record
from test_physical_baselines import legacy
from test_physical_control_history import original_control
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.lockouts import LockoutPolicy
from vati.risk.physical_runtime import PhysicalRiskRuntime


def test_pg_ordered_tail_is_scoped_even_with_sequence_gaps(pg_dsn):
    a=PostgresLedger(pg_dsn,ledger_name='tail-a');b=PostgresLedger(pg_dsn,ledger_name='tail-b')
    try:
        a.append(event(1));b.append(event(2));a.append(event(3));b.append(event(4))
        rows=list(a.iter_after(0))
        assert [e.hash for _,e in rows]==[event(1).hash,event(3).hash]
        assert [e.hash for _,e in a.iter_after(rows[0][0])]==[event(3).hash]
        assert list(a.iter_after(rows[-1][0]))==[]
        assert [e.hash for _,e in b.iter_after(0)]==[event(2).hash,event(4).hash]
        for bad in (True,-1,'0',0.0):
            with pytest.raises(ValueError):list(a.iter_after(bad))
    finally:a.close();b.close()


def test_pg_shared_peak_release_survives_independent_runtime_reopen(pg_dsn,tmp_path,eurusd):
    unused,adapter,account=setup(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='basis-runtime')
    try:
        capture=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=capture)
        a=snapshot(eurusd,account_alias=account.account_alias,balance=account.balance,
            equity=account.equity,native_account_context=context)
        legacy(ledger,a,'original-a','15000')
        b=other_context(ledger,adapter,account,a,alias='second_alias')
        state=PhysicalRiskRuntime(ledger,b.native_account_context,LockoutPolicy(5),now_ms=NOW*1000)
        ref,p=state.observe(b.native_account_context,now_ms=NOW*1000,producer='vati-account-service')
        record(ledger,replace(b,peak_equity=p.peak,day_start_equity=p.day,week_start_equity=p.week,
            native_risk_basis_ref=ref),request=intent(trade_intent_id='shared-b',account_alias=b.account_alias))
        original_control(ledger,a.native_account_context,action='resume_drawdown')
        assert state.refresh(b.native_account_context,now_ms=NOW*1000).peak==a.equity
        ledger.close();ledger=PostgresLedger(pg_dsn,ledger_name='basis-runtime')
        reopened=PhysicalRiskRuntime(ledger,b.native_account_context,LockoutPolicy(5),now_ms=NOW*1000)
        assert reopened.book.projection(NOW*1000).peak==a.equity
        assert not reopened.book.projection(NOW*1000).issue
        assert ledger.count(EventKind.ORDER_COMMAND)==0
    finally:ledger.close()
