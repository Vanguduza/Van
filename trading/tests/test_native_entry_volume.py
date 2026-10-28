"""Original dispatch/receipt/deal join, gross quantities and no re-entry credit."""
from dataclasses import asdict,replace
from decimal import Decimal as D,localcontext,Inexact,Rounded
from types import SimpleNamespace

import pytest

from test_native_fee_terms import original_fee_entry
from vati.core import EventKind,make_event
from vati.execution.base import ExecutionReceipt
from vati.funding.deals import NativeDeal,NativeDealStatement
from vati.funding.deal_journal import DealBook
from vati.risk.native_entry_volume import NativeEntryVolumeError


def dispatched(tmp_path,eurusd,*,ledger=None,receipt_changes=None):
    ledger,adapter,book,clock,command,binding=original_fee_entry(tmp_path,eurusd,ledger=ledger)
    now=clock['ms']+1
    payload=asdict(command)|{'native_entry_margin_ref':binding['record_ref']}
    event=make_event(EventKind.ORDER_COMMAND,'vati-execution-router',payload,
        event_time_ms=now,received_time_ms=now,decision_time_ms=now,correlation_id=command.trade_intent_id)
    ledger.append(event)
    receipt=ExecutionReceipt(command.trade_intent_id,command.decision_hash,command.venue,'PARTIAL',D('.05'),
        command.entry_price,command.entry_price,command.entry_price,command.entry_price,
        True,now+1,now+1,broker_order_id='2',broker_position_id='3',fees=D('0'))
    receipt=replace(receipt,**(receipt_changes or {})).sealed()
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',asdict(receipt),
        event_time_ms=now+1,received_time_ms=now+1,correlation_id=command.trade_intent_id))
    clock['ms']=now+2
    return ledger,adapter,book,clock,command,binding


def observe(ledger,clock,rows):
    at=clock['ms']
    deals=tuple(NativeDeal(i,order,3,symbol,at,'PARTIALLY_FILLED',1230000,volume,D('1.1'),fee,2,None)
        for i,order,symbol,volume,fee in rows)
    return DealBook(ledger,clock=lambda:at).record_statement(NativeDealStatement('CTRADER','DEMO','fixture',12345,2,
        'EUR',at-1000,at,at,deals,1))


def test_actual_original_entry_receipts_and_native_deals_retain_exact_gross_volume(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        observe(ledger,clock,[(1,2,7,200000,D('-.01')),(2,2,7,300000,None)])
        count=ledger.count();calls=len(adapter.transport.calls)
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
            result=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        assert result['state']=='ORIGINAL_GROSS_ENTRY_VOLUME_OBSERVED'
        assert result['observed_gross_filled_volume_cents']==500000
        assert result['observed_lot_equivalent']=={'numerator':'1','denominator':'20'}
        assert result['original_command_volume_cents']==1230000
        assert result['deal_facts'][0]['raw_commission']=='-0.01'
        assert result['deal_facts'][1]['raw_commission'] is None
        assert result['remaining_entry_allowance'] is None and result['fee_or_exit_budget_credit'] is False
        assert result['parent_lifetime_budget_complete'] is result['execution_authority'] is result['reservation_qualified'] is False
        assert ledger.count()==count and len(adapter.transport.calls)==calls
    finally:ledger.close()


def test_duplicate_native_statements_and_other_orders_never_reduce_or_repeat_gross_entries(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        rows=[(1,2,7,200000,D('-.01')),(2,2,7,300000,None)]
        observe(ledger,clock,rows)
        clock['ms']+=1
        # Preserve original economic row times when repeating a vintage.
        statement=list(ledger.iter(EventKind.FUNDING_DEAL_STATEMENT))[0].payload['statement']
        repeated=NativeDealStatement.from_body(statement)
        DealBook(ledger,clock=lambda:clock['ms']).record_statement(replace(repeated,observed_at_ms=clock['ms'],to_ms=clock['ms']))
        observe(ledger,clock,[(3,99,7,500000,D('99'))])
        result=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        assert result['observed_gross_filled_volume_cents']==500000 and len(result['deal_facts'])==2
        assert result['remaining_entry_allowance'] is None and result['fee_or_exit_budget_credit'] is False
    finally:ledger.close()


def test_missing_deals_are_not_zero_outstanding_and_late_conflicts_refuse_current_use(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        empty=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        assert empty['state']=='NO_MATCHING_OBSERVED_DEALS_NOT_ZERO_OUTSTANDING'
        assert empty['remaining_entry_allowance'] is None
        observe(ledger,clock,[(1,2,7,200000,None)])
        clock['ms']+=1;observe(ledger,clock,[(1,2,7,0,None)])
        with pytest.raises(NativeEntryVolumeError,match='HISTORY_CONFLICT'):
            book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
    finally:ledger.close()


def test_symbol_conflict_cannot_attribute_a_native_order_to_another_instrument(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        observe(ledger,clock,[(1,2,99,200000,None)])
        with pytest.raises(NativeEntryVolumeError,match='SYMBOL_CONFLICT'):
            book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
    finally:ledger.close()


def test_native_gross_overfill_is_visible_without_a_negative_or_reopened_allowance(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        observe(ledger,clock,[(1,2,7,1230000,None),(2,2,7,300000,None)])
        result=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        assert result['state']=='NATIVE_GROSS_VOLUME_EXCEEDS_ORIGINAL_COMMAND'
        assert result['observed_gross_filled_volume_cents']==1530000
        assert result['remaining_entry_allowance'] is None and result['execution_authority'] is False
    finally:ledger.close()


def test_native_future_deal_is_not_borrowed_before_its_original_publication(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        before=clock['ms'];clock['ms']+=1000
        observe(ledger,clock,[(1,2,7,200000,None)])
        result=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=before)
        assert result['observed_gross_filled_volume_cents']==0
        assert result['state']=='NO_MATCHING_OBSERVED_DEALS_NOT_ZERO_OUTSTANDING'
        assert result['deal_statement_knowledge_anchor'] is None and result['remaining_entry_allowance'] is None
        assert book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])['observed_gross_filled_volume_cents']==200000
    finally:ledger.close()


def test_actual_pending_owner_cannot_release_on_rejection_contradicted_by_original_native_fill(tmp_path,eurusd):
    from vati.risk.physical_pending import project_pending_risk
    from vati.risk.contracts import NativeAccountRiskContext
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd,
        receipt_changes={'status':'REJECTED','filled_qty':D('0'),'average_fill':None})
    try:
        q=book.lookup_entry(command.command_hash,binding['source_ref'])['observation']
        context=NativeAccountRiskContext(**q['native_account_context']);owner=SimpleNamespace()
        pending,issue=project_pending_risk(owner,ledger,context,(),now_ms=clock['ms'],contracts={})
        assert pending==() and issue==''
        observe(ledger,clock,[(1,2,7,200000,None)])
        result=book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
        assert result['state']=='NATIVE_DEALS_CONTRADICT_NO_EFFECT_RECEIPT'
        pending,issue=project_pending_risk(owner,ledger,context,(),now_ms=clock['ms'],contracts={})
        assert pending==() and issue.startswith('NATIVE_PENDING_RISK_UNAVAILABLE:'), 'actual native fill must invalidate a no-effect release'
    finally:ledger.close()


def test_actual_pending_owner_refuses_native_volume_above_the_original_command(tmp_path,eurusd):
    from vati.risk.physical_pending import project_pending_risk
    from vati.risk.contracts import NativeAccountRiskContext
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        q=book.lookup_entry(command.command_hash,binding['source_ref'])['observation']
        context=NativeAccountRiskContext(**q['native_account_context'])
        observe(ledger,clock,[(1,2,7,1230000,None),(2,2,7,300000,None)])
        pending,issue=project_pending_risk(SimpleNamespace(),ledger,context,(),now_ms=clock['ms'],contracts={})
        assert pending==() and issue.startswith('NATIVE_PENDING_RISK_UNAVAILABLE:')
    finally:ledger.close()


def test_a_staged_writer_cannot_supply_original_native_entry_volume(tmp_path,eurusd):
    from vati.core.ledger import LedgerError
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        with ledger.atomic():
            with pytest.raises(LedgerError,match='committed_source_read'):
                book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
    finally:ledger.close()
