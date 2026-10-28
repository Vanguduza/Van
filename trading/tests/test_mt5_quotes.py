"""Native quote source identity and causal state, never inferred live access."""
from copy import deepcopy
import pytest

from test_mt5_quote_worker import QuoteSdk
from test_mt5_worker_funding import connection
from vati.core import Ledger
from vati.core.canonical import canonical_hash
from vati.execution.mt5_quotes import Mt5QuoteObservation
from vati.execution.base import VenueUnavailable
from vati.funding.mt5_runtime import capture_cached_mt5
from vati.risk.account_context import context_for_account


def source(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk());ledger=Ledger(tmp_path/'quote-source.sqlite')
    account=adapter.sync_account();captured=capture_cached_mt5(ledger,account,now_ms=now['ms'])
    context=context_for_account(ledger,adapter,account,now_ms=now['ms'],mt5_capture=captured)
    return sdk,worker,adapter,now,ledger,context


def read(adapter,now,context):
    return adapter.quote_snapshot('EURUSD',context=context,deadline_ms=now['ms']+1000)


def test_actual_quote_read_preserves_native_prices_scope_and_re_evaluates_historical_age(tmp_path):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        before=ledger.count();q=read(adapter,now,context);body=q.body()
        view=q.snapshot(now_ms=now['ms'],max_age_ms=5000)
        assert view['state']=='OBSERVED_UNQUALIFIED' and view['age_ms']==50
        assert view['bid']=='1.1' and view['ask']=='1.10008'
        assert view['base_currency']=='EUR' and view['quote_currency']==view['account_currency']=='USD'
        assert view['provider_qualified'] is view['risk_terms_qualified'] is view['execution_authority'] is False
        assert body['native_read_identity']['request_nonce']==adapter.client.sent[-1].nonce
        assert q.snapshot(now_ms=now['ms']+6000,max_age_ms=5000)['state']=='STALE_NATIVE_QUOTE'
        assert q.body()==body and ledger.count()==before and not sdk.sent
        mutable=q.body();mutable['observation']['tick']['bid']='0'
        assert q.body()==body and Mt5QuoteObservation.from_body(body).body()==body
    finally:ledger.close()


@pytest.mark.parametrize('change,state',[
    ('no_tick','WAITING_NATIVE_QUOTE'),('no_bid','WAITING_NATIVE_BID'),('no_ask','WAITING_NATIVE_ASK'),
    ('no_time','NATIVE_TIME_UNAVAILABLE'),('bad_seconds','NATIVE_TIME_INCONSISTENT'),
    ('future_tick','HOST_CLOCK_BEHIND_NATIVE_QUOTE'),('crossed','CROSSED_NATIVE_QUOTE'),
    ('not_selected','SYMBOL_SUBSCRIPTION_UNVERIFIED'),('delayed','DELAYED_NATIVE_QUOTE'),
    ('unknown_entitlement','NATIVE_ENTITLEMENT_UNVERIFIED'),
])
def test_unpriced_stale_time_and_unverified_subscription_states_remain_explicit(tmp_path,change,state):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        if change=='no_tick':sdk.tick_available=False
        elif change in {'not_selected','delayed','unknown_entitlement'}:
            original=sdk.symbol_info
            def metadata(symbol):
                value=original(symbol)
                if change=='not_selected':value.select=False
                elif change=='delayed':value.subscription_delay=True
                else:value.subscription_delay=None
                return value
            sdk.symbol_info=metadata
        else:
            def altered(tick):
                if change=='no_bid':tick.bid=0.
                elif change=='no_ask':tick.ask=None
                elif change=='no_time':tick.time_msc=None
                elif change=='bad_seconds':tick.time=998
                elif change=='future_tick':tick.time_msc=1000010;tick.time=1000
                elif change=='crossed':tick.ask=1.
            sdk.on_tick=altered
        q=read(adapter,now,context);view=q.snapshot(now_ms=now['ms'],max_age_ms=5000)
        assert view['state']==state and view['execution_authority'] is False and not sdk.sent
        if change=='no_time':assert view['native_tick_time_ms'] is None
    finally:ledger.close()


@pytest.mark.parametrize('field',['authority','account','units','request','contract','nonce','clock','depth','tick'])
def test_changed_original_quote_cannot_acquire_valid_native_provenance(tmp_path,field):
    sdk,worker,adapter,now,ledger,context=source(tmp_path)
    try:
        body=read(adapter,now,context).body();raw=body['observation']
        if field=='authority':body['execution_authority']=True
        elif field=='account':raw['account_after']['login']=999
        elif field=='units':raw['account_before']['currency_digits']=8
        elif field=='request':raw['request']['symbol']='GBPUSD'
        elif field=='contract':raw['contract_after']['currency_profit']='JPY'
        elif field=='nonce':body['native_read_identity']['request_nonce']=True
        elif field=='clock':raw['received_at_ms']=body['valid_until_ms']
        elif field=='depth':raw['volume_basis']='GENUINE_DEPTH'
        elif field=='tick':raw['tick']['volume']='9007199254740993.0'
        body['source_ref']=canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
        with pytest.raises(ValueError):Mt5QuoteObservation.from_body(body)
        assert not sdk.sent
    finally:ledger.close()
