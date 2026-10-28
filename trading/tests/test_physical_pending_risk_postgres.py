"""Original pending risk survives independent PostgreSQL connections."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as N
import pytest

from conftest import NOW,snapshot,intent,mandate_dict
from test_postgres_ledger_isolation import pg_dsn
from test_native_risk_account_context import mt5_context
from test_native_risk_history_index import other_context
from test_physical_order_exposure import command,receipt
from test_physical_snapshot_producers import producer
from test_physical_pending_risk import position
from vati.core.ledger_pg import PostgresLedger
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account
from vati.risk.physical_pending import PhysicalPendingRisk,project_pending_risk
from vati.risk import RiskAuthority,TradingMandate


@pytest.mark.parametrize('kind',['single','account'])
def test_actual_owners_reopen_original_pending_risk_and_native_no_effect_release(pg_dsn,tmp_path,eurusd,kind):
    unused,adapter,account,_,_=mt5_context(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='pending-risk')
    reopened=PostgresLedger(pg_dsn,ledger_name='pending-risk')
    foreign=PostgresLedger(pg_dsn,ledger_name='foreign-risk')
    try:
        captured=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=captured)
        facts=snapshot(eurusd,account_alias=account.account_alias,balance=account.balance,
            equity=account.equity,native_account_context=context)
        _,cmd=command(ledger,facts,'pg-pending')
        receipt(ledger,cmd,status='ACCEPTED')
        b=other_context(ledger,adapter,account,facts,alias='second_alias')
        current=replace(account,account_alias=b.account_alias,
            funding_mark=replace(account.funding_mark,account_alias=b.account_alias),
            used_margin=D(0),free_margin=account.equity,margin_level_pct=None)
        service=producer(kind,reopened,adapter,current,b);now=NOW*1000+100
        def capture():
            if kind=='single':return service.snapshot(now_ms=now,quote_age_ms=0,strategy_id=intent().strategy_id)
            service.clock=lambda:now
            return service._snapshot_for(N(symbol='EURUSD',strategy_id=intent().strategy_id))
        grant=TradingMandate.from_mapping(mandate_dict(account_alias=b.account_alias,
            max_open_stop_risk='0.005',max_positions_per_instrument=10,max_total_positions=20))
        first=capture()
        assert not first.preservation_blocks_new_risk and first.reconciliation_ok
        assert first.pending_risk_commitments[0].quantity==cmd.quantity
        decision=RiskAuthority(grant).evaluate_safe(intent(account_alias=b.account_alias),first)
        assert decision.reason_code=='PORTFOLIO_HEAT'
        out,issue=project_pending_risk(N(),foreign,b.native_account_context,(),now_ms=now)
        assert out==() and issue.startswith('NATIVE_PENDING_RISK_UNAVAILABLE:')
        # A source-bound native no-effect receipt clears stop risk, not cash.
        receipt(ledger,cmd,status='CANCELLED',when=4,native_entry_observation={
            'schema':'vati.native-entry-observation/1','command_hash':cmd.command_hash,'source':'ORIGINAL_NATIVE_RESULT'})
        final=capture()
        assert final.pending_risk_commitments==() and not final.preservation_blocks_new_risk
        assert RiskAuthority(grant).evaluate_safe(intent(account_alias=b.account_alias),final).reason_code=='OK'
        assert ledger.verify_chain()[0] and foreign.count()==0
    finally:
        foreign.close();reopened.close();ledger.close()


def test_partial_native_coverage_uses_original_receipt_identity_after_pg_reopen(pg_dsn,tmp_path,eurusd):
    unused,adapter,account,_,_=mt5_context(tmp_path);unused.close()
    ledger=PostgresLedger(pg_dsn,ledger_name='partial-risk');reopened=None
    try:
        captured=capture_cached_mt5(ledger,account,now_ms=10000)
        context=context_for_account(ledger,adapter,account,now_ms=10000,mt5_capture=captured)
        facts=snapshot(eurusd,account_alias=account.account_alias,balance=account.balance,equity=account.equity,
            native_account_context=context)
        _,cmd=command(ledger,facts,'pg-partial');receipt(ledger,cmd,status='PARTIAL',filled=str(cmd.quantity/2))
        reopened=PostgresLedger(pg_dsn,ledger_name='partial-risk')
        runtime=PhysicalPendingRisk(reopened,context,now_ms=NOW*1000+100)
        out=runtime.refresh((position(cmd,eurusd,quantity=cmd.quantity/2),),now_ms=NOW*1000+100)
        assert len(out)==1 and out[0].quantity==cmd.quantity/2 and out[0].new_position_slots==0
        assert out[0].protection_confirmed is out[0].execution_authority is False
    finally:
        if reopened is not None:reopened.close()
        ledger.close()
