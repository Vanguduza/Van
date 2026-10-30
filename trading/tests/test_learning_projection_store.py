"""Real storage transactions for the applied revision/contribution/cursor snapshot."""
import json
from decimal import Decimal

import pytest

from vati.core import Ledger,EventKind,make_event
from vati.learning.projection_store import ProjectionStore,ProjectionConflict,ProjectionCorrupt


def source(ledger,name='one'):
    event=make_event(EventKind.SESSION,'native-test',{'name':name},event_time_ms=1,
        received_time_ms=1,correlation_id=name)
    ledger.append(event)
    return event


def snapshot(store,number=1):
    return store.envelope({'applied':['record-'+str(number)],'contributions':{'parent':str(number)},
        'aggregate':{'count':1,'net_r':str(number)}},cursor_seq=store.publication_rows(0)[-1][0],cursor_hash=store.ledger.head())


@pytest.mark.parametrize('stage',['after_history_before_cursor','after_cursor_before_commit'])
def test_fault_before_commit_retains_all_three_old_fields_and_history(tmp_path,stage):
    ledger=Ledger(tmp_path/'projection.sqlite')
    source(ledger)
    store=ProjectionStore(ledger,{'account':'one','environment':'DEMO'})
    first=snapshot(store);store.save(first,expected_hash=None)
    source(ledger,'two');second=snapshot(store,2)
    def fail(point):
        if point==stage:raise RuntimeError('induced crash')
    store.fault=fail
    with pytest.raises(RuntimeError,match='induced crash'):store.save(second,expected_hash=first['snapshot_hash'])
    store.fault=None
    assert store.load()==first
    assert store._read(f'SELECT COUNT(*) FROM {store.history}')[0][0]==1
    assert ledger.count()==2 and ledger.verify_chain()[0]


def test_lost_commit_reply_is_recovered_by_exact_idempotent_retry(tmp_path):
    ledger=Ledger(tmp_path/'projection.sqlite');source(ledger)
    store=ProjectionStore(ledger,{'account':'one'})
    current=snapshot(store)
    def fail(point):
        if point=='after_commit_before_reply':raise RuntimeError('reply lost')
    store.fault=fail
    with pytest.raises(RuntimeError,match='reply lost'):store.save(current,expected_hash=None)
    store.fault=None
    assert store.load()==current
    assert store.save(current,expected_hash=None)==current
    assert store._read(f'SELECT COUNT(*) FROM {store.history}')[0][0]==1


def test_compare_and_swap_prevents_a_stale_consumer_overwriting_a_new_cursor(tmp_path):
    ledger=Ledger(tmp_path/'projection.sqlite');source(ledger)
    store=ProjectionStore(ledger,{'account':'one'});first=snapshot(store)
    store.save(first,expected_hash=None);source(ledger,'two');new=snapshot(store,2)
    store.save(new,expected_hash=first['snapshot_hash'])
    with pytest.raises(ProjectionConflict):store.save(first,expected_hash=first['snapshot_hash'])
    with pytest.raises(ProjectionConflict):store.save(first,expected_hash=new['snapshot_hash'])
    assert store.load()==new


def test_scopes_and_cold_connections_cannot_read_each_others_checkpoints(tmp_path):
    path=tmp_path/'projection.sqlite';ledger=Ledger(path);source(ledger)
    one=ProjectionStore(ledger,{'account':'one','environment':'LIVE'})
    current=snapshot(one);one.save(current,expected_hash=None)
    for scope in [{'account':'other','environment':'LIVE'},{'account':'one','environment':'DEMO'}]:
        assert ProjectionStore(ledger,scope).load() is None
    cold=Ledger(path)
    assert ProjectionStore(cold,one.scope).load()==current
    assert ledger.verify_chain()[0] and ledger.count()==1


def test_a_missing_or_corrupt_checkpoint_never_looks_like_empty_fresh_history(tmp_path):
    ledger=Ledger(tmp_path/'projection.sqlite');source(ledger)
    store=ProjectionStore(ledger,{'account':'one'});current=snapshot(store);store.save(current,expected_hash=None)
    ledger._conn.execute(f'UPDATE {store.history} SET snapshot_json=?',('{"partial":true}',))
    with pytest.raises(ProjectionCorrupt):store.load()
    # A rebuild may publish the verified source-derived value, retaining the old row.
    store.save(current,expected_hash=current['snapshot_hash'],recovery_reason='verified source rebuild')
    assert store.load()==current
    assert store._read(f'SELECT COUNT(*) FROM {store.history}')[0][0]==2
    ledger._conn.execute(f'DELETE FROM {store.current}')
    with pytest.raises(ProjectionCorrupt):store.load()
    assert ledger.count()==1 and ledger.verify_chain()[0]


def test_cursor_must_belong_to_the_exact_native_journal_and_scope(tmp_path):
    ledger=Ledger(tmp_path/'projection.sqlite');source(ledger)
    store=ProjectionStore(ledger,{'account':'one'})
    bad=store.envelope({'applied':[],'contributions':{}},cursor_seq=1,cursor_hash='f'*64)
    with pytest.raises(ProjectionCorrupt):store.save(bad,expected_hash=None)
    other=ProjectionStore(ledger,{'account':'other'})
    with pytest.raises(ProjectionCorrupt):other.save(snapshot(store),expected_hash=None)
