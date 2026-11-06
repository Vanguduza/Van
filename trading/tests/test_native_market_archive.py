"""Durable raw native source revisions; no live-provider acceptance fixture."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from test_ctrader_feed_contract import fixture as bar_fixture, response
from vati.core.canonical import canonical_hash, canonical_json
from vati.execution.ctrader.contracts import NativeSymbolContract
from vati.execution.ctrader.feed import read_trendbars
from vati.market_data.feeds.lake import BarLake
from vati.market_data.native_archive import NativeMarketArchive, NativeArchiveError


def contract(**changes):
    fields = dict(account_id=123, transport_host='demo.ctraderapi.com',
        light={'symbolId':12,'symbolName':'EUR/USD','enabled':True,'description':'original native label'},
        detail={'symbolId':12,'digits':5,'pipPosition':4,'lotSize':10000000,'minVolume':1000,'stepVolume':1000,
                'maxVolume':1000000000,'swapLong':-2.25,'schedule':[{'startSecond':10,'endSecond':20}]},
        received_at_ms=100000)
    fields.update(changes)
    return NativeSymbolContract.capture(**fields)


def observation(c=None):
    c = c or contract()
    adapter, _ = bar_fixture(response())
    result = read_trendbars(adapter,'EURUSD','M1',from_ms=120000,to_ms=300000)
    scope = c.native_scope
    return replace(result, native_account_id=scope['native_account_id'],
        native_symbol_id=scope['native_symbol_id'], transport_host=scope['transport_host'],
        contract_revision=c.revision)


def archive(tmp_path, now=400000):
    return NativeMarketArchive(tmp_path/'native',clock=lambda:now)


def test_full_original_contract_is_immutable_and_roundtrips_without_changing_revision():
    c = contract(); body = c.body()
    expected = canonical_hash({'schema':'vati.ctrader-symbol/1','native_account_id':123,
        'transport_host':'demo.ctraderapi.com','light':body['metadata']['light'],'detail':body['metadata']['detail']})
    assert c.revision == expected and NativeSymbolContract.from_body(body) == c
    body['metadata']['detail']['schedule'][0]['startSecond'] = 999
    assert c.metadata['detail']['schedule'][0]['startSecond'] == 10
    assert c.body()['provider_qualified'] is False and c.body()['authority_effect'] == 'NONE'


@pytest.mark.parametrize('change',['wrong_revision','other_product','bool_product','missing_lot','nan','authority'])
def test_invalid_contract_capture_refuses_without_fabricating_native_fields(change):
    body = contract().body()
    if change=='wrong_revision':body['metadata_revision']='0'*64
    elif change=='other_product':body['metadata']['detail']['symbolId']=13
    elif change=='bool_product':body['metadata']['light']['symbolId']=True
    elif change=='missing_lot':del body['metadata']['detail']['lotSize']
    elif change=='nan':body['metadata']['detail']['swapLong']=float('nan')
    else:body['provider_qualified']=True
    with pytest.raises(ValueError):NativeSymbolContract.from_body(body)


def test_metadata_is_captured_from_the_actual_protocol_registry_before_publishing():
    from test_ctrader import FakeCtrader, make_adapter
    native = FakeCtrader(); adapter = make_adapter(native)
    adapter._ensure_auth()
    symbol = adapter.symbol('EURUSD'); original = symbol.native_contract
    assert original.revision == symbol.contract_revision
    assert original.native_scope['native_account_id'] == 12345
    assert original.metadata['detail']['lotSize'] == 10000000
    assert original.received_at_ms == adapter.clock()
    adapter.transport.close()


def test_durable_readback_cold_replay_and_as_of_revisions_keep_original_bytes(tmp_path):
    book = archive(tmp_path); c = contract(); sample = observation(c)
    first = book.record('original-request',c,sample)
    assert first['revision']==1 and first['state']=='OBSERVED_UNQUALIFIED'
    cold = archive(tmp_path,now=500000)
    assert cold.record('original-request',c,sample)==first
    second = cold.record('new-observation',c,replace(sample,received_at_ms=450000))
    assert second['revision']==2 and second['record_ref']!=first['record_ref']
    assert cold.snapshot(c.native_scope,'M1',revision=1)['receipt']['record_ref']==first['record_ref']
    assert cold.snapshot(c.native_scope,'M1',as_of_ms=400000)['receipt']['record_ref']==first['record_ref']
    assert cold.snapshot(c.native_scope,'M1',as_of_ms=399999) is None
    assert cold.lookup(c.native_scope,'M1','original-request')==first
    assert cold.snapshot(c.native_scope,'M1')['observation']['spread'] is None


@pytest.mark.parametrize('field,value',[('account_id',999),('transport_host','live.ctraderapi.com'),
    ('light',{'symbolId':13,'symbolName':'EUR/USD','enabled':True})])
def test_identical_ticker_cannot_collide_across_native_accounts_environments_or_products(tmp_path,field,value):
    book=archive(tmp_path);a=contract();changes={field:value}
    if field=='light':changes['detail']=dict(a.metadata['detail'],symbolId=13)
    b=contract(**changes)
    one=book.record('same-request',a,observation(a));two=book.record('same-request',b,observation(b))
    assert one['revision']==two['revision']==1 and one['record_ref']!=two['record_ref']
    assert book.snapshot(a.native_scope,'M1')['contract']['metadata_revision']==a.revision
    assert book.snapshot(b.native_scope,'M1')['contract']['metadata_revision']==b.revision


def test_contract_revision_and_price_correction_append_without_erasing_original_snapshot(tmp_path):
    book=archive(tmp_path);a=contract();before=book.record('original',a,observation(a))
    b=contract(detail=dict(a.metadata['detail'],minVolume=2000),received_at_ms=200000)
    after=book.record('new-contract',b,observation(b))
    assert after['revision']==2 and before['contract_revision']!=after['contract_revision']
    assert book.snapshot(a.native_scope,'M1',revision=1)['contract']==a.body()
    assert book.snapshot(a.native_scope,'M1',revision=2)['contract']==b.body()


def test_conflicting_retry_does_not_overwrite_the_original_request(tmp_path):
    book=archive(tmp_path);c=contract();sample=observation(c);first=book.record('original',c,sample)
    with pytest.raises(NativeArchiveError,match='conflicts'):
        book.record('original',c,replace(sample,received_at_ms=350000))
    assert book.lookup(c.native_scope,'M1','original')==first


@pytest.mark.parametrize('bad',['wrong_contract','wrong_account','wrong_product','bad_volume','fractional_tick',
                              'open_bar','spread','authority','defaults','unknown_host'])
def test_malformed_or_unqualified_source_cannot_be_relabelled_into_a_durable_market_fact(tmp_path,bad):
    c=contract();sample=observation(c)
    if bad=='wrong_contract':sample=replace(sample,contract_revision='0'*64)
    elif bad=='wrong_account':sample=replace(sample,native_account_id=999)
    elif bad=='wrong_product':sample=replace(sample,native_symbol_id=999)
    elif bad=='bad_volume':sample=replace(sample,bars=(replace(sample.bars[0],ticks=99),))
    elif bad=='fractional_tick':sample=replace(sample,bars=(replace(sample.bars[0],open=sample.bars[0].open+__import__('decimal').Decimal('.000001')),))
    elif bad=='open_bar':sample=replace(sample,received_at_ms=sample.bars[-1].end_ms-1)
    elif bad=='defaults':sample=replace(sample,defaulted_delta_fields=((sample.bars[0].start_ms,('deltaOpen',)),))
    elif bad=='unknown_host':c=contract(transport_host='unqualified.example')
    else:
        original=sample.body
        object.__setattr__(sample,'body',lambda:original()|({'spread':'0'} if bad=='spread' else {'provider_qualified':True}))
    with pytest.raises(NativeArchiveError):archive(tmp_path).record('refused',c,sample)
    assert not list((tmp_path/'native').rglob('*.json'))


@pytest.mark.parametrize('phase',['record','head'])
def test_actual_lost_ack_recovers_the_original_record_and_repairs_only_the_index(tmp_path,monkeypatch,phase):
    c=contract();sample=observation(c);book=archive(tmp_path)
    original=BarLake._atomic_write
    def lost_ack(path,payload):
        original(path,payload)
        if (path.name=='head.json')==(phase=='head'):raise OSError('fixture lost durable acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(BarLake,'_atomic_write',lost_ack)
        with pytest.raises(NativeArchiveError,match='acknowledgement'):book.record('original',c,sample)
    cold=archive(tmp_path);found=cold.lookup(c.native_scope,'M1','original')
    assert found['revision']==1 and found['index_state']==('MISSING' if phase=='record' else 'CONSISTENT')
    replay=cold.record('original',c,sample)
    assert replay['record_ref']==found['record_ref'] and replay['index_state']=='CONSISTENT'
    assert len(list((tmp_path/'native').glob('*/*-*.json')))==1


@pytest.mark.parametrize('corruption',['bytes','deleted_tail','head_hash','sequence','symlink'])
def test_corrupt_or_missing_committed_history_is_unavailable_instead_of_empty_or_latest(tmp_path,corruption):
    c=contract();book=archive(tmp_path);book.record('first',c,observation(c));book.record('second',c,observation(c))
    part=next((tmp_path/'native').iterdir());records=sorted(part.glob('*-*.json'))
    if corruption=='bytes':records[0].write_bytes(records[0].read_bytes()+b' ')
    elif corruption=='deleted_tail':records[-1].unlink()
    elif corruption=='head_hash':
        head=json.loads((part/'head.json').read_bytes());head['record_hash']='0'*64
        (part/'head.json').write_text(canonical_json(head))
    elif corruption=='sequence':records[0].rename(records[0].with_name('00000000000000000003-'+records[0].name.split('-',1)[1]))
    else:
        outside=tmp_path/'outside.json';outside.write_bytes(records[0].read_bytes());records[0].unlink();records[0].symlink_to(outside)
    with pytest.raises(NativeArchiveError):archive(tmp_path).snapshot(c.native_scope,'M1')


def append_process(root,number):
    c=contract();NativeMarketArchive(root,clock=lambda:400000).record('process-'+str(number),c,observation(c))


def test_actual_concurrent_threads_and_processes_publish_one_contiguous_original_chain(tmp_path):
    c=contract();book=archive(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(lambda i:book.record('thread-'+str(i),c,observation(c)),range(4)))
    assert sorted(r['revision'] for r in receipts)==[1,2,3,4]
    context=multiprocessing.get_context('spawn');children=[context.Process(target=append_process,args=(str(tmp_path/'native'),i)) for i in range(3)]
    try:
        for child in children:child.start()
        for child in children:child.join(8);assert child.exitcode==0
    finally:
        for child in children:
            if child.pid is not None and child.is_alive():child.terminate();child.join(3)
    assert book.snapshot(c.native_scope,'M1')['receipt']['revision']==7


def test_absent_history_and_empty_native_observation_preserve_explicit_unknowns(tmp_path):
    c=contract();book=archive(tmp_path)
    assert book.snapshot(c.native_scope,'M1') is None and not (tmp_path/'native').exists()
    receipt=book.record('empty-native',c,replace(observation(c),bars=(),has_more=None))
    snapshot=book.snapshot(c.native_scope,'M1')
    assert receipt['state']=='EMPTY_UNQUALIFIED' and snapshot['observation']['has_more'] is None
    assert snapshot['observation']['bars']==[] and snapshot['observation']['provider_qualified'] is False


def test_relative_storage_and_backward_archive_availability_refuse_without_rewriting_history(tmp_path):
    with pytest.raises(NativeArchiveError):NativeMarketArchive('data/native')
    c=contract();book=archive(tmp_path);before=book.record('original',c,observation(c))
    with pytest.raises(NativeArchiveError,match='backwards'):
        archive(tmp_path,now=399999).record('late-request',c,observation(c))
    assert book.snapshot(c.native_scope,'M1')['receipt']==before


@pytest.mark.parametrize('corruption',['qualified','fractional_price','duplicate_bar','false_scope','default_price',
                                      'calendar','previous_hash','recorded_before_native','nonfinite'])
def test_semantic_corruption_with_recomputed_file_and_observation_hashes_is_still_refused(tmp_path,corruption):
    c=contract(account_id=1);book=archive(tmp_path);book.record('original',c,observation(c))
    part=next((tmp_path/'native').iterdir());path=next(part.glob('*-*.json'));body=json.loads(path.read_bytes())
    sample=body['observation']
    if corruption=='qualified':sample['provider_qualified']=True
    elif corruption=='fractional_price':sample['bars'][0]['open']='1.100051'
    elif corruption=='duplicate_bar':sample['bars'].append(deepcopy(sample['bars'][0]))
    elif corruption=='false_scope':body['scope']['native_account_id']=True
    elif corruption=='default_price':sample['defaulted_delta_fields']=[{'start_ms':120000,'fields':['deltaOpen']}]
    elif corruption=='calendar':sample['interval_basis']='QUALIFIED_NATIVE_CALENDAR'
    elif corruption=='previous_hash':body['previous_hash']='0'*64
    elif corruption=='recorded_before_native':body['recorded_at_ms']=sample['received_at_ms']-1
    else:sample['bars'][0]['open']='NaN'
    sample['observation_sha256']=canonical_hash({k:v for k,v in sample.items() if k!='observation_sha256'})
    blob=canonical_json(body).encode();digest=hashlib.sha256(blob).hexdigest()
    replacement=path.with_name('00000000000000000001-'+digest+'.json');path.unlink();replacement.write_bytes(blob)
    head=json.loads((part/'head.json').read_bytes());head['record_hash']=digest
    (part/'head.json').write_text(canonical_json(head))
    with pytest.raises(NativeArchiveError):book.snapshot(c.native_scope,'M1')


def crash_after_publication(root, phase):
    original=BarLake._atomic_write
    def die(path,payload):
        original(path,payload)
        if (path.name=='head.json')==(phase=='head'):os._exit(74)
    BarLake._atomic_write=die
    c=contract();NativeMarketArchive(root,clock=lambda:400000).record('original',c,observation(c))


@pytest.mark.parametrize('phase',['record','head'])
def test_actual_process_death_after_durable_publication_replays_original_without_another_revision(tmp_path,phase):
    context=multiprocessing.get_context('spawn')
    child=context.Process(target=crash_after_publication,args=(str(tmp_path/'native'),phase))
    try:
        child.start();child.join(8)
        assert child.exitcode==74
    finally:
        if child.pid is not None and child.is_alive():child.terminate();child.join(3)
    c=contract();book=archive(tmp_path);original=book.lookup(c.native_scope,'M1','original')
    assert original['revision']==1
    replay=book.record('original',c,observation(c))
    assert replay['record_ref']==original['record_ref'] and replay['revision']==1


def test_stale_derived_index_recovers_the_already_committed_second_record(tmp_path,monkeypatch):
    c=contract();book=archive(tmp_path);book.record('first',c,observation(c))
    original=BarLake._atomic_write
    def lose_index(path,payload):
        if path.name=='head.json':raise OSError('fixture index update unavailable')
        original(path,payload)
    with monkeypatch.context() as patch:
        patch.setattr(BarLake,'_atomic_write',lose_index)
        with pytest.raises(NativeArchiveError):book.record('second',c,observation(c))
    before=book.lookup(c.native_scope,'M1','second')
    assert before['revision']==2 and before['index_state']=='STALE'
    after=book.record('second',c,observation(c))
    assert after['record_ref']==before['record_ref'] and after['index_state']=='CONSISTENT'
