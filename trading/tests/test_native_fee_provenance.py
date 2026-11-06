"""A historical default zero is not a measured native commission."""
from decimal import Decimal as D
from dataclasses import asdict,replace
from copy import deepcopy
from decimal import localcontext,Inexact,Rounded

import pytest

from test_ctrader_close_fee_knowledge import account_close_review
from vati.core import EventKind,Ledger
from vati.execution.router import ExecutionRouter
from test_native_receipt_fee_knowledge import native_fill
from vati.execution.ctrader.charge_source import validate_charge_source
from vati.core.canonical import canonical_hash


def test_historical_default_zero_close_without_native_charge_source_stays_unknown(tmp_path,monkeypatch):
    original=ExecutionRouter._log
    def legacy_log(self,kind,payload,**kwargs):
        payload=dict(payload)
        if kind is EventKind.EXECUTION_RECEIPT:
            payload.pop('recorded_native_charge',None)
        return original(self,kind,payload,**kwargs)
    monkeypatch.setattr(ExecutionRouter,'_log',legacy_log)
    ledger=Ledger(tmp_path/'historical-default-zero.sqlite')
    try:
        out=account_close_review(ledger,commission=0)
        assert out['receipt'].fees==D(0) and out['receipt'].status=='FILLED'
        assert out['review'].pnl_basis=='UNKNOWN_CHARGES'
        assert out['review'].broker_ok is False and ledger.verify_chain()[0]
    finally:ledger.close()


def test_measured_zero_close_survives_actual_native_provenance_and_durable_review(tmp_path):
    ledger=Ledger(tmp_path/'measured-zero.sqlite')
    try:
        out=account_close_review(ledger,commission=0)
        row=next(e for e in ledger.iter(EventKind.EXECUTION_RECEIPT) if e.payload.get('exit_action')=='CLOSE')
        source=row.payload['recorded_native_charge']
        assert source['raw_commission']==0 and source['money_digits']==2 and D(source['recorded_fee'])==0
        assert source['closing'] is True and source['fees_final'] is source['cash_reconciled'] is False
        assert out['review'].pnl==D('48.20') and out['review'].pnl_basis=='PRICE_DERIVED_NET_RECORDED_CHARGES'
        assert row.payload['receipt_hash']==out['receipt'].receipt_hash and ledger.verify_chain()[0]
    finally:ledger.close()


def test_old_entry_without_native_charge_evidence_cannot_supply_known_parent_costs(tmp_path,monkeypatch):
    from vati.execution.ctrader.adapter import CtraderAdapter
    original=CtraderAdapter.recorded_native_charge
    def old_entry(self,receipt):
        return None if receipt.trade_intent_id else original(self,receipt)
    monkeypatch.setattr(CtraderAdapter,'recorded_native_charge',old_entry)
    ledger=Ledger(tmp_path/'old-entry.sqlite')
    try:
        out=account_close_review(ledger)
        assert out['entry'].fees==D('1') and out['receipt'].fees==D('3.25')
        assert out['review'].pnl_basis=='UNKNOWN_CHARGES' and out['review'].broker_ok is False
        assert ledger.verify_chain()[0]
    finally:ledger.close()


@pytest.mark.parametrize('defect',['alias','kind','order','position','volume','price','execution',
    'scalar','precision','fee-integer','future','finality','cash','seal'])
def test_resealed_foreign_or_conflicting_native_charge_cannot_be_a_scalar_echo(defect):
    with native_fill(commission=-350) as (adapter,command,receipt):
        source=deepcopy(adapter.recorded_native_charge(receipt));assert source is not None
        if defect=='alias':source['account_alias']='foreign'
        elif defect=='kind':source['closing']=True
        elif defect=='order':source['native_order_id']+=1
        elif defect=='position':source['native_position_id']+=1
        elif defect=='volume':source['filled_volume_cents']+=1
        elif defect=='price':source['execution_price']='99'
        elif defect=='execution':source['execution_ref']='f'*64
        elif defect=='scalar':source['recorded_fee']='0'
        elif defect=='precision':source['money_digits']=3
        elif defect=='fee-integer':source['raw_commission']=True
        elif defect=='future':source['captured_at_ms']=receipt.received_time_unix_ms+1
        elif defect=='finality':source['fees_final']=True
        elif defect=='cash':source['cash_reconciled']=True
        if defect!='seal':source['source_ref']=canonical_hash({k:v for k,v in source.items() if k!='source_ref'})
        else:source['source_ref']='f'*64
        with pytest.raises(ValueError):
            validate_charge_source(source,receipt,account_alias=command.account_alias,closing=False)


def test_native_charge_survives_actual_receipt_availability_reseal_without_changing_original():
    with native_fill(commission=0) as (adapter,command,receipt):
        original=asdict(receipt)
        published=replace(receipt,received_time_unix_ms=receipt.received_time_unix_ms+7,receipt_hash='').sealed()
        source=adapter.recorded_native_charge(published)
        assert source['raw_commission']==0 and source['closing'] is False
        assert source['captured_at_ms']==receipt.received_time_unix_ms
        assert source['execution_ref']==adapter.recorded_native_charge(receipt)['execution_ref']
        assert published.receipt_hash!=receipt.receipt_hash and asdict(receipt)==original


def test_native_charge_parser_is_exact_under_hostile_decimal_context():
    with native_fill(commission=-(2**63),digits=18) as (adapter,command,receipt):
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=ctx.traps[Rounded]=True;flags=dict(ctx.flags)
            source=adapter.recorded_native_charge(receipt)
            assert source['raw_commission']==-(2**63) and D(source['recorded_fee'])==D('9.223372036854775808')
            assert dict(ctx.flags)==flags


@pytest.mark.parametrize('field',['native_account_id','native_symbol_id'])
def test_review_binds_closing_native_charge_scope_to_original_entry(tmp_path,monkeypatch,field):
    original=ExecutionRouter._log
    def foreign_close(self,kind,payload,**kwargs):
        payload=deepcopy(payload)
        if kind is EventKind.EXECUTION_RECEIPT and payload.get('exit_action')=='CLOSE':
            source=payload['recorded_native_charge'];source[field]+=1
            source['source_ref']=canonical_hash({k:v for k,v in source.items() if k!='source_ref'})
        return original(self,kind,payload,**kwargs)
    monkeypatch.setattr(ExecutionRouter,'_log',foreign_close)
    ledger=Ledger(tmp_path/'foreign-native-charge.sqlite')
    try:
        out=account_close_review(ledger)
        assert out['receipt'].status=='FILLED' and out['receipt'].fees==D('3.25')
        assert out['review'].pnl_basis=='UNKNOWN_CHARGES' and out['review'].broker_ok is False
        assert ledger.verify_chain()[0]
    finally:ledger.close()
