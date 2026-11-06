"""Positive reconciliation and ambiguous original order ownership."""
from dataclasses import asdict
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from test_native_entry_volume import dispatched,observe
from vati.core import EventKind,make_event
from vati.execution.base import ExecutionReceipt
from vati.risk.contracts import NativeAccountRiskContext
from vati.risk.native_entry_volume import NativeEntryVolumeError
from vati.risk.physical_pending import project_pending_risk
from vati.risk.serde import contract_from_dict,snapshot_from_dict


def native_receipt(ledger,command,clock,*,status,filled):
    clock['ms']+=1
    r=ExecutionReceipt(command.trade_intent_id,command.decision_hash,command.venue,status,D(filled),
        command.entry_price if D(filled)>0 else None,command.entry_price,command.entry_price,
        command.entry_price,True,clock['ms'],clock['ms'],broker_order_id='2',broker_position_id='3').sealed()
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',asdict(r),
        event_time_ms=clock['ms'],received_time_ms=clock['ms'],correlation_id=command.trade_intent_id))


def test_original_partial_readback_repairs_contradiction_while_retaining_full_possible_entry_risk(tmp_path,eurusd):
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd,
        receipt_changes={'status':'REJECTED','filled_qty':D('0'),'average_fill':None})
    try:
        read=book.lookup_entry(command.command_hash,binding['source_ref'])
        context=NativeAccountRiskContext(**read['observation']['native_account_context'])
        original=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.hash==binding['original_input_ref'])
        contract=contract_from_dict(original.payload['inputs']['snapshot']['symbol_contract'])
        owner=SimpleNamespace();observe(ledger,clock,[(1,2,7,200000,None)])
        assert project_pending_risk(owner,ledger,context,(),now_ms=clock['ms'],contracts={'EURUSD':contract})[1]
        native_receipt(ledger,command,clock,status='PARTIAL',filled='.02')
        pending,issue=project_pending_risk(owner,ledger,context,(),now_ms=clock['ms'],contracts={'EURUSD':contract})
        assert issue=='' and len(pending)==1 and pending[0].quantity==command.quantity
        assert pending[0].execution_authority is pending[0].protection_confirmed is False
        assert book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])['state']=='ORIGINAL_GROSS_ENTRY_VOLUME_OBSERVED'
        assert ledger.count(EventKind.ORDER_COMMAND)==1
    finally:ledger.close()


def test_two_original_parents_cannot_claim_the_same_native_order_volume(tmp_path,eurusd):
    from test_physical_order_exposure import command as another_command
    ledger,adapter,book,clock,command,binding=dispatched(tmp_path,eurusd)
    try:
        original=next(e for e in ledger.iter(EventKind.RISK_DECISION) if e.hash==binding['original_input_ref'])
        facts=snapshot_from_dict(original.payload['inputs']['snapshot'])
        _,other=another_command(ledger,facts,'another-original-parent')
        native_receipt(ledger,other,clock,status='ACCEPTED',filled='0')
        observe(ledger,clock,[(1,2,7,200000,None)])
        with pytest.raises(NativeEntryVolumeError,match='MULTIPLE_COMMANDS'):
            book.lookup_entry_volume(command.command_hash,binding['source_ref'],available_at_ms=clock['ms'])
    finally:ledger.close()
