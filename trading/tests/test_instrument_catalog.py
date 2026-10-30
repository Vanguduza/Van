"""Original discovery, collision handling and causal pagination on SQL owners."""
import sqlite3
from pathlib import Path
import pytest

from test_native_catalog_store import source
from test_native_symbol_catalog import SCOPE,NOW,captured,response
from vati.core import Ledger,EventKind,make_event
from vati.core.ledger import LedgerError
from vati.market_data.catalog_store import NativeCatalogStore,CatalogArchiveError
from vati.market_data.instrument_catalog import discover_instruments,CatalogSelectionConflict


def test_discovery_preserves_every_original_member_and_omitted_name(source):
    ledger,store=source;receipt=store.record('original',captured());head=ledger.head()
    view=discover_instruments(store,SCOPE)
    assert [r['native_symbol_id'] for r in view['members']]==[1,2,3,4]
    assert [r['listing_state'] for r in view['members']]==['NATIVE_ENABLED_UNQUALIFIED','NATIVE_DISABLED_OR_OMITTED','NATIVE_DISABLED_OR_OMITTED','ARCHIVED']
    assert view['members'][2]['instrument_ref'] is None and view['members'][2]['original']=={'symbolId':3}
    assert view['members'][0]['instrument_ref']['contract_revision'] is None
    assert view['receipt']==receipt and view['total_matches']==4 and ledger.head()==head
    assert view['provider_qualified'] is view['execution_authority'] is False


def test_same_native_alias_never_selects_first_or_discards_archived_conflicts(source):
    _,store=source;rows=response();rows['symbol'][1]['symbolName']='EUR/USD';rows['archivedSymbol'][0]['name']='EUR/USD'
    store.record('collision',captured(response=rows))
    ambiguous=discover_instruments(store,SCOPE,alias='EUR/USD',limit=1)
    assert ambiguous['resolution_state']=='AMBIGUOUS_NATIVE_ALIAS' and ambiguous['total_matches']==3
    chosen=discover_instruments(store,SCOPE,alias='EUR/USD',native_symbol_id=2)
    assert chosen['resolution_state']=='RESOLVED_NATIVE_IDENTITY' and chosen['members'][0]['native_symbol_id']==2
    assert chosen['members'][0]['listing_state']=='NATIVE_DISABLED_OR_OMITTED'
    assert discover_instruments(store,SCOPE,alias='EUR/USD',native_symbol_id=3)['resolution_state']=='NOT_FOUND'
    assert discover_instruments(store,SCOPE,alias='EURUSD')['resolution_state']=='NOT_FOUND'


def test_same_ticker_different_accounts_and_realms_do_not_collide(source):
    _,store=source;store.record('one',captured())
    other=SCOPE|{'native_account_id':999};store.record('two',captured(scope=other,response=response()|{'ctidTraderAccountId':999}))
    live=SCOPE|{'environment':'LIVE','transport_host':'live.ctraderapi.com'};store.record('three',captured(scope=live))
    views=[discover_instruments(store,s,alias='EUR/USD') for s in [SCOPE,other,live]]
    assert len({v['members'][0]['instrument_identity'] for v in views})==3
    assert all(v['resolution_state']=='RESOLVED_NATIVE_IDENTITY' for v in views)


def test_pagination_pins_original_revision_and_selector_and_never_renews_availability(source):
    _,store=source;receipt=store.record('one',captured());first=discover_instruments(store,SCOPE,limit=2)
    store.record('two',captured());head=store.ledger.head()
    with pytest.raises(CatalogSelectionConflict):discover_instruments(store,SCOPE,after=first['next_cursor'])
    second=discover_instruments(store,SCOPE,revision=1,record_ref=receipt['record_ref'],after=first['next_cursor'],limit=2)
    assert [r['native_symbol_id'] for r in first['members']+second['members']]==[1,2,3,4]
    assert second['next_cursor'] is None and second['receipt']==receipt and store.ledger.head()==head
    with pytest.raises(CatalogSelectionConflict):discover_instruments(store,SCOPE,revision=1,alias='EUR/USD',after=first['next_cursor'])
    with pytest.raises(CatalogSelectionConflict):discover_instruments(store,SCOPE,revision=100,record_ref=receipt['record_ref'])


def test_delisting_and_rename_cannot_rewrite_historical_alias_or_preavailability_absence(source):
    _,store=source;store.record('before',captured());before=discover_instruments(store,SCOPE,alias='EUR/USD',as_of_ms=NOW+100)
    rows=response();rows['symbol']=rows['symbol'][1:];rows['archivedSymbol'].append({'symbolId':1,'name':'old EUR/USD','utcLastUpdateTimestamp':NOW-10000})
    store.clock=lambda:NOW+300;store.record('after',captured(response=rows,received_at_ms=NOW+200))
    assert discover_instruments(store,SCOPE,alias='EUR/USD',as_of_ms=NOW+100)==before
    assert discover_instruments(store,SCOPE,alias='EUR/USD')['resolution_state']=='NOT_FOUND'
    now=discover_instruments(store,SCOPE,native_symbol_id=1)
    assert now['members'][0]['listing_state']=='ARCHIVED' and now['members'][0]['lifecycle_effective_at_ms'] is None
    missing=discover_instruments(store,SCOPE,alias='EUR/USD',as_of_ms=NOW+99)
    assert missing['state']=='NO_CAPTURE' and missing['resolution_state']=='SOURCE_UNAVAILABLE'


def test_successfully_empty_catalog_is_distinct_from_missing_capture(source):
    _,store=source;assert discover_instruments(store,SCOPE)['state']=='NO_CAPTURE'
    store.record('empty',captured(response={'ctidTraderAccountId':12345}))
    view=discover_instruments(store,SCOPE,alias='missing')
    assert view['state']=='EMPTY_CATALOG' and view['resolution_state']=='NOT_FOUND' and view['members']==[]


def test_future_source_availability_cannot_enter_current_discovery(source):
    _,store=source;receipt=store.record('future',captured());store.clock=lambda:NOW+99
    assert discover_instruments(store,SCOPE)['state']=='NO_CAPTURE'
    assert discover_instruments(store,SCOPE,revision=1)['state']=='NO_CAPTURE'
    with pytest.raises(CatalogSelectionConflict):discover_instruments(store,SCOPE,record_ref=receipt['record_ref'])


def test_original_unrepresentable_name_is_retained_without_fabricating_frontend_identity(source):
    _,store=source;rows=response();rows['symbol'][0]['symbolName']='x'*300
    store.record('long',captured(response=rows));v=discover_instruments(store,SCOPE,native_symbol_id=1)
    assert v['members'][0]['native_name']=='x'*300 and v['members'][0]['instrument_ref'] is None
    assert v['members'][0]['frontend_reference_state']=='NATIVE_NAME_OUTSIDE_FRONTEND_CONTRACT'


def test_uncommitted_writer_and_mixed_financial_source_are_refused(source):
    ledger,store=source;store.record('one',captured())
    with ledger.atomic():
        with pytest.raises(LedgerError):discover_instruments(store,SCOPE)
    ledger.append(make_event(EventKind.SESSION,'fixture',{},event_time_ms=NOW,received_time_ms=NOW))
    with pytest.raises(CatalogArchiveError,match='dedicated'):discover_instruments(store,SCOPE)


def test_readonly_existing_sqlite_reopens_original_without_schema_migration_or_writes(tmp_path):
    path=tmp_path/'source # original.sqlite';ledger=Ledger(path);store=NativeCatalogStore(ledger,clock=lambda:NOW+100)
    receipt=store.record('original',captured());ledger.close();original=path.read_bytes()
    reader=Ledger.open_read_only(path)
    try:
        assert discover_instruments(NativeCatalogStore(reader,clock=lambda:NOW+100),SCOPE)['receipt']==receipt
        with pytest.raises(sqlite3.OperationalError):reader._conn.execute('DELETE FROM events')
        with pytest.raises(CatalogArchiveError):NativeCatalogStore(reader).record('new',captured())
    finally:reader.close()
    assert path.read_bytes()==original
    missing=tmp_path/'missing.sqlite'
    with pytest.raises(LedgerError):Ledger.open_read_only(missing)
    assert not missing.exists()
