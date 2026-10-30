"""Actual pinned protobuf catalog and source lifecycle facts; no provider admission."""
from copy import deepcopy

import pytest

from vati.core.canonical import canonical_hash
from vati.execution.base import VenueUnavailable
from vati.execution.ctrader import SCHEMA
from vati.execution.ctrader.catalog import NativeSymbolCatalog
from test_ctrader import FakeCtrader,make_adapter

SCOPE={'provider':'CTRADER','environment':'DEMO','transport_host':'demo.ctraderapi.com','native_account_id':12345}
NOW=1_800_000_000_000


def response():
    return {'ctidTraderAccountId':12345,'symbol':[
        {'symbolId':1,'symbolName':'EUR/USD','enabled':True,'baseAssetId':1,'quoteAssetId':2},
        {'symbolId':2,'symbolName':'Hidden','enabled':False,'description':''},
        {'symbolId':3}],
        'archivedSymbol':[{'symbolId':4,'name':'Old','utcLastUpdateTimestamp':NOW-100000}]}


def captured(**changes):
    return NativeSymbolCatalog.capture(**({'scope':SCOPE,'response':response(),'received_at_ms':NOW,'include_archived_symbols':True}|changes))


def test_pinned_codec_preserves_hidden_archived_and_omitted_fields_without_execution_contracts():
    source=SCHEMA.decode('ProtoOASymbolsListRes',SCHEMA.encode('ProtoOASymbolsListRes',response()))
    value=captured(response=source);members=value.members()
    assert [r['native_symbol_id'] for r in members]==[1,2,3,4]
    assert [r['visible'] for r in members]==[True,False,False,False]
    assert members[2]['original']=={'symbolId':3}
    assert members[2]['visibility_basis']=='PROTO2_OMITTED_BOOL_DEFAULT_FALSE'
    assert members[3]['visibility_basis']=='ARCHIVED_SOURCE_RECORD'
    assert members[3]['original']['utcLastUpdateTimestamp']==NOW-100000
    assert all(r['lifecycle_effective_at_ms'] is None and r['qualified_for_research'] is False for r in members)
    assert value.body()['provider_qualified'] is False and value.body()['authority_effect']=='NONE'
    assert NativeSymbolCatalog.from_body(value.body())==value


def test_metadata_and_member_readbacks_cannot_mutate_original_native_vintage():
    value=captured();before=value.body();m=value.members();m[0]['original']['symbolName']='changed'
    body=value.body();body['metadata']['response']['symbol'].clear()
    assert value.body()==before


@pytest.mark.parametrize('change',[
    {'ctidTraderAccountId':999},{'ctidTraderAccountId':True},{'symbol':None},
    {'symbol':[{'symbolId':True}]},{'symbol':[{'symbolId':1,'enabled':'yes'}]},
    {'symbol':[{'symbolId':1},{'symbolId':1}]},
    {'archivedSymbol':[{'symbolId':1,'name':'collision','utcLastUpdateTimestamp':NOW}]},
    {'archivedSymbol':[{'symbolId':4,'name':'old'}]},
    {'archivedSymbol':[{'symbolId':4,'name':'old','utcLastUpdateTimestamp':NOW+1}]},
    {'extra_native_field':'unsupported'},
])
def test_malformed_native_identity_scope_or_clock_is_not_a_usable_catalog(change):
    with pytest.raises((ValueError,KeyError)):captured(response=response()|change)


def test_unrequested_archived_records_cannot_change_the_bound_request_profile():
    with pytest.raises(ValueError,match='unsolicited'):captured(include_archived_symbols=False)


def test_actual_protocol_schema_digest_is_part_of_catalog_identity():
    value=captured();body=value.body();body['metadata']['protocol_schema_sha256']='f'*64
    body['metadata_revision']=canonical_hash(body['metadata'])
    with pytest.raises(ValueError,match='protocol schema incompatible'):NativeSymbolCatalog.from_body(body)


@pytest.mark.parametrize('field,value',[('provider_qualified',True),('qualified_for_research',True),('authority_effect','ORDER')])
def test_catalog_cannot_self_grant_use_or_execution(field,value):
    body=captured().body();body[field]=value
    with pytest.raises(ValueError,match='authority'):NativeSymbolCatalog.from_body(body)


def test_same_native_id_or_display_label_does_not_collapse_other_scopes():
    one=captured();two=captured(scope=SCOPE|{'native_account_id':999},response=response()|{'ctidTraderAccountId':999})
    assert one.members()[0]['instrument_identity']!=two.members()[0]['instrument_identity']
    body=response();body['symbol'][1]['symbolName']=body['symbol'][0]['symbolName']
    value=captured(response=body)
    assert value.members()[0]['instrument_identity']!=value.members()[1]['instrument_identity']


class CatalogPeer(FakeCtrader):
    def handle(self,name,body,cid):
        if name=='ProtoOASymbolsListReq' and body.get('includeArchivedSymbols') is True:
            return self.send('ProtoOASymbolsListRes',response(),cid)
        return super().handle(name,body,cid)


def test_actual_independent_native_reader_requests_archived_rows_and_no_order_messages():
    peer=CatalogPeer();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader()
    try:
        value=reader.read_catalog(SCOPE)
        assert [r['native_symbol_id'] for r in value.members()]==[1,2,3,4]
        assert not parent.transport.connected and parent._authed is False
        assert [name for name,_ in peer.requests]==['ProtoOAApplicationAuthReq','ProtoOAAccountAuthReq','ProtoOASymbolsListReq']
        assert peer.requests[-1][1]['includeArchivedSymbols'] is True
    finally:reader.close();peer.close()


def test_wrong_catalog_scope_refuses_before_any_native_authentication():
    peer=CatalogPeer();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader()
    try:
        with pytest.raises(VenueUnavailable,match='account/environment'):reader.read_catalog(SCOPE|{'native_account_id':999})
        assert peer.requests==[]
    finally:reader.close();peer.close()


@pytest.mark.parametrize("payload",[True,"PROTO_OA_SYMBOL_BY_ID_RES",999999])
def test_catalog_payload_type_cannot_be_relabelled_from_another_native_response(payload):
    with pytest.raises(ValueError,match="payload type differs"):
        captured(response=response()|{"payloadType":payload})


def test_optional_native_label_and_multiline_description_are_retained_as_data_not_identity():
    body=response();body["symbol"][0]["symbolName"]="";body["symbol"][0]["description"]="first line\nsecond line"
    value=captured(response=body);row=value.members()[0]
    assert row["original"]["description"]=="first line\nsecond line"
    assert row["name_state"]=="UNAVAILABLE_NATIVE_NAME" and row["qualified_for_research"] is False


def test_actual_bad_native_catalog_response_is_typed_unavailable_and_not_published():
    class WrongAccount(CatalogPeer):
        def handle(self,name,body,cid):
            if name=='ProtoOASymbolsListReq':return self.send('ProtoOASymbolsListRes',response()|{'ctidTraderAccountId':999},cid)
            return super().handle(name,body,cid)
    peer=WrongAccount();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader()
    try:
        with pytest.raises(VenueUnavailable,match='catalog response invalid'):reader.read_catalog(SCOPE)
        assert not parent.transport.connected
    finally:reader.close();peer.close()


def test_actual_native_catalog_parse_expiry_cannot_escape_shared_read_budget(monkeypatch):
    from vati.execution.ctrader import CtraderReadTransport,CtraderError
    clock={'value':0.0};initialize=CtraderReadTransport.__init__;capture=NativeSymbolCatalog.capture.__func__
    def init(self,*args,**kwargs):return initialize(self,*args,**(kwargs|{'monotonic':lambda:clock['value']}))
    def expire(cls,**kwargs):
        value=capture(cls,**kwargs);clock['value']=31.0;return value
    monkeypatch.setattr(CtraderReadTransport,'__init__',init)
    monkeypatch.setattr(NativeSymbolCatalog,'capture',classmethod(expire))
    peer=CatalogPeer();parent=make_adapter(peer);parent.clock=lambda:NOW;reader=parent.market_reader(collection_timeout_s=30)
    try:
        with pytest.raises(CtraderError,match='budget|deadline'):reader.read_catalog(SCOPE)
        assert len(peer.requests)==3 and not parent.transport.connected
    finally:reader.close();peer.close()
