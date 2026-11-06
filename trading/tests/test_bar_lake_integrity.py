"""The research lake must consume exactly the bytes and identities it reports."""
from dataclasses import replace
from decimal import Decimal as D
import gzip
import json
from pathlib import Path

import pytest
from vati.market_data.bars import Bar
from vati.market_data.feeds.lake import BarLake


def bar(symbol='EURUSD',start=0,close='1.1'):
    return Bar(symbol,start,start+3600000,D('1.1'),D('1.3'),D('1.0'),D(close),D('10'),2,D('.01'))


def write(lake,bars=None,symbol='EURUSD'):
    return lake.write([bar()] if bars is None else bars,symbol=symbol,timeframe='H1',source='fixture:exact',provenance='SYNTHETIC')


def test_symbol_cannot_create_files_outside_the_lake(tmp_path):
    lake=BarLake(tmp_path/'lake')
    try:write(lake,[bar('../escaped')],symbol='../escaped')
    except ValueError:pass
    assert not (tmp_path/'ESCAPED').exists(),'symbol escaped the lake root'


def test_wrong_instrument_cannot_be_labelled_as_requested_symbol(tmp_path):
    lake=BarLake(tmp_path/'lake')
    with pytest.raises(ValueError):write(lake,[bar('GBPUSD')])
    assert lake.read('EURUSD','H1')[0]==[]


def test_conflicting_same_time_observations_are_not_silently_deduplicated(tmp_path):
    lake=BarLake(tmp_path/'lake')
    with pytest.raises(ValueError):write(lake,[bar(close='1.1'),bar(close='1.2')])
    assert lake.read('EURUSD','H1')[0]==[]


@pytest.mark.parametrize('change',[{'bars':999},{'symbol':'GBPUSD'},{'timeframe':'M1'},{'end_ms':7200000}])
def test_manifest_claims_must_match_the_hashed_slice(tmp_path,change):
    lake=BarLake(tmp_path/'lake');write(lake)
    path=tmp_path/'lake/EURUSD/H1/manifest.json';manifest=json.loads(path.read_text())
    manifest['slices'][0].update(change);path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):lake.read('EURUSD','H1')


@pytest.mark.parametrize('value',[D('NaN'),D('Infinity')])
def test_nonfinite_market_prices_never_enter_a_research_slice(tmp_path,value):
    lake=BarLake(tmp_path/'lake')
    with pytest.raises(ValueError):write(lake,[replace(bar(),close=value)])


def test_manifest_cannot_reference_a_slice_outside_its_partition(tmp_path):
    lake=BarLake(tmp_path/'lake');s=write(lake)
    directory=tmp_path/'lake/EURUSD/H1';outside=tmp_path/'outside.csv.gz'
    outside.write_bytes((directory/s.path).read_bytes())
    path=directory/'manifest.json';manifest=json.loads(path.read_text());manifest['slices'][0]['path']=str(outside)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):lake.read('EURUSD','H1')


def test_hash_verification_and_csv_parse_use_the_same_snapshot(tmp_path,monkeypatch):
    lake=BarLake(tmp_path/'lake');s=write(lake);path=tmp_path/'lake/EURUSD/H1'/s.path
    original_read=Path.read_bytes;reads=0
    def read_and_replace(self):
        nonlocal reads
        blob=original_read(self)
        if self==path:
            reads+=1
            replacement=gzip.decompress(blob).replace(b',1.1,10,',b',1.2,10,')
            self.write_bytes(gzip.compress(replacement,mtime=0))
        return blob
    monkeypatch.setattr(Path,'read_bytes',read_and_replace)
    rows,used=lake.read('EURUSD','H1')
    assert reads==1 and rows[0].close==D('1.1') and used==[s.sha256]


def test_failed_manifest_replace_keeps_original_snapshot_readable_and_retryable(tmp_path,monkeypatch):
    import os
    lake=BarLake(tmp_path/'lake');first=write(lake);replace_file=os.replace
    def unavailable(src,dst):
        if Path(dst).name=='manifest.json':raise OSError('manifest replacement unavailable')
        return replace_file(src,dst)
    monkeypatch.setattr(os,'replace',unavailable)
    with pytest.raises(OSError,match='manifest replacement unavailable'):
        write(lake,[bar(start=3600000)])
    rows,hashes=lake.read('EURUSD','H1')
    assert rows==[bar()] and hashes==[first.sha256]
    assert not list((tmp_path/'lake').rglob('.lake-*'))
    monkeypatch.setattr(os,'replace',replace_file)
    write(lake,[bar(start=3600000)])
    assert [row.start_ms for row in lake.read('EURUSD','H1')[0]]==[0,3600000]


def test_concurrent_appenders_do_not_overwrite_an_unseen_manifest(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    lake=BarLake(tmp_path/'lake');write(lake)
    manifest=BarLake.manifest;gate=threading.Barrier(2)
    def interleave(self,*args):
        snapshot=manifest(self,*args)
        if threading.current_thread() is not threading.main_thread():
            try:gate.wait(timeout=.5)
            except threading.BrokenBarrierError:pass
        return snapshot
    monkeypatch.setattr(BarLake,'manifest',interleave)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda start:write(BarLake(lake.root),[bar(start=start)]),[3600000,7200000]))
    assert len(results)==2
    assert [row.start_ms for row in lake.read('EURUSD','H1')[0]]==[0,3600000,7200000]


def _process_append(root,start):
    write(BarLake(root),[bar(start=start)])


def test_separate_writer_processes_preserve_all_committed_slices(tmp_path):
    import multiprocessing
    lake=BarLake(tmp_path/'lake');write(lake)
    # This host-level filesystem check is separate from any cloud/provider claim.
    ctx=multiprocessing.get_context('spawn')
    processes=[ctx.Process(target=_process_append,args=(str(lake.root),i*3600000)) for i in range(1,5)]
    for process in processes:process.start()
    for process in processes:
        process.join(15);assert process.exitcode==0
    assert [row.start_ms for row in lake.read('EURUSD','H1')[0]]==[i*3600000 for i in range(5)]


def test_overlapping_slices_with_conflicting_market_facts_require_reconciliation(tmp_path):
    lake=BarLake(tmp_path/'lake');write(lake,[bar(),bar(start=3600000)])
    write(lake,[bar(start=3600000,close='1.2'),bar(start=7200000)])
    with pytest.raises(ValueError,match='conflicting overlapping'):
        lake.read('EURUSD','H1')


def test_new_symbol_paths_are_injective_and_roundtrip_without_directory_escape(tmp_path):
    lake=BarLake(tmp_path/'lake')
    for symbol in ['BTC/USD','BTC%2FUSD','../ESCAPED','/ABSOLUTE']:
        write(lake,[bar(symbol)],symbol=symbol)
        assert lake.read(symbol,'H1')[0][0].symbol==symbol
    assert set(lake.symbols())=={'BTC/USD','BTC%2FUSD','../ESCAPED','/ABSOLUTE'}
    assert len(list(lake.root.glob('*/H1/manifest.json')))==4


def test_symlinked_partition_is_refused_without_writing_outside_root(tmp_path):
    lake=BarLake(tmp_path/'lake');outside=tmp_path/'outside';outside.mkdir()
    (lake.root/'EURUSD').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='escapes root'):write(lake)
    assert list(outside.iterdir())==[]


def test_symlinked_manifest_is_refused_before_creating_an_external_lock(tmp_path):
    lake=BarLake(tmp_path/'lake');directory=lake._dir('EURUSD','H1')
    outside=tmp_path/'outside.json';outside.write_text('{}')
    (directory/'manifest.json').symlink_to(outside)
    with pytest.raises(ValueError,match='symlink'):write(lake)
    assert not outside.with_suffix('.json.lock').exists()
    assert outside.read_text()=='{}'


def test_nonfinite_volume_is_not_a_valid_research_observation(tmp_path):
    lake=BarLake(tmp_path/'lake')
    with pytest.raises(ValueError):write(lake,[replace(bar(),volume=D('Infinity'))])


def test_valid_csv_tampering_is_rejected_even_when_gzip_and_shape_are_valid(tmp_path):
    lake=BarLake(tmp_path/'lake');item=write(lake)
    path=tmp_path/'lake/EURUSD/H1'/item.path
    path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes()).replace(b',1.1,10,',b',1.2,10,'),mtime=0))
    with pytest.raises(ValueError,match='manifest hash'):lake.read('EURUSD','H1')


def test_existing_twelve_character_slice_names_remain_readable(tmp_path):
    lake=BarLake(tmp_path/'lake');item=write(lake);directory=tmp_path/'lake/EURUSD/H1'
    legacy=f'{item.start_ms}-{item.end_ms}-{item.sha256[:12]}.csv.gz'
    (directory/item.path).rename(directory/legacy)
    path=directory/'manifest.json';manifest=json.loads(path.read_text());manifest['slices'][0]['path']=legacy;path.write_text(json.dumps(manifest))
    assert lake.read('EURUSD','H1')==([bar()],[item.sha256])


def test_lost_manifest_commit_ack_retries_without_duplicate_history(tmp_path,monkeypatch):
    lake=BarLake(tmp_path/'lake');write(lake);atomic=lake._atomic_write
    def lost(path,payload):
        atomic(path,payload)
        if path.name=='manifest.json':raise OSError('lost manifest commit acknowledgement')
    monkeypatch.setattr(lake,'_atomic_write',lost)
    with pytest.raises(OSError,match='lost manifest commit acknowledgement'):
        write(lake,[bar(start=3600000)])
    assert [row.start_ms for row in lake.read('EURUSD','H1')[0]]==[0,3600000]
    monkeypatch.setattr(lake,'_atomic_write',atomic)
    write(lake,[bar(start=3600000)])
    assert len(lake.manifest('EURUSD','H1'))==2
    assert [row.start_ms for row in lake.read('EURUSD','H1')[0]]==[0,3600000]
