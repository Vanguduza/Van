"""Exact read-only watchlist rows: independent expected values and failure states."""
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from van_gateway.trading.monitor_models import (WatchlistState, WatchlistView, WatchlistMarketRequest,
    ReplaceWatchlist)
from van_gateway.trading.monitor_service import MarketMonitorService, MonitorError, digest
from van_gateway.trading.watchlist_projection import project_watchlist
from test_market_monitor_measurements import snapshot
from test_market_monitor_persistence import instrument, service, create


def captured(entries=None, **preferences):
    state = WatchlistState.model_validate({'name':'Owner rows', 'entries':entries or [
        {'instrument':instrument(symbol='Zulu',product_id='z'),'favourite':False},
        {'instrument':instrument(symbol='Alpha',product_id='a'),'favourite':True},
        {'instrument':instrument(symbol='Beta',product_id='b'),'favourite':True}], **preferences})
    return WatchlistView(object_id='watch-one',revision=3,state=state,
        state_sha256=digest(state.model_dump()),updated_at_ms=900000)


class Source:
    def __init__(self, prices=None):
        self.prices = prices or {'z':[10,11], 'a':[10,9], 'b':[10,11]}
        self.calls = []

    def market(self, selected, timeframe):
        self.calls.append((selected.model_dump(),timeframe))
        closes = self.prices.get(selected.product_id)
        if closes is None:
            return None
        base = snapshot([1]*len(closes),instrument=selected.model_dump(),timeframe=timeframe)
        return base.model_copy(update={'bars':[
            bar.model_copy(update={'open':str(close),'high':str(close),'low':str(close),'close':str(close)})
            for bar,close in zip(base.bars,closes)]})


def project(view=None, body=None, source=None, clock=lambda:1000000):
    return project_watchlist(view or captured(),body or WatchlistMarketRequest(expected_revision=3),
        source=source or Source(),qualify=MarketMonitorService._qualified,clock=clock,digest=digest)


def test_exact_closed_price_previous_bar_change_and_provenance_are_not_live_quotes():
    view = captured()
    result = project(view)
    assert result.revision == 3 and result.state_sha256 == view.state_sha256
    row = result.rows[0]
    assert row.price == '11' and row.price_age_ms == 40000
    assert Decimal(row.change_pct) == Decimal('10') and row.reference_price == '10'
    assert row.change_basis == 'PREVIOUS_CONTIGUOUS_BAR' and row.change_interval_ms == 60000
    assert row.reference_time_ms == 900000 and row.event_time_ms == 960000
    assert row.available_at_ms == 960100 and row.source_revision == 'feed-one' and row.sample_id
    assert row.measurement_basis == 'CLOSED_BAR_CLOSE' and row.spread is None
    assert row.spread_state == 'NOT_REPORTED_IN_CLOSED_BAR_SOURCE' and result.authority_effect == 'NONE'


@pytest.mark.parametrize('sort,descending,expected',[
    ('MANUAL',False,['z','a','b']),('MANUAL',True,['b','a','z']),
    ('SYMBOL',False,['a','b','z']),('SYMBOL',True,['z','b','a']),
    ('PRICE',False,['a','z','b']),('PRICE',True,['z','b','a']),
    ('CHANGE_PCT',False,['a','z','b']),('CHANGE_PCT',True,['z','b','a']),
])
def test_saved_sort_direction_and_equal_value_owner_order(sort,descending,expected):
    result = project(captured(sort_by=sort,descending=descending))
    assert [row.instrument.product_id for row in result.rows] == expected
    assert result.sort_metric_state == 'AVAILABLE'


@pytest.mark.parametrize('descending',[False,True])
def test_missing_numeric_values_are_last_in_either_direction_and_never_fake_zero(descending):
    result = project(captured(sort_by='PRICE',descending=descending),source=Source({'z':[11],'b':[9]}))
    assert result.rows[-1].instrument.product_id == 'a'
    assert result.rows[-1].state == 'UNAVAILABLE' and result.rows[-1].price is None
    assert result.rows[-1].price_age_ms is None and result.rows[-1].change_pct is None
    assert result.sort_metric_state == 'PARTIAL'
    spread = project(captured(sort_by='SPREAD',descending=descending))
    assert [row.manual_index for row in spread.rows] == [0,1,2]
    assert spread.sort_metric_state == 'UNAVAILABLE' and all(row.spread is None for row in spread.rows)


def test_favourites_search_and_explicit_native_group_filters_apply_before_source_reads():
    entries = [
        {'instrument':instrument(symbol='Alpha',product_id='a',venue='v1'),'favourite':True},
        {'instrument':instrument(symbol='Alpha',product_id='b',venue='v2'),'favourite':True},
        {'instrument':instrument(symbol='Alpha',product_id='c',venue='v1'),'favourite':False},
    ]
    source = Source({'a':[11],'b':[10],'c':[9]})
    request = WatchlistMarketRequest(expected_revision=3,search=' ALP ',venue='v1',
        environment='DEMO',api_family='spot')
    result = project(captured(entries,favourites_only=True),request,source)
    assert result.selected_count == 3 and result.filtered_count == 1
    assert result.rows[0].instrument.product_id == 'a' and len(source.calls) == 1
    empty = project(captured(entries),WatchlistMarketRequest(expected_revision=3,environment='LIVE'),source)
    assert empty.rows == [] and empty.sort_metric_state == 'NOT_APPLICABLE'
    assert len(source.calls) == 1


def test_zero_reference_missing_history_and_tiny_changes_do_not_depend_on_ambient_precision():
    with localcontext() as context:
        context.prec = 3
        result = project(source=Source({'z':[0,11],'a':[9],'b':['1','1.00000000000000000001']}))
    assert result.rows[0].price == '11' and result.rows[0].change_pct is None
    assert result.rows[0].change_state == 'ZERO_REFERENCE' and result.rows[0].reference_price == '0'
    assert result.rows[1].change_state == 'HISTORY_UNAVAILABLE' and result.rows[1].reference_price is None
    assert Decimal(result.rows[2].change_pct) == Decimal('0.000000000000000001')


@pytest.mark.parametrize('change,reason',[
    ({'instrument':instrument(account_id='foreign')},'SOURCE_SCOPE_MISMATCH'),
    ({'instrument':instrument(contract_revision='foreign')},'SOURCE_SCOPE_MISMATCH'),
    ({'available_at_ms':1000001},'SOURCE_FROM_FUTURE'),
    ({'end_ms':600000},'SOURCE_STALE'),
])
def test_foreign_stale_and_future_snapshots_cannot_supply_row_values(change,reason):
    source = SimpleNamespace(market=lambda *args:snapshot([10,11],**change))
    view = captured([{'instrument':instrument()}])
    row = project(view,source=source).rows[0]
    assert row.state == 'UNAVAILABLE' and row.reason == reason
    assert row.price is None and row.change_pct is None and row.sample_id is None


def test_source_exception_is_an_unavailable_row_and_age_is_checked_after_source_returns():
    def broken(*args):
        raise OSError('private source internals')
    row = project(source=SimpleNamespace(market=broken)).rows[0]
    assert row.state == 'UNAVAILABLE' and row.reason == 'SOURCE_READ_FAILED'
    assert 'private' not in row.model_dump_json()
    values = iter([1200000,1200000,1200000,1200000])
    result = project(clock=lambda:next(values))
    assert all(row.reason == 'SOURCE_STALE' and row.price is None for row in result.rows)


def test_filter_contract_refuses_control_characters_unknown_fields_and_non_integer_revisions():
    for changes in [{'search':'a\nb'}, {'search':'a\x7fb'}, {'owner_id':'foreign'},
                    {'expected_revision':True},{'max_age_ms':0}]:
        with pytest.raises(ValidationError):
            WatchlistMarketRequest.model_validate({'expected_revision':3,**changes})


@pytest.mark.asyncio
async def test_real_store_checks_owner_and_revision_before_any_source_call_and_never_writes_effects(tmp_path):
    source = Source()
    s = await service(tmp_path,source=source)
    saved = await create(s,state=captured().state)
    with pytest.raises(MonitorError,match='MONITOR_REVISION_CONFLICT'):
        await s.watchlist_market('owner',saved.object_id,WatchlistMarketRequest(expected_revision=2))
    with pytest.raises(MonitorError,match='MONITOR_OBJECT_UNKNOWN'):
        await s.watchlist_market('foreign',saved.object_id,WatchlistMarketRequest(expected_revision=1))
    assert source.calls == []
    actual = await s.watchlist_market('owner',saved.object_id,WatchlistMarketRequest(expected_revision=1))
    assert len(actual.rows) == 3 and actual.revision == 1
    assert len(await s.store.fetchall('SELECT * FROM market_monitor_operations')) == 1
    for table in ['market_monitor_scan_budget','mission_activities','events']:
        assert not await s.store.fetchall('SELECT * FROM '+table)
    assert (await s.get('owner','WATCHLIST',saved.object_id)).state_sha256 == saved.state_sha256


@pytest.mark.asyncio
async def test_edit_during_real_store_read_keeps_captured_list_binding_and_clock_rollback_refuses(tmp_path):
    source = Source()
    s = await service(tmp_path,source=source)
    saved = await create(s,state=captured().state)
    original_get = s.get
    async def interleaved(*args):
        view = await original_get(*args)
        await s.write('owner','WATCHLIST','REPLACE',ReplaceWatchlist(request_id='edit',expected_revision=1,
            state=WatchlistState(name='Empty new revision',entries=[])),saved.object_id)
        return view
    s.get = interleaved
    result = await s.watchlist_market('owner',saved.object_id,WatchlistMarketRequest(expected_revision=1))
    assert result.revision == 1 and result.state_sha256 == saved.state_sha256 and len(result.rows) == 3
    s.get = original_get
    assert (await s.get('owner','WATCHLIST',saved.object_id)).revision == 2
    readings = iter([1000000,999999])
    s.clock = lambda:next(readings)
    with pytest.raises(MonitorError,match='MONITOR_CLOCK_ROLLBACK'):
        await s.watchlist_market('owner',saved.object_id,WatchlistMarketRequest(expected_revision=2))
