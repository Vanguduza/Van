"""Pinned native units, absence, conditional charge and original SQL vintage."""
from dataclasses import replace
from decimal import Decimal as D,localcontext,Inexact,Rounded
from fractions import Fraction as F

import pytest

from vati.core import EventKind
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.transport import DEMO_HOST
from vati.risk.native_fee_terms import NativeCommissionTerms,NativeFeeTermsError


def contract(**changes):
    detail=dict(symbolId=7,digits=5,pipPosition=4,lotSize=10000000,
        minVolume=1000,maxVolume=100000000,stepVolume=1000,
        commissionType=3,preciseTradingCommissionRate=17500,preciseMinCommission=250000000,
        minCommissionType=1,minCommissionAsset='USD')
    detail.update(changes)
    return NativeSymbolContract.capture(account_id=12345,transport_host=DEMO_HOST,
        light=dict(symbolId=7,symbolName='EURUSD',enabled=True,baseAssetId=2,quoteAssetId=3),
        detail=detail,received_at_ms=900)


@pytest.mark.parametrize('kind,rate,volume,turnover,expected,denomination',[
    (1,5000000000,10000000,F(1000000),F(50),'USD'),
    (2,1500000000,2500000,None,F(15,4),'USD'),
    (3,17500,10000000,F(1000),F(7,4),'NATIVE_QUOTE_ASSET'),
    (4,1500000000,2500000,None,F(15,4),'NATIVE_QUOTE_ASSET')])
def test_all_pinned_native_commission_types_have_correct_exact_units(kind,rate,volume,turnover,expected,denomination):
    terms=NativeCommissionTerms(contract(commissionType=kind,preciseTradingCommissionRate=rate))
    with localcontext() as context:
        context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
        estimate=terms.one_charge(native_volume=volume,usd_turnover=turnover,quote_turnover=turnover)
    assert F(int(estimate['amount']['numerator']),int(estimate['amount']['denominator']))==expected
    assert estimate['denomination']==denomination
    assert estimate['worst_case_fee'] is None and estimate['complete_future_obligation'] is False
    assert estimate['execution_authority'] is estimate['reservation_qualified'] is False
    # The observed2.50minimum is deliberately not mistaken for a complete,
    # converted reservation. The arithmetic above is before that minimum.
    assert terms.body()['minimum']['amount']=={'numerator':'5','denominator':'2'}


@pytest.mark.parametrize('field',['commissionType','preciseTradingCommissionRate','preciseMinCommission',
    'minCommissionType','minCommissionAsset'])
def test_absent_terms_never_become_zero_or_deprecated_guessed_rates(field):
    original=contract().metadata;del original['detail'][field]
    original['detail'].update(commission=0,minCommission=0)
    captured=NativeSymbolContract.capture(account_id=12345,transport_host=DEMO_HOST,
        light=original['light'],detail=original['detail'],received_at_ms=900)
    body=NativeCommissionTerms(captured).body()
    assert body['state']=='NATIVE_TERMS_INCOMPLETE' and field in body['missing_fields']
    if field=='preciseTradingCommissionRate':assert body['rate'] is None
    assert body['complete_future_obligation'] is False and body['charge_count_bound'] is None
    assert body['other_cost_field_presence']['pnlConversionFeeRate'] is False
    assert body['other_cost_field_presence']['swapLong'] is False


def test_quote_asset_minimum_is_scoped_by_native_asset_id_and_copies_are_immutable():
    terms=NativeCommissionTerms(contract(minCommissionType=2))
    body=terms.body();assert body['minimum']['native_quote_asset_id']==3
    assert body['minimum']['currency_label'] is None
    body['rate']['raw_precise_rate']=999999
    assert terms.body()['rate']['raw_precise_rate']==17500


def test_signed_native_rate_stays_signed_and_cannot_be_consumed_as_a_credit():
    terms=NativeCommissionTerms(contract(preciseTradingCommissionRate=-17500))
    assert terms.body()['rate']['raw_precise_rate']==-17500
    with pytest.raises(NativeFeeTermsError,match='SIGN_CONVENTION'):
        terms.one_charge(native_volume=10000000,quote_turnover=F(1000))


def test_unrecognized_native_commission_type_is_an_explicit_unsupported_state():
    body=NativeCommissionTerms(contract(commissionType=99)).body()
    assert body['state']=='NATIVE_TERMS_UNSUPPORTED' and body['rate'] is None


@pytest.mark.parametrize('field,value',[('preciseTradingCommissionRate',True),('preciseMinCommission',1.5),
    ('preciseTradingCommissionRate',2**63),('minCommissionAsset',' USD'),('minCommissionType',False)])
def test_malformed_native_term_values_are_refused(field,value):
    with pytest.raises(NativeFeeTermsError):NativeCommissionTerms(contract(**{field:value}))


@pytest.mark.parametrize('turnover',[None,1.0,True,F(-1),F(0)])
def test_turnover_is_an_explicit_exact_scenario_input_and_never_an_inferred_fx_rate(turnover):
    terms=NativeCommissionTerms(contract())
    with pytest.raises(NativeFeeTermsError,match='EXPLICIT_EXACT'):
        terms.one_charge(native_volume=10000000,quote_turnover=turnover)


def original_fee_entry(tmp_path,eurusd,*,ledger=None):
    from test_native_margin_book import setup_book
    from test_entry_margin_binding import entry_command
    from test_native_risk_history_inputs import record
    owner,adapter,old,book,clock,facts=setup_book(tmp_path,eurusd,ledger=ledger)
    native=contract();adapter.symbols['EURUSD']=replace(adapter.symbols['EURUSD'],native_contract=native,contract_revision=native.revision)
    original=record(owner,replace(facts,used_margin=D('0'),free_margin=D('10000'),margin_level_pct=None))
    command=replace(entry_command(original),quantity=D('.123'),command_hash='').sealed()
    receipt=book.capture_entry(adapter,original.hash,command,deadline_ms=clock['ms']+1000)
    return owner,adapter,book,clock,command,receipt


def test_actual_original_entry_fee_readback_uses_durable_contract_not_refreshed_adapter(tmp_path,eurusd):
    from vati.core import Ledger
    from vati.risk.native_margin_book import NativeMarginBook
    ledger,adapter,book,clock,command,receipt=original_fee_entry(tmp_path,eurusd)
    try:
        before=ledger.count();calls=len(adapter.transport.calls)
        first=book.lookup_entry_fee_terms(command.command_hash,receipt['source_ref'])
        assert first['entry_record_ref']==receipt['record_ref']
        assert first['terms']['rate']['raw_precise_rate']==17500
        refreshed=contract(preciseTradingCommissionRate=99999999)
        adapter.symbols['EURUSD']=replace(adapter.symbols['EURUSD'],native_contract=refreshed,contract_revision=refreshed.revision)
        clock['ms']+=10**9
        reader=Ledger(ledger.path)
        try:assert NativeMarginBook(reader).lookup_entry_fee_terms(command.command_hash,receipt['source_ref'])==first
        finally:reader.close()
        assert ledger.count()==before and len(adapter.transport.calls)==calls
        assert ledger.count(EventKind.ORDER_COMMAND)==0 and first['execution_authority'] is False
        assert first['quote_valid_until_ms']<clock['ms']
    finally:ledger.close()


@pytest.mark.parametrize('kind,minimum_kind,asset,expected_state,expected',[
    (2,1,'USD','APPLIED_SAME_NATIVE_DENOMINATION',F(5,2)),
    (4,2,'USD','APPLIED_SAME_NATIVE_DENOMINATION',F(5,2)),
    (2,1,'EUR','NATIVE_MINIMUM_ASSET_MAPPING_OR_CONVERSION_UNAVAILABLE',None),
    (4,1,'USD','NATIVE_MINIMUM_ASSET_MAPPING_OR_CONVERSION_UNAVAILABLE',None)])
def test_native_minimum_only_combines_commissions_of_the_same_proven_denomination(kind,minimum_kind,asset,expected_state,expected):
    terms=NativeCommissionTerms(contract(commissionType=kind,preciseTradingCommissionRate=100000000,
        minCommissionType=minimum_kind,minCommissionAsset=asset))
    result=terms.one_charge(native_volume=10000000)
    assert result['amount']=={'numerator':'1','denominator':'1'}
    assert result['minimum_state']==expected_state
    value=result['minimum_adjusted_amount']
    assert (None if value is None else F(int(value['numerator']),int(value['denominator'])))==expected
    assert result['worst_case_fee'] is None


def test_explicit_zero_rate_does_not_erase_a_nonzero_native_minimum():
    terms=NativeCommissionTerms(contract(commissionType=2,preciseTradingCommissionRate=0))
    result=terms.one_charge(native_volume=10000000)
    assert result['amount']['numerator']=='0'
    assert result['minimum_adjusted_amount']=={'numerator':'5','denominator':'2'}


def test_mt5_margin_estimate_is_explicitly_missing_fee_terms(tmp_path,eurusd):
    from test_entry_margin_binding import mt5_entry,entry_command
    from conftest import NOW
    sdk,adapter,clock,ledger,event,book=mt5_entry(tmp_path,eurusd)
    try:
        command=entry_command(event)
        receipt=book.capture_entry(adapter,event.hash,command,deadline_ms=NOW*1000+2000)
        result=book.lookup_entry_fee_terms(command.command_hash,receipt['source_ref'])
        assert result['state']=='PROVIDER_FEE_TERMS_UNAVAILABLE'
        assert result['complete_future_obligation'] is result['execution_authority'] is False
        assert 'terms' not in result and not sdk.sent
    finally:ledger.close()


def test_fractional_turnover_scenario_remains_exact_and_reconstructible_without_native_fx_claim():
    terms=NativeCommissionTerms(contract(commissionType=1,preciseTradingCommissionRate=5000000000))
    result=terms.one_charge(native_volume=10000000,usd_turnover=F(1000000,3))
    assert result['amount']=={'numerator':'50','denominator':'3'}
    assert result['scenario_inputs']['turnover']=={'numerator':'1000000','denominator':'3'}
    assert result['scenario_inputs']['native_price_or_fx_qualified'] is False
    assert result['native_value_basis_qualified'] is False
