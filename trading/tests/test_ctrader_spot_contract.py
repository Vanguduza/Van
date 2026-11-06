"""Native quote scope, partial updates, freshness and financial-event retention."""
from decimal import Decimal, localcontext

import pytest

from test_ctrader import FakeCtrader, make_adapter
from vati.execution.base import VenueUnavailable


def ready():
    native=FakeCtrader();adapter=make_adapter(native)
    adapter.subscribe_spots('EURUSD')
    barrier(adapter)  # The native heartbeat is unsolicited, not a correlated RPC.
    assert adapter.spot('EURUSD')==(Decimal('1.101'),Decimal('1.10108'))
    return adapter,native


def publish(adapter,native,**changes):
    body={'ctidTraderAccountId':12345,'symbolId':1,'bid':110100,'ask':110108,'timestamp':adapter.clock()}
    body.update(changes)
    native.send('ProtoOASpotEvent',body)
    barrier(adapter)


def barrier(adapter):
    adapter.transport.call('ProtoOASymbolByIdReq',{'ctidTraderAccountId':12345,'symbolId':[1]})


def test_foreign_native_account_cannot_replace_the_original_product_quote():
    adapter,native=ready();publish(adapter,native,ctidTraderAccountId=999,bid=99000,ask=99008)
    assert adapter.spot('EURUSD') is None,'foreign-account quote replaced the original account source'


def test_native_one_sided_update_preserves_the_other_side_without_ignoring_the_update():
    adapter,native=ready();now=adapter.clock()+1;adapter.clock=lambda:now
    native.send('ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'bid':110102,'timestamp':now})
    barrier(adapter)
    assert adapter.spot('EURUSD')==(Decimal('1.10102'),Decimal('1.10108'))


def test_spot_read_does_not_consume_an_original_financial_execution_event():
    adapter,native=ready()
    native.send('ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'})
    barrier(adapter)
    assert adapter.spot('EURUSD')==(Decimal('1.101'),Decimal('1.10108'))
    original=adapter.transport.wait_event(lambda name,body:name=='ProtoOAExecutionEvent',timeout_s=.05)
    assert original is not None and original[1]['executionType']=='ORDER_FILLED'


def test_crossed_native_snapshot_is_unavailable_instead_of_a_negative_spread():
    adapter,native=ready();publish(adapter,native,bid=110110,ask=110108)
    assert adapter.spot('EURUSD') is None


def test_native_price_conversion_is_exact_under_low_ambient_decimal_precision():
    adapter,native=ready();publish(adapter,native,bid=123456789012345,ask=123456789012353)
    with localcontext() as context:
        context.prec=2
        assert adapter.spot('EURUSD')==(Decimal('1234567890.12345'),Decimal('1234567890.12353'))


def test_native_quote_age_does_not_refresh_when_the_cached_quote_is_read_again():
    adapter,native=ready();now=adapter.clock()+5001;adapter.clock=lambda:now
    assert adapter.spot('EURUSD') is None,'reading the cache concealed an expired native quote'


def test_native_update_without_requested_time_does_not_become_a_fresh_quote():
    adapter,native=ready()
    native.send('ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'bid':110101,'ask':110109})
    barrier(adapter)
    assert adapter.spot('EURUSD') is None


@pytest.mark.parametrize('wrong',['account','type'])
def test_subscription_ack_must_match_the_native_account_and_response_type(wrong):
    class WrongAck(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOASubscribeSpotsReq':
                return self.send('ProtoOASubscribeSpotsRes',{'ctidTraderAccountId':999},cid) if wrong=='account' else self.send('ProtoHeartbeatEvent',{},cid)
            return super().handle(name,body,cid)
    native=WrongAck();adapter=make_adapter(native)
    with pytest.raises(VenueUnavailable):adapter.subscribe_spots('EURUSD')


def test_native_subscription_is_requested_once_with_timestamp_delivery():
    adapter,native=ready();adapter.subscribe_spots('EURUSD')
    requests=[body for name,body in native.requests if name=='ProtoOASubscribeSpotsReq']
    assert len(requests)==1 and requests[0]['subscribeToSpotTimestamp'] is True


def test_raw_spot_body_preserves_unqualified_session_time_and_immutable_native_scope():
    adapter,native=ready();observed=adapter.spot_observation('EURUSD');scope=observed.scope
    scope['native_account_id']=999
    body=observed.body()
    assert body['scope']['native_account_id']==12345 and body['provider_qualified'] is False
    assert body['authority_effect']=='NONE' and body['spread']=='0.00008'
    assert body['subscription_state']=='ACKNOWLEDGED_QUEUED_NOT_DELIVERY'
    assert 'UNKNOWN' in body['market_session_state'] and body['age_ms']==0
    assert 'NOT_NETWORK_RECEIPT' in body['availability_basis']


def test_one_fresh_side_cannot_rejuvenate_the_expired_other_side():
    adapter,native=ready();now=adapter.clock()+5001;adapter.clock=lambda:now
    native.send('ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'bid':110102,'timestamp':now})
    barrier(adapter)
    observed=adapter.spot_observation('EURUSD')
    assert observed.state=='STALE_NATIVE_QUOTE' and observed.age_ms==5001 and observed.prices is None


def test_older_side_update_does_not_overwrite_a_newer_native_value():
    adapter,native=ready();original=adapter.clock();now=original+5;adapter.clock=lambda:now
    publish(adapter,native,bid=110102,timestamp=now)
    assert adapter.spot('EURUSD')[0]==Decimal('1.10102')
    publish(adapter,native,bid=110101,timestamp=original)
    observed=adapter.spot_observation('EURUSD')
    assert observed.prices[0]==Decimal('1.10102') and observed.ignored_older_updates==2


def test_auxiliary_live_bar_envelope_does_not_refresh_or_erase_price_times():
    adapter,native=ready();original=adapter.spot_observation('EURUSD')
    native.send('ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'sessionClose':110000})
    barrier(adapter)
    observed=adapter.spot_observation('EURUSD')
    assert observed.prices==original.prices and observed.bid_time_ms==original.bid_time_ms


def test_unknown_product_cannot_allocate_an_unbound_quote_cache():
    adapter,native=ready();publish(adapter,native,symbolId=999)
    assert adapter.spot('EURUSD') is not None and 999 not in adapter._last_spot


@pytest.mark.parametrize('clock',[None,True,-1])
def test_unqualified_host_clock_does_not_turn_cached_prices_into_a_current_quote(clock):
    adapter,native=ready();adapter.clock=lambda:clock
    observed=adapter.spot_observation('EURUSD')
    assert observed.state=='HOST_CLOCK_UNAVAILABLE' and observed.prices is None


def test_known_unprocessed_quote_backlog_is_a_hold_until_consumed():
    adapter,native=ready()
    for _ in range(101):native.send('ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'bid':110100,'ask':110108,'timestamp':adapter.clock()})
    barrier(adapter)
    first=adapter.spot_observation('EURUSD')
    assert first.state=='NATIVE_QUOTE_BACKLOG_UNPROCESSED' and first.prices is None
    assert adapter.spot('EURUSD')==(Decimal('1.101'),Decimal('1.10108'))


def test_unsolicited_quote_without_a_valid_subscription_ack_cannot_grant_a_price():
    native=FakeCtrader();adapter=make_adapter(native);adapter._ensure_auth()
    publish(adapter,native)
    observed=adapter.spot_observation('EURUSD')
    assert observed.state=='SUBSCRIPTION_NOT_ACKNOWLEDGED' and observed.prices is None


def test_actual_independent_quote_reader_uses_selected_native_scope_and_leaves_order_socket_untouched():
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract;before=list(primary.requests);peers=[]
    def separate(host,port):
        native=FakeCtrader();peers.append(native);return native.connector(host,port)
    adapter.transport._connector=separate
    reader=adapter.market_reader()
    try:
        original,observed=reader.read_quote(expected)
        assert original.revision==expected.revision
        assert observed.prices==(Decimal('1.101'),Decimal('1.10108'))
        assert observed.scope['native_account_id']==12345 and observed.body()['provider_qualified'] is False
        assert primary.requests==before and adapter.transport.connected and len(peers)==1
        assert [name for name,_ in peers[0].requests]==['ProtoOAApplicationAuthReq','ProtoOAAccountAuthReq',
            'ProtoOASymbolsListReq','ProtoOASymbolByIdReq','ProtoOASubscribeSpotsReq']
        assert not hasattr(reader,'submit')
    finally:reader.close();adapter.transport.close()
    assert peers[0].a.fileno()==-1


def test_subscription_ack_without_native_quote_data_remains_unavailable_under_the_read_budget():
    primary=FakeCtrader();adapter=make_adapter(primary);adapter._ensure_auth()
    expected=adapter.symbol('EURUSD').native_contract
    class SilentQuotes(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOASubscribeSpotsReq':return self.send('ProtoOASubscribeSpotsRes',{'ctidTraderAccountId':12345},cid)
            return super().handle(name,body,cid)
    silent=SilentQuotes();adapter.transport._connector=silent.connector
    reader=adapter.market_reader(collection_timeout_s=.1)
    try:
        with pytest.raises(VenueUnavailable):reader.read_quote(expected)
    finally:reader.close();adapter.transport.close()
    assert silent.a.fileno()==-1


def test_unsubscribe_holds_local_prices_and_residual_packets_until_an_explicit_new_subscription():
    adapter,native=ready();adapter.unsubscribe_spots('EURUSD')
    publish(adapter,native)
    observed=adapter.spot_observation('EURUSD')
    assert observed.prices is None and observed.control_state=='UNSUBSCRIBE_ACKNOWLEDGED_QUEUED'
    adapter.subscribe_spots('EURUSD');barrier(adapter)
    assert adapter.spot('EURUSD')==(Decimal('1.101'),Decimal('1.10108'))
    assert sum(name=='ProtoOASubscribeSpotsReq' for name,_ in native.requests)==2


def test_unsubscribe_bad_ack_keeps_local_stop_and_explicit_unknown_native_control():
    class BadStop(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOAUnsubscribeSpotsReq':return self.send('ProtoOAUnsubscribeSpotsRes',{'ctidTraderAccountId':999},cid)
            return super().handle(name,body,cid)
    native=BadStop();adapter=make_adapter(native);adapter.subscribe_spots('EURUSD');barrier(adapter)
    with pytest.raises(VenueUnavailable):adapter.unsubscribe_spots('EURUSD')
    publish(adapter,native)
    observed=adapter.spot_observation('EURUSD')
    assert observed.prices is None and observed.control_state=='UNSUBSCRIBE_ACKNOWLEDGEMENT_INVALID'


@pytest.mark.parametrize('field,value',[('bid',True),('ask',0),('bid',-1),('ask',2**64),
    ('timestamp',True),('timestamp',-1),('timestamp',1700000000001)])
def test_invalid_decoded_native_fields_cannot_leave_an_apparently_usable_cached_pair(field,value):
    # Decoded-object validation, not a claim that protobuf distinguishes a
    # Python bool from an integer on the wire.
    adapter,native=ready();symbol=adapter.symbol('EURUSD');clock=adapter.clock()
    bad={'ctidTraderAccountId':12345,'symbolId':1,'bid':110100,'ask':110108,'timestamp':clock,field:value}
    adapter._spot_book.observe(symbol.native_contract,adapter.transport.connection_id,bad,clock)
    assert adapter.spot('EURUSD') is None


def test_contract_refresh_on_the_same_connection_fences_previous_quote_sides():
    adapter,native=ready();before=adapter.symbol('EURUSD').native_contract
    # A genuine new metadata revision is required; the old source value cannot
    # silently be retagged with the changed current contract.
    changed=type(before).capture(account_id=12345,transport_host=before.metadata['transport_host'],
        light=before.metadata['light'],detail=dict(before.metadata['detail'],minVolume=200000),received_at_ms=adapter.clock())
    adapter.symbols['EURUSD'].native_contract=changed
    adapter.symbols['EURUSD'].contract_revision=changed.revision
    observed=adapter.spot_observation('EURUSD')
    assert observed.contract_revision==changed.revision and observed.prices is None


def test_kind_drain_preserves_relative_order_and_payloads_of_other_event_types():
    adapter,native=ready()
    for kind,body in [('ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_ACCEPTED'}),
                      ('ProtoOASpotEvent',{'ctidTraderAccountId':12345,'symbolId':1,'bid':110100,'ask':110108,'timestamp':adapter.clock()}),
                      ('ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'})]:
        native.send(kind,body)
    barrier(adapter);adapter.spot('EURUSD')
    remaining=adapter.transport.drain_events()
    assert [body['executionType'] for name,body in remaining if name=='ProtoOAExecutionEvent']==['ORDER_ACCEPTED','ORDER_FILLED']
