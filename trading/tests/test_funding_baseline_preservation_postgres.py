"""Native baseline holds on an actual named PostgreSQL ledger."""
from decimal import Decimal as D
import pytest
from test_postgres_ledger_isolation import pg_dsn
from test_native_balance_reconciliation import mark, snapshot as original_snapshot, observe, cash
from test_funding_risk_fence import native
from test_funding_baseline_preservation import runtime, snapshot
from vati.core.ledger_pg import PostgresLedger


@pytest.mark.parametrize('producer', ['single', 'account'])
def test_original_postgres_capital_evidence_does_not_raise_held_baselines(pg_dsn, eurusd, producer):
    ledger = PostgresLedger(pg_dsn, ledger_name='native-baseline-' + producer)
    other = PostgresLedger(pg_dsn, ledger_name='other-baseline-' + producer)
    try:
        point = mark(3000, balance='200', equity='200', version=2)
        original_snapshot(ledger, mark(1000)); original_snapshot(ledger, point)
        observe(ledger, cash=[cash()])
        adapter, _ = native(point)
        service = runtime(producer, adapter, ledger, eurusd, '100')
        before = ledger.count()
        result = snapshot(service, producer)
        assert result.preservation_blocks_new_risk and result.equity == 200
        assert result.peak_equity == result.day_start_equity == result.week_start_equity == D('100')
        assert ledger.count() == before and other.count() == 0
        assert ledger.verify_incremental()[0]
    finally:
        other.close(); ledger.close()

def test_account_start_does_not_seed_unknown_credit_before_the_first_decision(tmp_path, eurusd, pg_dsn):
    from dataclasses import replace
    from test_single_session_lease import config
    from test_mt5_worker_funding import connection
    from vati.accounts import AccountRegistry
    from vati.app.account_service import AccountCoordinatorService
    from vati.risk.serde import contract_to_dict
    from conftest import historical_mandate_dict
    sdk, worker, adapter, now = connection(tmp_path)
    original = sdk.account_info
    def missing_credit():
        a = original(); del a.credit; return a
    sdk.account_info = missing_credit
    sdk.history_deals_get = lambda *a, **kw: None
    import os
    from urllib.parse import urlsplit, urlunsplit
    from psycopg.conninfo import conninfo_to_dict
    database = conninfo_to_dict(pg_dsn)["dbname"]
    uri = urlunsplit(urlsplit(os.environ["VATI_TEST_PG_DSN"])._replace(path="/"+database))
    cfg = config(tmp_path, eurusd, ledger=uri)
    registry = AccountRegistry(cfg.registry_path)
    registry.add(replace(registry.get(cfg.account_alias), alias='native'))
    cfg.account_alias = 'native'
    cfg.mandate = historical_mandate_dict(venue='paper', mode='DEMO_TRADER', account_alias='native',
        allowed_strategies=['FX-TREND-PULLBACK-01'])
    cfg.instruments = [{'symbol': 'GBPUSD', 'base': 'GBP', 'quote': 'USD',
        'contract': contract_to_dict(replace(eurusd, symbol='GBPUSD', base_currency='GBP'))}]
    # The existing builder uses actual disposable PostgreSQL authority.
    # Native SDK calls remain an explicit simulation; no broker or new order
    # authority is admitted by installing the signed fixture account reader.
    service = AccountCoordinatorService(cfg, clock=lambda: now['ms']).build()
    service.adapter = service.lifecycle.adapter = adapter
    try:
        service.start()
        assert service.peak_equity == service.day_start_equity == service.week_start_equity == 0
        assert not sdk.sent and service.adapter.positions() == []
    finally:
        service.lease.release(now_ms=now['ms'])
        service._lease_store.close(); service._ledger.close()
