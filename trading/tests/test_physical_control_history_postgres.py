"""Actual PostgreSQL readback for native-source, alias-scoped controls."""
from conftest import NOW, snapshot
from test_postgres_ledger_isolation import pg_dsn
from test_mt5_funding_runtime import setup
from test_native_risk_history_index import other_context
from test_physical_control_history import original_control
from test_physical_financial_history import approval, close
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.lockouts import ACCOUNT_SCOPE, LockoutPolicy
from vati.risk.physical_history import physical_financial_history
from vati.risk.physical_lockouts import PhysicalLossStreakGovernor


def test_native_applied_control_and_other_alias_loss_survive_original_postgres_readback(pg_dsn,tmp_path,eurusd):
    unused,adapter,account=setup(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='physical-control-source')
    try:
        capture=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=capture)
        facts=snapshot(eurusd,account_alias=account.account_alias,balance=account.balance,
            equity=account.equity,native_account_context=context)
        first=approval(ledger,facts,'original-a');close(ledger,first,alias='native')
        control=original_control(ledger,context)
        current=other_context(ledger,adapter,account,facts,alias='another_label')
        second=approval(ledger,current,'original-b');close(ledger,second,alias='another_label')
        before=ledger.count()
        history=physical_financial_history(ledger,current.native_account_context,available_at_ms=NOW*1000)
        assert history.unresolved_refs==()
        assert [(f.event_ref,f.origin_alias) for f in history.facts if f.kind=='SESSION']==[(control.hash,'native')]
        ledger.close();ledger=PostgresLedger(pg_dsn,ledger_name='physical-control-source')
        recovered=physical_financial_history(ledger,current.native_account_context,available_at_ms=(NOW+86400)*1000)
        assert recovered==history and ledger.count()==before
        g=PhysicalLossStreakGovernor.rebuild(LockoutPolicy(5),ledger,account_alias='another_label',
            native_context=current.native_account_context,available_at_ms=(NOW+86400)*1000)
        assert g._scopes[ACCOUNT_SCOPE].losses==1
        assert g.original_contributors(ACCOUNT_SCOPE)==('another_label',)
        assert not g.recovery_issue and ledger.verify_chain()[0]
        assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0
    finally:
        ledger.close()
