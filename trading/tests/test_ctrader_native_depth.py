"""Original framed native depth and explicit lack of continuity/price qualification."""
from decimal import localcontext,Inexact,Rounded
import pytest

from test_ctrader import FakeCtrader,make_adapter
from test_ctrader_spot_contract import barrier
from test_native_market_archive import contract
from vati.core.canonical import canonical_hash
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.depth import DepthBook
from vati.execution.ctrader.transport import CtraderError,CtraderReadTransport


def change(c=None,**values):
    c=c or contract()
    return {'ctidTraderAccountId':c.native_scope['native_account_id'],
            'symbolId':c.native_scope['native_symbol_id'],
            'newQuotes':[{'id':9007199254740993,'size':12345678901234567890,'bid':110100},
                         {'id':2,'size':300,'ask':110108}],**values}


def snapshot(book,c=None,**values):
    return book.snapshot(c or contract(),1,now_ms=200000,max_age_ms=5000,subscribed=True,**values).body()


def test_original_uint64_prices_id_and_cent_sizes_survive_without_float_or_price_scale_assumptions():
    c=contract();book=DepthBook()
    with localcontext() as ctx:
        ctx.clear_flags()
        ctx.prec=2;ctx.Emax=2;ctx.Emin=-2;ctx.traps[Inexact]=ctx.traps[Rounded]=True
        book.observe(c,1,change(),200000);body=snapshot(book)
        assert not any(ctx.flags.values())
    bid=body['bids'][0]
    assert bid=={'native_quote_id':'9007199254740993','native_price':'110100','side':'BID',
                 'native_size_cents':'12345678901234567890','native_size':'123456789012345678.90'}
    assert body['complete_book'] is body['provider_qualified'] is body['tradability_qualified'] is False
    assert body['price_scale'] is body['native_timestamp_ms'] is body['native_sequence'] is None
    assert body['normalized_prices_available'] is False and body['authority_effect']=='NONE'
    assert body['observation_sha256']==canonical_hash({k:v for k,v in body.items() if k!='observation_sha256'})
    body['scope']['native_account_id']=999
    assert snapshot(book)['scope']==c.native_scope


def test_native_changes_update_quote_ids_and_known_deletions_without_synthetic_levels():
    c=contract();book=DepthBook();book.observe(c,1,change(),200000)
    book.observe(c,1,change(newQuotes=[{'id':3,'size':900,'bid':110101},{'id':2,'size':100,'ask':110109}],deletedQuotes=[9007199254740993]),200000)
    body=snapshot(book);assert [x['native_quote_id'] for x in body['bids']]==['3']
    assert body['asks'][0]['native_price']=='110109' and body['observed_quote_count']==2
    book.observe(c,1,change(newQuotes=[],deletedQuotes=[2,3]),200000)
    body=snapshot(book)
    assert body['state']=='OBSERVED_PARTIAL_NATIVE_DEPTH' and body['bids']==body['asks']==[]
    assert body['observed_changes'] is True and body['empty_book_proven'] is False


@pytest.mark.parametrize('bad',['account','symbol','bool_id','bool_size','price_zero','both_sides','no_side',
                              'duplicate','unknown_delete','overlap','event_capacity','backward_clock','bad_list'])
def test_bad_native_change_latches_recovery_until_a_fresh_context(bad):
    c=contract();book=DepthBook(max_quotes=2);book.observe(c,1,change(),200000)
    event=change();now=200000
    if bad=='account':event['ctidTraderAccountId']=999
    elif bad=='symbol':event['symbolId']=99
    elif bad=='bool_id':event['newQuotes'][0]['id']=True
    elif bad=='bool_size':event['newQuotes'][0]['size']=False
    elif bad=='price_zero':event['newQuotes'][0]['bid']=0
    elif bad=='both_sides':event['newQuotes'][0]['ask']=110109
    elif bad=='no_side':event['newQuotes'][0].pop('bid')
    elif bad=='duplicate':event['newQuotes'][1]=dict(event['newQuotes'][0])
    elif bad=='unknown_delete':event.update(newQuotes=[],deletedQuotes=[99])
    elif bad=='overlap':event.update(newQuotes=[event['newQuotes'][0]],deletedQuotes=[9007199254740993])
    elif bad=='event_capacity':event['newQuotes']+= [{'id':3,'size':1,'ask':110109}]
    elif bad=='backward_clock':now-=1
    else:event['newQuotes']=None
    book.observe(c,1,event,now)
    body=snapshot(book,limit=2);assert body['state']=='RECOVERY_REQUIRED' and body['bids']==body['asks']==[]
    book.observe(c,1,change(),200001);assert snapshot(book,limit=2)['state']=='RECOVERY_REQUIRED'
    book.observe(c,2,change(),200001)
    assert book.snapshot(c,2,now_ms=200001,max_age_ms=5000,subscribed=True,limit=2).state=='OBSERVED_PARTIAL_NATIVE_DEPTH'


def test_noop_events_cannot_rejuvenate_a_book_and_stale_or_stopped_levels_are_withheld():
    c=contract();book=DepthBook();book.observe(c,1,change(),190000)
    book.observe(c,1,change(newQuotes=[]),200000)
    body=snapshot(book);assert body['processing_age_ms']==10000
    assert body['state']=='STALE_NATIVE_DEPTH_PROCESSING_AGE' and body['bids']==body['asks']==[]
    body=book.snapshot(c,1,now_ms=190000,max_age_ms=5000,subscribed=True).body()
    assert body['state']=='NATIVE_DEPTH_EVALUATION_CLOCK_INVALID'
    assert book.snapshot(c,1,now_ms=200000,max_age_ms=5000,subscribed=False).state=='SUBSCRIPTION_NOT_ACKNOWLEDGED'


def test_book_capacity_refuses_without_silent_eviction_and_display_limits_are_explicit():
    c=contract();book=DepthBook(max_quotes=2);book.observe(c,1,change(),200000)
    body=snapshot(book,limit=1);assert body['observed_quote_count']==2 and body['display_truncated'] is False
    book.observe(c,1,change(newQuotes=[{'id':3,'size':1,'bid':110099}]),200001)
    body=snapshot(book,limit=2);assert body['state']=='RECOVERY_REQUIRED' and body['recovery_reason']=='NATIVE_DEPTH_BOOK_CAPACITY'


def test_contract_revision_or_native_scope_cannot_reuse_an_old_ladder():
    c=contract();book=DepthBook();book.observe(c,1,change(),200000)
    other=contract(account_id=124)
    assert snapshot(book,other)['state']=='WAITING_NATIVE_DEPTH'
    assert snapshot(book)['bids']==[]


class DepthPeer(FakeCtrader):
    initial=True
    wrong_ack=None
    def handle(self,name,body,cid):
        if name in {'ProtoOASubscribeDepthQuotesReq','ProtoOAUnsubscribeDepthQuotesReq'}:
            response='ProtoOASubscribeDepthQuotesRes' if name=='ProtoOASubscribeDepthQuotesReq' else 'ProtoOAUnsubscribeDepthQuotesRes'
            if self.wrong_ack=='type':return self.send('ProtoHeartbeatEvent',{},cid)
            self.send(response,{'ctidTraderAccountId':999 if self.wrong_ack=='account' else body['ctidTraderAccountId']},cid)
            if self.initial and name=='ProtoOASubscribeDepthQuotesReq':
                return self.send('ProtoOADepthEvent',{'ctidTraderAccountId':12345,'symbolId':1,
                    'newQuotes':[{'id':9007199254740993,'size':12345,'bid':110100},{'id':2,'size':100,'ask':110108}]})
            return
        return super().handle(name,body,cid)


def ready():
    peer=DepthPeer();adapter=make_adapter(peer);adapter.subscribe_depth('EURUSD');barrier(adapter)
    return adapter,peer


def test_actual_framed_depth_subscribes_once_and_packed_deletions_preserve_original_ids():
    adapter,peer=ready();adapter.subscribe_depth('EURUSD')
    body=adapter.depth_observation('EURUSD').body()
    assert body['state']=='OBSERVED_PARTIAL_NATIVE_DEPTH' and body['bids'][0]['native_quote_id']=='9007199254740993'
    peer.send('ProtoOADepthEvent',{'ctidTraderAccountId':12345,'symbolId':1,'deletedQuotes':[9007199254740993]});barrier(adapter)
    body=adapter.depth_observation('EURUSD').body();assert body['bids']==[] and len(body['asks'])==1
    assert len([1 for n,b in peer.requests if n=='ProtoOASubscribeDepthQuotesReq'])==1
    assert not [n for n,b in peer.requests if n in {'ProtoOANewOrderReq','ProtoOAClosePositionReq'}]


def test_acknowledgement_without_delivery_is_never_a_depth_observation():
    peer=DepthPeer();peer.initial=False;adapter=make_adapter(peer);adapter.subscribe_depth('EURUSD');barrier(adapter)
    body=adapter.depth_observation('EURUSD').body()
    assert body['state']=='WAITING_NATIVE_DEPTH' and body['observed_changes'] is False
    assert body['subscription_state']=='ACKNOWLEDGED_QUEUED_NOT_DELIVERY'


@pytest.mark.parametrize('wrong',['account','type'])
def test_wrong_native_ack_refuses_and_cannot_be_blindly_retried(wrong):
    peer=DepthPeer();peer.wrong_ack=wrong;adapter=make_adapter(peer)
    with pytest.raises(VenueUnavailable,match='acknowledgement'):adapter.subscribe_depth('EURUSD')
    with pytest.raises(VenueUnavailable,match='fresh connection'):adapter.subscribe_depth('EURUSD')
    assert len([1 for n,b in peer.requests if n=='ProtoOASubscribeDepthQuotesReq'])==1


def test_stop_is_local_before_ack_and_late_updates_cannot_seed_same_session_replacement():
    adapter,peer=ready();assert adapter.depth_observation('EURUSD').body()['bids']
    peer.wrong_ack='account'
    with pytest.raises(VenueUnavailable):adapter.unsubscribe_depth('EURUSD')
    peer.send('ProtoOADepthEvent',{'ctidTraderAccountId':12345,'symbolId':1,'newQuotes':[{'id':9,'size':1,'bid':1}]});barrier(adapter)
    body=adapter.depth_observation('EURUSD').body()
    assert body['state']=='SUBSCRIPTION_NOT_ACKNOWLEDGED' and body['bids']==body['asks']==[]
    with pytest.raises(VenueUnavailable,match='fresh connection'):adapter.subscribe_depth('EURUSD')


def test_actual_separate_market_reader_returns_native_depth_and_closes_its_owned_socket():
    protective=DepthPeer();adapter=make_adapter(protective);adapter._ensure_auth()
    original=adapter.symbol('EURUSD').native_contract;peers=[]
    def independent(host,port):
        peer=DepthPeer();peers.append(peer);return peer.connector(host,port)
    adapter.transport._connector=independent
    reader=adapter.market_reader(collection_timeout_s=3)
    try:
        actual,observed=reader.read_depth(original)
        assert actual.revision==original.revision and observed.state=='OBSERVED_PARTIAL_NATIVE_DEPTH'
        assert observed.body()['scope']==original.native_scope
    finally:reader.close()
    assert reader.read_capacity_snapshot()['state']=='WITHIN_LIMIT'
    assert not any(n=='ProtoOASubscribeDepthQuotesReq' for n,b in protective.requests)
    assert len(peers)==1 and peers[0].a.fileno()==-1


def test_depth_selection_retains_the_original_financial_execution_event():
    adapter,peer=ready()
    peer.send('ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'});barrier(adapter)
    assert adapter.depth_observation('EURUSD').state=='OBSERVED_PARTIAL_NATIVE_DEPTH'
    original=adapter.transport.wait_event(lambda name,body:name=='ProtoOAExecutionEvent',timeout_s=.1)
    assert original is not None and original[1]['executionType']=='ORDER_FILLED'


def test_pending_native_depth_backlog_withholds_levels_until_original_changes_are_processed():
    adapter,peer=ready();adapter.depth_observation('EURUSD')
    for identity in range(100,201):
        peer.send('ProtoOADepthEvent',{'ctidTraderAccountId':12345,'symbolId':1,
            'newQuotes':[{'id':identity,'size':identity,'bid':110099}]})
    barrier(adapter)
    body=adapter.depth_observation('EURUSD').body()
    assert body['state']=='NATIVE_DEPTH_BACKLOG_UNPROCESSED' and body['bids']==body['asks']==[]
    body=adapter.depth_observation('EURUSD',limit=4096).body()
    assert body['state']=='OBSERVED_PARTIAL_NATIVE_DEPTH' and body['observed_quote_count']==103


def test_fresh_connection_drops_retired_depth_but_keeps_original_financial_evidence():
    adapter,peer=ready();adapter.depth_observation('EURUSD')
    peer.send('ProtoOADepthEvent',{'ctidTraderAccountId':12345,'symbolId':1,
        'newQuotes':[{'id':999,'size':1,'bid':1}]})
    peer.send('ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_FILLED'});barrier(adapter)
    adapter.transport.close();fresh=DepthPeer();fresh.initial=False;adapter.transport._connector=fresh.connector
    adapter.subscribe_depth('EURUSD');barrier(adapter)
    body=adapter.depth_observation('EURUSD').body()
    assert body['state']=='WAITING_NATIVE_DEPTH' and body['observed_changes'] is False
    assert adapter.transport.wait_event(lambda name,body:name=='ProtoOAExecutionEvent',timeout_s=.1) is not None


def test_separate_depth_reader_without_delivery_expires_and_joins_its_original_socket():
    primary=DepthPeer();adapter=make_adapter(primary);adapter._ensure_auth();peers=[]
    def independent(host,port):
        peer=DepthPeer();peer.initial=False;peers.append(peer);return peer.connector(host,port)
    adapter.transport._connector=independent;reader=adapter.market_reader(collection_timeout_s=.5)
    try:
        with pytest.raises((CtraderError,VenueUnavailable),match='depth|budget|deadline|time'):
            reader.read_depth(adapter.symbol('EURUSD').native_contract)
    finally:reader.close()
    assert len(peers)==1 and peers[0].a.fileno()==-1


def test_depth_read_transport_still_rejects_order_and_payment_requests_before_sending():
    peer=DepthPeer();transport=CtraderReadTransport(host='demo.ctraderapi.com',connector=peer.connector)
    try:
        for message in ('ProtoOANewOrderReq','ProtoOAClosePositionReq','ProtoOATraderReq'):
            with pytest.raises(CtraderError,match='read-only|read only|read allowlist'):
                transport.call(message,{})
        assert peer.requests==[]
    finally:transport.close()


def test_many_products_refuse_at_the_declared_bound_without_evicting_original_scopes():
    book=DepthBook()
    for product in range(1,65):
        c=contract(light={'symbolId':product,'symbolName':'P'+str(product),'enabled':True},
                   detail={'symbolId':product,'digits':5,'pipPosition':4,'lotSize':10000000,
                           'minVolume':1000,'stepVolume':1000,'maxVolume':1000000000})
        book.observe(c,1,change(c),200000)
    extra=contract()
    # A different existing product can change its identity; a 65th product cannot.
    extra=contract(light={'symbolId':65,'symbolName':'P65','enabled':True},
                   detail={'symbolId':65,'digits':5,'pipPosition':4,'lotSize':10000000,
                           'minVolume':1000,'stepVolume':1000,'maxVolume':1000000000})
    with pytest.raises(ValueError,match='PRODUCT_CAPACITY'):book.observe(extra,1,change(extra),200000)
    assert len(book.rows)==64


def test_display_truncation_preserves_original_native_count_and_deterministic_price_order():
    c=contract();book=DepthBook()
    book.observe(c,1,change(newQuotes=[{'id':3,'size':100,'bid':110099},
                                    {'id':2,'size':100,'bid':110101},
                                    {'id':1,'size':100,'ask':110108}]),200000)
    body=snapshot(book,limit=1)
    assert body['display_truncated'] is True and body['observed_bid_count']==2
    assert body['observed_quote_count']==3 and body['bids'][0]['native_quote_id']=='2'
