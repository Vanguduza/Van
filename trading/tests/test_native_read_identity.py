"""Inactive native history remains data, separate from enabled execution contracts."""
from copy import deepcopy
from dataclasses import replace

import pytest

from test_native_symbol_catalog import captured, response, SCOPE, NOW, CatalogPeer
from test_ctrader import make_adapter
from test_ctrader_feed_contract import response as bar_response
from test_native_market_archive import contract as execution_contract
from vati.core.canonical import canonical_json
from vati.execution.ctrader import SCHEMA
from vati.execution.ctrader.catalog import NativeSymbolCatalog
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.read_identity import NativeReadIdentity
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader.transport import CtraderReadTransport, CtraderApiError, CtraderError
from vati.market_data.native_archive import NativeMarketArchive, NativeArchiveError
from vati.market_data.native_collector import NativeMarketCollector
from vati.market_data.native_windows import NativeBarWindowReader
from vati.market_data.native_quotes import NativeQuoteArchive, NativeQuoteCollector


def identity(native_id=4, *, wire=False, **changes):
    source=response()
    if wire: source=SCHEMA.decode('ProtoOASymbolsListRes',SCHEMA.encode('ProtoOASymbolsListRes',source))
    return NativeReadIdentity.capture(captured(response=source,**changes),native_id)


@pytest.mark.parametrize('native_id',[1,2,3,4])
def test_visible_hidden_nameless_and_archived_entries_have_read_only_identity(native_id):
    value=identity(native_id)
    assert value.native_scope==SCOPE|{'native_symbol_id':native_id}
    assert not isinstance(value,NativeSymbolContract)
    assert value.body()['qualified_for_execution'] is value.body()['qualified_for_research'] is False
    assert value.body()['provider_qualified'] is False and value.body()['authority_effect']=='NONE'
    assert value.body()['lifecycle_effective_at_ms'] is None
    assert NativeReadIdentity.from_body(value.body())==value
    if native_id==3:
        assert value.display_name is None and value.series_label=='CTRADER_NATIVE_3'
    if native_id==4:
        assert value.body()['source_kind']=='ARCHIVED'
        assert value.member['original']['utcLastUpdateTimestamp']==NOW-100000


@pytest.mark.parametrize('name',['','/','x'*300])
def test_unknown_or_unusable_display_label_retains_native_identity_without_truncating_data(name):
    body=response();body['symbol'][1]['symbolName']=name
    value=NativeReadIdentity.capture(captured(response=body),2)
    assert value.display_name==name and value.series_label=='CTRADER_NATIVE_2'
    assert value.body()['series_label_basis']=='NATIVE_ID_LABEL_NAME_UNAVAILABLE_OR_TOO_LONG'


def test_identity_revision_ignores_receipt_clock_but_retains_original_metadata_and_private_copies():
    first=identity();later=identity(received_at_ms=NOW+1000)
    assert first.revision==later.revision and first.received_at_ms!=later.received_at_ms
    before=first.body();changed=first.metadata;changed['catalog_metadata']['response'].clear()
    changed=first.member;changed['original']['name']='rewritten'
    assert first.body()==before


@pytest.mark.parametrize('field',['qualified_for_execution','qualified_for_research','provider_qualified'])
@pytest.mark.parametrize('value',[True,0,None,'false'])
def test_read_identity_cannot_self_grant_or_corrupt_qualification_types(field,value):
    body=identity().body();body[field]=value
    with pytest.raises(ValueError):NativeReadIdentity.from_body(body)


def test_missing_native_id_and_incomplete_catalog_request_cannot_supply_an_identity():
    with pytest.raises(ValueError,match='absent'):identity(999)
    raw=response();raw.pop('archivedSymbol')
    source=captured(response=raw,include_archived_symbols=False)
    with pytest.raises(ValueError,match='archived catalog'):NativeReadIdentity.capture(source,2)


def test_invalid_blank_archived_name_does_not_weaken_existing_catalog_refusal():
    raw=response();raw['archivedSymbol'][0]['name']=''
    with pytest.raises(ValueError,match='catalog text invalid'):captured(response=raw)


def test_enabled_execution_contract_remains_independently_required():
    value=identity()
    with pytest.raises(ValueError):NativeSymbolContract.from_body(value.body())
    with pytest.raises(ValueError,match='product scope'):
        execution_contract(light={'symbolId':12,'symbolName':'Old','enabled':False})


class HistoryPeer(CatalogPeer):
    def handle(self,name,body,cid):
        if name=='ProtoOAGetTrendbarsReq':
            return self.send('ProtoOAGetTrendbarsRes',bar_response()|{'ctidTraderAccountId':12345,
                'symbolId':body['symbolId'],'hasMore':False},cid)
        return super().handle(name,body,cid)


@pytest.mark.parametrize('native_id',[2,3,4])
def test_actual_inactive_native_history_uses_catalog_id_without_loading_execution_metadata(native_id):
    expected=identity(native_id,wire=True);peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW
    reader=parent.market_reader()
    try:
        original,observed=reader.read_window(expected,timeframe='M1',from_ms=120000,to_ms=300000)
        assert original.revision==expected.revision and len(observed.bars)==3
        assert observed.native_symbol_id==native_id and observed.symbol==expected.series_label
        assert all(b.symbol==expected.series_label for b in observed.bars)
        assert not parent.transport.connected and parent.symbols=={}
        names=[n for n,_ in peer.requests]
        assert names==['ProtoOAApplicationAuthReq','ProtoOAAccountAuthReq','ProtoOASymbolsListReq','ProtoOAGetTrendbarsReq']
        assert peer.requests[-1][1]['symbolId']==native_id
        assert 'ProtoOASymbolByIdReq' not in names and 'ProtoOANewOrderReq' not in names
    finally:reader.close();peer.close()


def test_actual_collector_persists_inactive_source_and_replay_never_reads_native_again(tmp_path):
    expected=identity(wire=True);book=NativeMarketArchive(tmp_path/'native',clock=lambda:NOW+1000)
    peers=[]
    def factory():
        peer=HistoryPeer();peers.append(peer);parent=make_adapter(peer);parent.clock=lambda:NOW
        return parent.market_reader()
    collector=NativeMarketCollector(book,factory)
    try:
        first=collector.collect('inactive-history',expected,timeframe='M1',from_ms=120000,to_ms=300000)
        assert len(peers)==1 and first['available_at_ms']==NOW+1000
        assert collector.collect('inactive-history',expected,timeframe='M1',from_ms=120000,to_ms=300000)==first
        assert len(peers)==1
        cold=NativeMarketArchive(book.root,clock=lambda:NOW+2000)
        source=cold.snapshot(expected.native_scope,'M1',revision=1)
        assert source['contract']['schema']=='vati.ctrader-read-identity-capture/1'
        assert source['contract']['qualified_for_execution'] is False
        view=NativeBarWindowReader(cold).capture(expected.native_scope,'M1',through_revision=1,
            boundary_ref=first['record_ref'],as_of_ms=NOW+1000,from_ms=120000,to_ms=300000)
        assert len(view['rows'])==3 and view['qualified_for_research'] is False
        assert NativeBarWindowReader(cold).verify(view,expected_scope=expected.native_scope)==view
    finally:
        for peer in peers:peer.close()


def test_quote_owner_and_active_quote_reader_do_not_accept_read_only_identity(tmp_path):
    value=identity();quotes=NativeQuoteArchive(tmp_path/'quotes',clock=lambda:NOW+1000)
    assert quotes.contract_types==(NativeSymbolContract,)
    with pytest.raises(NativeArchiveError):quotes.record('not-a-quote',value,object())
    def forbidden():pytest.fail('quote native reader opened for read-only history identity')
    with pytest.raises(NativeArchiveError):NativeQuoteCollector(quotes,forbidden).collect('not-a-quote',value)


def test_changed_catalog_refuses_before_historical_request():
    expected=identity(wire=True)
    body=expected.body();body['metadata']['catalog_metadata']['response']['archivedSymbol'][0]['name']='different'
    changed=NativeReadIdentity(canonical_json(body['metadata']),NOW)
    peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader()
    try:
        with pytest.raises(VenueUnavailable,match='changed or unavailable'):
            reader.read_window(changed,timeframe='M1',from_ms=120000,to_ms=300000)
        assert all(n!='ProtoOAGetTrendbarsReq' for n,_ in peer.requests)
    finally:reader.close();peer.close()


def test_wrong_read_account_refuses_before_native_authentication():
    raw=response()|{'ctidTraderAccountId':999}
    expected=NativeReadIdentity.capture(captured(scope=SCOPE|{'native_account_id':999},response=raw),4)
    peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader()
    try:
        with pytest.raises(VenueUnavailable,match='account/environment differs'):
            reader.read_window(expected,timeframe='M1',from_ms=120000,to_ms=300000)
        assert peer.requests==[]
    finally:reader.close();peer.close()


@pytest.mark.parametrize('options',[{'timeframe':'UNKNOWN','from_ms':120000,'to_ms':300000},
    {'timeframe':'M1','from_ms':True,'to_ms':300000}, {'timeframe':'M1','from_ms':300000,'to_ms':120000}])
def test_invalid_read_window_refuses_before_native_authentication(options):
    peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader()
    try:
        with pytest.raises((VenueUnavailable,ValueError)):
            reader.read_window(identity(wire=True),**options)
        assert peer.requests==[]
    finally:reader.close();peer.close()


class UnavailableHistoryPeer(HistoryPeer):
    def handle(self,name,body,cid):
        if name=='ProtoOAGetTrendbarsReq':
            return self.send('ProtoOAErrorRes',{'errorCode':'SYMBOL_NOT_FOUND','description':'history unavailable'},cid)
        return super().handle(name,body,cid)


def test_native_unavailable_history_does_not_become_empty_archive_success(tmp_path):
    expected=identity(wire=True);peer=UnavailableHistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW
    book=NativeMarketArchive(tmp_path/'native',clock=lambda:NOW+1000)
    try:
        with pytest.raises(CtraderApiError,match='history unavailable') as refused:
            NativeMarketCollector(book,parent.market_reader).collect('unavailable',expected,
                timeframe='M1',from_ms=120000,to_ms=300000)
        assert refused.value.code=='SYMBOL_NOT_FOUND'
        assert book.lookup(expected.native_scope,'M1','unavailable') is None
    finally:peer.close()


def test_retired_history_connection_cannot_publish_success(tmp_path,monkeypatch):
    expected=identity(wire=True);peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW
    book=NativeMarketArchive(tmp_path/'native',clock=lambda:NOW+1000)
    call=CtraderReadTransport.call
    def retire(transport,message,*args,**kwargs):
        result=call(transport,message,*args,**kwargs)
        if message=='ProtoOAGetTrendbarsReq':transport.close()
        return result
    monkeypatch.setattr(CtraderReadTransport,'call',retire)
    try:
        with pytest.raises(VenueUnavailable,match='session changed'):
            NativeMarketCollector(book,parent.market_reader).collect('retired',expected,
                timeframe='M1',from_ms=120000,to_ms=300000)
        assert book.lookup(expected.native_scope,'M1','retired') is None
    finally:peer.close()


def test_deadline_expiring_during_history_parse_prevents_archive_publication(tmp_path,monkeypatch):
    from vati.execution.ctrader import feed
    expected=identity(wire=True);peer=HistoryPeer();parent=make_adapter(peer);parent.clock=lambda:NOW
    book=NativeMarketArchive(tmp_path/'native',clock=lambda:NOW+1000);read=feed.read_trendbars
    def expire(source,*args,**kwargs):
        result=read(source,*args,**kwargs)
        source.transport._operation_deadline=0.0
        return result
    monkeypatch.setattr(feed,'read_trendbars',expire)
    try:
        with pytest.raises(CtraderError):
            NativeMarketCollector(book,parent.market_reader).collect('parse-expired',expected,
                timeframe='M1',from_ms=120000,to_ms=300000)
        assert book.lookup(expected.native_scope,'M1','parse-expired') is None
    finally:peer.close()
