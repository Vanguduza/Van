"""Pending/uncertain original order exposure in isolated PostgreSQL."""
from dataclasses import replace
import pytest

from conftest import NOW, snapshot
from test_native_risk_account_context import mt5_context
from test_native_risk_history_index import other_context
from test_physical_order_exposure import command, receipt
from test_postgres_ledger_isolation import pg_dsn
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.physical_orders import physical_order_exposure
from vati.risk.native_history import NativeRiskSourceUnavailable


def test_postgres_alias_change_reopen_and_native_no_effect_preserve_original_exposure(pg_dsn,tmp_path,eurusd):
    unused,adapter,account,_,_=mt5_context(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='original-order-exposure')
    other=PostgresLedger(pg_dsn,ledger_name='other-order-exposure');reopened=None
    try:
        captured=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=captured)
        facts=snapshot(eurusd,account_alias=account.account_alias,balance=account.balance,
            equity=account.equity,native_account_context=context)
        _,cmd=command(ledger,facts,'original-pg-order')
        b=other_context(ledger,adapter,account,facts,alias='another_alias')
        receipt(ledger,cmd,status='ACCEPTED')
        receipt(ledger,cmd,status='CANCELLED',when=3)
        reopened=PostgresLedger(pg_dsn,ledger_name='original-order-exposure')
        value=physical_order_exposure(reopened,b.native_account_context,available_at_ms=NOW*1000+100)
        assert len(value.orders)==1 and value.orders[0].state=='UNCERTAIN'
        assert value.orders[0].origin_alias==facts.account_alias
        assert value.orders[0].active_quantity_bound==cmd.quantity and value.orders[0].required_margin is None
        with pytest.raises(NativeRiskSourceUnavailable,match='query receipt is unavailable'):
            physical_order_exposure(other,b.native_account_context,available_at_ms=NOW*1000+100)
        receipt(ledger,cmd,status='CANCELLED',when=4,native_entry_observation={
            'schema':'vati.native-entry-observation/1','command_hash':cmd.command_hash,'source':'ORIGINAL_NATIVE_RESULT'})
        final=physical_order_exposure(reopened,b.native_account_context,available_at_ms=NOW*1000+100)
        assert final.orders[0].state=='NO_EFFECT' and final.orders[0].active_quantity_bound==0
        assert final.unpriced_order_refs==() and final.execution_authority is False
        assert ledger.verify_chain()[0] and other.count()==0
    finally:
        if reopened is not None:reopened.close()
        other.close();ledger.close()
