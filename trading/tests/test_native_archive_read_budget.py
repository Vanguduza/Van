"""Bounded source verification before historical captures reach a request path."""
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from test_native_depth_archive import sample
from test_native_market_archive import contract
from vati.market_data import native_archive
from vati.market_data.native_archive import NativeMarketArchive,NativeArchiveError
from vati.market_data.native_depth import NativeDepthArchive,NativeDepthCollector


def test_growing_native_record_is_read_with_a_real_bound_even_after_a_small_stat(tmp_path,monkeypatch):
    target=tmp_path/'growing.json';target.write_bytes(b'x'*5000)
    stat=Path.stat;opened=Path.open;requests=[]
    class Tracked:
        def __init__(self,raw):self.raw=raw
        def __enter__(self):return self
        def __exit__(self,*exc):self.raw.close()
        def read(self,size=-1):requests.append(size);return self.raw.read(size)
    def small(path,*args,**kwargs):
        value=stat(path,*args,**kwargs)
        return SimpleNamespace(st_size=1) if path==target and kwargs.get('follow_symlinks',True) else value
    def track(path,*args,**kwargs):
        value=opened(path,*args,**kwargs)
        return Tracked(value) if path==target else value
    monkeypatch.setattr(native_archive,'MAX_RECORD_BYTES',64)
    monkeypatch.setattr(Path,'stat',small);monkeypatch.setattr(Path,'open',track)
    with pytest.raises(ValueError,match='resource bound'):NativeMarketArchive._read(target)
    assert requests==[65],'native source consumed an unbounded record after its pre-read stat'


def test_request_budget_refuses_valid_history_without_modifying_or_recapturing_it(tmp_path):
    c=contract();root=tmp_path/'depth';writer=NativeDepthArchive(root,clock=lambda:250000)
    first=writer.record('original',c,sample(c));part=writer._partition(c.native_scope,'DEPTH')
    files={p.name:p.read_bytes() for p in part.glob('*.json')};size=sum(map(len,files.values()))
    bounded=NativeDepthArchive(root,clock=lambda:500000,max_history_bytes=size-1)
    def never():raise AssertionError('read-budget refusal performed a replacement native read')
    with pytest.raises(NativeArchiveError,match='capacity|resource bound'):
        NativeDepthCollector(bounded,never).collect('original',c)
    assert {p.name:p.read_bytes() for p in part.glob('*.json')}==files
    assert NativeDepthArchive(root,clock=lambda:500000).lookup(c.native_scope,'DEPTH','original')==first


def test_exact_record_and_index_byte_budget_admits_the_original_snapshot(tmp_path):
    c=contract();root=tmp_path/'depth';writer=NativeDepthArchive(root,clock=lambda:250000)
    first=writer.record('original',c,sample(c));part=writer._partition(c.native_scope,'DEPTH')
    size=sum(p.stat().st_size for p in part.glob('*.json'))
    bounded=NativeDepthArchive(root,clock=lambda:500000,max_history_bytes=size)
    assert bounded.snapshot(c.native_scope,'DEPTH')['receipt']==first


def test_configured_publication_capacity_refuses_before_a_new_record_commits(tmp_path):
    c=contract();root=tmp_path/'depth';writer=NativeDepthArchive(root,clock=lambda:250000)
    writer.record('original',c,sample(c));part=writer._partition(c.native_scope,'DEPTH')
    files={p.name:p.read_bytes() for p in part.glob('*.json')};size=sum(map(len,files.values()))
    bounded=NativeDepthArchive(root,clock=lambda:400000,max_history_bytes=size)
    with pytest.raises(NativeArchiveError,match='capacity'):bounded.record('second',c,sample(c,now=300000))
    assert {p.name:p.read_bytes() for p in part.glob('*.json')}==files
    assert writer.snapshot(c.native_scope,'DEPTH')['receipt']['revision']==1


@pytest.mark.parametrize('bad',[True,0,-1,1.0,256*1024**2+1])
def test_native_history_budget_is_a_bounded_integer_or_explicit_legacy_mode(tmp_path,bad):
    with pytest.raises(ValueError):NativeDepthArchive(tmp_path/'depth',max_history_bytes=bad)


def test_cumulative_budget_cannot_be_reset_for_each_individually_small_record(tmp_path):
    c=contract();root=tmp_path/'depth';writer=NativeDepthArchive(root,clock=lambda:400000)
    writer.record('first',c,sample(c));writer.record('second',c,sample(c,now=300000))
    part=writer._partition(c.native_scope,'DEPTH');sizes=[p.stat().st_size for p in part.glob('*.json')]
    budget=max(sizes)+1;assert all(size<budget for size in sizes) and sum(sizes)>budget
    with pytest.raises(NativeArchiveError):NativeDepthArchive(root,max_history_bytes=budget).snapshot(c.native_scope,'DEPTH')
    assert writer.snapshot(c.native_scope,'DEPTH')['receipt']['revision']==2


def test_index_recovery_cannot_grow_its_head_past_the_original_budget(tmp_path):
    c=contract();root=tmp_path/'depth';writer=NativeDepthArchive(root,clock=lambda:400000)
    for n in range(9):writer.record('request-'+str(n),c,sample(c))
    part=writer._partition(c.native_scope,'DEPTH');old_head=(part/'head.json').read_bytes()
    tenth=writer.record('request-9',c,sample(c));new_head=(part/'head.json').read_bytes()
    assert len(new_head)==len(old_head)+1  # The original owner advances revision9 ->10.
    (part/'head.json').write_bytes(old_head)
    budget=sum(p.stat().st_size for p in part.glob('*.json'))
    bounded=NativeDepthArchive(root,max_history_bytes=budget)
    def never():raise AssertionError('index capacity refusal recaptured original depth')
    with pytest.raises(NativeArchiveError):NativeDepthCollector(bounded,never).collect('request-9',c)
    assert (part/'head.json').read_bytes()==old_head
    recovered=NativeDepthCollector(NativeDepthArchive(root,max_history_bytes=budget+1),never).collect('request-9',c)
    assert recovered['record_ref']==tenth['record_ref'] and recovered['index_state']=='CONSISTENT'
