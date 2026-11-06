"""Actual archive bytes and ordinal cutoffs; source fixtures are not licensed datasets."""
from copy import deepcopy
from dataclasses import replace

import pytest

from test_native_market_archive import archive,contract,observation
from vati.core.canonical import canonical_hash
from vati.market_data.native_archive import NativeArchiveError
from vati.market_data.native_windows import NativeBarWindowReader,WindowBudget


def original(tmp_path):
    book=archive(tmp_path);c=contract();sample=replace(observation(c),has_more=False)
    receipt=book.record('original',c,sample)
    return book,c,sample,receipt


def capture(book,c,receipt,**changes):
    options=dict(through_revision=receipt['revision'],boundary_ref=receipt['record_ref'],as_of_ms=400000,from_ms=120000,to_ms=300000)
    return NativeBarWindowReader(book).capture(c.native_scope,'M1',**(options|changes))


def test_window_pins_actual_bar_vintages_and_keeps_unavailable_native_fields(tmp_path):
    book,c,sample,receipt=original(tmp_path);value=capture(book,c,receipt)
    assert len(value['rows'])==3 and value['max_input_available_ms']==400000
    assert value['rows'][0]['bar']==sample.body()['bars'][0]
    assert value['rows'][0]['source_record_ref']==receipt['record_ref']
    assert value['source_records'][0]['spread'] is None
    assert value['coverage_state']=='UNQUALIFIED_SCHEDULE_COVERAGE'
    assert value['provider_qualified'] is value['qualified_for_research'] is False and value['authority_effect']=='NONE'
    body={k:v for k,v in value.items() if k!='window_sha256'};assert canonical_hash(body)==value['window_sha256']
    assert NativeBarWindowReader(book).verify(value,expected_scope=c.native_scope)==value


def test_same_millisecond_future_correction_cannot_change_pinned_original_window(tmp_path):
    book,c,sample,first=original(tmp_path);before=capture(book,c,first)
    changed=replace(sample,bars=(replace(sample.bars[0],close=sample.bars[0].low),))
    second=book.record('correction-at-same-clock',c,changed)
    assert second['available_at_ms']==first['available_at_ms']
    assert capture(book,c,first)==before
    current=capture(book,c,second)
    assert current['window_sha256']!=before['window_sha256']
    assert [r['source_revision'] for r in current['rows']]==[2,1,1]
    assert current['rows'][0]['bar']['close']==str(sample.bars[0].low)
    assert NativeBarWindowReader(book).verify(before,expected_scope=c.native_scope)==before


def test_late_capture_is_not_visible_before_its_local_availability(tmp_path):
    book,c,sample,first=original(tmp_path);book.clock=lambda:500000
    second=book.record('late',c,replace(sample,received_at_ms=450000))
    assert capture(book,c,first,as_of_ms=499999)['through_revision']==1
    with pytest.raises(NativeArchiveError,match='AFTER_CUTOFF'):capture(book,c,second,as_of_ms=499999)
    assert capture(book,c,second,as_of_ms=500000)['max_input_available_ms']==500000


@pytest.mark.parametrize('field,value',[('account_id',999),('transport_host','live.ctraderapi.com'),
    ('light',{'symbolId':13,'symbolName':'EUR/USD','enabled':True})])
def test_same_ticker_from_other_native_scope_cannot_supply_a_boundary(tmp_path,field,value):
    book,c,sample,first=original(tmp_path);change={field:value}
    if field=='light':change['detail']=dict(c.metadata['detail'],symbolId=13)
    other=contract(**change);second=book.record('other-native-scope',other,replace(observation(other),has_more=False))
    with pytest.raises(NativeArchiveError,match='BOUNDARY_CONFLICT'):
        capture(book,c,first,boundary_ref=second['record_ref'])
    value=capture(book,c,first)
    with pytest.raises(NativeArchiveError,match='SCOPE_CONFLICT'):
        NativeBarWindowReader(book).verify(value,expected_scope=other.native_scope)


def test_contract_metadata_revision_remains_exact_in_past_source_membership(tmp_path):
    book,c,sample,first=original(tmp_path);past=capture(book,c,first)
    revised=contract(detail=dict(c.metadata['detail'],minVolume=2000),received_at_ms=200000)
    second=book.record('metadata-vintage',revised,replace(observation(revised),has_more=False))
    current=capture(book,revised,second)
    assert current['source_records'][-1]['contract']['metadata']['detail']['minVolume']==2000
    assert capture(book,c,first)==past and past['source_records'][0]['contract']['metadata']['detail']['minVolume']==1000


@pytest.mark.parametrize('more,state',[(True,'INCOMPLETE_NATIVE_PAGE'),(None,'PAGINATION_UNAVAILABLE')])
def test_pagination_cannot_be_relabelled_complete_dataset_coverage(tmp_path,more,state):
    book=archive(tmp_path);c=contract();receipt=book.record('page',c,replace(observation(c),has_more=more))
    value=capture(book,c,receipt)
    assert value['coverage_state']==state and value['qualified_for_research'] is False


def test_query_boundary_keeps_only_whole_bars_and_declares_excluded_intervals(tmp_path):
    book,c,sample,first=original(tmp_path);value=capture(book,c,first,from_ms=150000,to_ms=270000)
    assert len(value['rows'])==1 and value['rows'][0]['bar']['start_ms']==180000
    assert value['excluded_boundary_intervals']==[{'start_ms':120000,'end_ms':180000},{'start_ms':240000,'end_ms':300000}]
    assert value['coverage_state']=='UNQUALIFIED_SCHEDULE_COVERAGE'


def test_empty_original_stays_in_lineage_without_invented_zero_bars(tmp_path):
    book=archive(tmp_path);c=contract();receipt=book.record('empty',c,replace(observation(c),bars=(),has_more=False))
    value=capture(book,c,receipt)
    assert value['rows']==[] and len(value['source_records'])==1
    assert value['source_records'][0]['receipt']['state']=='EMPTY_UNQUALIFIED'
    assert value['qualified_for_research'] is False


@pytest.mark.parametrize('budget',[WindowBudget(records=1),WindowBudget(source_bytes=1),WindowBudget(rows=1)])
def test_resource_limit_refuses_instead_of_truncating_source_membership(tmp_path,budget):
    book,c,sample,first=original(tmp_path);book.record('second',c,sample)
    reader=NativeBarWindowReader(book,budget=budget)
    with pytest.raises(NativeArchiveError,match='CAPACITY|BYTE_LIMIT|ROW_LIMIT'):
        reader.capture(c.native_scope,'M1',through_revision=first['revision'],boundary_ref=first['record_ref'],as_of_ms=400000,from_ms=120000,to_ms=300000)


@pytest.mark.parametrize('changes',[{'through_revision':True},{'through_revision':2},{'boundary_ref':'f'*64},
    {'as_of_ms':400001},{'from_ms':True},{'to_ms':120000}])
def test_unknown_revision_scope_clock_or_interval_never_becomes_empty_success(tmp_path,changes):
    book,c,sample,first=original(tmp_path)
    with pytest.raises(NativeArchiveError):capture(book,c,first,**changes)


def test_missing_derived_index_requires_original_reconciliation(tmp_path):
    book,c,sample,first=original(tmp_path);part=book._partition(c.native_scope,'M1');(part/'head.json').unlink()
    with pytest.raises(NativeArchiveError,match='INDEX_UNCONFIRMED'):capture(book,c,first)
    book.reconcile(c.native_scope,'M1','original')
    assert capture(book,c,first)['boundary_ref']==first['record_ref']


def test_corrupt_original_cannot_be_overridden_by_a_self_consistent_client_hash(tmp_path):
    book,c,sample,first=original(tmp_path);value=capture(book,c,first)
    altered=deepcopy(value);altered['rows'][0]['bar']['close']='999'
    altered['window_sha256']=canonical_hash({k:v for k,v in altered.items() if k!='window_sha256'})
    with pytest.raises(NativeArchiveError,match='ORIGINAL_READBACK_CONFLICT'):
        NativeBarWindowReader(book).verify(altered,expected_scope=c.native_scope)
    path=next(p for p in book._partition(c.native_scope,'M1').glob('*.json') if p.name!='head.json')
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(NativeArchiveError):NativeBarWindowReader(book).verify(value,expected_scope=c.native_scope)


@pytest.mark.parametrize('field,value',[('authority_effect','ORDER'),('provider_qualified',True),('qualified_for_research',True)])
def test_source_window_cannot_self_grant_research_or_execution(tmp_path,field,value):
    book,c,sample,first=original(tmp_path);window=capture(book,c,first);window[field]=value
    window['window_sha256']=canonical_hash({k:v for k,v in window.items() if k!='window_sha256'})
    with pytest.raises(NativeArchiveError,match='ORIGINAL_READBACK_CONFLICT'):
        NativeBarWindowReader(book).verify(window,expected_scope=c.native_scope)


def test_disabled_instrument_cannot_be_constructed_as_an_execution_contract():
    with pytest.raises(ValueError,match="product scope invalid"):
        contract(light=dict(contract().metadata["light"],enabled=False))
