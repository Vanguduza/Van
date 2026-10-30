"""Original mandate proof survives actual PostgreSQL commit/reopen boundaries."""
from contextlib import contextmanager

import pytest

from conftest import NOW, snapshot, mandate_dict
from test_native_risk_account_context import mt5_context
from test_native_risk_history_inputs import record
from test_postgres_ledger_isolation import pg_dsn
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk import TradingMandate
from vati.risk.account_context import context_for_account
from vati.risk.mandate_source import capture_mandate_source, original_native_risk_mandate
from vati.risk.native_history import NativeRiskSourceUnavailable


@pytest.mark.parametrize('lost_ack',[False,True])
def test_original_postgres_policy_reopen_expiry_scope_and_actual_commit_ack_loss(pg_dsn,tmp_path,eurusd,monkeypatch,lost_ack):
    unused,adapter,account,_,_=mt5_context(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='original-policy')
    other=PostgresLedger(pg_dsn,ledger_name='other-policy');reopened=None
    try:
        capture=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=capture)
        facts=snapshot(eurusd,account_alias=account.account_alias,balance=account.balance,equity=account.equity,native_account_context=context)
        raw=mandate_dict(account_alias=facts.account_alias,venue=facts.symbol_contract.venue)
        source=capture_mandate_source(TradingMandate.from_mapping(raw),raw,now_ms=NOW*1000)
        assert source['state']=='ORIGINAL_BOUND'
        original_atomic=ledger.atomic;depth=0
        @contextmanager
        def commit_then_lose_reply():
            nonlocal depth
            outer=depth==0;depth+=1
            try:
                with original_atomic():yield ledger
            finally:depth-=1
            if outer:raise OSError('fixture actual PostgreSQL commit acknowledgement loss')
        if lost_ack:monkeypatch.setattr(ledger,'atomic',commit_then_lose_reply)
        def attach(payload):payload['inputs']['original_mandate_source']=source
        if lost_ack:
            with pytest.raises(OSError,match='acknowledgement loss'):
                with ledger.atomic():record(ledger,facts,grant=raw,damage=attach)
        else:record(ledger,facts,grant=raw,damage=attach)
        events=list(ledger.iter(EventKind.RISK_DECISION));assert len(events)==1
        reopened=PostgresLedger(pg_dsn,ledger_name='original-policy')
        result=original_native_risk_mandate(reopened,events[0].hash,available_at_ms=(NOW+100*86400)*1000)
        assert result['state']=='ORIGINAL_BOUND' and result['effective_policy']==source['effective_policy']
        assert result['execution_authority'] is result['current_policy_qualified'] is False
        with pytest.raises(NativeRiskSourceUnavailable):
            original_native_risk_mandate(other,events[0].hash,available_at_ms=NOW*1000)
        assert other.count()==0 and ledger.count(EventKind.RISK_DECISION)==1 and ledger.count(EventKind.ORDER_COMMAND)==0
        assert ledger.verify_chain()[0]
    finally:
        if reopened is not None:reopened.close()
        other.close();ledger.close()
