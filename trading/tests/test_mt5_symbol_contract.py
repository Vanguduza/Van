"""Original public symbol-read inputs, exact source data and unavailable states."""
from copy import deepcopy
from dataclasses import replace
import pytest

from test_mt5_symbol_contract_worker import TermsSdk
from test_mt5_worker_funding import connection
from vati.core import Ledger
from vati.core.canonical import canonical_hash
from vati.execution.base import VenueUnavailable
from vati.execution.mt5_symbol_contract import Mt5SymbolContractObservation
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account


def source(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk())
    ledger=Ledger(tmp_path/'symbol-source.sqlite');account=adapter.sync_account()
    captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
    context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
    return sdk,worker,adapter,now,ledger,context


def read(adapter,now,context):
    return adapter.symbol_contract('EURUSD',context=context,deadline_ms=now['ms']+1000)


def test_actual_public_read_binds_original_account_and_signed_request_without_a_risk_grant(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        before=ledger.count();value=read(adapter,now,context);body=value.body()
        assert body['state']=='OBSERVED_NATIVE_TERMS'
        assert body['native_account_context']['physical_account_key']==context.physical_account_key
        assert body['native_read_identity']['request_nonce']==adapter.client.sent[-1].nonce
        assert body['observation']['contract']['trade_tick_value_loss']=='0.9'
        assert body['risk_terms_qualified'] is body['provider_qualified'] is body['execution_authority'] is False
        copy=value.body();copy['observation']['contract']['trade_tick_value_loss']='0'
        assert value.body()==body and ledger.count()==before and not sdk.sent
        assert Mt5SymbolContractObservation.from_body(body).body()==body
    finally:ledger.close()


@pytest.mark.parametrize('damage',['account','currency','nonce','expiry','request','state','authority','tick','clock','format','unknown'])
def test_mutated_original_native_symbol_reply_is_not_admitted_as_source_data(tmp_path,damage):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        body=read(adapter,now,context).body()
        if damage=='account':body['observation']['account_after']['login']=999
        elif damage=='currency':body['observation']['account_before']['currency_digits']=8
        elif damage=='nonce':body['native_read_identity']['request_nonce']=True
        elif damage=='expiry':body['observation']['received_at_ms']=body['valid_until_ms']
        elif damage=='request':body['observation']['request']['symbol']='GBPUSD'
        elif damage=='state':body['state']='LIVE'
        elif damage=='authority':body['risk_terms_qualified']=True
        elif damage=='tick':body['observation']['contract']['trade_tick_value_loss']='NaN'
        elif damage=='clock':body['observation']['native_clock_basis']='BROKER_ASSUMED'
        elif damage=='format':body['observation']['native_numeric_format']='DECIMAL_ASSUMED'
        elif damage=='unknown':body['unearned_owner_grant']=True
        body['source_ref']=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
        with pytest.raises(ValueError):Mt5SymbolContractObservation.from_body(body)
        assert not sdk.sent
    finally:ledger.close()


def test_explicit_zero_loss_value_is_unpriced_and_changed_context_is_refused(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        sdk.on_symbol=lambda row:setattr(row,'trade_tick_value_loss',0)
        value=read(adapter,now,context).body()
        assert value['state']=='UNPRICED' and value['observation']['contract']['trade_tick_value_loss']=='0'
        with pytest.raises(VenueUnavailable):read(adapter,now,replace(context,account_alias='another_alias'))
        assert not sdk.sent
    finally:ledger.close()
