"""Actual PostgreSQL evidence cannot be borrowed across native ledger scopes."""
import pytest
from test_postgres_ledger_isolation import pg_dsn
from test_native_balance_reconciliation import mark,snapshot,observe,cash
from test_funding_risk_fence import native
from vati.core.ledger_pg import PostgresLedger
from vati.funding.risk_fence import funding_risk_fence


@pytest.mark.parametrize('external_capital',[False,True])
def test_postgres_native_risk_fence_preserves_original_named_evidence_and_connection(pg_dsn,external_capital):
    ledger=PostgresLedger(pg_dsn,ledger_name='funding-risk-original')
    other=PostgresLedger(pg_dsn,ledger_name='funding-risk-other')
    try:
        point=mark(3000,balance='200',equity='200',version=2) if external_capital else mark(3000,equity='98')
        snapshot(ledger,mark(1000));snapshot(ledger,point)
        observe(ledger,cash=[cash()] if external_capital else [])
        adapter,current=native(point);count=ledger.count();requests=list(adapter.transport.requests)
        with ledger.read_snapshot():
            original=funding_risk_fence(ledger,adapter,current,now_ms=7000)
        assert original.available is (not external_capital)
        if external_capital:assert original.reason.endswith('FLOW_ADJUSTED_RISK_NOT_QUALIFIED')
        assert not funding_risk_fence(other,adapter,current,now_ms=7000).available
        assert ledger.count()==count and other.count()==0 and adapter.transport.requests==requests
        snapshot(ledger,point)
        assert ledger.count()==count+1 and ledger.verify_incremental()[0]
    finally:
        ledger.close();other.close()
