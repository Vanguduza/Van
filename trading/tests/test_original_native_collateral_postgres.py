"""Native collateral data reopens without crossing real PostgreSQL scopes."""
from decimal import Decimal as D
from dataclasses import replace

from conftest import NOW,snapshot
from test_postgres_ledger_isolation import pg_dsn
from test_mt5_funding_runtime import setup
from test_native_risk_history_inputs import record
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.native_collateral import original_native_collateral
from vati.core.units import Money


def test_original_native_collateral_reopens_without_relabel_or_new_authority(pg_dsn,tmp_path,eurusd):
    unused,adapter,account=setup(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='original-collateral')
    other=PostgresLedger(pg_dsn,ledger_name='foreign-collateral')
    try:
        captured=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=captured)
        facts=snapshot(eurusd,account_alias=account.account_alias,equity=account.equity,
            balance=account.balance,native_account_context=context,used_margin=D('1000'),
            free_margin=D('11000'),margin_level_pct=D('1200'))
        event=record(ledger,facts)
        original=original_native_collateral(ledger,event.hash,available_at_ms=NOW*1000)
        assert original.body()['state']=='MEASURED'
        assert Money.from_body(original.body()['available_capacity']).decimal==D('9000')
        assert original_native_collateral(other,event.hash,available_at_ms=NOW*1000).body()['state']=='UNAVAILABLE'
        count=ledger.count();ledger.close();ledger=PostgresLedger(pg_dsn,ledger_name='original-collateral')
        assert original_native_collateral(ledger,event.hash,available_at_ms=(NOW+90*86400)*1000)==original
        assert ledger.count()==count and other.count()==0
        assert original.body()['risk_capital_qualified'] is original.body()['execution_authority'] is False
        assert adapter.queue._conn.execute('SELECT count(*) FROM commands').fetchone()[0]==0
    finally:ledger.close();other.close()
