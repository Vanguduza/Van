"""Independent measurement fixtures and strict refusal cases; no native-feed qualification."""
from decimal import Decimal
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from van_gateway.storage.db import Store
from van_gateway.trading.monitor_models import (AlertView, EvaluationStatus, IndicatorCondition,
    WatchlistState, AlertState, ScreenRequest)
from van_gateway.trading.monitor_source import MarketSnapshot, MonitorBar, NewsObservation
from van_gateway.trading.monitor_service import MarketMonitorService, digest
from van_gateway.trading.monitor_calculations import measurement
from test_market_monitor_persistence import Source, instrument, alert


def snapshot(closes=(9,), end_ms=960000, **changes):
    count = len(closes)
    bars = [dict(start_ms=end_ms-(count-n)*60000, end_ms=end_ms-(count-1-n)*60000,
                 open=str(c), high=str(Decimal(str(c))+1), low=str(Decimal(str(c))-1),
                 close=str(c), volume='1') for n, c in enumerate(closes)]
    return MarketSnapshot.model_validate(dict(instrument=instrument(), timeframe='M1',
        qualification='NATIVE_IDENTITY_BOUND', source_id='fixture-only-not-live',
        source_revision='feed-one', available_at_ms=end_ms+100, bars=bars) | changes)


def view(state=None, previous=None, **changes):
    state = state or alert(condition={'kind': 'PRICE', 'comparator': 'CROSS_ABOVE', 'threshold': '10'})
    return AlertView(object_id='fixture-alert', revision=1, state=state, state_sha256=digest(state.model_dump()),
                     lifecycle='ACTIVE', arm_generation=1, armed_at_ms=800000, updated_at_ms=800000,
                     evaluation=previous, **changes)


def comparisons(tmp_path):
    return MarketMonitorService(Store(str(tmp_path/'not-opened.sqlite3')), Source(), clock=lambda: 1000000)


def test_first_sample_establishes_crossing_then_only_new_contiguous_sample_can_fire(tmp_path):
    s = comparisons(tmp_path)
    first, fire = s._technical(view(), snapshot((9,)), 1000000)
    assert first.state == 'BASELINE' and not fire
    second, fire = s._technical(view(previous=first), snapshot((11,), end_ms=1020000), 1040000)
    assert fire and second.state == 'TRIGGERED' and second.value == '11'
    repeated, fire = s._technical(view(previous=first), snapshot((9,)), 1000000)
    assert not fire and repeated.reason == 'OBSERVATION_ALREADY_EVALUATED'


@pytest.mark.parametrize('change,reason', [
    ({'instrument': instrument(venue='other-venue')}, 'SOURCE_SCOPE_MISMATCH'),
    ({'instrument': instrument(account_id='other-account')}, 'SOURCE_SCOPE_MISMATCH'),
    ({'instrument': instrument(contract_revision='new-contract')}, 'SOURCE_SCOPE_MISMATCH'),
    ({'available_at_ms': 1000001}, 'SOURCE_FROM_FUTURE'),
])
def test_full_scope_and_actual_availability_refusals(tmp_path, change, reason):
    s = comparisons(tmp_path)
    actual, fire = s._technical(view(), snapshot(**change), 1000000)
    assert not fire and actual.state == 'UNAVAILABLE' and actual.reason == reason


def test_stale_data_missing_binding_and_short_indicator_history_are_not_zeroes(tmp_path):
    s = comparisons(tmp_path)
    stale, fire = s._technical(view(), snapshot(), 1200000)
    assert not fire and stale.reason == 'SOURCE_STALE' and stale.value is None
    missing, fire = s._technical(view(), None, 1000000)
    assert not fire and missing.reason == 'NATIVE_INSTRUMENT_BINDING_UNAVAILABLE' and missing.value is None
    state = alert(condition={'kind': 'INDICATOR', 'indicator': {'kind': 'SMA', 'period': 20},
        'comparator': 'AT_OR_ABOVE', 'threshold': '0'})
    short, fire = s._technical(view(state), snapshot(), 1000000)
    assert not fire and short.reason == 'INDICATOR_HISTORY_UNAVAILABLE' and short.value is None


def test_correction_gap_source_revision_and_out_of_order_data_cannot_manufacture_crossing(tmp_path):
    s = comparisons(tmp_path)
    previous, _ = s._technical(view(), snapshot((9,)), 1000000)
    corrected, fire = s._technical(view(previous=previous), snapshot((11,)), 1000000)
    assert not fire and corrected.reason == 'CORRECTED_OBSERVATION_BASELINE'
    for data in [snapshot((11,), end_ms=1080000),
                 snapshot((11,), end_ms=1020000, source_revision='different-feed')]:
        actual, fire = s._technical(view(previous=previous), data, 1100000)
        assert not fire and actual.state == 'BASELINE'
    actual, fire = s._technical(view(previous=previous), snapshot((7,), end_ms=900000), 1000000)
    assert not fire and actual.sample_id == previous.sample_id and actual.value == '9'
    assert actual.reason == 'OUT_OF_ORDER_OBSERVATION'


@pytest.mark.parametrize('kind,component,spec,closes,expected', [
    ('SMA', 'VALUE', {'period': 3}, [1,2,3,4], '3'),
    ('EMA', 'VALUE', {'period': 3}, [1,2,3,4], '3'),
    ('RSI', 'VALUE', {'period': 2}, [1,2,3,4], '100'),
    ('ATR', 'VALUE', {'period': 2}, [1,2,3,4], '2'),
    ('MACD', 'MACD', {'fast': 2,'slow': 3,'signal': 2}, [1,2,3,4,5], '0.5'),
    ('MACD', 'SIGNAL', {'fast': 2,'slow': 3,'signal': 2}, [1,2,3,4,5], '0.5'),
    ('MACD', 'HISTOGRAM', {'fast': 2,'slow': 3,'signal': 2}, [1,2,3,4,5], '0'),
    ('BOLLINGER', 'UPPER', {'period': 3,'deviations': '2'}, [1,1,1], '1'),
    ('BOLLINGER', 'LOWER', {'period': 3,'deviations': '2'}, [1,1,1], '1'),
    ('VWAP', 'VALUE', {'anchor_ms': 780000}, [2,4,6], '4'),
])
def test_measurements_match_independent_hand_calculated_series(kind, component, spec, closes, expected):
    condition = IndicatorCondition.model_validate({'kind':'INDICATOR','indicator':{'kind':kind,**spec},
        'component':component,'comparator':'AT_OR_ABOVE','threshold':'0'})
    data = snapshot(closes)
    assert measurement(data, condition) == Decimal(expected)
    assert measurement(data, condition) == Decimal(expected)


def test_vwap_does_not_silently_move_an_uncaptured_or_partial_bar_anchor():
    for anchor in [0, 800000, 2000000]:
        condition = IndicatorCondition.model_validate({'kind':'INDICATOR',
            'indicator':{'kind':'VWAP','anchor_ms':anchor},
            'comparator':'AT_OR_ABOVE','threshold':'0'})
        assert measurement(snapshot([2,4,6]), condition) is None


def test_moving_pinned_trend_uses_price_minus_line_at_each_observation_time(tmp_path):
    s = comparisons(tmp_path)
    condition={'kind':'DRAWING','drawing':{'drawing_id':'owner-line','kind':'TREND',
        'anchors':[{'time_ms':960000,'price':'9'},{'time_ms':1020000,'price':'13'}]},
        'comparator':'CROSS_BELOW'}
    state=alert(condition=condition)
    previous, fire=s._technical(view(state), snapshot([12]), 1000000)
    assert not fire and previous.value=='3'
    current, fire=s._technical(view(state,previous), snapshot([12],end_ms=1020000),1040000)
    assert fire and current.value=='-1'


def news(**changes):
    return NewsObservation.model_validate(dict(sample_id='headline-id', source_id='fixture-primary',
        trust='T1_PRIMARY', title='Central bank announces gold export rules', excerpt='',
        published_ms=900000, available_at_ms=910000, symbols=['SAME']) | changes)


def test_literal_news_keyword_matching_preserves_trust_freshness_time_and_declared_relevance(tmp_path):
    s=comparisons(tmp_path)
    state=alert(condition={'kind':'NEWS','keywords':['GOLD EXPORT'],'match':'ALL','minimum_trust':'T1_PRIMARY'})
    current, fire=s._news(view(state),True,[news()],1000000)
    assert fire and current.sample_id=='headline-id' and current.source_id=='fixture-primary'
    for row in [news(trust='UNTRUSTED'),news(trust='T2_SECONDARY'),news(symbols=['OTHER']),
                news(published_ms=700000,available_at_ms=710000),news(available_at_ms=1000001)]:
        current, fire=s._news(view(state),True,[row],1000000)
        assert not fire and current.state=='NO_MATCH'
    missing, fire=s._news(view(state),False,[],1000000)
    assert not fire and missing.state=='UNAVAILABLE'


@pytest.mark.parametrize('data', [
    {'condition':{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':True}},
    {'condition':{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'NaN'}},
    {'condition':{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'1'},'instrument':None},
    {'condition':{'kind':'NEWS','keywords':[' ','gold']}},
    {'condition':{'kind':'NEWS','keywords':['Gold',' GOLD ']}},
    {'max_age_ms':True},
    {'condition':{'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'1','place_order':True}},
])
def test_invalid_or_authority_bearing_alerts_cannot_be_saved(data):
    with pytest.raises(ValidationError):
        alert(**data)


def test_duplicate_native_identity_is_refused_but_same_symbol_on_distinct_venues_is_preserved():
    with pytest.raises(ValidationError):
        WatchlistState.model_validate({'name':'duplicate','entries':[{'instrument':instrument()}]*2})
    state=WatchlistState.model_validate({'name':'distinct','entries':[
        {'instrument':instrument()},{'instrument':instrument(venue='other-venue')}]})
    assert len(state.entries)==2


def test_scan_has_closed_level_predicates_and_bounded_distinct_universe():
    with pytest.raises(ValidationError):
        ScreenRequest.model_validate({'instruments':[instrument()],'conditions':[
            {'kind':'PRICE','comparator':'CROSS_ABOVE','threshold':'1'}]})
    with pytest.raises(ValidationError):
        ScreenRequest.model_validate({'instruments':[instrument()]*65,'conditions':[
            {'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'1'}]})


def test_a_first_sample_already_above_the_line_is_not_an_observed_crossing(tmp_path):
    current, fire = comparisons(tmp_path)._technical(view(), snapshot([11]), 1000000)
    assert not fire and current.state == 'BASELINE'


def test_same_time_price_correction_cannot_become_a_new_level_trigger(tmp_path):
    s = comparisons(tmp_path)
    state = alert(condition={'kind':'PRICE','comparator':'AT_OR_ABOVE','threshold':'10'})
    previous, fire = s._technical(view(state), snapshot([9]), 1000000)
    assert not fire and previous.state == 'NO_MATCH'
    corrected, fire = s._technical(view(state, previous), snapshot([11]), 1000000)
    assert not fire and corrected.reason == 'CORRECTED_OBSERVATION_BASELINE'
