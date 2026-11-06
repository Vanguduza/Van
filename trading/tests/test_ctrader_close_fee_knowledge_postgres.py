"""Original native close charge readback across PostgreSQL owners."""
import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_ctrader_close_fee_knowledge import account_close_review
from vati.core.ledger_pg import PostgresLedger
from vati.execution.recorded_close_costs import recorded_close_cost_entry
from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.core import EventKind
from decimal import Decimal as D


@pytest.mark.parametrize('missing,commission,expected_fee,expected_total',[
    ((),-325,D('3.25'),D('4.25')),(('commission',),-325,None,None),((),0,D(0),D('1'))])
def test_pg_native_close_costs_reopen_original_receipt_without_provider_or_foreign_scope(pg_dsn,missing,commission,expected_fee,expected_total):
    writer=PostgresLedger(pg_dsn,ledger_name='native-close-fees')
    reader=PostgresLedger(pg_dsn,ledger_name='native-close-fees')
    other=PostgresLedger(pg_dsn,ledger_name='foreign-native-close-fees')
    try:
        out=account_close_review(writer,missing=missing,commission=commission);count=writer.count()
        args={'trade_intent_id':out['command'].trade_intent_id,'venue':'ctrader',
              'account_alias':out['command'].account_alias,'available_at_ms':out['closed_at_ms']}
        projected=recorded_close_cost_entry(reader,out['original_entry_row'],**args)
        assert projected['fees']==expected_total and out['receipt'].fees==expected_fee
        original=next(e for e in reader.iter(EventKind.EXECUTION_RECEIPT) if e.payload.get('exit_action')=='CLOSE')
        receipt=AccountTradeLifecycle._receipt_from_payload(original.payload)
        assert receipt.receipt_hash==out['receipt'].receipt_hash and receipt.fees==out['receipt'].fees
        assert projected['recorded_close_costs']['exit_receipt_refs']==[original.hash]
        foreign=recorded_close_cost_entry(other,out['original_entry_row'],**args)
        assert foreign['fees'] is None and other.count()==0
        assert writer.count()==count and writer.verify_chain()[0]
    finally:other.close();reader.close();writer.close()
